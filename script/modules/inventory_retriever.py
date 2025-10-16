"""
Paginated inventory retrieval functionality for Lacework Alert Reporting.
Optimized to handle large accounts with 5000+ resources through pagination.
"""
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from .cache_manager import CacheManager
from .lacework_client import LaceworkClientWrapper


class InventoryRetriever:
    """Handles paginated retrieval of complete account inventory from Lacework."""
    
    def __init__(self, client_wrapper: LaceworkClientWrapper, cache_manager: CacheManager):
        """Initialize inventory retriever with client and cache manager."""
        self.client_wrapper = client_wrapper
        self.cache_manager = cache_manager
        self.page_size = 5000  # Lacework's maximum resources per API call
        
    def get_account_inventory(self, account_id: str, start_date: str = None, end_date: str = None, 
                            force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get complete inventory for an AWS account using pagination.
        
        Args:
            account_id: AWS account ID
            start_date: Start date for cache key (optional)
            end_date: End date for cache key (optional)
            force_refresh: Force refresh cache even if valid cache exists
            
        Returns:
            Dictionary containing all account resources with metadata
        """
        print(f"Getting inventory for account {account_id}...")
        
        # Check cache first
        if not force_refresh:
            cached_inventory = self._load_from_cache(account_id, start_date, end_date)
            if cached_inventory:
                print(f"  → Using cached inventory: {cached_inventory['metadata']['total_resources']} resources")
                return cached_inventory
        
        # Fetch fresh inventory with pagination
        print(f"  → Fetching fresh inventory with pagination...")
        inventory_data = self._fetch_paginated_inventory(account_id, start_date, end_date)
        
        # Save to cache
        self._save_to_cache(account_id, inventory_data, start_date, end_date)
        
        return inventory_data
    
    def _fetch_paginated_inventory(self, account_id: str, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        Fetch complete account inventory using pagination to handle 5000+ resources.
        
        Args:
            account_id: AWS account ID
            start_date: Start date for filtering (optional)
            end_date: End date for filtering (optional)
            
        Returns:
            Dictionary with all resources and pagination metadata
        """
        all_resources = []
        page_count = 0
        total_api_calls = 0
        start_time = time.time()
        
        # Build base search request using cloudDetails.accountID filter (like original tag retriever)
        search_request = {
            "csp": "AWS",
            "filters": [
                {
                    "field": "cloudDetails.accountID",
                    "expression": "eq",
                    "value": account_id
                }
            ],
            "returns": [
                "resourceId", 
                "resourceType", 
                "resourceConfig", 
                "resourceTags",
                "cloudDetails"
            ]
        }
        
        # Paginated API calls to get all resources for the account
        print(f"    Fetching all resources for account {account_id} with pagination...")
        
        try:
            # Make initial API call
            results = self.client_wrapper.make_api_call_with_retry(
                lambda: self.client_wrapper.client.inventory.search(search_request)
            )
            
            # Handle generator response
            if hasattr(results, '__iter__') and not isinstance(results, dict):
                response_objects = list(results)
            else:
                response_objects = results.get('data', []) if isinstance(results, dict) else []
            
            # Extract resources from first page
            all_resources = []
            for response_obj in response_objects:
                if isinstance(response_obj, dict) and 'data' in response_obj:
                    all_resources.extend(response_obj['data'])
            
            page_count = 1
            total_api_calls = 1
            
            # Check if we need to paginate
            total_rows = 0
            if response_objects and 'paging' in response_objects[0]:
                total_rows = response_objects[0]['paging'].get('totalRows', 0)
                rows_per_page = response_objects[0]['paging'].get('rows', 5000)
                
                print(f"      → Page {page_count}: Retrieved {len(all_resources)} resources (Total available: {total_rows})")
                
                # Continue pagination if needed
                while len(all_resources) < total_rows and 'nextPage' in response_objects[0].get('paging', {}).get('urls', {}):
                    page_count += 1
                    total_api_calls += 1
                    
                    # Use next page URL for subsequent requests
                    next_page_url = response_objects[0]['paging']['urls']['nextPage']
                    
                    # Make next page API call
                    next_results = self.client_wrapper.make_api_call_with_retry(
                        lambda: self.client_wrapper.client.inventory.search_next_page(next_page_url)
                    )
                    
                    # Handle next page response
                    if hasattr(next_results, '__iter__') and not isinstance(next_results, dict):
                        next_response_objects = list(next_results)
                    else:
                        next_response_objects = next_results.get('data', []) if isinstance(next_results, dict) else []
                    
                    # Extract resources from next page
                    page_resources = []
                    for response_obj in next_response_objects:
                        if isinstance(response_obj, dict) and 'data' in response_obj:
                            page_resources.extend(response_obj['data'])
                    
                    all_resources.extend(page_resources)
                    print(f"      → Page {page_count}: Retrieved {len(page_resources)} resources (Total: {len(all_resources)})")
                    
                    # Update response_objects for next iteration
                    response_objects = next_response_objects
                    
                    # Rate limiting: Add delay between pages
                    time.sleep(1)
            else:
                print(f"      → Retrieved {len(all_resources)} resources from {len(response_objects)} response objects")
            
        except Exception as e:
            print(f"      → Error fetching resources: {str(e)}")
            raise e
        
        # Calculate performance metrics
        total_time = time.time() - start_time
        total_resources = len(all_resources)
        
        print(f"  → Pagination complete: {total_resources} resources in {page_count} pages")
        print(f"  → Performance: {total_api_calls} API calls in {total_time:.2f}s ({total_resources/total_time:.1f} resources/sec)")
        
        # Build inventory data structure
        inventory_data = {
            "metadata": {
                "account_id": account_id,
                "total_resources": total_resources,
                "total_pages": page_count,
                "total_api_calls": total_api_calls,
                "fetch_time": total_time,
                "start_date": start_date,
                "end_date": end_date,
                "timestamp": datetime.now().isoformat()
            },
            "resources": all_resources,
            "resource_index": self._build_resource_index(all_resources)
        }
        
        return inventory_data
    
    def _build_resource_index(self, resources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Build fast lookup index for resources by ARN and resource type.
        
        Args:
            resources: List of resource dictionaries
            
        Returns:
            Dictionary with resource lookup indices
        """
        arn_index = {}
        type_index = {}
        
        for resource in resources:
            resource_id = resource.get('resourceId', '')
            resource_type = resource.get('resourceType', '')
            
            # Index by ARN/resource ID
            if resource_id:
                arn_index[resource_id] = resource
            
            # Index by resource type
            if resource_type:
                if resource_type not in type_index:
                    type_index[resource_type] = []
                type_index[resource_type].append(resource)
        
        return {
            "by_arn": arn_index,
            "by_type": type_index
        }
    
    def _load_from_cache(self, account_id: str, start_date: str = None, end_date: str = None) -> Optional[Dict[str, Any]]:
        """Load inventory from cache if available and valid."""
        cache_file = self.cache_manager.get_account_inventory_cache_path(account_id, start_date, end_date)
        
        if not cache_file.exists():
            return None
        
        try:
            cached_data = self.cache_manager.load_from_cache(cache_file)
            
            # Check cache validity (24 hours for account inventory)
            if cached_data and 'metadata' in cached_data:
                cache_timestamp = datetime.fromisoformat(cached_data['metadata']['timestamp'])
                cache_age = datetime.now() - cache_timestamp
                
                if cache_age.total_seconds() < 24 * 60 * 60:  # 24 hours
                    return cached_data
                else:
                    print(f"  → Cache expired (age: {cache_age}), refreshing...")
                    return None
            
            return cached_data
            
        except Exception as e:
            print(f"  → Error loading cache: {str(e)}, fetching fresh data...")
            return None
    
    def _save_to_cache(self, account_id: str, inventory_data: Dict[str, Any], start_date: str = None, end_date: str = None):
        """Save inventory data to cache."""
        try:
            cache_file = self.cache_manager.get_account_inventory_cache_path(account_id, start_date, end_date)
            self.cache_manager.save_to_cache(cache_file, inventory_data)
            print(f"  → Cached {inventory_data['metadata']['total_resources']} resources to {cache_file}")
        except Exception as e:
            print(f"  → Warning: Failed to save cache: {str(e)}")
    
    def get_resources_by_arns(self, account_id: str, resource_arns: List[str], start_date: str = None, end_date: str = None) -> Dict[str, Dict[str, Any]]:
        """
        Get specific resources by their ARNs from account inventory.
        
        Args:
            account_id: AWS account ID
            resource_arns: List of resource ARNs to retrieve
            start_date: Start date for cache key (optional)
            end_date: End date for cache key (optional)
            
        Returns:
            Dictionary mapping ARNs to resource data
        """
        # Get complete account inventory (cached)
        inventory = self.get_account_inventory(account_id, start_date, end_date)
        
        # Extract requested resources by matching resource IDs from ARNs
        requested_resources = {}
        
        for arn in resource_arns:
            # Extract resource ID from ARN
            resource_id = self._extract_resource_id_from_arn(arn)
            
            # Find resource in inventory by resource ID
            found_resource = None
            for resource in inventory.get('resources', []):
                if resource.get('resourceId') == resource_id:
                    found_resource = resource
                    break
            
            if found_resource:
                requested_resources[arn] = found_resource
        
        print(f"  → Found {len(requested_resources)}/{len(resource_arns)} requested resources in inventory")
        
        return requested_resources
    
    def _extract_resource_id_from_arn(self, arn: str) -> str:
        """
        Extract resource ID from AWS ARN.
        
        Args:
            arn: AWS resource ARN
            
        Returns:
            Resource ID portion of the ARN
        """
        if not arn.startswith('arn:'):
            return arn
        
        # Parse ARN: arn:partition:service:region:account-id:resource
        parts = arn.split(':')
        if len(parts) < 6:
            return arn
        
        # Extract resource part (everything after account ID)
        resource_part = ':'.join(parts[5:])
        
        # Handle different resource formats
        if '/' in resource_part:
            # Format: resource-type/resource-id
            return resource_part.split('/')[-1]
        else:
            # Format: just resource-id
            return resource_part
    
    def extract_tags_from_resources(self, resources: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """
        Extract tags from resources dictionary.
        
        Args:
            resources: Dictionary mapping ARNs to resource data
            
        Returns:
            Dictionary mapping ARNs to formatted tag strings
        """
        tags_result = {}
        
        for arn, resource in resources.items():
            tags = self._extract_resource_tags(resource)
            tags_result[arn] = tags
        
        return tags_result
    
    def _extract_resource_tags(self, resource: Dict[str, Any]) -> str:
        """
        Extract formatted tags from a single resource.
        
        Args:
            resource: Resource dictionary from Lacework
            
        Returns:
            Formatted tag string or 'N/A' if no tags
        """
        # Try resourceTags first
        resource_tags = resource.get('resourceTags', {})
        if resource_tags and isinstance(resource_tags, dict):
            tag_pairs = []
            for key, value in resource_tags.items():
                tag_pairs.append(f"{key}:{value}")
            return "; ".join(tag_pairs)
        
        # Try resourceConfig for tags
        resource_config = resource.get('resourceConfig', {})
        if resource_config and isinstance(resource_config, dict):
            # Look for common tag fields in resource config
            tag_fields = ['tags', 'Tags', 'TagSet', 'tagSet']
            for tag_field in tag_fields:
                if tag_field in resource_config:
                    tags_data = resource_config[tag_field]
                    if isinstance(tags_data, dict):
                        tag_pairs = []
                        for key, value in tags_data.items():
                            tag_pairs.append(f"{key}:{value}")
                        return "; ".join(tag_pairs)
                    elif isinstance(tags_data, list):
                        tag_pairs = []
                        for tag in tags_data:
                            if isinstance(tag, dict) and 'Key' in tag and 'Value' in tag:
                                tag_pairs.append(f"{tag['Key']}:{tag['Value']}")
                        return "; ".join(tag_pairs)
        
        return 'N/A'
