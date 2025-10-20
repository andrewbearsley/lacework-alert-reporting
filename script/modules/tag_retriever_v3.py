"""
Tag Retriever V3 with Fallback Strategy

Enhanced tag retrieval with fallback ownership information for untagged resources.
"""

import json
import os
from typing import Dict, List, Optional, Tuple
from .inventory_retriever import InventoryRetriever
from .account_tag_analyzer import AccountTagAnalyzer


class TagRetrieverV3:
    """Enhanced tag retriever with fallback strategy for untagged resources."""
    
    def __init__(self, lacework_client, cache_manager):
        self.lacework_client = lacework_client
        self.cache_manager = cache_manager
        self.inventory_retriever = InventoryRetriever(lacework_client, cache_manager)
        self.account_analyzer = AccountTagAnalyzer(cache_manager)
        
        # Cache for account fallback info per account
        self._fallback_cache = {}
    
    def get_resource_tags_optimized(self, account_id: str, resource_arns: List[str], 
                                   account_name: str = None) -> Dict[str, Dict]:
        """
        Get tags for resources with fallback strategy for untagged resources.
        
        Args:
            account_id: AWS account ID
            resource_arns: List of resource ARNs to get tags for
            account_name: AWS account name (optional)
            
        Returns:
            Dict mapping ARN to tag information with fallback data
        """
        print(f"Getting tags for {len(resource_arns)} resources in account {account_id}")
        
        # Get inventory for the account FIRST
        inventory = self.inventory_retriever.get_account_inventory(account_id, account_name)
        
        # Get account fallback information (now that we have inventory)
        # Retry logic for corrupted inventory files
        max_retries = 2
        for attempt in range(max_retries):
            try:
                fallback_info = self._get_account_fallback_info(account_id, account_name)
                break
            except FileNotFoundError as e:
                if "Corrupted inventory file" in str(e) and attempt < max_retries - 1:
                    print(f"   🔄 Retrying after corrupted file cleanup (attempt {attempt + 2}/{max_retries})")
                    # Force refresh inventory
                    inventory = self.inventory_retriever.get_account_inventory(account_id, account_name, force_refresh=True)
                    continue
                else:
                    raise
        
        # Get resources by ARNs from inventory
        inventory_resources = self.inventory_retriever.get_resources_by_arns(account_id, resource_arns)
        
        # Process each resource
        result = {}
        for arn in resource_arns:
            resource_tags = self._get_resource_tags_with_fallback(
                arn, inventory_resources, fallback_info
            )
            result[arn] = resource_tags
        
        # Summary
        tagged_count = sum(1 for tags in result.values() if tags.get('has_tags', False))
        fallback_count = sum(1 for tags in result.values() if tags.get('used_fallback', False))
        
        print(f"Tag retrieval complete:")
        print(f"  • Resources with tags: {tagged_count}")
        print(f"  • Resources using fallback: {fallback_count}")
        print(f"  • Total processed: {len(result)}")
        
        return result
    
    def _get_account_fallback_info(self, account_id: str, account_name: str = None) -> Dict:
        """Get account fallback information, using cache if available."""
        cache_key = f"{account_id}_{account_name or 'default'}"
        
        if cache_key not in self._fallback_cache:
            self._fallback_cache[cache_key] = self.account_analyzer.get_account_fallback_info(
                account_id, account_name
            )
        
        return self._fallback_cache[cache_key]
    
    def _get_resource_tags_with_fallback(self, arn: str, inventory_resources: Dict, 
                                       fallback_info: Dict) -> Dict:
        """
        Get tags for a single resource with fallback strategy.
        
        Args:
            arn: Resource ARN
            inventory_resources: Dict of inventory resources by ARN
            fallback_info: Account fallback information
            
        Returns:
            Dict containing tag information with fallback data
        """
        # Try to find the resource in inventory
        resource = inventory_resources.get(arn)
        
        if not resource:
            # Resource not found in inventory - use fallback
            return self._create_fallback_tags(arn, fallback_info, reason="not_found_in_inventory")
        
        # Get tags from inventory
        resource_tags = resource.get('resourceTags', {})
        
        if not resource_tags:
            # Resource found but has no tags - use fallback
            return self._create_fallback_tags(arn, fallback_info, reason="no_tags_in_inventory")
        
        # Resource has tags - check if we need partial fallback for missing ownership tags
        technical_owner = resource_tags.get('unsw:technical-owner')
        business_owner = resource_tags.get('unsw:business-owner')
        
        # Determine if we need partial fallback
        needs_partial_fallback = False
        partial_fallback_reasons = []
        
        if not technical_owner and fallback_info.get('default_technical_owner'):
            technical_owner = fallback_info['default_technical_owner'][0]
            needs_partial_fallback = True
            partial_fallback_reasons.append('missing_technical_owner')
        
        if not business_owner and fallback_info.get('default_business_owner'):
            business_owner = fallback_info['default_business_owner'][0]
            needs_partial_fallback = True
            partial_fallback_reasons.append('missing_business_owner')
        
        # Determine tag source
        if needs_partial_fallback:
            tag_source = 'partial_fallback'
            fallback_reason = ', '.join(partial_fallback_reasons)
        else:
            tag_source = 'inventory'
            fallback_reason = None
        
        return {
            'arn': arn,
            'resource_id': resource.get('resourceId'),
            'resource_type': resource.get('resourceType'),
            'has_tags': True,
            'used_fallback': needs_partial_fallback,
            'fallback_reason': fallback_reason,
            'tag_source': tag_source,
            'tags': resource_tags,
            'tag_count': len(resource_tags),
            
            # Extract key ownership information (with partial fallback applied)
            'technical_owner': technical_owner,
            'business_owner': business_owner,
            'billing_project': resource_tags.get('unsw:billing-project-id'),
            'environment': resource_tags.get('unsw:environment'),
            'project_name': resource_tags.get('customProjectName'),
            'project_owner': resource_tags.get('customProjectOwner')
        }
    
    def _create_fallback_tags(self, arn: str, fallback_info: Dict, reason: str) -> Dict:
        """
        Create fallback tag information for untagged resources.
        
        Args:
            arn: Resource ARN
            fallback_info: Account fallback information
            reason: Reason for using fallback
            
        Returns:
            Dict containing fallback tag information
        """
        # Extract resource info from ARN
        resource_id = self._extract_resource_id_from_arn(arn)
        resource_type = self._extract_resource_type_from_arn(arn)
        
        # Create fallback tags
        fallback_tags = {}
        
        # Add fallback ownership information
        if fallback_info.get('default_technical_owner'):
            fallback_tags['unsw:technical-owner'] = fallback_info['default_technical_owner'][0]
        
        if fallback_info.get('default_business_owner'):
            fallback_tags['unsw:business-owner'] = fallback_info['default_business_owner'][0]
        
        if fallback_info.get('billing_project_id'):
            fallback_tags['unsw:billing-project-id'] = fallback_info['billing_project_id'][0]
        
        # Don't apply environment fallback - only use actual environment tags
        # if fallback_info.get('default_environment'):
        #     fallback_tags['unsw:environment'] = fallback_info['default_environment']
        
        # Add fallback indicators
        fallback_tags['unsw:fallback-applied'] = 'true'
        fallback_tags['unsw:fallback-reason'] = reason
        fallback_tags['unsw:fallback-source'] = 'account-analysis'
        
        return {
            'arn': arn,
            'resource_id': resource_id,
            'resource_type': resource_type,
            'has_tags': False,
            'used_fallback': True,
            'fallback_reason': reason,
            'tag_source': 'fallback',
            'tags': fallback_tags,
            'tag_count': len(fallback_tags),
            
            # Extract key ownership information from fallback
            'technical_owner': fallback_tags.get('unsw:technical-owner'),
            'business_owner': fallback_tags.get('unsw:business-owner'),
            'billing_project': fallback_tags.get('unsw:billing-project-id'),
            'environment': None,  # Don't apply environment fallback
            'project_name': None,
            'project_owner': None,
            
            # Fallback metadata
            'fallback_info': {
                'account_id': fallback_info.get('account_id'),
                'account_name': fallback_info.get('account_name'),
                'analysis_timestamp': fallback_info.get('analysis_timestamp'),
                'tagging_coverage': fallback_info.get('tagging_coverage')
            }
        }
    
    def _extract_resource_id_from_arn(self, arn: str) -> str:
        """Extract resource ID from ARN."""
        if not arn:
            return 'unknown'
        
        # Handle different ARN formats
        if '/app/' in arn and 'elasticloadbalancing' in arn:
            # ELB ARN: arn:aws:elasticloadbalancing:region:account:loadbalancer/app/name/uuid
            parts = arn.split('/')
            if len(parts) >= 3:
                return parts[2]  # Load balancer name
        
        # Standard ARN format: arn:aws:service:region:account:resource-type/resource-id
        parts = arn.split('/')
        if len(parts) >= 2:
            return parts[-1]  # Last part is usually the resource ID
        
        return 'unknown'
    
    def _extract_resource_type_from_arn(self, arn: str) -> str:
        """Extract resource type from ARN."""
        if not arn or not arn.startswith('arn:aws:'):
            return 'unknown'
        
        parts = arn.split(':')
        if len(parts) >= 3:
            service = parts[2]
            
            # Map service to Lacework resource type
            if service == 'elasticloadbalancing':
                return 'elbv2:loadbalancer'
            elif service == 's3':
                return 's3:bucket'
            elif service == 'cloudtrail':
                return 'cloudtrail:trail'
            elif service == 'lambda':
                return 'lambda:function'
            else:
                return f"{service}:*"
        
        return 'unknown'
    
    def get_fallback_summary(self, account_id: str) -> Dict:
        """Get summary of fallback information for an account."""
        fallback_info = self._get_account_fallback_info(account_id)
        
        return {
            'account_id': account_id,
            'account_name': fallback_info.get('account_name'),
            'total_resources': fallback_info.get('total_resources'),
            'tagged_resources': fallback_info.get('tagged_resources'),
            'tagging_coverage': fallback_info.get('tagging_coverage'),
            'default_technical_owner': fallback_info.get('default_technical_owner'),
            'default_business_owner': fallback_info.get('default_business_owner'),
            'default_environment': fallback_info.get('default_environment'),
            'billing_project_id': fallback_info.get('billing_project_id'),
            'analysis_timestamp': fallback_info.get('analysis_timestamp')
        }
