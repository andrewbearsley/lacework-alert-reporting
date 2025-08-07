# Lacework Framework Mapping

This repository automates the extraction and analysis of compliance data for the a compliance framework using the Lacework CLI and Python SDK.

This script handles the workflow:
1. Retrieves the report definition
2. Extracts unique policy IDs from the report definition
3. Retrieves policy details (with caching and rate limiting)
4. Gets list of AWS accounts from cloud integrations
5. Fetches compliance reports for each account using Lacework CLI
6. Aggregates compliance statistics and writes to CSV

## Prerequisites

- Python 3.7+
- Lacework CLI installed and configured
- Lacework Python SDK: `pip install laceworksdk`
- API credentials eg. `api-key/my-api-key.json`

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
lacework --version

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
python --version
```

### Install Lacework Python SDK

Docs: https://lacework.github.io/python-sdk
```bash
pip install laceworksdk
```

## Usage

```bash
python script/compliance_framework_mapping.py -r "REPORT_NAME" -k "API_KEY_FILE"
```

### Examples

```bash
# AWS ISO 27001:2013 framework
python script/compliance_framework_mapping.py -r "AWS ISO 27001:2013" -k api-key/my-lw-api-key.json

# Show help
python script/compliance_framework_mapping.py --help
```

## Output

Generates a CSV report:
- **File:** `output/my_report_name_compliance.csv`
- **Columns:** Policy Name, Policy ID, Severity, Status, Framework Name, Policy Type, Compliant Resources, Non-Compliant Resources, Accounts with Violations
- **Sorting:** Policy Type → Status → Severity → Policy ID

## Architecture

- **CLI-based compliance reports:** Uses Lacework CLI for custom framework support
- **Comprehensive caching:** Report definitions, policy details, and compliance reports
- **Rate limiting:** HTTP 429 handling with exponential backoff
- **Error handling:** Robust retry logic and graceful degradation

## References

- Lacework Python SDK Documentation: https://lacework.github.io/python-sdk
- Lacework API Documentation: https://docs.lacework.com/api



