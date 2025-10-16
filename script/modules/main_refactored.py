"""
Main orchestration logic for Lacework Alert Reporting - REFACTORED VERSION.
Optimized to minimize duplicate API calls.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Set

# Add the script directory to the path so we can import our modules
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir))

from modules.config import parse_arguments, get_date_range, load_api_credentials, get_output_filename, get_cache_directory, get_output_directory
from modules.lacework_client import LaceworkClientWrapper
from modules.cache_manager import CacheManager
from modules.alert_processor import AlertProcessor
from modules.compliance_processor import ComplianceProcessor
from modules.tag_retriever import TagRetriever
from modules.excel_generator import ExcelGenerator


def extract_arns_from_resource_field(resource: str) -> Set[str]:
    """Extract ARNs from a resource field (handles newline-separated ARNs)."""
    arns = set()
    if resource and resource != 'N/A':
        if '\n' in resource:
            for arn in resource.split('\n'):
                arn = arn.strip()
                if arn and arn.startswith('arn:'):
                    arns.add(arn)
        elif resource.startswith('arn:'):
            arns.add(resource)
    return arns


def apply_tags_to_items(items: List[Dict[str, Any]], resource_tags: Dict[str, str]):
    """Apply tags from resource_tags dict to items based on their 'resource' field."""
    for item in items:
        resource = item.get('resource', '')
        if resource and resource != 'N/A':
            # Handle multiple ARNs separated by newlines
            if '\n' in resource:
                all_tags = []
                for arn in resource.split('\n'):
                    arn = arn.strip()
                    if arn and arn.startswith('arn:'):
                        tags = resource_tags.get(arn, 'N/A')
                        if tags != 'N/A':
                            all_tags.append(tags)
                item['tags'] = '; '.join(all_tags) if all_tags else 'N/A'
            elif resource.startswith('arn:'):
                item['tags'] = resource_tags.get(resource, 'N/A')
            else:
                item['tags'] = 'N/A'
        else:
            item['tags'] = 'N/A'


def main():
    """Main function to orchestrate the Lacework alert reporting process."""
    print("\n=== Lacework Alert Reporting Tool ===")
    
    # Parse arguments
    args = parse_arguments()
    print(f"API Key: {args.api_key_file}")
    
    # Get date range
    start_date, end_date = get_date_range(args)
    print(f"Date Range: {start_date} to {end_date}")
    
    # ============================================================================
    # PHASE 1: DATA COLLECTION
    # ============================================================================
    
    # Step 1: Initialize
    print("-"*80)
    print("\033[1;36mStep 1: Initializing\033[0m")
    credentials = load_api_credentials(args.api_key_file)
    client_wrapper = LaceworkClientWrapper(credentials)
    cache_dir = get_cache_directory()
    cache_manager = CacheManager(cache_dir)
    
    if args.clear_cache:
        print("Clearing cache...")
        cache_manager.clear_cache()
    
    alert_processor = AlertProcessor(client_wrapper, cache_manager)
    compliance_processor = ComplianceProcessor(client_wrapper, cache_manager)
    tag_retriever = TagRetriever(client_wrapper, cache_manager)
    excel_generator = ExcelGenerator()
    
    # Step 2: Get alerts
    print("-"*80)
    print("\033[1;36mStep 2: Retrieving compliance alerts\033[0m")
    alerts = alert_processor.get_compliance_alerts(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d'),
        args.report
    )
    
    if not alerts:
        print("No compliance alerts found.")
        return
    
    alert_ids = [alert['alertId'] for alert in alerts]
    print(f"Found {len(alert_ids)} alert IDs: {alert_ids[:5]}...")
    detailed_alerts = alert_processor.get_alert_details(alert_ids)
    print(f"Retrieved {len(detailed_alerts)} detailed alerts")
    
    # Apply AWS account filtering if specified
    if args.aws_account:
        print(f"Filtering alerts for AWS account {args.aws_account}...")
        original_count = len(detailed_alerts)
        detailed_alerts = [
            alert for alert in detailed_alerts
            if alert.get('account') == args.aws_account
        ]
        print(f"Filtered from {original_count} to {len(detailed_alerts)} alerts")
    
    # Step 3: Get compliance reports
    compliance_data = []
    if not args.skip_compliance:
        print("-"*80)
        print("\033[1;36mStep 3: Retrieving compliance reports\033[0m")
        
        aws_accounts = compliance_processor.get_aws_accounts()
        if not aws_accounts:
            print("No AWS accounts found for compliance reporting")
        else:
            compliance_data = compliance_processor.get_compliance_data_for_accounts(
                aws_accounts, 
                args.compliance_report, 
                args.aws_account
            )
            
            if compliance_data:
                print(f"Retrieved {len(compliance_data)} compliance items")
            else:
                print("No compliance data found")
    
    # Step 4: Get all unique policy IDs (from both alerts and compliance)
    print("-"*80)
    print("\033[1;36mStep 4: Retrieving policy details\033[0m")
    
    alert_policy_ids = set(alert.get('policyId') for alert in detailed_alerts if alert.get('policyId'))
    compliance_policy_ids = set(item.get('policy_id') for item in compliance_data if item.get('policy_id'))
    all_policy_ids = list(alert_policy_ids | compliance_policy_ids)
    
    print(f"Found {len(all_policy_ids)} unique policy IDs across alerts and compliance")
    print(f"  Alert policies: {len(alert_policy_ids)}")
    print(f"  Compliance policies: {len(compliance_policy_ids)}")
    
    policy_details = alert_processor.get_policy_details(all_policy_ids)
    print(f"Retrieved {len(policy_details)} policy details")
    
    # Step 5: Get all unique resource ARNs (from both alerts and compliance)
    if not args.no_tags:
        print("-"*80)
        print("\033[1;36mStep 5: Retrieving resource tags\033[0m")
        
        all_resource_arns = set()
        
        # Extract ARNs from alerts
        for alert in detailed_alerts:
            all_resource_arns.update(extract_arns_from_resource_field(alert.get('resource', '')))
        
        # Extract ARNs from compliance
        for item in compliance_data:
            all_resource_arns.update(extract_arns_from_resource_field(item.get('resource', '')))
        
        print(f"Found {len(all_resource_arns)} unique resource ARNs across alerts and compliance")
        
        if all_resource_arns:
            resource_tags = tag_retriever.get_resource_tags_by_type(list(all_resource_arns), start_date, end_date)
        else:
            resource_tags = {}
    else:
        print("-"*80)
        print("Step 5: Skipping tag retrieval (--no-tags specified)")
        resource_tags = {}
    
    # ============================================================================
    # PHASE 2: ENRICHMENT
    # ============================================================================
    
    print("-"*80)
    print("\033[1;36mStep 6: Enriching data with policies and tags\033[0m")
    
    # Enrich alerts
    print("Enriching alerts with policy details...")
    enriched_alerts = alert_processor.enrich_alerts_with_policy_details(detailed_alerts, policy_details)
    print(f"  Enriched {len(enriched_alerts)} alerts with policy details")
    
    if not args.no_tags:
        print("Applying tags to alerts...")
        apply_tags_to_items(enriched_alerts, resource_tags)
    else:
        for alert in enriched_alerts:
            alert['tags'] = 'N/A'
    
    # Enrich compliance
    if compliance_data:
        print("Enriching compliance data with policy details...")
        for item in compliance_data:
            policy_id = item.get('policy_id')
            if policy_id and policy_id in policy_details:
                policy_info = policy_details[policy_id]
                item['policy_title'] = policy_info.get('policy_name', item.get('policy_title', 'Unknown'))
                item['description'] = policy_info.get('description', item.get('description', 'N/A'))
                item['remediation_steps'] = policy_info.get('remediation', item.get('remediation_steps', 'N/A'))
        print(f"  Enriched {len(compliance_data)} compliance items with policy details")
        
        if not args.no_tags:
            print("Applying tags to compliance items...")
            apply_tags_to_items(compliance_data, resource_tags)
        else:
            for item in compliance_data:
                item['tags'] = 'N/A'
    
    # ============================================================================
    # PHASE 3: OUTPUT
    # ============================================================================
    
    print("-"*80)
    print("\033[1;36mStep 7: Writing Excel output\033[0m")
    output_dir = get_output_directory()
    output_filename = get_output_filename(start_date, end_date, args)
    output_path = output_dir / output_filename
    
    # Create alerts sheet
    if enriched_alerts:
        excel_generator.create_alerts_sheet(enriched_alerts)
        print(f"Successfully wrote {len(enriched_alerts)} alerts to {output_path}")
    
    # Create compliance sheet
    if compliance_data:
        excel_generator.create_compliance_sheet(compliance_data)
        print(f"Successfully wrote {len(compliance_data)} compliance items to Compliance Status tab")
    
    # Save the workbook
    excel_generator.save_workbook(output_path)
    
    # Print final summary
    print("\n" + "="*80)
    print("\033[1;32m=== Final Summary ===\033[0m")
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Total alerts processed: {len(enriched_alerts)}")
    if compliance_data:
        print(f"Total compliance items: {len(compliance_data)}")
    print(f"Unique policies: {len(all_policy_ids)}")
    if not args.no_tags:
        print(f"Unique resources tagged: {len(all_resource_arns)}")
    print(f"Output file: {output_path}")
    
    # Print severity distribution
    if enriched_alerts:
        severity_counts = {}
        for alert in enriched_alerts:
            severity = alert.get('severity', 'Unknown')
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        print("\nAlert severity distribution:")
        for severity, count in sorted(severity_counts.items()):
            print(f"  {severity}: {count}")


if __name__ == "__main__":
    main()



