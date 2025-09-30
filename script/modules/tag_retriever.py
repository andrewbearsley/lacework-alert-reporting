"""
Resource tag retrieval functionality for Lacework Alert Reporting.
"""
import time
from typing import Dict, List, Set
from datetime import datetime
from .cache_manager import CacheManager, extract_account_id_from_arn, extract_resource_types_from_arns, map_aws_service_to_lacework_types
from .lacework_client import LaceworkClientWrapper


class TagRetriever:
    """Handles retrieval of resource tags from Lacework API."""
    
    def __init__(self, client_wrapper: LaceworkClientWrapper, cache_manager: CacheManager):
        """Initialize tag retriever with client and cache manager."""
        self.client_wrapper = client_wrapper
        self.cache_manager = cache_manager
        
        # Define fallback tag strategies for resources without direct tags
        self.fallback_strategies = {
            'elbv2:loadbalancer': {
                'primary': 'ec2:security-group',
                'secondary': 'ec2:vpc',
                'description': 'ELB -> Security Group -> VPC'
            },
            'lambda:function': {
                'primary': 'ec2:security-group', 
                'secondary': 'ec2:vpc',
                'description': 'Lambda -> Security Group -> VPC'
            },
            'rds:db': {
                'primary': 'ec2:subnet',
                'secondary': 'ec2:vpc', 
                'description': 'RDS -> Subnet -> VPC'
            },
            'ec2:security-group': {
                'primary': 'ec2:vpc',
                'secondary': None,
                'description': 'Security Group -> VPC'
            }
        }
    
    def _get_related_resource_tags(self, arn: str, resource_type: str, resource_config: dict, account_id: str = None, start_date: str = None, end_date: str = None) -> str:
        """
        Get tags from related resources when the primary resource has no tags.
        
        Args:
            arn: Resource ARN
            resource_type: Lacework resource type
            resource_config: Resource configuration from Lacework
            
        Returns:
            Formatted tag string from related resource, or 'N/A' if none found
        """
        if resource_type not in self.fallback_strategies:
            return 'N/A'
        
        strategy = self.fallback_strategies[resource_type]
        
        if not account_id:
            account_id = extract_account_id_from_arn(arn)
            if not account_id:
                return 'N/A'
        
        # Try primary fallback strategy
        primary_type = strategy['primary']
        related_arn = self._extract_related_arn(arn, resource_type, resource_config, primary_type, account_id)
        
        if related_arn:
            related_tags = self._get_cached_resource_tags(related_arn, account_id, start_date, end_date)
            if related_tags and related_tags != 'N/A':
                return f"{related_tags} (from {primary_type})"
        
        # Try secondary fallback strategy (if it exists)
        secondary_type = strategy['secondary']
        if secondary_type:
            related_arn = self._extract_related_arn(arn, resource_type, resource_config, secondary_type, account_id)
            
            if related_arn:
                related_tags = self._get_cached_resource_tags(related_arn, account_id, start_date, end_date)
                if related_tags and related_tags != 'N/A':
                    return f"{related_tags} (from {secondary_type})"
        
        return 'N/A'
    
    def _extract_related_arn(self, arn: str, resource_type: str, resource_config: dict, related_type: str, account_id: str) -> str:
        """Extract ARN of related resource based on type."""
        if isinstance(resource_config, str):
            import json
            resource_config = json.loads(resource_config)
        
        if related_type == 'ec2:security-group':
            # For ELB and Lambda, get security group from resource config
            if resource_type == 'elbv2:loadbalancer':
                security_groups = resource_config.get('SecurityGroups', [])
                if security_groups:
                    return f"arn:aws:ec2:ap-southeast-2:{account_id}:security-group/{security_groups[0]}"
            elif resource_type == 'lambda:function':
                # Lambda security groups are in VpcConfig
                vpc_config = resource_config.get('VpcConfig', {})
                security_groups = vpc_config.get('SecurityGroupIds', [])
                if security_groups:
                    return f"arn:aws:ec2:ap-southeast-2:{account_id}:security-group/{security_groups[0]}"
        
        elif related_type == 'ec2:subnet':
            # For RDS, get subnet from resource config
            if resource_type == 'rds:db':
                subnet_group = resource_config.get('DBSubnetGroup', {})
                subnets = subnet_group.get('Subnets', [])
                if subnets:
                    subnet_id = subnets[0].get('SubnetIdentifier')
                    if subnet_id:
                        return f"arn:aws:ec2:ap-southeast-2:{account_id}:subnet/{subnet_id}"
        
        elif related_type == 'ec2:vpc':
            # Get VPC ID from resource config
            vpc_id = resource_config.get('VpcId')
            if vpc_id:
                return f"arn:aws:ec2:ap-southeast-2:{account_id}:vpc/{vpc_id}"
        
        return None
    
    def _get_cached_resource_tags(self, related_arn: str, account_id: str, start_date: str = None, end_date: str = None) -> str:
        """Get tags for a related resource from cache."""
        # Extract resource type from ARN to find the right cache file
        resource_type = self._get_resource_type_from_arn(related_arn)
        if not resource_type:
            return 'N/A'
        
        # Use the new cache naming scheme
        cache_file = self.cache_manager.get_resource_cache_file_path('account-tags', account_id, resource_type, start_date, end_date)
        
        if cache_file and cache_file.exists():
            cache_data = self.cache_manager.load_from_cache(cache_file)
            if cache_data and 'resource_tags' in cache_data:
                return cache_data['resource_tags'].get(related_arn, 'N/A')
        
        return 'N/A'
    
    def get_resource_tags_by_type(self, resource_arns: List[str], start_date: str = None, end_date: str = None) -> Dict[str, str]:
        """
        Retrieve tags for resources, optimized by resource type.
        
        Args:
            resource_arns: List of resource ARNs to get tags for
            
        Returns:
            Dictionary mapping ARNs to formatted tag strings
        """
        if not resource_arns:
            return {}
        
        print(f"=== OPTIMIZED TAG RETRIEVAL PERFORMANCE ANALYSIS ===")
        print(f"Total resources requested: {len(resource_arns)}")
        
        # Extract resource types
        resource_types = extract_resource_types_from_arns(resource_arns)
        
        # Always include fallback resource types for tag fallback strategies
        fallback_types = set()
        for strategy in self.fallback_strategies.values():
            if strategy['primary']:
                fallback_types.add(strategy['primary'])
            if strategy['secondary']:
                fallback_types.add(strategy['secondary'])
        
        resource_types.update(fallback_types)
        print(f"Resource types identified: {sorted(resource_types)}")
        
        # Check cache first
        start_time = time.time()
        tags_result = {}
        uncached_resources = []
        
        for arn in resource_arns:
            account_id = extract_account_id_from_arn(arn)
            if not account_id:
                tags_result[arn] = 'N/A'
                continue
            
            # Check cache for this specific resource type
            resource_type = self._get_resource_type_from_arn(arn)
            cache_file = self.cache_manager.get_resource_cache_file_path(
                'account-tags', account_id, resource_type, start_date, end_date
            )
            
            cached_data = self.cache_manager.load_from_cache(cache_file)
            if cached_data and arn in cached_data.get('resource_tags', {}):
                tags_result[arn] = cached_data['resource_tags'][arn]
                print(f"    Found {arn} in cache: {tags_result[arn]}")
                # If tags are N/A, mark for fallback strategy
                if tags_result[arn] == 'N/A':
                    print(f"    Marking {arn} for fallback strategy")
                    uncached_resources.append(arn)
            elif cached_data and 'all_resources' in cached_data:
                # Try to find the resource in all_resources by matching ARN to resource ID
                found_in_all_resources = False
                for resource_id, resource_info in cached_data['all_resources'].items():
                    # Check if this resource matches the ARN
                    if self._match_resource_to_arn(resource_id, [arn]):
                        tags_result[arn] = resource_info.get('formatted_tags', 'N/A')
                        found_in_all_resources = True
                        break
                
                if not found_in_all_resources:
                    # If not found in mixed cache, try individual resource type caches
                    arn_resource_type = self._get_resource_type_from_arn(arn)
                    if arn_resource_type:
                        individual_cache_file = self.cache_manager.get_resource_cache_file_path(
                            'account-tags', account_id, arn_resource_type, start_date, end_date
                        )
                        individual_cached_data = self.cache_manager.load_from_cache(individual_cache_file)
                        if individual_cached_data and arn in individual_cached_data.get('resource_tags', {}):
                            tags_result[arn] = individual_cached_data['resource_tags'][arn]
                            # If tags are N/A, mark for fallback strategy
                            if tags_result[arn] == 'N/A':
                                uncached_resources.append(arn)
                        elif individual_cached_data and 'all_resources' in individual_cached_data:
                            # Try to find in individual cache's all_resources
                            for resource_id, resource_info in individual_cached_data['all_resources'].items():
                                if self._match_resource_to_arn(resource_id, [arn]):
                                    tags_result[arn] = resource_info.get('formatted_tags', 'N/A')
                                    found_in_all_resources = True
                                    # If tags are N/A, mark for fallback strategy
                                    if tags_result[arn] == 'N/A':
                                        uncached_resources.append(arn)
                                    break
                        
                        if not found_in_all_resources:
                            uncached_resources.append(arn)
                    else:
                        uncached_resources.append(arn)
            else:
                # If not found in mixed cache, try individual resource type caches
                arn_resource_type = self._get_resource_type_from_arn(arn)
                if arn_resource_type:
                    # Use the new cache naming scheme
                    individual_cache_file = self.cache_manager.get_resource_cache_file_path(
                        'account-tags', account_id, arn_resource_type, start_date, end_date
                    )
                    individual_cached_data = self.cache_manager.load_from_cache(individual_cache_file)
                    if individual_cached_data and arn in individual_cached_data.get('resource_tags', {}):
                        tags_result[arn] = individual_cached_data['resource_tags'][arn]
                    elif individual_cached_data and 'all_resources' in individual_cached_data:
                        # Try to find in individual cache's all_resources
                        found_in_all_resources = False
                        for resource_id, resource_info in individual_cached_data['all_resources'].items():
                            if self._match_resource_to_arn(resource_id, [arn]):
                                tags_result[arn] = resource_info.get('formatted_tags', 'N/A')
                                found_in_all_resources = True
                                break
                        
                        if not found_in_all_resources:
                            uncached_resources.append(arn)
                    else:
                        uncached_resources.append(arn)
                else:
                    uncached_resources.append(arn)
        
        cache_duration = time.time() - start_time
        print(f"Cache check completed in {cache_duration:.2f}s - {len(resource_arns) - len(uncached_resources)} cached, {len(uncached_resources)} uncached")
        
        if not uncached_resources:
            return tags_result
        
        print(f"Retrieving tags for {len(uncached_resources)} uncached resources using type-specific queries...")
        
        # Group by account
        accounts_resources = {}
        for arn in uncached_resources:
            account_id = extract_account_id_from_arn(arn)
            if account_id:
                if account_id not in accounts_resources:
                    accounts_resources[account_id] = []
                accounts_resources[account_id].append(arn)
        
        print(f"Grouped resources into {len(accounts_resources)} AWS accounts")
        for account_id, resources in accounts_resources.items():
            print(f"  Account {account_id}: {len(resources)} resources")
        
        # Process each account
        start_time_total = time.time()
        for account_id, account_resources in accounts_resources.items():
            account_start_time = time.time()
            print(f"Processing account {account_id} ({len(account_resources)} resources)...")
            
            # Check if we have cached data for this account and resource types
            # For each resource type, check its individual cache
            cache_file = None
            for resource_type in resource_types:
                type_cache_file = self.cache_manager.get_resource_cache_file_path(
                    'account-tags', account_id, resource_type, start_date, end_date
                )
                if type_cache_file.exists():
                    cache_file = type_cache_file
                    break
            
            cached_data = None
            if cache_file:
                cached_data = self.cache_manager.load_from_cache(cache_file)
            
            if cached_data and len(uncached_resources) == 0:
                print(f"  → Using cached data for account {account_id}")
                account_tags_data = cached_data
            else:
                if cached_data and len(uncached_resources) > 0:
                    print(f"  → Cache exists but {len(uncached_resources)} resources missing, fetching fresh data for account {account_id}")
                else:
                    print(f"  → Fetching fresh data for account {account_id}")
                
                # Use specific resource types directly from ARNs
                lacework_resource_types = list(resource_types)
                print(f"    Specific resource types from ARNs: {lacework_resource_types}")
                
                # Process each resource type individually to avoid API timeouts
                api_start_time = time.time()
                all_resources = []
                for resource_type in lacework_resource_types:
                    print(f"    Processing resource type: {resource_type}")
                    # Use resourceConfig filter with regex to match account ID
                    # This matches the UI's approach to filtering by AWS account
                    search_request = {
                        "csp": "AWS",
                        "filters": [
                            {
                                "field": "resourceType",
                                "expression": "eq",
                                "value": resource_type
                            },
                            {
                                "field": "resourceConfig",
                                "expression": "rlike",
                                "value": f'.*{account_id}.*'
                            }
                        ],
                        "returns": ["resourceId", "resourceType", "resourceConfig"]
                    }
                    
                    try:
                        response = self.client_wrapper.search_resources(search_request)
                        # Handle both dict and generator responses
                        if hasattr(response, 'get'):
                            type_data = response.get('data', [])
                        else:
                            # Convert generator to list
                            response_items = list(response)
                            if response_items and isinstance(response_items[0], dict) and 'data' in response_items[0]:
                                # Extract data from the first item
                                type_data = response_items[0]['data']
                                if isinstance(type_data, str):
                                    import json
                                    type_data = json.loads(type_data)
                            else:
                                type_data = response_items
                        
                        print(f"      Found {len(type_data)} resources of type {resource_type}")
                        all_resources.extend(type_data)
                        
                    except Exception as e:
                        print(f"      API call failed for {resource_type}: {e}")
                        continue
                
                actual_data = all_resources
                print(f"    Total resources collected: {len(actual_data)}")
                
                # Check resource types in response
                if actual_data:
                    response_resource_types = {}
                    for item in actual_data[:100]:  # Check first 100 items
                        resource_type = item.get('resourceType', 'unknown')
                        response_resource_types[resource_type] = response_resource_types.get(resource_type, 0) + 1
                    print(f"    Resource types in collected data: {response_resource_types}")
                
                api_duration = time.time() - api_start_time
                print(f"    API call completed in {api_duration:.2f}s, found {len(actual_data)} resources")
                
                # Process results
                account_tags_data = {
                    'account_id': account_id,
                    'resource_tags': {},
                    'all_resources': {},
                    'cached_at': datetime.now().isoformat()
                }
                
                if actual_data:
                    # No need to filter - API already filtered by account ID using resourceConfig regex
                    print(f"    API returned {len(actual_data)} resources for account {account_id}")
                    
                    # Count by resource type
                    type_counts = {}
                    for item in actual_data:
                        resource_type = item.get('resourceType', 'unknown')
                        type_counts[resource_type] = type_counts.get(resource_type, 0) + 1
                    
                    print(f"    Resource type breakdown:")
                    for resource_type, count in sorted(type_counts.items()):
                        print(f"      {resource_type}: {count}")
                    
                    # Process each resource
                    for item in actual_data:
                        resource_id = item.get('resourceId')
                        resource_config = item.get('resourceConfig', {})
                        
                        if resource_id:
                            # Extract tags
                            tags = self._extract_tags_from_resource_config(resource_config)
                            formatted_tags = self._format_tags(tags)
                            
                            # Only store in cache if not already cached, or if new data is more complete
                            # (to avoid overwriting good data with incomplete data from subsequent queries)
                            if resource_id not in account_tags_data['all_resources']:
                                # Store in cache
                                account_tags_data['all_resources'][resource_id] = {
                                    'resource_type': item.get('resourceType'),
                                    'tags': tags,
                                    'formatted_tags': formatted_tags,
                                    'resource_config': resource_config
                                }
                            else:
                                # Already cached - only update if new data has more fields in resource_config
                                existing_config = account_tags_data['all_resources'][resource_id].get('resource_config', {})
                                if isinstance(resource_config, dict) and isinstance(existing_config, dict):
                                    if len(resource_config.keys()) > len(existing_config.keys()):
                                        account_tags_data['all_resources'][resource_id]['resource_config'] = resource_config
                                        account_tags_data['all_resources'][resource_id]['tags'] = tags
                                        account_tags_data['all_resources'][resource_id]['formatted_tags'] = formatted_tags
                            
                            # Match with requested ARNs
                            matched_arn = self._match_resource_to_arn(resource_id, account_resources, resource_config)
                            if matched_arn:
                                tags_result[matched_arn] = formatted_tags
                                account_tags_data['resource_tags'][matched_arn] = formatted_tags
                            
                            # Also populate resource_tags for all resources (for future lookups)
                            # Construct ARN from resource data
                            if resource_config and isinstance(resource_config, dict):
                                # For EC2 instances
                                if 'InstanceId' in resource_config:
                                    instance_id = resource_config['InstanceId']
                                    arn = f"arn:aws:ec2:ap-southeast-2:{account_id}:instance/{instance_id}"
                                    account_tags_data['resource_tags'][arn] = formatted_tags
                                # For RDS instances
                                elif 'DBInstanceIdentifier' in resource_config:
                                    db_id = resource_config['DBInstanceIdentifier']
                                    arn = f"arn:aws:rds:ap-southeast-2:{account_id}:db/{db_id}"
                                    account_tags_data['resource_tags'][arn] = formatted_tags
                                # For Lambda functions
                                elif 'FunctionName' in resource_config:
                                    function_name = resource_config['FunctionName']
                                    arn = f"arn:aws:lambda:ap-southeast-2:{account_id}:function:{function_name}"
                                    account_tags_data['resource_tags'][arn] = formatted_tags
                                # For ELB load balancers
                                elif 'LoadBalancerName' in resource_config:
                                    loadbalancer_name = resource_config['LoadBalancerName']
                                    # Use the LoadBalancerArn from resourceConfig if available
                                    if 'LoadBalancerArn' in resource_config:
                                        arn = resource_config['LoadBalancerArn']
                                    else:
                                        # Fallback: determine type from resource config
                                        if 'Type' in resource_config:
                                            elb_type = resource_config['Type']
                                            if elb_type == 'Network':
                                                arn = f"arn:aws:elasticloadbalancing:ap-southeast-2:{account_id}:loadbalancer/net/{loadbalancer_name}"
                                            else:
                                                arn = f"arn:aws:elasticloadbalancing:ap-southeast-2:{account_id}:loadbalancer/app/{loadbalancer_name}"
                                        else:
                                            # Default to app type
                                            arn = f"arn:aws:elasticloadbalancing:ap-southeast-2:{account_id}:loadbalancer/app/{loadbalancer_name}"
                                    account_tags_data['resource_tags'][arn] = formatted_tags
                                # For Security Groups
                                elif 'GroupId' in resource_config:
                                    group_id = resource_config['GroupId']
                                    arn = f"arn:aws:ec2:ap-southeast-2:{account_id}:security-group/{group_id}"
                                    account_tags_data['resource_tags'][arn] = formatted_tags
                                # For Subnets
                                elif 'SubnetId' in resource_config:
                                    subnet_id = resource_config['SubnetId']
                                    arn = f"arn:aws:ec2:ap-southeast-2:{account_id}:subnet/{subnet_id}"
                                    account_tags_data['resource_tags'][arn] = formatted_tags
                            
                            # Handle VPCs separately (not in elif chain)
                            if resource_config and isinstance(resource_config, dict) and item.get('resourceType') == 'ec2:vpc':
                                if 'VpcId' in resource_config:
                                    vpc_id = resource_config['VpcId']
                                    arn = f"arn:aws:ec2:ap-southeast-2:{account_id}:vpc/{vpc_id}"
                                    account_tags_data['resource_tags'][arn] = formatted_tags
                
                # Sort the cache by resource type and then resource name
                sorted_resources = {}
                for resource_id in sorted(account_tags_data['all_resources'].keys(), 
                                        key=lambda x: (account_tags_data['all_resources'][x]['resource_type'], x)):
                    sorted_resources[resource_id] = account_tags_data['all_resources'][resource_id]
                account_tags_data['all_resources'] = sorted_resources
                
                # Cache the data for each resource type separately
                for resource_type in resource_types:
                    type_cache_file = self.cache_manager.get_resource_cache_file_path(
                        'account-tags', account_id, resource_type, start_date, end_date
                    )
                    
                    # Filter data for this resource type
                    type_data = {
                        'all_resources': {},
                        'resource_tags': {}
                    }
                    
                    for resource_id, resource_info in account_tags_data.get('all_resources', {}).items():
                        if resource_info.get('resource_type') == resource_type:
                            type_data['all_resources'][resource_id] = resource_info
                    
                    for arn, tags in account_tags_data.get('resource_tags', {}).items():
                        if self._get_resource_type_from_arn(arn) == resource_type:
                            type_data['resource_tags'][arn] = tags
                    
                    self.cache_manager.save_to_cache(type_cache_file, type_data)
            
            # Fill in any missing tags for this account (only for requested ARNs)
            for arn in account_resources:
                if arn not in tags_result:
                    tags_result[arn] = 'N/A'
            
            # Apply fallback strategies for resources with N/A tags
            for arn in account_resources:
                if tags_result.get(arn) == 'N/A':
                    resource_type = self._get_resource_type_from_arn(arn)
                    if resource_type in self.fallback_strategies:
                        print(f"    Applying fallback strategy for {resource_type}: {self.fallback_strategies[resource_type]['description']}")
                        # Find the resource in our cached data to get resource_config
                        resource_config = None
                        for cached_resource_id, cached_info in account_tags_data.get('all_resources', {}).items():
                            if self._match_resource_to_arn(cached_resource_id, [arn]):
                                # Get the original resource_config from the API response
                                # We need to find this in the actual_data from the API call
                                for item in actual_data:
                                    if item.get('resourceId') == cached_resource_id:
                                        resource_config = item.get('resourceConfig', {})
                                        break
                                break
                        
                        if resource_config:
                            fallback_tags = self._get_related_resource_tags(arn, resource_type, resource_config)
                            print(f"    Fallback tags for {arn}: {fallback_tags}")
                            tags_result[arn] = fallback_tags
                        else:
                            print(f"    No resource_config found for {arn}")
            
            account_duration = time.time() - account_start_time
            print(f"  → Account {account_id} completed in {account_duration:.2f}s")
        
        # Apply fallback strategies for resources with N/A tags (after API calls)
        fallback_resources = []
        for arn in resource_arns:
            if tags_result.get(arn) == 'N/A':
                resource_type = self._get_resource_type_from_arn(arn)
                if resource_type in self.fallback_strategies:
                    fallback_resources.append(arn)
        
        if fallback_resources:
            print(f"Applying fallback strategies for {len(fallback_resources)} resources with N/A tags...")
            # Group fallback resources by account
            fallback_accounts = {}
            for arn in fallback_resources:
                account_id = extract_account_id_from_arn(arn)
                if account_id:
                    if account_id not in fallback_accounts:
                        fallback_accounts[account_id] = []
                    fallback_accounts[account_id].append(arn)
            
            # Process fallback for each account
            for account_id, account_fallback_resources in fallback_accounts.items():
                print(f"  Processing fallback for account {account_id} ({len(account_fallback_resources)} resources)")
                
                # Process fallback for each resource
                for arn in account_fallback_resources:
                    resource_type = self._get_resource_type_from_arn(arn)
                    if resource_type in self.fallback_strategies:
                        print(f"    Applying fallback strategy for {resource_type}: {self.fallback_strategies[resource_type]['description']}")
                        
                        # Get the cache file for this specific resource type
                        cache_file = self.cache_manager.get_resource_cache_file_path('account-tags', account_id, resource_type, start_date, end_date)
                        cached_data = self.cache_manager.load_from_cache(cache_file)
                        
                        if cached_data and 'all_resources' in cached_data:
                            # Find the resource in cached data to get resource_config
                            resource_config = None
                            for cached_resource_id, cached_info in cached_data['all_resources'].items():
                                if self._match_resource_to_arn(cached_resource_id, [arn], cached_info.get('resource_config')):
                                    # Get the original resource_config from the cached data
                                    if 'resource_config' in cached_info:
                                        resource_config = cached_info['resource_config']
                                    break
                            
                            if resource_config:
                                fallback_tags = self._get_related_resource_tags(arn, resource_type, resource_config, account_id, start_date, end_date)
                                print(f"    Fallback tags for {arn}: {fallback_tags}")
                                tags_result[arn] = fallback_tags
                            else:
                                print(f"    No resource_config found for {arn}")
                        else:
                            print(f"    No cached data found for {resource_type}")
        
        duration_total = time.time() - start_time_total
        print(f"=== TAG RETRIEVAL SUMMARY ===")
        print(f"Total time: {duration_total:.2f}s")
        print(f"Resources processed: {len(resource_arns)}")
        print(f"Accounts processed: {len(accounts_resources)}")
        print(f"Average time per account: {duration_total/len(accounts_resources):.2f}s")
        print(f"Average time per resource: {duration_total/len(resource_arns):.2f}s")
        
        return tags_result
    
    def _get_resource_type_from_arn(self, arn: str) -> str:
        """Extract resource type from ARN."""
        if not arn or not arn.startswith('arn:aws:'):
            return None
        
        # Extract service and resource type from ARN
        arn_parts = arn.split(':')
        if len(arn_parts) >= 6:
            service = arn_parts[2]
            resource_name = arn_parts[5]
            
            # Handle specific resource types
            if service == 'ec2':
                if 'vpc/' in resource_name:
                    return 'ec2:vpc'
                elif 'security-group/' in resource_name:
                    return 'ec2:security-group'
                elif 'subnet/' in resource_name:
                    return 'ec2:subnet'
                elif 'instance/' in resource_name:
                    return 'ec2:instance'
            elif service == 'rds':
                if 'db/' in resource_name:
                    return 'rds:db'
            elif service == 'lambda':
                if 'function:' in resource_name:
                    return 'lambda:function'
            elif service == 's3':
                return 's3:bucket'
            elif service == 'elasticloadbalancing':
                return 'elbv2:loadbalancer'
            
            # Fallback to service name
            return service
        
        return None
    
    def _extract_tags_from_resource_config(self, resource_config: dict) -> dict:
        """Extract tags from resource configuration."""
        if not isinstance(resource_config, dict):
            return {}
        
        # Try different tag field names
        tag_fields = ['TagList', 'Tags', 'tags', 'TagSet', 'tagSet', 'tagList']
        
        for field in tag_fields:
            if field in resource_config:
                tags = resource_config[field]
                if tags:
                    return tags
        
        return {}
    
    def _format_tags(self, tags: dict) -> str:
        """Format tags into a readable string."""
        if not tags:
            return 'N/A'
        
        if isinstance(tags, list):
            formatted_tags = ', '.join([
                f"{tag.get('Key', '')}:{tag.get('Value', '')}" 
                for tag in tags 
                if isinstance(tag, dict)
            ])
        elif isinstance(tags, dict):
            formatted_tags = ', '.join([f"{k}:{v}" for k, v in tags.items()])
        else:
            formatted_tags = 'N/A'
        
        return formatted_tags if formatted_tags else 'N/A'
    
    def _match_resource_to_arn(self, resource_id: str, arns: List[str], resource_config: dict = None) -> str:
        """Match a resource ID to an ARN from the list."""
        for arn in arns:
            if resource_id == arn:
                return arn
            
            # Extract resource name from ARN and compare
            if 'arn:aws:' in arn and ':' in arn:
                arn_parts = arn.split(':')
                if len(arn_parts) >= 6:
                    arn_resource_name = arn_parts[-1]
                    
                    # For RDS, try to match using DB instance identifier from resource config
                    if resource_config and isinstance(resource_config, dict):
                        if 'DBInstanceIdentifier' in resource_config:
                            db_identifier = resource_config['DBInstanceIdentifier']
                            if db_identifier == arn_resource_name:
                                return arn
                        
                        # For EC2, try to match using InstanceId from resource config
                        if 'InstanceId' in resource_config:
                            instance_id = resource_config['InstanceId']
                            # Extract instance ID from ARN (e.g., "instance/i-123" -> "i-123")
                            if '/' in arn_resource_name:
                                arn_instance_id = arn_resource_name.split('/')[-1]
                                if instance_id == arn_instance_id:
                                    return arn
                            elif instance_id == arn_resource_name:
                                return arn
                        
                        # For Lambda, try to match using FunctionName from resource config
                        if 'FunctionName' in resource_config:
                            function_name = resource_config['FunctionName']
                            if function_name == arn_resource_name:
                                return arn
                        
                        # For ELB, try to match using LoadBalancerName from resource config
                        if 'LoadBalancerName' in resource_config:
                            loadbalancer_name = resource_config['LoadBalancerName']
                            # Extract LB name from ARN (e.g., "loadbalancer/net/business-sit6-nlb/8cc..." -> "business-sit6-nlb")
                            if '/' in arn_resource_name:
                                # ARN format: loadbalancer/TYPE/NAME/ID
                                arn_parts = arn_resource_name.split('/')
                                if len(arn_parts) >= 3:
                                    arn_lb_name = arn_parts[2]
                                    if loadbalancer_name == arn_lb_name:
                                        return arn
                            elif loadbalancer_name == arn_resource_name:
                                return arn
                        
                        # For Security Groups, try to match using GroupId from resource config
                        if 'GroupId' in resource_config:
                            group_id = resource_config['GroupId']
                            # Extract security group ID from ARN (e.g., "security-group/sg-123" -> "sg-123")
                            if '/' in arn_resource_name:
                                arn_sg_id = arn_resource_name.split('/')[-1]
                                if group_id == arn_sg_id:
                                    return arn
                            elif group_id == arn_resource_name:
                                return arn
                    
                    # Fallback to direct comparison
                    if arn_resource_name == resource_id:
                        return arn
        
        return None
