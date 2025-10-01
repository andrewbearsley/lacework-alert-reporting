"""
Main orchestration logic for Lacework Alert Reporting.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any

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


def main():
    """Main function to orchestrate the Lacework alert reporting process."""
    print("=== Lacework Alert Reporting Tool ===")
    
    # Parse arguments
    args = parse_arguments()
    print(f"API Key: {args.api_key_file}")
    
    # Get date range
    start_date, end_date = get_date_range(args)
    print(f"Date Range: {start_date} to {end_date}")
    
    # Load API credentials
    print("Step 1: Loading API credentials...")
    credentials = load_api_credentials(args.api_key_file)
    
    # Initialize components
    print("Step 2: Initializing Lacework client...")
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
    
    # Get compliance alerts
    print("Step 3: Retrieving compliance alerts...")
    alerts = alert_processor.get_compliance_alerts(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d'),
        args.report
    )
    
    if not alerts:
        print("No compliance alerts found.")
        return
    
    # Process alert details
    print("Step 4: Processing alert details...")
    alert_ids = [alert['alertId'] for alert in alerts]
    print(f"Found {len(alert_ids)} alert IDs: {alert_ids[:5]}...")
    detailed_alerts = alert_processor.get_alert_details(alert_ids)
    print(f"Retrieved {len(detailed_alerts)} detailed alerts")
    
    # Get policy details
    print("Step 5: Retrieving policy details...")
    policy_ids = list(set(alert.get('policyId') for alert in detailed_alerts if alert.get('policyId')))
    print(f"Found {len(policy_ids)} unique policy IDs: {policy_ids[:5]}...")
    policy_details = alert_processor.get_policy_details(policy_ids)
    print(f"Retrieved {len(policy_details)} policy details")
    
    # Enrich alerts with policy details
    print("Step 6: Enriching alerts with policy details...")
    print(f"Detailed alerts count: {len(detailed_alerts)}")
    print(f"Policy details count: {len(policy_details)}")
    enriched_alerts = alert_processor.enrich_alerts_with_policy_details(detailed_alerts, policy_details)
    print(f"Enriched alerts count: {len(enriched_alerts)}")
    
    # Apply AWS account filtering if specified
    if args.aws_account:
        print(f"Step 6.1: Filtering alerts for AWS account {args.aws_account}...")
        original_count = len(enriched_alerts)
        enriched_alerts = [
            alert for alert in enriched_alerts
            if alert.get('account') == args.aws_account
        ]
        print(f"Filtered from {original_count} to {len(enriched_alerts)} alerts for account {args.aws_account}")
    
    # Print alert summary
    alert_processor.print_alert_summary(enriched_alerts)
    
    # Get resource tags for alerts (unless disabled)
    if enriched_alerts and not args.no_tags:
        print("Step 6.5: Retrieving resource tags for alerts...")
        alert_resource_arns = set()
        for alert in enriched_alerts:
            resource = alert.get('resource', '')
            if resource and resource != 'N/A':
                # Handle multiple ARNs separated by newlines
                if '\n' in resource:
                    for arn in resource.split('\n'):
                        if arn.strip() and arn.strip().startswith('arn:'):
                            alert_resource_arns.add(arn.strip())
                elif resource.startswith('arn:'):
                    alert_resource_arns.add(resource)
        
        if alert_resource_arns:
            print(f"Retrieving tags for {len(alert_resource_arns)} unique alert resources...")
            alert_resource_tags = tag_retriever.get_resource_tags_by_type(list(alert_resource_arns), start_date, end_date)
            
            for i, alert in enumerate(enriched_alerts):
                resource = alert.get('resource', '')
                if resource and resource != 'N/A':
                    # Handle multiple ARNs separated by newlines
                    if '\n' in resource:
                        all_tags = []
                        for arn in resource.split('\n'):
                            if arn.strip() and arn.strip().startswith('arn:'):
                                tags = alert_resource_tags.get(arn.strip(), 'N/A')
                                if tags != 'N/A':
                                    all_tags.append(tags)
                        alert['tags'] = '; '.join(all_tags) if all_tags else 'N/A'
                    elif resource.startswith('arn:'):
                        alert['tags'] = alert_resource_tags.get(resource, 'N/A')
                    else:
                        alert['tags'] = 'N/A'
                else:
                    alert['tags'] = 'N/A'
        else:
            for alert in enriched_alerts:
                alert['tags'] = 'N/A'
    elif enriched_alerts and args.no_tags:
        print("Step 6.5: Skipping tag retrieval (--no-tags specified)")
        for alert in enriched_alerts:
            alert['tags'] = 'N/A'
    
    # Get compliance status (unless skipped)
    compliance_data = []
    if not args.skip_compliance:
        print("Step 7: Retrieving compliance status...")
        
        # Get AWS accounts
        aws_accounts = compliance_processor.get_aws_accounts()
        if not aws_accounts:
            print("No AWS accounts found for compliance reporting")
        else:
            # Get compliance data for all accounts
            compliance_data = compliance_processor.get_compliance_data_for_accounts(
                aws_accounts, 
                args.compliance_report, 
                args.aws_account
            )
            
            if compliance_data:
                print(f"Retrieved {len(compliance_data)} compliance items")
                
                # Get policy details for compliance items
                compliance_policy_ids = list(set(item.get('policy_id') for item in compliance_data if item.get('policy_id')))
                if compliance_policy_ids:
                    print(f"Retrieving policy details for {len(compliance_policy_ids)} compliance policies...")
                    compliance_policy_details = alert_processor.get_policy_details(compliance_policy_ids)
                    
                    # Enrich compliance data with policy details
                    for item in compliance_data:
                        policy_id = item.get('policy_id')
                        if policy_id and policy_id in compliance_policy_details:
                            policy_info = compliance_policy_details[policy_id]
                            item['policy_title'] = policy_info.get('policy_name', item.get('policy_title', 'Unknown'))
                            item['description'] = policy_info.get('description', item.get('description', 'N/A'))
                            item['remediation_steps'] = policy_info.get('remediation', item.get('remediation_steps', 'N/A'))
            else:
                print("No compliance data found")
    
    # Get resource tags for compliance data (unless disabled)
    if compliance_data and not args.no_tags:
        print("Step 7: Retrieving resource tags...")
        # Extract all unique resource ARNs from compliance data
        resource_arns = set()
        for item in compliance_data:
            resource = item.get('resource', '')
            if resource and resource.startswith('arn:'):
                # Handle multiple resources (newlines) by splitting and adding each ARN
                if '\n' in resource:
                    for arn in resource.split('\n'):
                        arn = arn.strip()
                        if arn and arn.startswith('arn:'):
                            resource_arns.add(arn)
                else:
                    resource_arns.add(resource)
        
        if resource_arns:
            print(f"Retrieving tags for {len(resource_arns)} unique resources...")
            print("Starting tag retrieval process...")
            resource_tags = tag_retriever.get_resource_tags_by_type(list(resource_arns), start_date, end_date)
            print("Tag retrieval completed, processing results...")
            
            # Add tags to compliance data
            s3_count = 0
            s3_with_tags = 0
            for item in compliance_data:
                resource = item.get('resource', '')
                if ':s3:' in resource:
                    s3_count += 1
                
                if resource and resource.startswith('arn:'):
                    # Handle multiple resources by combining their tags
                    if '\n' in resource:
                        all_tags = []
                        for arn in resource.split('\n'):
                            arn = arn.strip()
                            if arn and arn.startswith('arn:'):
                                tags = resource_tags.get(arn, 'N/A')
                                if tags != 'N/A':
                                    all_tags.append(tags)
                        
                        if all_tags:
                            item['tags'] = ' | '.join(all_tags)
                        else:
                            item['tags'] = 'N/A'
                    else:
                        item['tags'] = resource_tags.get(resource, 'N/A')
                        if ':s3:' in resource:
                            if resource_tags.get(resource, 'N/A') != 'N/A':
                                s3_with_tags += 1
                            elif s3_count <= 3:  # Debug first 3
                                print(f"DEBUG S3: {resource}")
                                print(f"  In resource_tags: {resource in resource_tags}")
                                print(f"  Value: {resource_tags.get(resource, 'NOT FOUND')}")
                else:
                    item['tags'] = 'N/A'
            
            print("Compliance data tag processing completed.")
            if s3_count > 0:
                print(f"DEBUG: S3 buckets processed: {s3_count}, with tags: {s3_with_tags}")
        else:
            print("No resource ARNs found in compliance data")
            # Add N/A tags to all items
            for item in compliance_data:
                item['tags'] = 'N/A'
    elif compliance_data and args.no_tags:
        print("Step 7: Skipping tag retrieval (--no-tags specified)")
        # Add N/A tags to all items
        for item in compliance_data:
            item['tags'] = 'N/A'
    
    # Generate Excel report
    print("Step 8: Writing Excel output...")
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
    print("\n=== Final Summary ===")
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Total alerts processed: {len(enriched_alerts)}")
    if compliance_data:
        print(f"Total compliance items: {len(compliance_data)}")
    print(f"Unique policies: {len(policy_ids)}")
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
    
    if compliance_data:
        severity_counts = {}
        for item in compliance_data:
            severity = item.get('severity', 'Unknown')
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        print("\nCompliance severity distribution:")
        for severity, count in sorted(severity_counts.items()):
            print(f"  {severity}: {count}")
    
    print("\nLacework reporting analysis complete!")


if __name__ == "__main__":
    main()

