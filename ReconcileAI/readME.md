
ReconcileAI — Payment Reconciliation Dashboard
ReconcileAI is a portfolio project for reconciling payment exports against bank statement CSV files. It helps identify matched transactions, amount mismatches, missing records, duplicate references, and other data-quality exceptions, then provides a downloadable CSV report.

Project status: Prototype / active development. The browser dashboard and Python/FastAPI workflows currently exist as separate paths. The HTML dashboard runs reconciliation in the browser; it does not call the FastAPI endpoint unless you explicitly integrate that in script.js.

Features
Upload payment and bank CSV files through a dashboard.
Detect matching references and amount discrepancies.
Flag missing transactions and duplicate references.
Show KPI cards, reconciliation status charts, discrepancy distribution, and amount comparisons.
Search and filter transaction results.
Download the reconciliation results as a CSV file.
Generate deterministic synthetic datasets for repeatable development and testing.
Run batch reconciliation and produce summary, duplicate, and risk-scoring reports.
Expose a FastAPI health endpoint and CSV reconciliation endpoint.
Test core workflows with pytest.
Tech stack
Frontend: HTML, CSS, JavaScript
Data processing: Python, pandas, NumPy
API: FastAPI, Uvicorn
Testing: pytest
Optional dashboard/reporting tools: Streamlit, Plotly, scikit-learn (only where used by the corresponding modules)
Project structure
ReconcileAI/
├── app/
│   ├── api.py
│   ├── generate_data.py
│   ├── reconcile.py
│   ├── risk_scoring.py
│   └── upload_processor.py
├── data/                       # Generated/sample CSVs; don't commit private data
├── reports/                    # Generated reports; don't commit sensitive reports
├── tests/
│   ├── test_reconcile.py
│   ├── test_risk_scoring.py
│   └── test_upload_processor.py
├── index.html
├── script.js
├── style.css
├── streamlit_app.py            # If included in your local project
├── requirements.txt
├── .gitignore
└── README.md
Your actual file tree may differ slightly. Keep each code module in its own file and update this structure if you add or rename files.

Requirements
Python 3.10 or newer is recommended.
Git
A modern browser
Setup on Windows
Open PowerShell and move to the project folder:

cd "C:\Users\SUKLA DEY\OneDrive\Desktop\ReconcileAI"
Create and activate a virtual environment:

python -m venv .venv
.\.venv\Scripts\Activate.ps1
If PowerShell blocks activation, you can run the environment's Python directly:

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Install the project dependencies:

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
If app/api.py imports FastAPI but fastapi is missing from requirements.txt, install it and add it to that file:

python -m pip install fastapi
python -m pip freeze
Prefer a maintained, intentional dependency list over blindly pinning every package installed in your environment.

Run the browser dashboard
Open index.html in your browser, or serve the folder locally:

python -m http.server 5500
Then open http://127.0.0.1:5500.

The current script.js performs reconciliation locally in the browser. The page's browser-only privacy message applies to this workflow.

Run the FastAPI service
Start the API from the project root:

python -m uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
Check the health endpoint in a second PowerShell window:

Invoke-RestMethod http://127.0.0.1:8000/health
Open the interactive API documentation at:

http://127.0.0.1:8000/docs
The API endpoint is POST /api/reconcile. The frontend is not automatically connected to this endpoint in the current browser-only implementation. If you connect it later, update the privacy messaging because files will be sent to the server for processing.

Generate sample data and run the batch pipeline
From the project root, with the virtual environment active:

python -m app.generate_data
python -m app.reconcile
python -m app.risk_scoring
The pipeline is expected to generate sample input files and reports under data/ and reports/. Exact output names depend on the implementation in your local modules.

Run tests
From the project root:

python -m pytest -v
Run a single test file when debugging:

python -m pytest -v tests/test_reconcile.py
python -m pytest -v tests/test_risk_scoring.py
python -m pytest -v tests/test_upload_processor.py
The tests should prepare the reports they need instead of relying on a stale report from an earlier run.

CSV input formats
Browser dashboard
The browser dashboard attempts to detect reference and amount columns from common names. For reliable results, use explicit headers such as:

Payments CSV

payment_reference,payment_amount,customer,payment_date
TXN001,100.00,Customer A,2026-10-20
TXN002,250.00,Customer B,2026-10-20
Bank CSV

bank_reference,bank_amount,bank_date,description
TXN001,100.00,2026-10-20,Settlement A
TXN002,260.00,2026-10-20,Settlement B
The exact required columns for the FastAPI upload endpoint are determined by app/upload_processor.py. Keep its schema and the sample templates aligned.

Important reconciliation notes
A matching reference does not prove that a transaction is financially correct; compare amounts and investigate exceptions.
Duplicate references should be reviewed rather than silently discarded.
Missing or invalid amounts should be reported as data-quality issues.
Source totals should be calculated from original uploaded records. Result-row totals can be misleading when duplicates or unmatched records are present.
Synthetic datasets are for development and demonstration, not real financial decision-making.
Privacy and security
Do not upload real customer or bank data to a public GitHub repository.
Do not commit .env files, API keys, credentials, or private reports.
The browser-only workflow processes selected CSV contents in the browser. The FastAPI workflow processes uploaded files on the server; these are different privacy models.
This project is a prototype and should not be used as the sole basis for financial decisions.
Roadmap
Standardize reference normalization across all workflows.
Align CSV column aliases and status names.
Ensure duplicate transactions are consistently represented in the main report.
Include duplicate risk in risk scoring.
Connect the frontend to FastAPI only if server-side processing is intended.
Add robust tests for malformed CSVs, duplicate references, invalid amounts, and empty files.
Add screenshots and a short demo video.
Add deployment instructions after choosing a hosting platform.
GitHub
Repository description suggestion:

Privacy-focused payment reconciliation dashboard with CSV matching, duplicate and mismatch detection, downloadable reports, and Python-based risk scoring.

Suggested topics:

python pandas fastapi javascript data-analytics reconciliation csv pytest risk-scoring

Author
Built as a data analytics and Python portfolio project.

Disclaimer: ReconcileAI is an educational prototype. Always review exceptions and validate reports before making financial or operational decisions.

