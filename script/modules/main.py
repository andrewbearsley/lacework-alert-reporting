"""
Optimized main orchestration using compliance-first approach with paginated inventory.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add the script directory to the path so we can import our modules
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir))

from modules.config import parse_arguments, get_date_range, load_api_credentials, get_output_filename, get_cache_directory, get_output_directory
from modules.lacework_client import LaceworkClientWrapper
from modules.cache_manager import CacheManager
from modules.compliance_processor import ComplianceProcessorV2
from modules.excel_generator import ExcelGenerator


def main():
    """Main function using optimized compliance-first approach."""
    print("\n=== Lacework Compliance Reporting Tool V2 ===")
    print("Optimized for large FortiCNP environments with paginated inventory")
    
    # Parse arguments
    args = parse_arguments()
    print(f"API Key: {args.api_key_file}")
    
    # Get date range
    start_date, end_date = get_date_range(args)
    print(f"Date Range: {start_date} to {end_date}")
    
    # Initialize components
    print("-"*80)
    print("\033[1;36mStep 1: Initializing components\033[0m")
    
    credentials = load_api_credentials(args.api_key_file)
    client_wrapper = LaceworkClientWrapper(credentials)
    cache_dir = get_cache_directory()
    cache_manager = CacheManager(cache_dir)
    
    if args.clear_cache:
        print("Clearing cache...")
        cache_manager.clear_cache()
    
    compliance_processor = ComplianceProcessorV2(client_wrapper, cache_manager)
    excel_generator = ExcelGenerator()
    
    # Process compliance report using compliance-first approach
    print("-"*80)
    print("\033[1;36mStep 2: Processing compliance report\033[0m")
    
    compliance_violations = compliance_processor.process_compliance_report(
        report_name=args.compliance_report or "AWS CIS 1.5.0",
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        aws_account_filter=args.aws_account
    )
    
    if not compliance_violations:
        print("No compliance violations found.")
        return
    
    # Flatten compliance violations for Excel output
    print("-"*80)
    print("\033[1;36mStep 3: Preparing data for Excel output\033[0m")
    
    flattened_data = flatten_compliance_violations(compliance_violations)
    print(f"Flattened {len(flattened_data)} compliance violations into {len(flattened_data)} rows")
    
    # Generate Excel output
    print("-"*80)
    print("\033[1;36mStep 4: Generating Excel report\033[0m")
    
    output_dir = get_output_directory()
    output_filename = get_output_filename(start_date, end_date, args)
    output_path = output_dir / output_filename
    
    # Create compliance violations sheet
    excel_generator.create_compliance_sheet(flattened_data)
    print(f"Successfully wrote {len(flattened_data)} compliance violations to {output_path}")
    
    # Save the workbook
    excel_generator.save_workbook(output_path)
    
    # Print final summary
    print("\n" + "="*80)
    print("\033[1;32m=== Final Summary ===\033[0m")
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Total compliance violations: {len(compliance_violations)}")
    print(f"Total violation rows: {len(flattened_data)}")
    print(f"Output file: {output_path}")
    
    # Print violation statistics
    if compliance_violations:
        print("\nViolation statistics:")
        
        # Count by account
        account_counts = {}
        severity_counts = {}
        policy_counts = {}
        
        for violation in compliance_violations:
            account_id = violation['account_id']
            severity = violation['severity']
            policy_id = violation['policy_id']
            
            account_counts[account_id] = account_counts.get(account_id, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            policy_counts[policy_id] = policy_counts.get(policy_id, 0) + 1
        
        print(f"  Accounts with violations: {len(account_counts)}")
        for account_id, count in sorted(account_counts.items()):
            print(f"    {account_id}: {count} violations")
        
        print(f"  Severity distribution:")
        for severity, count in sorted(severity_counts.items()):
            print(f"    {severity}: {count}")
        
        print(f"  Unique policies violated: {len(policy_counts)}")


def flatten_compliance_violations(compliance_violations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten compliance violations into rows suitable for Excel output.
    
    Args:
        compliance_violations: List of compliance violation objects
        
    Returns:
        List of flattened violation rows
    """
    flattened_data = []
    
    for violation in compliance_violations:
        base_violation = {
            'account_id': violation['account_id'],
            'account_alias': violation['account_alias'],
            'policy_id': violation['policy_id'],
            'policy_title': violation['policy_title'],
            'severity': violation['severity'],
            'status': violation['status'],
            'description': violation['description'],
            'remediation': violation['remediation'],
            'resource_count': violation['resource_count'],
            'timestamp': violation['timestamp']
        }
        
        # If violation has resources, create a row for each resource
        resources = violation.get('resources', [])
        if resources:
            for resource in resources:
                row = base_violation.copy()
                # Format tags for display
                tags = resource.get('tags', {})
                if isinstance(tags, dict):
                    # Format tags as key=value pairs
                    tag_pairs = [f"{k}={v}" for k, v in tags.items()]
                    tags_display = "; ".join(tag_pairs) if tag_pairs else 'N/A'
                else:
                    tags_display = str(tags) if tags else 'N/A'
                
                row.update({
                    'resource': resource.get('arn', ''),
                    'region': resource.get('region', ''),
                    'account': violation['account_alias'],
                    'tags': tags_display,
                    'tag_source': resource.get('tag_source', 'unknown'),
                    'technical_owner': resource.get('technical_owner', ''),
                    'business_owner': resource.get('business_owner', ''),
                    'environment': resource.get('environment', ''),
                    'remediation_steps': violation.get('remediation', 'N/A')
                })
                
                # Add fallback information if applicable
                if resource.get('tag_source') == 'fallback':
                    row['fallback_reason'] = resource.get('fallback_reason', '')
                flattened_data.append(row)
        else:
            # No resources, just add the violation info
            row = base_violation.copy()
            row.update({
                'resource': '',
                'region': '',
                'account': violation['account_alias'],
                'tags': 'N/A',
                'remediation_steps': violation.get('remediation', 'N/A')
            })
            flattened_data.append(row)
    
    return flattened_data


if __name__ == "__main__":
    main()
