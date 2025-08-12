# Lacework Framework Mapping

This repository automates the extraction and analysis of compliance data for a compliance framework using the Lacework CLI and Python SDK.

This script handles the workflow:
1. Retrieves the report definition
2. Extracts unique policy IDs from the report definition
3. Retrieves policy details (with caching and rate limiting)
4. Lists AWS accounts from cloud integrations
5. Fetches compliance reports for each account using Lacework CLI
6. Aggregates compliance statistics and writes to CSV

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
python3 script/compliance_framework_mapping.py -r "REPORT_NAME" -k "API_KEY_FILE" [--clear-cache]
```

### Command-Line Options

- `-r, --report-name`: Name of the Lacework report definition (required)
- `-k, --api-key-file`: Path to the Lacework API key JSON file (required)
- `--clear-cache`: Clear all cached data before running (forces fresh API calls)

### Examples

```bash
# AWS ISO 27001:2013 framework
python3 script/compliance_framework_mapping.py -r "AWS ISO 27001:2013" -k api-key/my-lw-api-key.json

# Clear cache and run with fresh data
python3 script/compliance_framework_mapping.py -r "AWS ISO 27001:2013" -k api-key/my-lw-api-key.json --clear-cache

# Show help
python3 script/compliance_framework_mapping.py --help
```

## Output

Generates a comprehensive CSV report:
- **File:** `output/my_report_name_compliance.csv`
- **Columns:** 
  - Policy Name, Policy ID, Severity, Status, Framework Name, Policy Type
  - Compliant Resources, Non-Compliant Resources, Accounts with Violations
  - **Description** (policy description with preserved formatting)
  - **Remediation** (detailed remediation steps with preserved formatting)
- **Sorting:** Policy Type → Status → Severity → Policy ID
- **Format:** CSV with proper quoting for multi-line text fields (Excel-compatible)

## Architecture

- **CLI-based compliance reports:** Uses Lacework CLI for custom framework support
- **Comprehensive caching:** Report definitions, policy details, and compliance reports
- **Rate limiting:** HTTP 429 handling with exponential backoff
- **Error handling:** Robust retry logic and graceful degradation

## References
- Lacework CLI Documentation: 
https://docs.fortinet.com/document/lacework-forticnapp/latest/cli-reference/68020/get-started-with-the-lacework-forticnapp-cli
- Lacework API Documentation:
https://docs.fortinet.com/document/lacework-forticnapp/latest/api-reference/863111/about-the-lacework-forticnapp-api
- Lacework LQL Documentation: 
https://docs.fortinet.com/document/lacework-forticnapp/latest/lql-reference/598361/lql-overview
- Lacework Python SDK Documentation: https://lacework.github.io/python-sdk

