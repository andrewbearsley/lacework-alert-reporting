"""
Account Tag Analyzer

Analyzes tag distribution across an AWS account to determine fallback ownership
and environment information for untagged resources.
"""

import json
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta


class AccountTagAnalyzer:
    """Analyzes account-level tag patterns for fallback ownership information."""
    
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
        self.cache_ttl_hours = 24  # Cache for 24 hours
    
    def get_account_fallback_info(self, account_id: str, account_name: str = None) -> Dict:
        """
        Get account-level fallback ownership and environment information.
        
        Args:
            account_id: AWS account ID
            account_name: AWS account name (optional)
            
        Returns:
            Dict containing fallback ownership and environment information
        """
        cache_path = self.cache_manager.get_account_fallback_cache_path(account_id)
        
        # Check if we have valid cached data
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cached_data = json.load(f)
                
                # Check if cache is still valid
                cache_time = datetime.fromisoformat(cached_data.get('cache_timestamp', ''))
                if datetime.now() - cache_time < timedelta(hours=self.cache_ttl_hours):
                    print(f"Using cached fallback info for account {account_id}")
                    return cached_data['fallback_info']
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"Error reading cached fallback info: {e}")
        
        # Generate fresh fallback information
        print(f"Analyzing tag distribution for account {account_id}")
        fallback_info = self._analyze_account_tags(account_id, account_name)
        
        # Cache the results
        self._cache_fallback_info(cache_path, fallback_info)
        
        return fallback_info
    
    def _analyze_account_tags(self, account_id: str, account_name: str = None) -> Dict:
        """
        Analyze tag distribution across the account to determine fallback information.
        
        Args:
            account_id: AWS account ID
            account_name: AWS account name
            
        Returns:
            Dict containing fallback ownership and environment information
        """
        # Load account inventory - try different date ranges
        inventory_path = None
        possible_paths = [
            self.cache_manager.get_account_inventory_cache_path(account_id, "2025-10-20", "2025-10-20"),
            self.cache_manager.get_account_inventory_cache_path(account_id, "2025-10-16", "2025-10-16"),
            self.cache_manager.get_account_inventory_cache_path(account_id, "2025-10-09", "2025-10-15"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                inventory_path = path
                break
        
        if not inventory_path or not os.path.exists(inventory_path):
            raise FileNotFoundError(f"No inventory found for account {account_id}")
        
        with open(inventory_path, 'r') as f:
            inventory_data = json.load(f)
        
        resources = inventory_data.get('resources', [])
        
        # Analyze tag patterns
        tag_analysis = self._analyze_tag_patterns(resources)
        
        # Determine fallback information
        fallback_info = {
            'account_id': account_id,
            'account_name': account_name or f"account-{account_id}",
            'analysis_timestamp': datetime.now().isoformat(),
            'total_resources': len(resources),
            'tagged_resources': tag_analysis['total_tagged_resources'],
            'tagging_coverage': tag_analysis['tagging_coverage'],
            
            # Ownership fallbacks
            'default_technical_owner': tag_analysis['most_common_technical_owner'],
            'default_business_owner': tag_analysis['most_common_business_owner'],
            'billing_project_id': tag_analysis['most_common_billing_project'],
            
            # Environment fallbacks
            'default_environment': tag_analysis['default_environment'],
            'environment_coverage': tag_analysis['environment_coverage'],
            
            # Additional context
            'owner_distribution': tag_analysis['owner_distribution'],
            'environment_distribution': tag_analysis['environment_distribution'],
            'billing_distribution': tag_analysis['billing_distribution']
        }
        
        return fallback_info
    
    def _analyze_tag_patterns(self, resources: List[Dict]) -> Dict:
        """
        Analyze tag patterns across all resources.
        
        Args:
            resources: List of resource dictionaries
            
        Returns:
            Dict containing tag analysis results
        """
        # Counters for analysis
        total_resources = len(resources)
        tagged_resources = 0
        
        technical_owners = {}
        business_owners = {}
        billing_projects = {}
        environments = {}
        
        # Analyze each resource
        for resource in resources:
            tags = resource.get('resourceTags', {})
            if tags:
                tagged_resources += 1
                
                # Technical owners
                tech_owner = tags.get('unsw:technical-owner')
                if tech_owner:
                    technical_owners[tech_owner] = technical_owners.get(tech_owner, 0) + 1
                
                # Business owners
                business_owner = tags.get('unsw:business-owner')
                if business_owner:
                    business_owners[business_owner] = business_owners.get(business_owner, 0) + 1
                
                # Billing projects
                billing_project = tags.get('unsw:billing-project-id')
                if billing_project:
                    billing_projects[billing_project] = billing_projects.get(billing_project, 0) + 1
                
                # Environments
                environment = tags.get('unsw:environment')
                if environment:
                    environments[environment] = environments.get(environment, 0) + 1
        
        # Calculate coverage
        tagging_coverage = (tagged_resources / total_resources * 100) if total_resources > 0 else 0
        environment_coverage = (sum(environments.values()) / tagged_resources * 100) if tagged_resources > 0 else 0
        
        # Find most common values
        most_common_technical_owner = self._get_most_common(technical_owners)
        most_common_business_owner = self._get_most_common(business_owners)
        most_common_billing_project = self._get_most_common(billing_projects)
        
        # Determine default environment
        default_environment = self._determine_default_environment(environments, resources)
        
        return {
            'total_tagged_resources': tagged_resources,
            'tagging_coverage': tagging_coverage,
            'most_common_technical_owner': most_common_technical_owner,
            'most_common_business_owner': most_common_business_owner,
            'most_common_billing_project': most_common_billing_project,
            'default_environment': default_environment,
            'environment_coverage': environment_coverage,
            'owner_distribution': {
                'technical_owners': dict(sorted(technical_owners.items(), key=lambda x: x[1], reverse=True)[:10]),
                'business_owners': dict(sorted(business_owners.items(), key=lambda x: x[1], reverse=True)[:10])
            },
            'environment_distribution': dict(sorted(environments.items(), key=lambda x: x[1], reverse=True)),
            'billing_distribution': dict(sorted(billing_projects.items(), key=lambda x: x[1], reverse=True))
        }
    
    def _get_most_common(self, counter_dict: Dict) -> Optional[Tuple[str, int]]:
        """
        Get the most common value from a counter dictionary.
        
        Args:
            counter_dict: Dictionary with values as counts
            
        Returns:
            Tuple of (value, count) or None if empty
        """
        if not counter_dict:
            return None
        
        most_common = max(counter_dict.items(), key=lambda x: x[1])
        return most_common
    
    def _determine_default_environment(self, environments: Dict, resources: List[Dict]) -> str:
        """
        Determine the default environment for the account.
        
        Args:
            environments: Dictionary of environment counts
            resources: List of all resources
            
        Returns:
            Default environment string
        """
        if not environments:
            # Don't infer environment - only use actual tags
            return 'N/A'
        
        # Get the most common environment
        most_common_env = max(environments.items(), key=lambda x: x[1])[0]
        
        # Normalize environment names
        env_mapping = {
            'prod': 'prod',
            'PROD': 'prod',
            'production': 'prod',
            'dev': 'dev',
            'development': 'dev',
            'test': 'test',
            'testing': 'test',
            'uat': 'uat',
            'staging': 'staging',
            'sandbox': 'sandbox'
        }
        
        return env_mapping.get(most_common_env.lower(), most_common_env)
    
    def _infer_environment_from_context(self, resources: List[Dict]) -> str:
        """
        Infer environment from account context and resource patterns.
        
        Args:
            resources: List of all resources
            
        Returns:
            Inferred environment
        """
        # Look for environment patterns in resource names
        env_patterns = {
            'dev': 0,
            'prod': 0,
            'test': 0,
            'sandbox': 0,
            'demo': 0
        }
        
        for resource in resources:
            resource_id = resource.get('resourceId', '').lower()
            resource_name = resource.get('resourceName', '').lower()
            combined_text = f'{resource_id} {resource_name}'
            
            for pattern in env_patterns:
                if pattern in combined_text:
                    env_patterns[pattern] += 1
        
        # Return the most common pattern, or default to 'dev'
        most_common_pattern = max(env_patterns.items(), key=lambda x: x[1])
        if most_common_pattern[1] > 0:
            return most_common_pattern[0]
        
        return 'dev'  # Default fallback
    
    def _cache_fallback_info(self, cache_path: str, fallback_info: Dict):
        """
        Cache fallback information to disk.
        
        Args:
            cache_path: Path to cache file
            fallback_info: Fallback information to cache
        """
        cache_data = {
            'cache_timestamp': datetime.now().isoformat(),
            'fallback_info': fallback_info
        }
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        print(f"Cached fallback info to {cache_path}")
