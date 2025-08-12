#!/usr/bin/env python3
"""
Compliance-Based Lacework Framework Mapping Script

This script performs the complete workflow using compliance reports:
1. Retrieves the report definition for 'UNSW AWS Cyber Security Standards'
2. Extracts unique policy IDs from the report definition
3. Retrieves policy details (with caching and 429 handling)
4. Gets list of AWS accounts from cloud integrations
5. For each AWS account, fetches the most recent compliance report (with caching)
6. Extracts compliant/non-compliant stats per policy from reports
7. Writes comprehensive output to CSV
"""

import json
import csv
import os
import sys
import time
import re
import subprocess
import hashlib
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set, List, Dict, Optional

try:
    from laceworksdk import LaceworkClient
except ImportError:
    print("Error: laceworksdk not installed. Please install it with: pip install laceworksdk")
    sys.exit(1)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Extract compliance data from Lacework custom framework',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python compliance_framework_mapping.py -r "UNSW AWS Cyber Security Standards" -k api-key/unsw-lw-api-key.json
  python compliance_framework_mapping.py --report-name "My Custom Framework" --api-key-file api-key/my-key.json
        """
    )
    
    parser.add_argument(
        '-r', '--report-name',
        required=True,
        help='Name of the Lacework report definition (e.g., "UNSW AWS Cyber Security Standards")'
    )
    
    parser.add_argument(
        '-k', '--api-key-file',
        required=True,
        help='Path to the Lacework API key JSON file (e.g., api-key/unsw-lw-api-key.json)'
    )
    
    return parser.parse_args()


def generate_filename_from_report_name(report_name: str) -> str:
    """Generate a filename-safe string from report name (lowercase, spaces and slashes to underscores)."""
    return report_name.lower().replace(' ', '_').replace('/', '_')


def load_api_credentials(api_key_file):
    """Load API credentials from JSON file."""
    try:
        with open(api_key_file, 'r') as f:
            credentials = json.load(f)
        return credentials
    except FileNotFoundError:
        print(f"Error: API key file not found: {api_key_file}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in API key file: {api_key_file}")
        sys.exit(1)


def find_report_definition_by_name(client, report_name):
    """Find a report definition by name."""
    try:
        response = client.report_definitions.get()
        
        if 'data' not in response:
            print("Error: No data returned from report definitions API")
            return None
        
        report_definitions = response['data']
        
        for report_def in report_definitions:
            if report_def.get('reportName') == report_name:
                return report_def
        
        print(f"Report definition '{report_name}' not found.")
        print("\nAvailable report definitions:")
        for report_def in report_definitions:
            print(f"  - {report_def.get('reportName', 'Unknown')}")
        
        return None
        
    except Exception as e:
        print(f"Error retrieving report definitions: {e}")
        return None


def save_report_definition(report_definition, cache_dir, report_filename):
    """Save report definition to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{report_filename}.json"
    
    try:
        with open(cache_file, 'w') as f:
            json.dump(report_definition, f, indent=2, sort_keys=True)
        print(f"Report definition saved to: {cache_file}")
        return cache_file
    except Exception as e:
        print(f"Error saving report definition: {e}")
        return None


def load_report_definition_from_cache(cache_file):
    """Load report definition from cache if available."""
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Error reading cached report definition: {e}")
    return None


def extract_unique_policy_ids(report_definition):
    """Extract unique policy IDs from the report definition."""
    policy_ids = set()
    
    if 'reportDefinition' in report_definition and 'sections' in report_definition['reportDefinition']:
        sections = report_definition['reportDefinition']['sections']
        
        for section in sections:
            if 'policies' in section:
                for policy_id in section['policies']:
                    policy_ids.add(policy_id)
    
    return sorted(list(policy_ids))


def load_policy_from_cache(cache_dir: Path, policy_id: str) -> Optional[Dict]:
    """Load policy details from cache if available."""
    cache_file = cache_dir / f"{policy_id}.json"
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Error reading cache file for {policy_id}: {e}")
    return None


def save_policy_to_cache(cache_dir: Path, policy_id: str, policy_data: Dict) -> None:
    """Save policy details to cache."""
    cache_file = cache_dir / f"{policy_id}.json"
    try:
        with open(cache_file, 'w') as f:
            json.dump(policy_data, f, indent=2)
    except IOError as e:
        print(f"Warning: Error writing cache file for {policy_id}: {e}")


def api_call_with_retry(func, *args, max_retries: int = 3, **kwargs):
    """Generic API call wrapper with retry logic for 429 errors."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        
        except Exception as e:
            error_str = str(e)
            
            # Check for HTTP 429 (Too Many Requests)
            if "429" in error_str or "Too Many Requests" in error_str:
                if attempt < max_retries - 1:
                    # Try to extract Retry-After header value
                    retry_after = 60  # Default backoff
                    
                    if "Retry-After" in error_str:
                        try:
                            match = re.search(r'Retry-After[:\s]+(\d+)', error_str)
                            if match:
                                retry_after = int(match.group(1))
                        except:
                            pass
                    
                    print(f"  Rate limited (429). Waiting {retry_after} seconds before retry {attempt + 1}/{max_retries}...")
                    time.sleep(retry_after)
                    continue
            
            # For other errors or final attempt, re-raise
            if attempt == max_retries - 1:
                raise e
            else:
                print(f"  Error on attempt {attempt + 1}: {e}. Retrying...")
                time.sleep(2 ** attempt)  # Exponential backoff


def get_policy_details_with_retry(client, policy_id: str, cache_dir: Path) -> Dict:
    """Retrieve policy details with caching and retry logic."""
    # First, try to load from cache
    cached_policy = load_policy_from_cache(cache_dir, policy_id)
    if cached_policy:
        print(f"  Using cached data for {policy_id}")
        return cached_policy
    
    # If not in cache, retrieve from API with retry logic
    try:
        response = api_call_with_retry(client.policies.get_by_id, policy_id)
        
        if 'data' in response:
            policy_data = response['data']
            result = {
                'policy_id': policy_id,
                'policy_name': policy_data.get('title', 'Unknown'),
                'severity': policy_data.get('severity', 'Unknown'),
                'status': 'Enabled' if policy_data.get('enabled', False) else 'Disabled',
                'policy_type': policy_data.get('policyType', 'Unknown'),
                'raw_data': policy_data
            }
            
            save_policy_to_cache(cache_dir, policy_id, result)
            return result
        else:
            print(f"Warning: No data returned for policy ID: {policy_id}")
            result = {
                'policy_id': policy_id,
                'policy_name': 'Not Found',
                'severity': 'Unknown',
                'status': 'Unknown',
                'policy_type': 'Unknown'
            }
            save_policy_to_cache(cache_dir, policy_id, result)
            return result
    
    except Exception as e:
        print(f"Error retrieving policy {policy_id}: {e}")
        result = {
            'policy_id': policy_id,
            'policy_name': 'Error',
            'severity': 'Unknown',
            'status': 'Unknown',
            'policy_type': 'Unknown'
        }
        save_policy_to_cache(cache_dir, policy_id, result)
        return result


def get_aws_accounts(client):
    """Get list of AWS accounts from cloud integrations."""
    try:
        print("  Retrieving AWS cloud account integrations...")
        # Get AWS configuration integrations
        response = api_call_with_retry(client.cloud_accounts.get, type="AwsCfg")
        
        aws_accounts = []
        if 'data' in response:
            for integration in response['data']:
                if integration.get('enabled') and 'data' in integration:
                    account_id = integration['data'].get('awsAccountId')
                    if account_id:
                        aws_accounts.append({
                            'account_id': account_id,
                            'integration_name': integration.get('name', 'Unknown'),
                            'integration_guid': integration.get('intgGuid', '')
                        })
        
        print(f"  Found {len(aws_accounts)} AWS accounts")
        return aws_accounts
        
    except Exception as e:
        print(f"Error retrieving AWS accounts: {e}")
        return []


def load_compliance_report_from_cache(cache_dir: Path, account_id: str, report_identifier: str) -> Optional[Dict]:
    """Load compliance report from cache if available."""
    # Use a hash of the report identifier to create a shorter filename
    import hashlib
    report_hash = hashlib.md5(report_identifier.encode()).hexdigest()[:8]
    cache_file = cache_dir / f"{account_id}_{report_hash}.json"
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Error reading cached report for {account_id}: {e}")
    return None


def save_compliance_report_to_cache(cache_dir: Path, account_id: str, report_identifier: str, report_data: Dict) -> None:
    """Save compliance report to cache."""
    import hashlib
    report_hash = hashlib.md5(report_identifier.encode()).hexdigest()[:8]
    cache_file = cache_dir / f"{account_id}_{report_hash}.json"
    try:
        with open(cache_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        print(f"  Cached report for account {account_id}")
    except IOError as e:
        print(f"Warning: Error writing cache file for {account_id}: {e}")


def get_compliance_report_via_cli(account_id: str, report_name: str, cache_dir: Path, credentials: Dict) -> Optional[Dict]:
    """Get compliance report using Lacework CLI as fallback with rate limiting."""
    max_retries = 3
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"  Retry attempt {attempt + 1}/{max_retries} for account {account_id}...")
            else:
                print(f"  Fetching compliance report via CLI for account {account_id}...")
            
            # Run the lacework CLI command with explicit credentials
            cmd = [
                "lacework", "compliance", "aws", "get-report", account_id,
                "--report_name", report_name,
                "--details", "--json"
            ]
            
            # Set up environment variables for Lacework CLI authentication
            env = os.environ.copy()
            env['LW_ACCOUNT'] = credentials.get('account', '')
            env['LW_API_KEY'] = credentials.get('keyId', '')
            env['LW_API_SECRET'] = credentials.get('secret', '')
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
            
            if result.returncode == 0:
                # Parse the JSON output
                report_data = json.loads(result.stdout)
                
                # Save to cache
                report_hash = hashlib.md5(report_name.encode()).hexdigest()[:8]
                save_compliance_report_to_cache(cache_dir, account_id, report_hash, report_data)
                
                return report_data
            else:
                # Check if this is a rate limiting error
                stderr_lower = result.stderr.lower()
                if '429' in stderr_lower or 'rate limit' in stderr_lower or 'too many requests' in stderr_lower:
                    if attempt < max_retries - 1:
                        # Extract retry-after if available, otherwise use exponential backoff
                        retry_after = None
                        for line in result.stderr.split('\n'):
                            if 'retry-after' in line.lower():
                                try:
                                    retry_after = int(re.search(r'\d+', line).group())
                                except:
                                    pass
                        
                        delay = retry_after if retry_after else base_delay * (2 ** attempt)
                        print(f"  Rate limited (429). Waiting {delay} seconds before retry...")
                        time.sleep(delay)
                        continue
                    else:
                        print(f"  Rate limited (429) - max retries exceeded for account {account_id}")
                        return None
                else:
                    print(f"  CLI error for account {account_id}: {result.stderr}")
                    return None
                
        except subprocess.TimeoutExpired:
            print(f"  CLI timeout for account {account_id}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"  Waiting {delay} seconds before retry...")
                time.sleep(delay)
                continue
            return None
        except json.JSONDecodeError as e:
            print(f"  JSON parsing error for account {account_id}: {e}")
            return None
        except Exception as e:
            print(f"  CLI execution error for account {account_id}: {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"  Waiting {delay} seconds before retry...")
                time.sleep(delay)
                continue
            return None
    
    return None


def get_compliance_report_for_account(account_id: str, report_name: str, cache_dir: Path, credentials: Dict) -> Optional[Dict]:
    """Get compliance report for a specific AWS account using CLI only (SDK doesn't support custom frameworks)."""
    report_hash = hashlib.md5(report_name.encode()).hexdigest()[:8]
    
    # Try to load from cache first
    cached_report = load_compliance_report_from_cache(cache_dir, account_id, report_hash)
    if cached_report:
        print(f"  Using cached report for account {account_id}")
        return cached_report
    
    # Use CLI directly (SDK doesn't support custom report definitions)
    return get_compliance_report_via_cli(account_id, report_name, cache_dir, credentials)


def extract_policy_compliance_stats(report_data: Dict, policy_ids: List[str]) -> Dict[str, Dict]:
    """Extract compliance statistics for each policy from the report data (CLI format)."""
    policy_stats = {}
    
    # Initialize all policies with zero counts
    for policy_id in policy_ids:
        policy_stats[policy_id] = {
            'compliant': 0,
            'non_compliant': 0,
            'could_not_assess': 0,
            'total_resources': 0
        }
    
    try:
        # Handle CLI JSON format - recommendations are directly in the root
        if 'recommendations' in report_data:
            recommendations = report_data['recommendations']
            for rec in recommendations:
                # Use REC_ID field from CLI output
                policy_id = rec.get('REC_ID', '')
                if policy_id in policy_stats:
                    status = rec.get('STATUS', '').lower()
                    resource_count = int(rec.get('RESOURCE_COUNT', 0))
                    assessed_count = int(rec.get('ASSESSED_RESOURCE_COUNT', 0))
                    
                    # Map CLI status values to our categories
                    if status == 'compliant':
                        policy_stats[policy_id]['compliant'] += assessed_count
                    elif status == 'noncompliant' or status == 'non-compliant':
                        policy_stats[policy_id]['non_compliant'] += resource_count
                    elif status in ['requiresmanualassessment', 'requires_manual_assessment', 'couldnotassess', 'could_not_assess']:
                        policy_stats[policy_id]['could_not_assess'] += assessed_count
                    
                    # Use assessed count as total (this is what was actually evaluated)
                    policy_stats[policy_id]['total_resources'] += assessed_count
        
        # Also handle nested data format (fallback)
        elif 'data' in report_data and 'recommendations' in report_data['data']:
            recommendations = report_data['data']['recommendations']
            for rec in recommendations:
                policy_id = rec.get('REC_ID', '')
                if policy_id in policy_stats:
                    status = rec.get('STATUS', '').lower()
                    resource_count = int(rec.get('RESOURCE_COUNT', 0))
                    assessed_count = int(rec.get('ASSESSED_RESOURCE_COUNT', 0))
                    
                    if status == 'compliant':
                        policy_stats[policy_id]['compliant'] += assessed_count
                    elif status == 'noncompliant' or status == 'non-compliant':
                        policy_stats[policy_id]['non_compliant'] += resource_count
                    elif status in ['requiresmanualassessment', 'requires_manual_assessment', 'couldnotassess', 'could_not_assess']:
                        policy_stats[policy_id]['could_not_assess'] += assessed_count
                    
                    policy_stats[policy_id]['total_resources'] += assessed_count
    
    except Exception as e:
        print(f"  Error extracting policy stats from report: {e}")
        print(f"  Report data keys: {list(report_data.keys()) if isinstance(report_data, dict) else 'Not a dict'}")
    
    return policy_stats


def aggregate_policy_compliance_across_accounts(all_account_stats: Dict[str, Dict]) -> Dict[str, Dict]:
    """Aggregate compliance statistics across all AWS accounts for each policy."""
    aggregated_stats = {}
    
    # Get all unique policy IDs
    all_policy_ids = set()
    for account_stats in all_account_stats.values():
        all_policy_ids.update(account_stats.keys())
    
    # Initialize aggregated stats
    for policy_id in all_policy_ids:
        aggregated_stats[policy_id] = {
            'compliant': 0,
            'non_compliant': 0,
            'could_not_assess': 0,
            'total_resources': 0,
            'accounts_with_violations': 0
        }
    
    # Aggregate across accounts
    for account_id, account_stats in all_account_stats.items():
        for policy_id, stats in account_stats.items():
            aggregated_stats[policy_id]['compliant'] += stats['compliant']
            aggregated_stats[policy_id]['non_compliant'] += stats['non_compliant']
            aggregated_stats[policy_id]['could_not_assess'] += stats['could_not_assess']
            aggregated_stats[policy_id]['total_resources'] += stats['total_resources']
            
            if stats['non_compliant'] > 0:
                aggregated_stats[policy_id]['accounts_with_violations'] += 1
    
    return aggregated_stats


def write_compliance_csv(policies_data, compliance_stats, output_file, framework_name):
    """Write comprehensive policy compliance details to CSV file."""
    fieldnames = [
        'Policy Name',
        'Policy ID', 
        'Severity',
        'Status',
        'Framework Name',
        'Policy Type',
        'Compliant Resources',
        'Non-Compliant Resources',
        'Accounts with Violations'
    ]
    
    # Define severity and status order for sorting (case-insensitive)
    severity_order = {
        'critical': 1, 'high': 2, 'medium': 3, 'low': 4, 'info': 5, 'unknown': 6
    }
    status_order = {'enabled': 1, 'disabled': 2, 'unknown': 3}
    
    # Sort policies by Policy Type (alphabetically), Status (Enabled first), then Severity, then Policy ID
    def sort_key(policy):
        policy_type = policy.get('policy_type', 'Unknown')
        status = policy.get('status', 'Unknown').lower()
        severity = policy.get('severity', 'Unknown').lower()
        status_rank = status_order.get(status, 999)
        severity_rank = severity_order.get(severity, 999)
        policy_id = policy.get('policy_id', '')
        return (policy_type, status_rank, severity_rank, policy_id)
    
    # Filter out policies with 'Manual' policy type
    filtered_policies = [policy for policy in policies_data if policy.get('policy_type', '').lower() != 'manual']
    
    sorted_policies = sorted(filtered_policies, key=sort_key)
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()
            
            # Write data for each policy in sorted order
            for policy in sorted_policies:
                policy_id = policy['policy_id']
                stats = compliance_stats.get(policy_id, {
                    'compliant': 0,
                    'non_compliant': 0,
                    'could_not_assess': 0,
                    'total_resources': 0,
                    'accounts_with_violations': 0
                })
                
                writer.writerow({
                    'Policy Name': policy['policy_name'],
                    'Policy ID': policy_id,
                    'Severity': policy['severity'].title() if policy['severity'] != 'Unknown' else 'Unknown',
                    'Status': policy['status'],
                    'Framework Name': framework_name,
                    'Policy Type': policy.get('policy_type', 'Unknown'),
                    'Compliant Resources': stats['compliant'],
                    'Non-Compliant Resources': stats['non_compliant'],
                    'Accounts with Violations': stats['accounts_with_violations']
                })
        
        print(f"Successfully wrote {len(policies_data)} policies to {output_file}")
        
    except Exception as e:
        print(f"Error writing CSV file: {e}")
        sys.exit(1)


def main():
    """Main function to execute the complete compliance-based framework mapping workflow."""
    
    # Parse command-line arguments
    args = parse_arguments()
    
    print("=== Lacework Compliance-Based Framework Mapping Tool ===")
    print(f"Report: {args.report_name}")
    print(f"API Key: {args.api_key_file}")
    print("Performing comprehensive policy compliance analysis...\n")
    
    # Generate filename-safe version of report name
    report_filename = generate_filename_from_report_name(args.report_name)
    
    # Define paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    api_key_file = Path(args.api_key_file)
    report_cache_dir = project_root / "cache" / "report-definitions"
    policy_cache_dir = project_root / "cache" / "policy-details"
    compliance_cache_dir = project_root / "cache" / "compliance-reports"
    output_dir = project_root / "output"
    
    # Ensure directories exist
    report_cache_dir.mkdir(parents=True, exist_ok=True)
    policy_cache_dir.mkdir(parents=True, exist_ok=True)
    compliance_cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load API credentials
    print("Step 1: Loading API credentials...")
    credentials = load_api_credentials(api_key_file)
    
    # Initialize Lacework client
    print("Step 2: Initializing Lacework client...")
    try:
        client = LaceworkClient(
            account=credentials['account'],
            api_key=credentials['keyId'],
            api_secret=credentials['secret']
        )
    except Exception as e:
        print(f"Error initializing Lacework client: {e}")
        sys.exit(1)
    
    # Step 1: Get report definition
    print("Step 3: Retrieving report definition...")
    report_name = args.report_name
    report_cache_file = report_cache_dir / f"{report_filename}.json"
    
    # Try to load from cache first
    report_definition = load_report_definition_from_cache(report_cache_file)
    
    if not report_definition:
        print("  Report definition not cached, retrieving from API...")
        report_definition = find_report_definition_by_name(client, report_name)
        
        if not report_definition:
            print(f"Failed to retrieve report definition for '{report_name}'")
            sys.exit(1)
        
        # Save to cache
        save_report_definition(report_definition, report_cache_dir, report_filename)
    else:
        print("  Using cached report definition")
    
    # Step 2: Extract unique policy IDs
    print("Step 4: Extracting unique policy IDs...")
    policy_ids = extract_unique_policy_ids(report_definition)
    print(f"Found {len(policy_ids)} unique policy IDs")
    
    # Step 3: Get policy details
    print("Step 5: Retrieving policy details...")
    cached_count = sum(1 for policy_id in policy_ids if (policy_cache_dir / f"{policy_id}.json").exists())
    print(f"Found {cached_count} policies already cached, {len(policy_ids) - cached_count} to retrieve from API")
    
    policies_data = []
    excluded_policies = []
    for i, policy_id in enumerate(policy_ids, 1):
        print(f"Processing policy {i}/{len(policy_ids)}: {policy_id}")
        policy_details = get_policy_details_with_retry(client, policy_id, policy_cache_dir)
        
        # Filter out policies with policy type "violation"
        if policy_details.get('policy_type', '').lower() == 'violation':
            excluded_policies.append(policy_details)
            print(f"  Excluding policy {policy_id} (policy type: violation)")
        else:
            policies_data.append(policy_details)
    
    # Step 4: Get AWS accounts
    print("Step 6: Retrieving AWS accounts...")
    aws_accounts = get_aws_accounts(client)
    
    if not aws_accounts:
        print("No AWS accounts found. Cannot proceed with compliance analysis.")
        sys.exit(1)
    
    # Step 5: Get compliance reports for each account
    print("Step 7: Retrieving compliance reports...")
    # For custom report definitions, we need to use the report name
    report_name = report_definition.get('reportName', 'UNSW AWS Cyber Security Standards')
    print(f"Using report name: {report_name}")
    
    all_account_stats = {}
    for i, account in enumerate(aws_accounts, 1):
        account_id = account['account_id']
        print(f"Processing account {i}/{len(aws_accounts)}: {account_id} ({account['integration_name']})")
        
        report_data = get_compliance_report_for_account(account_id, report_name, compliance_cache_dir, credentials)
        
        if report_data:
            account_stats = extract_policy_compliance_stats(report_data, policy_ids)
            all_account_stats[account_id] = account_stats
        else:
            print(f"  No compliance data available for account {account_id}")
    
    # Step 6: Aggregate compliance statistics
    print("Step 8: Aggregating compliance statistics...")
    aggregated_compliance_stats = aggregate_policy_compliance_across_accounts(all_account_stats)
    
    # Step 7: Write comprehensive CSV output
    print("Step 9: Writing comprehensive CSV output...")
    framework_name = report_definition.get('reportName', 'UNSW AWS Cyber Security Standards')
    output_file = output_dir / f"{report_filename}_compliance.csv"
    
    write_compliance_csv(policies_data, aggregated_compliance_stats, output_file, framework_name)
    
    # Final summary
    print("\n=== Final Summary ===")
    print(f"Framework: {framework_name}")
    print(f"Total policies processed: {len(policies_data)}")
    print(f"AWS accounts analyzed: {len(aws_accounts)}")
    print(f"Output file: {output_file}")
    
    # Statistics
    enabled_count = sum(1 for p in policies_data if p['status'] == 'Enabled')
    disabled_count = sum(1 for p in policies_data if p['status'] == 'Disabled')
    total_non_compliant = sum(stats['non_compliant'] for stats in aggregated_compliance_stats.values())
    total_compliant = sum(stats['compliant'] for stats in aggregated_compliance_stats.values())
    policies_with_violations = sum(1 for stats in aggregated_compliance_stats.values() if stats['non_compliant'] > 0)
    
    print(f"Enabled policies: {enabled_count}")
    print(f"Disabled policies: {disabled_count}")
    print(f"Total compliant resources: {total_compliant}")
    print(f"Total non-compliant resources: {total_non_compliant}")
    print(f"Policies with violations: {policies_with_violations}")
    
    # Severity distribution
    severity_counts = {}
    for policy in policies_data:
        severity = policy['severity'].title() if policy['severity'] != 'Unknown' else 'Unknown'
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    
    print("\nSeverity distribution:")
    for severity, count in sorted(severity_counts.items()):
        print(f"  {severity}: {count}")
    
    print(f"\nCompliance-based framework mapping analysis complete!")


if __name__ == "__main__":
    main()
