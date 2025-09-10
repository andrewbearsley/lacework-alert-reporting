# Lacework Alert Reporting Tool

This repository provides automated alert reporting for Lacework compliance alerts using the Lacework CLI and Python SDK. It generates a report of compliance alerts with policy details and remediation information.

**Features:**
- Configurable date ranges (defaults to previous week Mon-Sun)
- Retrieves compliance alerts using Lacework API and CLI
- Enriches alerts with policy details using intelligent caching
- Generates CSV reports with alert information
- Handles rate limiting and retry logic

## Prerequisites

- Python 3.7+
- Lacework CLI installed and configured
- Lacework API key: `api-key/my-api-key.json`
- Lacework Python SDK: `pip3 install laceworksdk`

### Lacework CLI

Docs: https://docs.lacework.com/cli

#### Install Lacework CLI (Mac)
```bash
brew install lacework-cli
```

#### Install Lacework CLI (Windows via Chocolatey)
```powershell
choco install lacework
```

#### Install Lacework CLI (Windows via PowerShell)
```powershell
iwr -useb https://raw.githubusercontent.com/lacework/go-sdk/main/scripts/install.ps1 | iex
```

#### Configure Lacework CLI
```bash
# Verify installation
lacework version

# Initial setup
lacework configure
# Enter your: Account name, API key, API secret

# Get help 
lacework help

# List available reports
lacework report-definitions list
```

### Install Python 3

Option 1: Download from python.org
Download Python 3 from python.org/downloads/
Run the installer and check "Add Python to PATH"

Option 2: Windows: Install via Chocolatey
```powershell
choco install python
```

Option 3: Windows: Install via Winget
```powershell
winget install Python.Python.3
```

Verify installation:
```bash
python3 --version
```

### Install Lacework Python SDK

Docs: https://lacework.github.io/python-sdk
```bash
pip3 install laceworksdk
```

## Usage

```bash
python3 script/lacework_alert_reporting.py -k "API_KEY_FILE" [OPTIONS]
```

### Command-Line Options
- `-k, --api-key-file`: Path to the Lacework API key JSON file (required)
- `--start-date`: Start date for alert retrieval (YYYY-MM-DD format)
- `--end-date`: End date for alert retrieval (YYYY-MM-DD format)
- `--current-week`: Use current week (Monday to Sunday) instead of previous week
- `-r, --report`: Filter alerts to only include policies from the specified compliance report (e.g., "AWS Foundational Security Best Practices (FSBP) Standard")
- `--clear-cache`: Clear all cached data before running (forces fresh API calls)
- `--output-file`: Custom output filename (default: auto-generated based on date range)

### Examples

```bash
# Use default (previous week Mon-Sun)
python3 script/lacework_alert_reporting.py -k api-key/my-lw-api-key.json

# Use current week Mon-Sun
python3 script/lacework_alert_reporting.py -k api-key/my-lw-api-key.json --current-week

# Specify custom date range
python3 script/lacework_alert_reporting.py -k api-key/my-lw-api-key.json --start-date 2024-01-01 --end-date 2024-01-07

# Filter by compliance report
python3 script/lacework_alert_reporting.py -k api-key/my-lw-api-key.json --current-week -r "CIS Amazon Web Services Foundations Benchmark v1.4.0"

# Filter by PCI DSS compliance report
python3 script/lacework_alert_reporting.py -k api-key/my-lw-api-key.json --current-week -r "AWS PCI DSS 4.0.0"

# Clear cache and use custom output file
python3 script/lacework_alert_reporting.py -k api-key/my-lw-api-key.json --clear-cache --output-file my_alerts.csv

# Show help
python3 script/lacework_alert_reporting.py --help
```

### Available Compliance Reports

To see all available compliance reports in your Lacework environment:

```bash
# List all available report definitions
lacework report-definitions list
```

Common compliance reports include:
- **AWS Foundational Security Best Practices (FSBP) Standard**
- **AWS PCI DSS 4.0.0**
- **AWS NIST 800-53 rev5**
- **Azure CIS Benchmark**
- **GCP CIS Benchmark**
- **Custom reports** (e.g., "UNSW AWS Cyber Security Standards")

## Output

Generates a CSV report:
- **File:** 
  - Default: `output/lacework_alerts_YYYY-MM-DD_to_YYYY-MM-DD.csv`
  - With report: `output/lacework_alerts_YYYY-MM-DD_to_YYYY-MM-DD_REPORT-NAME.csv`
  - Custom: `output/CUSTOM_FILENAME.csv` (when using `--output-file`)
- **Columns:**
  - Policy ID, Policy Title, Description, Remediation Steps
  - Severity, Resource, Region, Account, Date/Time, Alert ID
- **Sorting:** Severity → Date/Time
- **Format:** CSV with proper quoting for multi-line text fields (Excel-compatible)
- **Resource Enhancement:** AWS resources include account ID and alias information for better context

## Architecture

- **Flexible date ranges:** Configurable date range selection with sensible defaults
- **Dual API approach:** Uses both Lacework SDK and CLI for alert retrieval
- **Policy enrichment:** Combines alert data with detailed policy information
- **Intelligent caching:** Reuses policy details cache for performance optimization
- **Rate limiting:** HTTP 429 handling with exponential backoff
- **Error handling:** Retry logic and graceful degradation

## Features

- **Configurable date ranges:** Previous week (default), current week, or custom date ranges
- **Compliance report filtering:** Filter alerts by specific compliance frameworks (e.g., AWS FSBP, PCI DSS, custom reports)
- **Detailed Alert data:** Retrieves all compliance alerts for the specified time period
- **Policy enrichment:** Automatically enriches alerts with policy details and remediation steps
- **Intelligent caching:** Caches policy details and report definitions to avoid redundant API calls
- **Rate limiting:** Handles API rate limits with exponential backoff and retry logic
- **Enhanced resource information:** AWS resources include account ID and alias for better context
- **Smart filename generation:** Report names automatically included in output filenames
- **Formatted output:** Generates well-formatted CSV reports suitable for analysis

## References

- CLI Documentation: [Get started with Lacework FortiCNAPP CLI](https://docs.fortinet.com/document/lacework-forticnapp/latest/cli-reference/68020/get-started-with-the-lacework-forticnapp-cli)
- API Documentation: [About the Lacework FortiCNAPP API](https://docs.fortinet.com/document/lacework-forticnapp/latest/api-reference/863111/about-the-lacework-forticnapp-api)
- Query Language Documentation: [LQL Overview](https://docs.fortinet.com/document/lacework-forticnapp/latest/lql-reference/598361/lql-overview)
- Python SDK Documentation: [Lacework Python SDK Documentation](https://lacework.github.io/python-sdk)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Third-Party Licenses

This project includes software from third parties. The full license text for each can be found in the `LICENSES` directory.

* **Lacework Python SDK:** [MIT License](./LICENSES/LACEWORK_SDK_LICENSE.md)
