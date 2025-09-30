"""
Compliance processing functionality for Lacework Alert Reporting.
"""
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

from .cache_manager import CacheManager
from .lacework_client import LaceworkClientWrapper


class ComplianceProcessor:
    """Handles compliance report retrieval and processing."""
    
    def __init__(self, client_wrapper: LaceworkClientWrapper, cache_manager: CacheManager):
        """Initialize compliance processor with client and cache manager."""
        self.client_wrapper = client_wrapper
        self.cache_manager = cache_manager
    
    def get_aws_accounts(self) -> List[Dict[str, Any]]:
        """Get configured AWS accounts."""
        try:
            # Use the client wrapper to get AWS accounts
            accounts_data = self.client_wrapper.get_aws_accounts()
            
            if accounts_data and 'data' in accounts_data:
                accounts = []
                for account in accounts_data['data']:
                    # Extract account ID from the data structure
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
                
                # Filter to only enabled accounts for compliance reporting
                enabled_accounts = [acc for acc in accounts if acc['enabled'] == 1]
                print(f"Found {len(accounts)} total AWS accounts ({len(enabled_accounts)} enabled)")
                return enabled_accounts
            else:
                print(f"No AWS accounts found in response. Data structure: {accounts_data}")
                return []
                
        except Exception as e:
            print(f"Error retrieving AWS accounts: {e}")
            return []
    
    def get_compliance_report(self, account_id: str, report_name: str = None) -> Dict[str, Any]:
        """Get compliance report for a specific AWS account with non-compliant resources."""
        
        # Create cache filename that includes both account ID and report name
        if report_name:
            report_suffix = report_name.lower().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '').replace(':', '').replace('.', '')
            cache_suffix = f"compliance_{account_id}_{report_suffix}"
        else:
            cache_suffix = f"compliance_{account_id}_default"
        
        cache_file = self.cache_manager.get_cache_file_path('compliance-reports', cache_suffix)
        
        # Check if cache file exists and is less than 24 hours old
        cached_data = self.cache_manager.load_from_cache(cache_file)
        if cached_data:
            return cached_data
        
        try:
            # Get credentials from client wrapper
            credentials = self.client_wrapper.credentials
            
            # Set up environment variables for Lacework CLI authentication
            env = os.environ.copy()
            env['LW_ACCOUNT'] = credentials.get('account', '')
            env['LW_API_KEY'] = credentials.get('keyId', '')
            env['LW_API_SECRET'] = credentials.get('secret', '')
            
            # Build command to get compliance report
            cmd = [
                "lacework", "compliance", "aws", "get-report", account_id,
                "--status", "non-compliant",
                "--json",
                "--api_key", credentials.get('keyId', ''),
                "--api_secret", credentials.get('secret', ''),
                "--account", credentials.get('account', '')
            ]
            
            # Add report name filter if specified
            if report_name:
                cmd.extend(["--report_name", report_name])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
            
            if result.returncode == 0:
                compliance_data = json.loads(result.stdout)
                
                # Cache the result
                self.cache_manager.save_to_cache(cache_file, compliance_data)
                print(f"Cached compliance report: {cache_file}")
                
                return compliance_data
            else:
                print(f"CLI error retrieving compliance report: {result.stderr}")
                return {}
        
        except subprocess.TimeoutExpired:
            print("CLI timeout retrieving compliance report")
            return {}
        except json.JSONDecodeError as e:
            print(f"JSON parsing error retrieving compliance report: {e}")
            return {}
        except Exception as e:
            print(f"Error retrieving compliance report: {e}")
            return {}
    
    def parse_compliance_report_data(self, compliance_data: Dict[str, Any], policy_details: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse compliance report data and extract relevant fields for Excel output."""
        compliance_items = []
        
        # Handle the actual Lacework compliance report format
        if 'recommendations' in compliance_data and isinstance(compliance_data['recommendations'], list):
            items = compliance_data['recommendations']
            recommendations_count = len(items)
        elif 'data' in compliance_data:
            report_data = compliance_data['data']
            
            # Handle different compliance report formats
            if isinstance(report_data, list):
                # Direct list of compliance items
                items = report_data
                recommendations_count = len(items)
            elif isinstance(report_data, dict) and 'recommendations' in report_data:
                # Format with recommendations array
                items = report_data['recommendations']
                recommendations_count = len(items)
            elif isinstance(report_data, dict) and 'violations' in report_data:
                # Format with violations array
                items = report_data['violations']
                recommendations_count = len(items)
            else:
                print(f"Unknown compliance report format: {type(report_data)}")
                return compliance_items
            
        else:
            print("No recommendations or data found in compliance report")
            return compliance_items
        
        print(f"Processing {recommendations_count} compliance recommendations...")
        
        for item in items:
            # Extract policy information
            policy_id = item.get('policyId', item.get('REC_ID', 'Unknown'))
            policy_info = policy_details.get(policy_id, {})
            
            # Skip if policy is not a compliance policy
            if policy_info.get('status') == 'Skipped':
                continue
            
            # Extract account information
            account_id = item.get('accountId', item.get('ACCOUNT_ID', 'Unknown'))
            account_alias = item.get('accountAlias', item.get('ACCOUNT_ALIAS', ''))
            
            # Format account information
            if account_alias:
                account = f"{account_id} ({account_alias})"
            else:
                account = account_id
            
            # Extract compliance status
            status = item.get('status', item.get('STATUS', 'Non-Compliant'))
            
            # Handle violations array - each violation is a separate compliance item
            violations = item.get('VIOLATIONS', [])
            if violations:
                for violation in violations:
                    # Extract resource information from violation
                    resource_arn = violation.get('resource', 'Unknown')
                    region = violation.get('region', 'Unknown')
                    
                    # Format resource with account information
                    if resource_arn != 'Unknown' and resource_arn.startswith('arn:aws:'):
                        if account_alias:
                            resource_arn += f" (Account: {account_id}, Alias: {account_alias})"
                        elif account_id != 'Unknown':
                            resource_arn += f" (Account: {account_id})"
                    
                    # Use compliance report severity (numeric) over policy cache severity (text)
                    compliance_severity = item.get('SEVERITY', 'Unknown')
                    if compliance_severity != 'Unknown':
                        severity = self._map_compliance_severity(compliance_severity)
                    else:
                        severity = self._map_compliance_severity(policy_info.get('severity', 'Unknown'))
                    
                    compliance_item = {
                        'policy_id': policy_id,
                        'policy_title': policy_info.get('policy_name', item.get('TITLE', 'Unknown')),
                        'description': policy_info.get('description', item.get('TITLE', 'N/A')),
                        'remediation_steps': policy_info.get('remediation', 'N/A'),
                        'severity': severity,
                        'resource': resource_arn,
                        'region': region,
                        'account': account,
                        'compliance_status': status,
                        'raw_data': item
                    }
                    
                    compliance_items.append(compliance_item)
            else:
                # No violations, but still create a compliance item for the policy
                compliance_item = {
                    'policy_id': policy_id,
                    'policy_title': policy_info.get('policy_name', item.get('TITLE', 'Unknown')),
                    'description': policy_info.get('description', item.get('TITLE', 'N/A')),
                    'remediation_steps': policy_info.get('remediation', 'N/A'),
                    'severity': self._map_compliance_severity(policy_info.get('severity', item.get('SEVERITY', 'Unknown'))),
                    'resource': account_id,  # Use account ID as resource if no specific resource
                    'region': 'Unknown',
                    'account': account,
                    'compliance_status': status,
                    'raw_data': item
                }
                
                compliance_items.append(compliance_item)
        
        print(f"Parsed {len(compliance_items)} compliance items from {recommendations_count} recommendations")
        return compliance_items
    
    def get_compliance_data_for_accounts(self, accounts: List[Dict[str, Any]], report_name: str = None, aws_account_filter: str = None) -> List[Dict[str, Any]]:
        """Get compliance data for multiple AWS accounts."""
        all_compliance_data = []
        
        # Filter accounts if specific AWS account is requested
        if aws_account_filter:
            accounts = [acc for acc in accounts if acc['account_id'] == aws_account_filter]
            print(f"Filtered to {len(accounts)} accounts matching {aws_account_filter}")
        
        for account in accounts:
            account_id = account['account_id']
            account_alias = account.get('account_alias', '')
            
            print(f"Processing compliance report for account {account_id} ({account_alias})...")
            
            # Get compliance report for this account
            compliance_data = self.get_compliance_report(account_id, report_name)
            
            if compliance_data:
                # Parse the compliance data
                # Note: We need policy details to parse compliance data properly
                # For now, we'll create a basic structure
                compliance_items = self._parse_compliance_data_basic(compliance_data, account_id, account_alias)
                all_compliance_data.extend(compliance_items)
            else:
                print(f"No compliance data found for account {account_id}")
        
        return all_compliance_data
    
    def _map_compliance_severity(self, severity_value: Any) -> str:
        """Map numeric severity from compliance reports to text labels."""
        severity_map = {
            '1': 'Critical',
            '2': 'High', 
            '3': 'Medium',
            '4': 'Low',
            '5': 'Info',
            '6': 'Info',  # Additional severity levels map to Info
            '0': 'Info',  # Some systems use 0 for informational
            '': 'Info',   # Empty severity defaults to Info
            None: 'Info'  # None severity defaults to Info
        }
        return severity_map.get(str(severity_value), 'Info')
    
    def _parse_compliance_data_basic(self, compliance_data: Dict[str, Any], account_id: str, account_alias: str) -> List[Dict[str, Any]]:
        """Basic parsing of compliance data without policy details."""
        compliance_items = []
        
        # Handle the actual Lacework compliance report format
        if 'recommendations' in compliance_data and isinstance(compliance_data['recommendations'], list):
            items = compliance_data['recommendations']
        elif 'data' in compliance_data:
            report_data = compliance_data['data']
            
            # Handle different compliance report formats
            if isinstance(report_data, list):
                items = report_data
            elif isinstance(report_data, dict) and 'recommendations' in report_data:
                items = report_data['recommendations']
            elif isinstance(report_data, dict) and 'violations' in report_data:
                items = report_data['violations']
            else:
                print(f"Unknown compliance report format: {type(report_data)}")
                return compliance_items
        else:
            print("No recommendations or data found in compliance report")
            return compliance_items
        
        for item in items:
            # Extract policy information
            policy_id = item.get('policyId', item.get('REC_ID', 'Unknown'))
            
            # Extract account information
            account_alias = item.get('accountAlias', item.get('ACCOUNT_ALIAS', account_alias))
            
            # Format account information
            if account_alias:
                account = f"{account_id} ({account_alias})"
            else:
                account = account_id
            
            # Extract compliance status
            status = item.get('status', item.get('STATUS', 'Non-Compliant'))
            
            # Handle violations array - each violation is a separate compliance item
            violations = item.get('VIOLATIONS', [])
            if violations:
                for violation in violations:
                    # Extract resource information from violation
                    resource_arn = violation.get('resource', 'Unknown')
                    region = violation.get('region', 'Unknown')
                    
                    # Use compliance report severity (numeric)
                    compliance_severity = item.get('SEVERITY', 'Unknown')
                    severity = self._map_compliance_severity(compliance_severity) if compliance_severity != 'Unknown' else 'Unknown'
                    
                    compliance_item = {
                        'policy_id': policy_id,
                        'policy_title': item.get('TITLE', 'Unknown'),
                        'description': item.get('TITLE', 'N/A'),
                        'remediation_steps': 'N/A',  # Will be filled in later with policy details
                        'severity': severity,
                        'resource': resource_arn,
                        'region': region,
                        'account': account,
                        'compliance_status': status,
                        'raw_data': item
                    }
                    
                    compliance_items.append(compliance_item)
            else:
                # No violations, but still create a compliance item for the policy
                compliance_item = {
                    'policy_id': policy_id,
                    'policy_title': item.get('TITLE', 'Unknown'),
                    'description': item.get('TITLE', 'N/A'),
                    'remediation_steps': 'N/A',  # Will be filled in later with policy details
                    'severity': self._map_compliance_severity(item.get('SEVERITY', 'Unknown')),
                    'resource': account_id,  # Use account ID as resource if no specific resource
                    'region': 'Unknown',
                    'account': account,
                    'compliance_status': status,
                    'raw_data': item
                }
                
                compliance_items.append(compliance_item)
        
        return compliance_items
