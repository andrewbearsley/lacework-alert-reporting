# Lacework API Reporting Tool

This tool retrieves Lacework compliance alerts and generates Excel reports with policy details and remediation information.

**Features:**
- Configurable date ranges (defaults to previous week Mon-Sun)
- Retrieves compliance alerts using Lacework API and CLI
- Retrieves compliance status (non-compliant resources) from compliance reports
- Enriches alerts with policy details using caching
- Generates Excel reports with both Alerts and Compliance Status tabs
- Professional formatting with proper styling and text wrapping
- Handles rate limiting and retry logic
- Perfect line break handling for multi-line content

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

### Install Python Dependencies

Install all required Python packages:
```bash
pip3 install -r requirements.txt
```

This includes:
- **Lacework Python SDK:** For Lacework API integration
- **Tabulate:** For formatted CLI table output
- **OpenPyXL:** For Excel file generation with professional formatting

Docs: https://lacework.github.io/python-sdk

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
- `--skip-compliance`: Skip Compliance Status tab (only generate Alerts tab)
- `--compliance-report`: Specific compliance report name to use for compliance status (e.g., "AWS PCI DSS 4.0.0")
- `--clear-cache`: Clear all cached data before running (forces fresh API calls)
- `--output-file`: Custom Excel output filename (default: auto-generated based on date range)

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

# Skip compliance status tab (alerts only)
python3 script/lacework_alert_reporting.py -k api-key/my-lw-api-key.json --skip-compliance

# Use specific compliance report for compliance status
python3 script/lacework_alert_reporting.py -k api-key/my-lw-api-key.json --compliance-report "AWS PCI DSS 4.0.0"

# Clear cache and use custom output file
python3 script/lacework_alert_reporting.py -k api-key/my-lw-api-key.json --clear-cache --output-file my_alerts.xlsx

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
- **Custom reports**

## Output

Generates an Excel report.
- **File:** 
  - Default: `output/lacework_alerts_YYYY-MM-DD_to_YYYY-MM-DD.xlsx`
  - With report: `output/lacework_alerts_YYYY-MM-DD_to_YYYY-MM-DD_REPORT-NAME.xlsx`

## References

- CLI Documentation: [Get started with Lacework FortiCNAPP CLI](https://docs.fortinet.com/document/lacework-forticnapp/latest/cli-reference/68020/get-started-with-the-lacework-forticnapp-cli)
- API Documentation: [About the Lacework FortiCNAPP API](https://docs.fortinet.com/document/lacework-forticnapp/latest/api-reference/863111/about-the-lacework-forticnapp-api)
- API Documentation: [Lacework API Documentation](https://yourlacework.lacework.net/api/v2/docs)
- Query Language Documentation: [LQL Overview](https://docs.fortinet.com/document/lacework-forticnapp/latest/lql-reference/598361/lql-overview)
- Python SDK Documentation: [Lacework Python SDK Documentation](https://lacework.github.io/python-sdk)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Third-Party Licenses

This project includes software from third parties. The full license text for each can be found in the `LICENSES` directory.

* **Lacework Python SDK:** [MIT License](./LICENSES/LACEWORK_SDK_LICENSE.md)
