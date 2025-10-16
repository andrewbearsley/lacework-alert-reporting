"""
Optimized tag retrieval using paginated account inventory.
Replaces resource-type queries with efficient account-level inventory retrieval.
"""
import time
from typing import Dict, List, Set, Any, Optional
from datetime import datetime

from .cache_manager import CacheManager, extract_account_id_from_arn
from .lacework_client import LaceworkClientWrapper
from .inventory_retriever import InventoryRetriever


class TagRetrieverV2:
    """
    Optimized tag retriever using paginated account inventory.
    
    Key improvements:
    - Single paginated query per account instead of multiple resource-type queries
    - Handles accounts with 5000+ resources efficiently
    - 80-90% reduction in API calls for large accounts
    - Complete resource inventory cached and reused
    """
    
    def __init__(self, client_wrapper: LaceworkClientWrapper, cache_manager: CacheManager):
        """Initialize tag retriever with client and cache manager."""
        self.client_wrapper = client_wrapper
        self.cache_manager = cache_manager
        self.inventory_retriever = InventoryRetriever(client_wrapper, cache_manager)
        
        # Define fallback tag strategies for resources without direct tags
        self.fallback_strategies = {
            'elbv2:loadbalancer': {
                'primary': 'ec2:security-group',
                'secondary': 'ec2:vpc',
                'description': 'ELB -> Security Group -> VPC'
            },
            'lambda:function': {
                'primary': 'ec2:security-group', 
                'secondary': 'iam:role',
                'tertiary': 'ec2:vpc',
                'description': 'Lambda -> Security Group -> IAM Role -> VPC'
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
            },
            'ec2:vpc-endpoint': {
                'primary': 'ec2:security-group',
                'secondary': 'ec2:vpc',
                'description': 'VPC Endpoint -> Security Group -> VPC'
            }
        }
    
    def get_resource_tags_optimized(self, resource_arns: List[str], start_date: str = None, end_date: str = None) -> Dict[str, str]:
        """
        Retrieve tags for resources using optimized paginated account inventory approach.
        
        Args:
            resource_arns: List of resource ARNs to get tags for
            start_date: Start date for date-based caching
            end_date: End date for date-based caching
            
        Returns:
            Dictionary mapping ARNs to formatted tag strings
        """
        if not resource_arns:
            return {}
        
        print(f"=== OPTIMIZED TAG RETRIEVAL V2 ===")
        print(f"Total resources requested: {len(resource_arns)}")
        
        # Group resources by AWS account
        accounts_resources = {}
        s3_buckets_no_account = []
        
        for arn in resource_arns:
            account_id = extract_account_id_from_arn(arn)
            
            # Special handling for S3 - ARNs don't contain account ID
            if not account_id and ':s3:' in arn:
                s3_buckets_no_account.append(arn)
            elif account_id:
                if account_id not in accounts_resources:
                    accounts_resources[account_id] = []
                accounts_resources[account_id].append(arn)
        
        print(f"Grouped resources into {len(accounts_resources)} AWS accounts")
        for account_id, resources in accounts_resources.items():
            print(f"  Account {account_id}: {len(resources)} resources")
        
        # Handle S3 buckets without account ID
        if s3_buckets_no_account:
            print(f"  S3 buckets (no account in ARN): {len(s3_buckets_no_account)} resources")
            # If we're processing a single account, assume S3 buckets belong to that account
            if len(accounts_resources) == 1:
                inferred_account = list(accounts_resources.keys())[0]
                print(f"  Inferring S3 buckets belong to account: {inferred_account}")
                accounts_resources[inferred_account].extend(s3_buckets_no_account)
        
        # Process each account using paginated inventory
        all_tags_result = {}
        total_api_calls = 0
        
        for account_id, account_resources in accounts_resources.items():
            print(f"Processing account {account_id} ({len(account_resources)} resources)...")
            
            # Get complete account inventory (paginated, cached)
            account_start_time = time.time()
            inventory_data = self.inventory_retriever.get_account_inventory(account_id, start_date, end_date)
            account_time = time.time() - account_start_time
            
            total_api_calls += inventory_data['metadata']['total_api_calls']
            
            print(f"  → Account inventory: {inventory_data['metadata']['total_resources']} resources in {inventory_data['metadata']['total_api_calls']} API calls ({account_time:.2f}s)")
            
            # Extract tags for requested resources
            requested_resources = self.inventory_retriever.get_resources_by_arns(account_id, account_resources, start_date, end_date)
            account_tags = self.inventory_retriever.extract_tags_from_resources(requested_resources)
            
            # Apply fallback strategies for resources with N/A tags
            fallback_tags = self._apply_fallback_strategies(account_tags, requested_resources, inventory_data)
            account_tags.update(fallback_tags)
            
            all_tags_result.update(account_tags)
            
            # Handle resources not found in inventory
            for arn in account_resources:
                if arn not in all_tags_result:
                    all_tags_result[arn] = 'N/A'
                    print(f"    Resource not found in inventory: {arn}")
        
        # Performance summary
        print(f"\n=== TAG RETRIEVAL PERFORMANCE SUMMARY ===")
        print(f"Total resources processed: {len(resource_arns)}")
        print(f"Total API calls: {total_api_calls}")
        print(f"Resources with tags: {sum(1 for tags in all_tags_result.values() if tags != 'N/A')}")
        print(f"Resources without tags: {sum(1 for tags in all_tags_result.values() if tags == 'N/A')}")
        
        # Calculate efficiency metrics
        if len(accounts_resources) > 0:
            avg_resources_per_call = len(resource_arns) / total_api_calls if total_api_calls > 0 else 0
            print(f"Efficiency: {avg_resources_per_call:.1f} resources per API call")
        
        return all_tags_result
    
    def _apply_fallback_strategies(self, account_tags: Dict[str, str], requested_resources: Dict[str, Dict[str, Any]], 
                                 inventory_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Apply fallback tag strategies for resources with N/A tags using complete account inventory.
        
        Args:
            account_tags: Current tags for requested resources
            requested_resources: Requested resource data
            inventory_data: Complete account inventory
            
        Returns:
            Dictionary of additional tags from fallback strategies
        """
        fallback_tags = {}
        resource_index = inventory_data.get('resource_index', {})
        
        for arn, tags in account_tags.items():
            if tags == 'N/A':
                resource = requested_resources.get(arn)
                if not resource:
                    continue
                
                resource_type = resource.get('resourceType', '')
                if resource_type in self.fallback_strategies:
                    fallback_tag = self._get_fallback_tag_from_inventory(arn, resource, resource_type, resource_index)
                    if fallback_tag:
                        fallback_tags[arn] = fallback_tag
                        print(f"    Applied fallback tag for {arn}: {fallback_tag}")
        
        return fallback_tags
    
    def _get_fallback_tag_from_inventory(self, arn: str, resource: Dict[str, Any], resource_type: str, 
                                       resource_index: Dict[str, Any]) -> Optional[str]:
        """
        Get fallback tags from complete account inventory without additional API calls.
        
        Args:
            arn: Resource ARN
            resource: Resource data
            resource_type: Lacework resource type
            resource_index: Complete account inventory index
            
        Returns:
            Fallback tag string or None
        """
        strategy = self.fallback_strategies.get(resource_type)
        if not strategy:
            return None
        
        # Try primary fallback strategy
        primary_type = strategy['primary']
        related_arn = self._extract_related_arn(resource, primary_type)
        
        if related_arn:
            related_resource = resource_index.get('by_arn', {}).get(related_arn)
            if related_resource:
                related_tags = self.inventory_retriever._extract_resource_tags(related_resource)
                if related_tags != 'N/A':
                    return f"{related_tags} (from {primary_type})"
        
        # Try secondary fallback strategy
        secondary_type = strategy.get('secondary')
        if secondary_type:
            related_arn = self._extract_related_arn(resource, secondary_type)
            if related_arn:
                related_resource = resource_index.get('by_arn', {}).get(related_arn)
                if related_resource:
                    related_tags = self.inventory_retriever._extract_resource_tags(related_resource)
                    if related_tags != 'N/A':
                        return f"{related_tags} (from {secondary_type})"
        
        # Try tertiary fallback strategy
        tertiary_type = strategy.get('tertiary')
        if tertiary_type:
            related_arn = self._extract_related_arn(resource, tertiary_type)
            if related_arn:
                related_resource = resource_index.get('by_arn', {}).get(related_arn)
                if related_resource:
                    related_tags = self.inventory_retriever._extract_resource_tags(related_resource)
                    if related_tags != 'N/A':
                        return f"{related_tags} (from {tertiary_type})"
        
        return None
    
    def _extract_related_arn(self, resource: Dict[str, Any], related_type: str) -> Optional[str]:
        """
        Extract related resource ARN from resource configuration.
        
        Args:
            resource: Resource data from Lacework
            related_type: Type of related resource to find
            
        Returns:
            Related resource ARN or None
        """
        resource_config = resource.get('resourceConfig', {})
        if not resource_config:
            return None
        
        # Common field mappings for different resource types
        field_mappings = {
            'ec2:security-group': ['SecurityGroups', 'securityGroups', 'GroupId', 'groupId'],
            'ec2:vpc': ['VpcId', 'vpcId', 'Vpc', 'vpc'],
            'ec2:subnet': ['SubnetId', 'subnetId', 'Subnet', 'subnet'],
            'iam:role': ['RoleArn', 'roleArn', 'Role', 'role']
        }
        
        fields_to_check = field_mappings.get(related_type, [])
        
        for field in fields_to_check:
            if field in resource_config:
                value = resource_config[field]
                
                # Handle different value formats
                if isinstance(value, str):
                    if value.startswith('arn:'):
                        return value
                    elif 'sg-' in value and related_type == 'ec2:security-group':
                        # Construct ARN for security group
                        account_id = resource.get('cloudDetails', {}).get('accountID', '')
                        region = resource.get('cloudDetails', {}).get('region', '')
                        if account_id and region:
                            return f"arn:aws:ec2:{region}:{account_id}:security-group/{value}"
                    elif 'vpc-' in value and related_type == 'ec2:vpc':
                        # Construct ARN for VPC
                        account_id = resource.get('cloudDetails', {}).get('accountID', '')
                        region = resource.get('cloudDetails', {}).get('region', '')
                        if account_id and region:
                            return f"arn:aws:ec2:{region}:{account_id}:vpc/{value}"
                
                elif isinstance(value, list) and len(value) > 0:
                    # Handle list of IDs (e.g., SecurityGroups array)
                    first_value = value[0]
                    if isinstance(first_value, str):
                        if first_value.startswith('arn:'):
                            return first_value
                        elif 'sg-' in first_value and related_type == 'ec2:security-group':
                            account_id = resource.get('cloudDetails', {}).get('accountID', '')
                            region = resource.get('cloudDetails', {}).get('region', '')
                            if account_id and region:
                                return f"arn:aws:ec2:{region}:{account_id}:security-group/{first_value}"
        
        return None
