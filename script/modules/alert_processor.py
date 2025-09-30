"""
Alert processing functionality for Lacework Alert Reporting.
"""
import subprocess
import json
from typing import List, Dict, Any
from .cache_manager import CacheManager
from .lacework_client import LaceworkClientWrapper


class AlertProcessor:
    """Handles alert retrieval, processing, and enrichment."""
    
    def __init__(self, client_wrapper: LaceworkClientWrapper, cache_manager: CacheManager):
        """Initialize alert processor with client and cache manager."""
        self.client_wrapper = client_wrapper
        self.cache_manager = cache_manager
    
    def get_compliance_alerts(self, start_date: str, end_date: str, report_filter: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve compliance alerts from Lacework CLI.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            report_filter: Optional report name to filter by
            
        Returns:
            List of alert dictionaries
        """
        print(f"Retrieving compliance alerts from {start_date} to {end_date}...")
        
        # Build CLI command
        cmd = [
            'lacework', 'alert', 'list',
            '--start', f"{start_date}T00:00:00Z",
            '--end', f"{end_date}T23:59:59Z",
            '--json'
        ]
        
        if report_filter:
            cmd.extend(['--report', report_filter])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            alerts_data = json.loads(result.stdout)
            
            # Handle both list and dict responses
            if isinstance(alerts_data, list):
                alerts_list = alerts_data
            else:
                alerts_list = alerts_data.get('data', [])
            
            # Filter for compliance alerts
            compliance_alerts = [
                alert for alert in alerts_list
                if alert.get('derivedFields', {}).get('category') == 'Policy' and 
                   alert.get('derivedFields', {}).get('sub_category') == 'Compliance'
            ]
            
            print(f"Found {len(compliance_alerts)} compliance alerts out of {len(alerts_list)} total alerts")
            return compliance_alerts
            
        except subprocess.CalledProcessError as e:
            print(f"Error retrieving alerts: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"Error parsing alert data: {e}")
            return []
    
    def get_alert_details(self, alert_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Get detailed information for specific alerts.
        
        Args:
            alert_ids: List of alert IDs to get details for
            
        Returns:
            List of detailed alert dictionaries
        """
        if not alert_ids:
            return []
        
        print(f"Retrieving details for {len(alert_ids)} alerts...")
        
        detailed_alerts = []
        cached_count = 0
        
        for alert_id in alert_ids:
            # Check cache first
            cache_file = self.cache_manager.get_cache_file_path('alert-details', f"alert_{alert_id}")
            cached_data = self.cache_manager.load_from_cache(cache_file)
            
            if cached_data:
                detailed_alerts.append(cached_data)
                cached_count += 1
            else:
                # Get from CLI
                try:
                    cmd = ['lacework', 'alert', 'show', str(alert_id), '--json']
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    alert_data = json.loads(result.stdout)
                    
                    # Handle both direct alert data and wrapped in 'data' field
                    if alert_data.get('data'):
                        detailed_alerts.append(alert_data['data'])
                        # Cache the result
                        self.cache_manager.save_to_cache(cache_file, alert_data['data'])
                    elif alert_data.get('alertId'):
                        # Direct alert data
                        detailed_alerts.append(alert_data)
                        # Cache the result
                        self.cache_manager.save_to_cache(cache_file, alert_data)
                    else:
                        print(f"Warning: Alert {alert_id} has no data or alertId field")
                
                except subprocess.CalledProcessError as e:
                    print(f"Error retrieving alert {alert_id}: {e}")
                except json.JSONDecodeError as e:
                    print(f"Error parsing alert {alert_id} data: {e}")
        
        print(f"Found {cached_count} alerts already cached, {len(alert_ids) - cached_count} to retrieve from CLI")
        return detailed_alerts
    
    def get_policy_details(self, policy_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get policy details for the given policy IDs.
        
        Args:
            policy_ids: List of policy IDs to get details for
            
        Returns:
            Dictionary mapping policy IDs to policy details
        """
        if not policy_ids:
            return {}
        
        print(f"Retrieving details for {len(policy_ids)} policies...")
        
        policy_details = {}
        cached_count = 0
        
        for policy_id in policy_ids:
            # Check cache first
            cache_file = self.cache_manager.get_cache_file_path('policy-details', f"policy_{policy_id}")
            cached_data = self.cache_manager.load_from_cache(cache_file)
            
            if cached_data:
                policy_details[policy_id] = cached_data
                cached_count += 1
            else:
                # Get from CLI
                try:
                    cmd = ['lacework', 'policy', 'show', policy_id, '--json']
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    policy_data = json.loads(result.stdout)
                    
                    if policy_data:
                        policy_details[policy_id] = policy_data
                        # Cache the result
                        self.cache_manager.save_to_cache(cache_file, policy_data)
                
                except subprocess.CalledProcessError as e:
                    print(f"Error retrieving policy {policy_id}: {e}")
                except json.JSONDecodeError as e:
                    print(f"Error parsing policy {policy_id} data: {e}")
        
        print(f"Found {cached_count} policies already cached, {len(policy_ids) - cached_count} to retrieve from API")
        return policy_details
    
    def enrich_alerts_with_policy_details(self, alerts: List[Dict[str, Any]], policy_details: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich alerts with policy details.
        
        Args:
            alerts: List of alert dictionaries
            policy_details: Dictionary mapping policy IDs to policy details
            
        Returns:
            List of enriched alert dictionaries
        """
        enriched_alerts = []
        
        for alert in alerts:
            policy_id = alert.get('policyId')
            if policy_id and policy_id in policy_details:
                policy = policy_details[policy_id]
                
                # Extract resource, region, and account from entityMap
                resource = self._extract_resource_from_entity_map(alert.get('entityMap', {}))
                region = self._extract_region_from_entity_map(alert.get('entityMap', {}))
                account = self._extract_account_from_entity_map(alert.get('entityMap', {}))
                
                # Create enriched alert
                enriched_alert = {
                    'policy_id': policy_id,
                    'policy_title': policy.get('policy_name', policy.get('title', 'N/A')),
                    'description': policy.get('description', 'N/A'),
                    'remediation_steps': policy.get('remediation', 'N/A'),
                    'severity': alert.get('severity', 'N/A'),
                    'resource': resource,
                    'region': region,
                    'account': account,
                    'alert_status': alert.get('status', 'N/A'),
                    'alert_id': alert.get('alertId', 'N/A'),
                    'alert_type': alert.get('alertType', 'N/A'),
                    'category': alert.get('derivedFields', {}).get('category', 'N/A'),
                    'subCategory': alert.get('derivedFields', {}).get('sub_category', 'N/A'),
                    'source': alert.get('derivedFields', {}).get('source', 'N/A')
                }
                
                enriched_alerts.append(enriched_alert)
            else:
                # Extract resource, region, and account from entityMap
                resource = self._extract_resource_from_entity_map(alert.get('entityMap', {}))
                region = self._extract_region_from_entity_map(alert.get('entityMap', {}))
                account = self._extract_account_from_entity_map(alert.get('entityMap', {}))
                
                # Create alert without policy details if policy not found
                enriched_alert = {
                    'policy_id': policy_id or 'N/A',
                    'policy_title': 'N/A',
                    'description': 'N/A',
                    'remediation_steps': 'N/A',
                    'severity': alert.get('severity', 'N/A'),
                    'resource': resource,
                    'region': region,
                    'account': account,
                    'alert_status': alert.get('status', 'N/A'),
                    'alert_id': alert.get('alertId', 'N/A'),
                    'alert_type': alert.get('alertType', 'N/A'),
                    'category': alert.get('derivedFields', {}).get('category', 'N/A'),
                    'subCategory': alert.get('derivedFields', {}).get('sub_category', 'N/A'),
                    'source': alert.get('derivedFields', {}).get('source', 'N/A')
                }
                
                enriched_alerts.append(enriched_alert)
        
        return enriched_alerts
    
    def print_alert_summary(self, alerts: List[Dict[str, Any]]) -> None:
        """Print a summary table of alerts."""
        if not alerts:
            print("No alerts to display.")
            return
        
        # Create summary table
        from tabulate import tabulate
        
        summary_data = []
        for alert in alerts:
            summary_data.append([
                alert.get('alert_id', 'N/A'),
                alert.get('policy_title', 'N/A')[:50] + '...' if len(alert.get('policy_title', '')) > 50 else alert.get('policy_title', 'N/A'),
                alert.get('severity', 'N/A'),
                alert.get('alert_type', 'N/A'),
                alert.get('alert_status', 'N/A'),
                alert.get('category', 'N/A'),
                alert.get('subCategory', 'N/A'),
                alert.get('source', 'N/A')
            ])
        
        headers = ['Alert ID', 'Alert Name', 'Severity', 'Alert Type', 'Status', 'Category', 'Sub-Category', 'Source']
        print("\n=== Alert Summary Table ===")
        print(tabulate(summary_data, headers=headers, tablefmt='grid'))
    
    def _extract_resource_from_entity_map(self, entity_map: Dict[str, Any]) -> str:
        """Extract resource information from entityMap."""
        # First, look for resources in the Resource entities (compliance alerts)
        resource_entities = entity_map.get('Resource', [])
        resources = set()
        
        for resource_entity in resource_entities:
            resource_arn = resource_entity.get('KEY', {}).get('resource', '')
            if resource_arn and resource_arn.startswith('arn:'):
                resources.add(resource_arn)
        
        # If no resources found, look for security group IDs in API calls (activity alerts)
        if not resources:
            api_entities = entity_map.get('API', [])
            for api_entity in api_entities:
                props = api_entity.get('PROPS', {})
                request_params = props.get('request_parameters', {})
                
                # Extract security group IDs
                if 'groupId' in request_params:
                    group_id = request_params['groupId'].strip('"')
                    if group_id.startswith('sg-'):
                        resources.add(f"arn:aws:ec2:ap-southeast-2:339712743186:security-group/{group_id}")
                
                # Extract VPC IDs
                if 'vpcId' in request_params:
                    vpc_id = request_params['vpcId'].strip('"')
                    if vpc_id.startswith('vpc-'):
                        resources.add(f"arn:aws:ec2:ap-southeast-2:339712743186:vpc/{vpc_id}")
        
        return '\n'.join(sorted(resources)) if resources else 'N/A'
    
    def _extract_region_from_entity_map(self, entity_map: Dict[str, Any]) -> str:
        """Extract region information from entityMap."""
        # First, look for region in Resource entities (compliance alerts)
        resource_entities = entity_map.get('Resource', [])
        if resource_entities:
            region = resource_entities[0].get('KEY', {}).get('resource_region', 'N/A')
            if region != 'N/A':
                return region
        
        # Fall back to Region entities
        region_entities = entity_map.get('Region', [])
        if region_entities:
            return region_entities[0].get('KEY', {}).get('region', 'N/A')
        return 'N/A'
    
    def _extract_account_from_entity_map(self, entity_map: Dict[str, Any]) -> str:
        """Extract account information from entityMap."""
        # First, look in Resource entities (compliance alerts)
        resource_entities = entity_map.get('Resource', [])
        if resource_entities:
            account = resource_entities[0].get('KEY', {}).get('account_id', 'N/A')
            if account != 'N/A':
                return account
        
        # Look in CT_User entities (activity alerts)
        user_entities = entity_map.get('CT_User', [])
        if user_entities:
            account = user_entities[0].get('KEY', {}).get('account', 'N/A')
            if account != 'N/A':
                return account
        
        return 'N/A'
