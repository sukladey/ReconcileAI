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
