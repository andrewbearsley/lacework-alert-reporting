"""
Configuration management and argument parsing for Lacework Alert Reporting.
"""
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Generate Lacework compliance alert reports in Excel format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use previous week Mon-Sun
  python lacework_alert_reporting.py --api-key-file api-key/my-key.json -r "AWS Foundational Security Best Practices (FSBP) Standard"
  
  # Specify custom date range
  python lacework_alert_reporting.py --api-key-file api-key/my-key.json --start-date 2024-01-01 --end-date 2024-01-07 -r "AWS CIS 1.5.0"
  
  # Use current week Mon-Sun
  python lacework_alert_reporting.py --api-key-file api-key/my-key.json --current-week -r "AWS Foundational Security Best Practices (FSBP) Standard"
  
  # Use --compliance-report (same as -r)
  python lacework_alert_reporting.py --api-key-file api-key/my-key.json --compliance-report "AWS PCI DSS 4.0.0"
  
  # Skip compliance status tab (alerts only)
  python lacework_alert_reporting.py --api-key-file api-key/my-key.json -r "AWS Foundational Security Best Practices (FSBP) Standard" --skip-compliance
  
  # Filter to specific AWS account for testing
  python lacework_alert_reporting.py --api-key-file api-key/my-key.json -r "AWS Foundational Security Best Practices (FSBP) Standard" --aws-account "123456789012"
  
  # Skip tag retrieval for faster testing
  python lacework_alert_reporting.py --api-key-file api-key/my-key.json -r "AWS Foundational Security Best Practices (FSBP) Standard" --no-tags
        """
    )
    
    # Required arguments
    parser.add_argument(
        '-k', '--api-key-file',
        required=True,
        help='Path to the Lacework API key JSON file (e.g., api-key/my-key.json)'
    )
    
    # Date range arguments
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        '--start-date',
        help='Start date for alert retrieval (YYYY-MM-DD format)'
    )
    date_group.add_argument(
        '--current-week',
        action='store_true',
        help='Use current week (Monday to Sunday) instead of previous week'
    )
    
    parser.add_argument(
        '--end-date',
        help='End date for alert retrieval (YYYY-MM-DD format)'
    )
    
    # Output and cache options
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear all cached data before running (forces fresh API calls)'
    )
    parser.add_argument(
        '--output-file',
        help='Custom Excel output filename (default: auto-generated based on date range)'
    )
    
    # Required compliance report
    report_group = parser.add_mutually_exclusive_group(required=True)
    report_group.add_argument(
        '-r', '--report',
        help='Compliance report name to use (e.g., "AWS Foundational Security Best Practices (FSBP) Standard")'
    )
    report_group.add_argument(
        '--compliance-report',
        help='Compliance report name to use (same as -r/--report)'
    )
    
    # Other filtering options
    parser.add_argument(
        '--skip-compliance',
        action='store_true',
        help='Skip Compliance Status tab (only generate Alerts tab)'
    )
    parser.add_argument(
        '--aws-account',
        help='Filter to specific AWS account ID (e.g., "123456789012") for testing/development'
    )
    parser.add_argument(
        '--no-tags',
        action='store_true',
        help='Skip tag retrieval to speed up testing (tags will show as N/A)'
    )
    
    return parser.parse_args()


def get_date_range(args):
    """Calculate start and end dates based on arguments."""
    if args.current_week:
        # Current week (Monday to Sunday)
        today = datetime.now().date()
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif args.start_date:
        # Custom date range
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        if args.end_date:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        else:
            end_date = start_date + timedelta(days=6)
    else:
        # Default: previous week (Monday to Sunday)
        today = datetime.now().date()
        last_monday = today - timedelta(days=today.weekday() + 7)
        start_date = last_monday
        end_date = start_date + timedelta(days=6)
    
    return start_date, end_date


def load_api_credentials(api_key_file):
    """Load Lacework API credentials from JSON file."""
    try:
        with open(api_key_file, 'r') as f:
            credentials = json.load(f)
        return credentials
    except FileNotFoundError:
        raise FileNotFoundError(f"API key file not found: {api_key_file}")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in API key file: {api_key_file}")


def get_output_filename(start_date, end_date, args):
    """Generate output filename based on date range and arguments."""
    if args.output_file:
        return args.output_file
    
    date_str = f"{start_date}_to_{end_date}"
    
    # Include compliance report name in filename if specified
    if hasattr(args, 'compliance_report') and args.compliance_report:
        # Clean the report name for filename (remove spaces, special chars)
        report_name = args.compliance_report.replace(' ', '-').replace('(', '').replace(')', '')
        return f"lacework_alerts_{date_str}_{report_name}.xlsx"
    
    return f"lacework_alerts_{date_str}.xlsx"


def get_cache_directory():
    """Get the cache directory path."""
    return Path("cache")


def get_output_directory():
    """Get the output directory path."""
    return Path("output")

