"""
Optimized compliance processing using compliance-first approach.
Focuses on non-compliant policies only and uses paginated inventory for tag retrieval.
"""
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

from .cache_manager import CacheManager
from .lacework_client import LaceworkClientWrapper
from .tag_retriever_v3 import TagRetrieverV3


class ComplianceProcessorV2:
    """
    Optimized compliance processor using compliance-first approach.
    
    Key improvements:
    - Focus on non-compliant policies only
    - Use paginated account inventory for efficient tag retrieval
    - Cache compliance reports per account and time range
    - Sequential processing to respect rate limits
    """
    
    def __init__(self, client_wrapper: LaceworkClientWrapper, cache_manager: CacheManager):
        """Initialize compliance processor with client and cache manager."""
        self.client_wrapper = client_wrapper
        self.cache_manager = cache_manager
        self.tag_retriever = TagRetrieverV3(client_wrapper, cache_manager)
    
    def process_compliance_report(self, report_name: str, start_date: str, end_date: str, 
                                aws_account_filter: str = None) -> List[Dict[str, Any]]:
        """
        Process compliance report using compliance-first approach.
        
        Args:
            report_name: Name of compliance report (e.g., "UNSW-AWS-Cyber-Security-Standards")
            start_date: Start date for compliance report
            end_date: End date for compliance report
            aws_account_filter: Optional AWS account ID to filter to
            
        Returns:
            List of compliance violations with enhanced resource tags
        """
        print(f"=== COMPLIANCE-FIRST PROCESSING ===")
        print(f"Report: {report_name}")
        print(f"Date Range: {start_date} to {end_date}")
        if aws_account_filter:
            print(f"Account Filter: {aws_account_filter}")
        
        # Step 1: Get AWS accounts
        print(f"\nStep 1: Getting AWS accounts...")
        aws_accounts = self._get_aws_accounts()
        if not aws_accounts:
            print("No AWS accounts found")
            return []
        
        # Apply account filtering if specified
        if aws_account_filter:
            aws_accounts = [acc for acc in aws_accounts if acc['account_id'] == aws_account_filter]
            print(f"Filtered to {len(aws_accounts)} accounts matching {aws_account_filter}")
        
        print(f"Processing {len(aws_accounts)} AWS accounts...")
        
        # Step 2: Process each account sequentially (respect rate limits)
        all_compliance_violations = []
        
        for i, account in enumerate(aws_accounts, 1):
            account_id = account['account_id']
            account_alias = account.get('account_alias', '')
            
            print(f"\n--- Account {i}/{len(aws_accounts)}: {account_id} ({account_alias}) ---")
            
            # Get compliance report for this account
            compliance_data = self._get_account_compliance_report(account_id, report_name, start_date, end_date)
            
            if not compliance_data:
                print(f"No compliance data found for account {account_id}")
                continue
            
            # Extract non-compliant policies only
            non_compliant_policies = self._extract_non_compliant_policies(compliance_data)
            print(f"Found {len(non_compliant_policies)} non-compliant policies")
            
            if not non_compliant_policies:
                print(f"No non-compliant policies found for account {account_id}")
                continue
            
            # Extract resources from non-compliant policies
            all_resources = []
            for policy in non_compliant_policies:
                policy_resources = self._extract_resources_from_policy(policy)
                all_resources.extend(policy_resources)
            
            print(f"Extracted {len(all_resources)} resources from non-compliant policies")
            
            # Get resource ARNs for tag retrieval
            resource_arns = [resource['arn'] for resource in all_resources if resource.get('arn')]
            
            # Get resource tags using optimized paginated approach with fallback
            if resource_arns:
                print(f"Retrieving tags for {len(resource_arns)} resources...")
                resource_tag_info = self.tag_retriever.get_resource_tags_optimized(
                    account_id, resource_arns, account_alias
                )
                
                # Apply tags to resources with fallback information
                for resource in all_resources:
                    arn = resource.get('arn')
                    if arn:
                        tag_info = resource_tag_info.get(arn, {})
                        
                        # Use actual tags if available, otherwise use fallback
                        if tag_info.get('has_tags'):
                            resource['tags'] = tag_info.get('tags', {})
                            resource['tag_source'] = 'inventory'
                        else:
                            resource['tags'] = tag_info.get('tags', {})
                            resource['tag_source'] = 'fallback'
                            resource['fallback_reason'] = tag_info.get('fallback_reason')
                        
                        # Add ownership information for easier access
                        resource['technical_owner'] = tag_info.get('technical_owner')
                        resource['business_owner'] = tag_info.get('business_owner')
                        resource['environment'] = tag_info.get('environment')
                    else:
                        resource['tags'] = 'N/A'
                        resource['tag_source'] = 'none'
            
            # Create compliance violations with enhanced data
            account_violations = self._create_compliance_violations(
                account_id, account_alias, non_compliant_policies, all_resources
            )
            
            all_compliance_violations.extend(account_violations)
            print(f"Created {len(account_violations)} compliance violations for account {account_id}")
            
            # Rate limiting: Add delay between accounts
            if i < len(aws_accounts):
                print("Waiting 2 seconds before next account...")
                time.sleep(2)
        
        print(f"\n=== COMPLIANCE PROCESSING COMPLETE ===")
        print(f"Total compliance violations: {len(all_compliance_violations)}")
        
        return all_compliance_violations
    
    def _get_aws_accounts(self) -> List[Dict[str, Any]]:
        """Get configured AWS accounts."""
        try:
            accounts_data = self.client_wrapper.get_aws_accounts()
            
            if accounts_data and 'data' in accounts_data:
                accounts = []
                for account in accounts_data['data']:
                    # Extract account ID from the data structure (same as original processor)
                    account_id = account.get('data', {}).get('awsAccountId', '')
                    if not account_id:
                        # Fallback to other possible fields
                        account_id = account.get('awsAccountId', '')
                    
                    accounts.append({
                        'account_id': account_id,
                        'account_alias': account.get('name', ''),
                        'enabled': account.get('enabled', 0),
                        'integration_guid': account.get('intgGuid', '')
                    })
                
                # Filter to enabled accounts only (enabled = 1)
                enabled_accounts = [acc for acc in accounts if acc['enabled'] == 1 and acc['account_id']]
                print(f"Found {len(accounts)} total AWS accounts ({len(enabled_accounts)} enabled)")
                return enabled_accounts
            
            return []
            
        except Exception as e:
            print(f"Error getting AWS accounts: {str(e)}")
            return []
    
    def _get_account_compliance_report(self, account_id: str, report_name: str, start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
        """
        Get compliance report for a specific account (cached).
        
        Args:
            account_id: AWS account ID
            report_name: Compliance report name
            start_date: Start date
            end_date: End date
            
        Returns:
            Compliance report data or None
        """
        # Check cache first
        cache_file = self.cache_manager.get_account_compliance_cache_path(account_id, report_name, start_date, end_date)
        cached_data = self.cache_manager.load_from_cache(cache_file)
        
        if cached_data:
            print(f"Using cached compliance report for account {account_id}")
            return cached_data
        
        # Fetch fresh compliance report
        print(f"Fetching fresh compliance report for account {account_id}...")
        
        try:
            # Use Lacework CLI to get compliance report
            compliance_data = self._fetch_compliance_report_via_cli(account_id, report_name, start_date, end_date)
            
            if compliance_data:
                # Cache the compliance report
                self.cache_manager.save_to_cache(cache_file, compliance_data)
                print(f"Cached compliance report for account {account_id}")
            
            return compliance_data
            
        except Exception as e:
            print(f"Error fetching compliance report for account {account_id}: {str(e)}")
            return None
    
    def _fetch_compliance_report_via_cli(self, account_id: str, report_name: str, start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
        """
        Fetch compliance report using Lacework CLI.
        
        Args:
            account_id: AWS account ID
            report_name: Compliance report name
            start_date: Start date
            end_date: End date
            
        Returns:
            Compliance report data or None
        """
        try:
            import subprocess
            import json
            
            # Build lacework CLI command (CLI gets latest report, no date filtering)
            cmd = [
                "lacework", "compliance", "aws", "get-report", account_id,
                "--report_name", report_name,
                "--json"
            ]
            
            print(f"Running: {' '.join(cmd)}")
            
            # Execute command
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                compliance_data = json.loads(result.stdout)
                print(f"Successfully fetched compliance report")
                return compliance_data
            else:
                print(f"CLI command failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"CLI command timed out after 300 seconds")
            return None
        except Exception as e:
            print(f"Error running CLI command: {str(e)}")
            return None
    
    def _extract_non_compliant_policies(self, compliance_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract only non-compliant policies from compliance report.
        
        Args:
            compliance_data: Raw compliance report data
            
        Returns:
            List of non-compliant policies
        """
        non_compliant_policies = []
        
        # Navigate the compliance report structure
        recommendations = compliance_data.get('recommendations', [])
        for recommendation in recommendations:
            # Check if policy is non-compliant
            status = recommendation.get('STATUS', '').lower()
            if status in ['noncompliant', 'non-compliant', 'violation', 'failed']:
                non_compliant_policies.append(recommendation)
        
        return non_compliant_policies
    
    def _extract_resources_from_policy(self, policy: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract resources from a non-compliant policy.
        
        Args:
            policy: Policy data from compliance report
            
        Returns:
            List of resources from the policy
        """
        resources = []
        
        # Extract resources from VIOLATIONS array in policy data
        violations = policy.get('VIOLATIONS', [])
        for violation in violations:
            if isinstance(violation, dict):
                # Extract ARN and other resource info
                arn = violation.get('resource', '')
                if arn:
                    resources.append({
                        'arn': arn,
                        'resource_type': '',  # Will be extracted from ARN
                        'resource_name': '',  # Will be extracted from ARN
                        'region': violation.get('region', ''),
                        'policy_id': policy.get('REC_ID', ''),
                        'policy_title': policy.get('TITLE', ''),
                        'severity': policy.get('SEVERITY', ''),
                        'description': policy.get('TITLE', '')
                    })
        
        return resources
    
    def _create_compliance_violations(self, account_id: str, account_alias: str, 
                                    non_compliant_policies: List[Dict[str, Any]], 
                                    resources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create compliance violations with enhanced resource data.
        
        Args:
            account_id: AWS account ID
            account_alias: AWS account alias
            non_compliant_policies: List of non-compliant policies
            resources: List of resources with tags
            
        Returns:
            List of compliance violations
        """
        violations = []
        
        # Group resources by policy
        resources_by_policy = {}
        for resource in resources:
            policy_id = resource.get('policy_id', 'unknown')
            if policy_id not in resources_by_policy:
                resources_by_policy[policy_id] = []
            resources_by_policy[policy_id].append(resource)
        
        # Create violation for each policy
        for policy in non_compliant_policies:
            policy_id = policy.get('REC_ID', 'unknown')
            policy_resources = resources_by_policy.get(policy_id, [])
            
            # Create violation record
            violation = {
                'account_id': account_id,
                'account_alias': account_alias,
                'policy_id': policy_id,
                'policy_title': policy.get('TITLE', ''),
                'severity': policy.get('SEVERITY', ''),
                'status': policy.get('STATUS', ''),
                'description': policy.get('TITLE', ''),
                'remediation': policy.get('INFO_LINK', ''),
                'resource_count': len(policy_resources),
                'resources': policy_resources,
                'timestamp': datetime.now().isoformat()
            }
            
            violations.append(violation)
        
        return violations
