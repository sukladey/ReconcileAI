# ReconcileAI — Payment Reconciliation & Risk Analysis

**A data analytics project for reconciling payment and bank transactions, detecting duplicates and mismatches, and identifying potential financial exceptions using Python and interactive dashboards.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Pandas](https://img.shields.io/badge/Pandas-Data%20Analysis-150458)
![JavaScript](https://img.shields.io/badge/JavaScript-Frontend-yellow)
![Status](https://img.shields.io/badge/Project-Portfolio%20Project-purple)

## Overview

ReconcileAI is a payment reconciliation dashboard designed to help analyze payment records against bank transactions. It highlights transaction discrepancies and supports investigation through summaries, charts, filters, and downloadable CSV reports.

The project demonstrates practical skills in data cleaning, transaction matching, exception detection, data visualization, Python development, and automated testing.

## Key Features

- **CSV Upload:** Load payment and bank transaction files for reconciliation.
- **Transaction Matching:** Compare records using transaction or reference identifiers.
- **Duplicate Detection:** Identify duplicate payment references and other repeated records.
- **Mismatch Detection:** Highlight transactions where payment and bank amounts differ.
- **Missing Transaction Detection:** Identify records that appear on one side but not the other.
- **Interactive Dashboard:** Display reconciliation metrics, charts, and transaction-level results.
- **Search and Filtering:** Explore records and investigate exceptions.
- **CSV Export:** Download reconciliation results for further analysis.
- **Risk Scoring:** Assign risk scores to reconciliation exceptions through the Python workflow, where implemented.
- **Automated Testing:** Validate reconciliation and risk-scoring behavior using pytest.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Reconciliation logic and data processing |
| Pandas | Data cleaning, transformation, and analysis |
| NumPy | Numerical operations |
| HTML and CSS | Dashboard structure and styling |
| JavaScript | Browser-side CSV processing and interactivity |
| FastAPI | Optional API backend |
| Uvicorn | Running the API server |
| pytest | Automated testing |
| Git and GitHub | Version control and project hosting |

## Project Structure

The structure below is a reference. Keep only the files and folders that actually exist in your repository.

```text
ReconcileAI-/
├── app/
│   ├── api.py
│   ├── dashboard.py
│   ├── generate_data.py
│   ├── reconcile.py
│   ├── risk_scoring.py
│   └── upload_processor.py
├── data/
├── reports/
├── tests/
│   ├── test_reconcile.py
│   ├── test_upload_processor.py
│   └── test_risk_scoring.py
├── index.html
├── script.js
├── style.css
├── streamlit_app.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.10 or later
- Git
- A modern web browser
- Visual Studio Code (recommended)

### 1. Clone the Repository

```bash
git clone https://github.com/sukladey/ReconcileAI-.git
cd ReconcileAI-
```

### 2. Create a Virtual Environment

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this for the current terminal session and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you use the FastAPI backend, make sure `fastapi`, `uvicorn`, and `python-multipart` are included in `requirements.txt`.

## Run the Dashboard

For the browser-based dashboard, open `index.html` in your browser.

Alternatively, start a local web server from the project root:

```bash
python -m http.server 5500
```

Then open:

**http://127.0.0.1:5500**

Press `Ctrl+C` in the terminal to stop the server.

## Run the Python Reconciliation Workflow

If the corresponding modules exist in your project, run these commands from the project root:

```bash
python -m app.generate_data
python -m app.reconcile
python -m app.risk_scoring
```

Check the console output and the `data/` and `reports/` folders to confirm which files were generated.

## Run the FastAPI Backend (Optional)

If `app/api.py` defines a FastAPI instance named `app`, start the API using:

```bash
python -m uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
```

Check the health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

If API documentation is enabled, open:

**http://127.0.0.1:8000/docs**

> **Architecture note:** The browser dashboard and FastAPI backend are separate unless the frontend explicitly sends requests to the API. The privacy description and upload behavior should match the implementation you actually run.

## Run Automated Tests

Run the test suite from the project root:

```bash
python -m pytest -v
```

To run individual test files:

```bash
python -m pytest tests/test_reconcile.py -v
python -m pytest tests/test_risk_scoring.py -v
```

Some tests may depend on generated input files or reports. If a test fails because a file is missing, check the test fixtures and run the required data-generation or reconciliation step first.

## Sample CSV Formats

The following are example formats. Confirm that your current CSV parser supports these column names.

**Payments — `payments.csv`**

```csv
payment_reference,payment_amount,customer,payment_date
PAY001,1200.00,Customer A,2026-10-01
PAY002,850.00,Customer B,2026-10-01
PAY003,500.00,Customer C,2026-10-02
```

**Bank Transactions — `bank_transactions.csv`**

```csv
bank_reference,bank_amount,bank_date,description
PAY001,1200.00,2026-10-01,Payment received
PAY002,900.00,2026-10-01,Payment received
PAY004,700.00,2026-10-02,Payment received
```

These examples illustrate the types of exceptions a reconciliation workflow can identify:

- `PAY001` — matching reference and amount.
- `PAY002` — amount mismatch.
- `PAY003` — payment without a corresponding bank record.
- `PAY004` — bank record without a corresponding payment.

Actual classifications depend on the reconciliation rules implemented in the application.

## Privacy and Data Security

- Use synthetic or anonymized data for demonstrations.
- Do not commit real customer details, bank statements, or payment records.
- Keep passwords, API keys, and `.env` files out of GitHub.
- Exclude virtual environments and generated reports unless they are safe and intentionally included.
- Review `.gitignore` and run `git status` before committing.
- If uploaded files are sent to a backend, do not describe that processing as browser-only.

## Skills Demonstrated

- Data cleaning and preprocessing
- Exploratory data analysis
- Transaction reconciliation
- Exception and duplicate detection
- Data visualization and dashboard development
- Python application development
- API development (if enabled)
- Test-driven validation with pytest
- Git and GitHub version control

## Future Improvements

- Add more robust CSV column normalization and validation.
- Improve handling of duplicate bank and payment references.
- Add tests for missing columns, invalid amounts, empty files, and malformed CSVs.
- Connect the dashboard to the API if backend-based processing is desired.
- Add dashboard screenshots and a demo video.
- Deploy the application after testing the full workflow.



## Author

**Sukla Dey**

- GitHub: [@sukladey](https://github.com/sukladey)
- Project Repository: [ReconcileAI-](https://github.com/sukladey/ReconcileAI-)

## Disclaimer

ReconcileAI is an educational portfolio project intended to demonstrate data analytics and reconciliation concepts. Its results should be reviewed before being used for financial decisions. It is not a substitute for a production financial control system or formal audit.
