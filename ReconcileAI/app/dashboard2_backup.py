
from pathlib import Path
from io import BytesIO
import re

import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# ReconcileAI — Secure Session-Based Reconciliation Dashboard
# ============================================================

st.set_page_config(
    page_title="ReconcileAI | Reconciliation Dashboard",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT_DIR / "reports"

RECONCILIATION_FILE = REPORTS_DIR / "reconciliation_results.csv"
RISK_FILE = REPORTS_DIR / "risk_scored_transactions.csv"
DUPLICATE_FILE = REPORTS_DIR / "duplicate_payments.csv"
INVESTIGATION_FILE = REPORTS_DIR / "investigation_log.csv"

MAX_UPLOAD_MB = 20
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

st.title("🔎 ReconcileAI")
st.caption(
    "Payment reconciliation • Data quality • Risk monitoring "
    "• Company file reconciliation"
)


# ============================================================
# General helpers
# ============================================================

def safe_read_report(path):
    """Read an existing project report without changing it."""
    if not path.is_file():
        return pd.DataFrame()

    try:
        return pd.read_csv(path)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        st.warning(f"Could not read report {path.name}: {exc}")
        return pd.DataFrame()


def read_investigation_log():
    return safe_read_report(INVESTIGATION_FILE)


def save_investigation_log(frame):
    """Save only the existing project's investigation log."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(INVESTIGATION_FILE, index=False)


def first_existing_column(frame, candidates):
    """Return the first matching column name, ignoring case."""
    lookup = {str(c).strip().casefold(): c for c in frame.columns}

    for candidate in candidates:
        if candidate.casefold() in lookup:
            return lookup[candidate.casefold()]

    return None


def numeric_series(frame, column):
    if column is None or column not in frame.columns:
        return pd.Series(0, index=frame.index, dtype="float64")

    return pd.to_numeric(frame[column], errors="coerce").fillna(0)


def format_inr(value):
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₹0.00"


def safe_download_csv(frame):
    """
    Reduce spreadsheet formula-injection risk in text cells
    when users open downloaded CSV files in spreadsheet software.
    """
    export_frame = frame.copy()

    dangerous_prefix = re.compile(r"^\s*[=+\-@\t\r]")

    for column in export_frame.columns:
        if (
            pd.api.types.is_object_dtype(export_frame[column])
            or pd.api.types.is_string_dtype(export_frame[column])
        ):
            export_frame[column] = export_frame[column].map(
                lambda value: (
                    "'" + str(value)
                    if isinstance(value, str)
                    and dangerous_prefix.match(value)
                    else value
                )
            )

    return export_frame.to_csv(index=False).encode("utf-8-sig")


# ============================================================
# Company upload and reconciliation helpers
# ============================================================

def read_company_file(uploaded_file):
    """
    Read CSV/XLS/XLSX in memory.

    This function does not write the uploaded source file to disk.
    """
    if uploaded_file is None:
        raise ValueError("Upload both payment and bank files.")

    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"{uploaded_file.name} exceeds the "
            f"{MAX_UPLOAD_MB} MB upload limit."
        )

    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):
        frame = pd.read_csv(
            BytesIO(uploaded_file.getvalue()),
            encoding_errors="replace",
            on_bad_lines="error",
        )
    elif filename.endswith((".xlsx", ".xls")):
        frame = pd.read_excel(
            BytesIO(uploaded_file.getvalue())
        )
    else:
        raise ValueError("Only CSV, XLSX, and XLS files are supported.")

    if frame.empty:
        raise ValueError(f"{uploaded_file.name} has no data rows.")

    if len(frame.columns) > 200:
        raise ValueError(
            f"{uploaded_file.name} contains too many columns."
        )

    frame.columns = [str(column).strip() for column in frame.columns]

    if any(not column for column in frame.columns):
        raise ValueError(
            f"{uploaded_file.name} has an empty column name."
        )

    if frame.columns.duplicated().any():
        raise ValueError(
            f"{uploaded_file.name} has duplicate column names."
        )

    # Avoid processing unnecessarily large tables.
    if len(frame) > 250_000:
        raise ValueError(
            f"{uploaded_file.name} has more than 250,000 rows."
        )

    return frame


def normalize_reference(series):
    return (
        series.astype("string")
        .str.strip()
        .str.casefold()
    )


def parse_amount(series, label):
    """
    Convert amounts to numeric values.

    Supports values such as 1200, 1,200.50, ₹1200, and INR 1200.
    """
    cleaned = (
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.replace(r"(?i)\bINR\b", "", regex=True)
        .str.strip()
    )

    amounts = pd.to_numeric(cleaned, errors="coerce")

    if amounts.isna().any():
        raise ValueError(
            f"{label} amount column has blank or non-numeric values."
        )

    if not amounts.map(lambda value: pd.notna(value) and abs(value) < 1e15).all():
        raise ValueError(
            f"{label} amount column contains unsupported values."
        )

    return amounts.astype(float).round(2)


def reconcile_company_files(
    payments,
    bank,
    payment_ref,
    payment_amount,
    bank_ref,
    bank_amount,
):
    """
    Reconcile records by reference and amount.

    Duplicate references are explicitly flagged. Matching is one-to-one:
    one bank row cannot be used to match multiple payment rows.
    """
    payments = payments.copy().reset_index(drop=True)
    bank = bank.copy().reset_index(drop=True)

    for frame, ref_col, amount_col, label in [
        (payments, payment_ref, payment_amount, "Payment"),
        (bank, bank_ref, bank_amount, "Bank"),
    ]:
        if ref_col == amount_col:
            raise ValueError(
                f"Select different reference and amount columns for {label}."
            )

        if ref_col not in frame.columns or amount_col not in frame.columns:
            raise ValueError(f"Selected {label} columns are invalid.")

        if frame[ref_col].isna().any():
            raise ValueError(
                f"{label} reference column contains blank values."
            )

        frame["_reconcile_ref"] = normalize_reference(frame[ref_col])

        if (
            frame["_reconcile_ref"].isna().any()
            or frame["_reconcile_ref"].eq("").any()
        ):
            raise ValueError(
                f"{label} reference column contains blank values."
            )

        frame["_reconcile_amount"] = parse_amount(
            frame[amount_col], label
        )

    payment_duplicate = payments["_reconcile_ref"].duplicated(keep=False)
    bank_duplicate = bank["_reconcile_ref"].duplicated(keep=False)

    payment_groups = {}
    bank_groups = {}

    for index, ref in payments["_reconcile_ref"].items():
        payment_groups.setdefault(ref, []).append(index)

    for index, ref in bank["_reconcile_ref"].items():
        bank_groups.setdefault(ref, []).append(index)

    used_bank_rows = set()
    results = []

    for payment_index, payment in payments.iterrows():
        ref = payment["_reconcile_ref"]
        payment_value = float(payment["_reconcile_amount"])
        candidates = bank_groups.get(ref, [])

        if payment_duplicate.iloc[payment_index]:
            status = "DUPLICATE_PAYMENT_REFERENCE"
            bank_value = None

        else:
            available = [
                idx for idx in candidates
                if idx not in used_bank_rows
            ]

            if not available:
                status = "MISSING_BANK_RECORD"
                bank_value = None

            else:
                bank_index = available[0]
                bank_row = bank.loc[bank_index]
                bank_value = float(bank_row["_reconcile_amount"])
                used_bank_rows.add(bank_index)

                if bank_duplicate.iloc[bank_index]:
                    status = "DUPLICATE_BANK_REFERENCE"
                elif abs(payment_value - bank_value) > 0.01:
                    status = "AMOUNT_MISMATCH"
                else:
                    status = "MATCHED"

        results.append({
            "Transaction Reference": str(payment[payment_ref]),
            "Payment Amount": payment_value,
            "Bank Amount": bank_value,
            "Amount Difference": (
                round(payment_value - bank_value, 2)
                if bank_value is not None else None
            ),
            "Reconciliation Status": status,
        })

    for bank_index, bank_row in bank.iterrows():
        if bank_index not in used_bank_rows:
            if bank_duplicate.iloc[bank_index]:
                status = "DUPLICATE_BANK_REFERENCE"
            else:
                status = "MISSING_PAYMENT"

            results.append({
                "Transaction Reference": str(bank_row[bank_ref]),
                "Payment Amount": None,
                "Bank Amount": float(bank_row["_reconcile_amount"]),
                "Amount Difference": None,
                "Reconciliation Status": status,
            })

    return pd.DataFrame(results)


# ============================================================
# Load existing project reports
# ============================================================

reconciliation = safe_read_report(RECONCILIATION_FILE)
risk = safe_read_report(RISK_FILE)
duplicates = safe_read_report(DUPLICATE_FILE)

if reconciliation.empty:
    st.error(
        "The existing reconciliation report is missing or empty:\n\n"
        f"{RECONCILIATION_FILE}\n\n"
        "Generate the project's reports first. Company uploads are "
        "available after the existing dashboard reports load."
    )
    st.stop()

# Keep the existing report data unchanged.
all_data = reconciliation.copy()

if not risk.empty:
    common_keys = [
        column for column in all_data.columns
        if column in risk.columns
    ]

    # Merge only when a suitable transaction key exists.
    key = first_existing_column(
        all_data,
        ["transaction_id", "transaction_reference", "transaction_ref",
         "transaction_id", "order_id", "reference", "transaction_reference"],
    )

    risk_key = (
        first_existing_column(
            risk,
            ["transaction_id", "transaction_reference", "transaction_ref",
             "order_id", "reference"],
        )
    )

    if key and risk_key and key != risk_key:
        risk = risk.rename(columns={risk_key: key})

    if key and key in risk.columns:
        risk_columns = [
            column for column in risk.columns
            if column == key or column not in all_data.columns
        ]

        all_data = all_data.merge(
            risk[risk_columns],
            on=key,
            how="left",
        )

status_col = first_existing_column(
    all_data,
    ["reconciliation_status", "status", "match_status", "result"],
)
amount_col = first_existing_column(
    all_data,
    ["amount", "transaction_amount", "payment_amount", "order_amount"],
)
risk_col = first_existing_column(
    all_data,
    ["risk_level", "risk_category", "risk_label"],
)
risk_score_col = first_existing_column(
    all_data,
    ["risk_score", "anomaly_score", "score"],
)
risk_reasons_col = first_existing_column(
    all_data,
    ["risk_reasons", "risk_reason", "reasons"],
)

if status_col:
    all_data[status_col] = all_data[status_col].fillna("UNKNOWN").astype(str)

if risk_reasons_col:
    all_data[risk_reasons_col] = (
        all_data[risk_reasons_col].fillna("").astype(str)
    )


# ============================================================
# Existing dashboard overview
# ============================================================

st.header("Project Reconciliation Overview")

total_records = len(all_data)

if status_col:
    normalized_status = all_data[status_col].str.strip().str.upper()
    matched_count = int(
        normalized_status.isin(["MATCHED", "MATCH", "RECONCILED"]).sum()
    )
    exception_count = total_records - matched_count
else:
    normalized_status = pd.Series(
        ["UNKNOWN"] * total_records, index=all_data.index
    )
    matched_count = 0
    exception_count = total_records

high_risk_count = 0
if risk_col:
    high_risk_count = int(
        all_data[risk_col]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(["HIGH", "CRITICAL", "VERY HIGH"])
        .sum()
    )
elif risk_score_col:
    high_risk_count = int(
        (numeric_series(all_data, risk_score_col) >= 0.8).sum()
    )

metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric("Transactions", f"{total_records:,}")
metric2.metric("Matched", f"{matched_count:,}")
metric3.metric("Exceptions", f"{exception_count:,}")
metric4.metric("High-risk records", f"{high_risk_count:,}")

chart_left, chart_right = st.columns(2)

with chart_left:
    st.subheader("Reconciliation Status")
    if status_col:
        status_counts = (
            all_data[status_col]
            .value_counts(dropna=False)
            .rename_axis("Status")
            .reset_index(name="Records")
        )
        fig_status = px.bar(
            status_counts,
            x="Status",
            y="Records",
            title="Records by status",
        )
        st.plotly_chart(fig_status, use_container_width=True)
    else:
        st.info("No recognized status column exists in the report.")

with chart_right:
    st.subheader("Risk Overview")
    if risk_col:
        risk_counts = (
            all_data[risk_col]
            .fillna("Unknown")
            .astype(str)
            .value_counts()
            .rename_axis("Risk Level")
            .reset_index(name="Records")
        )
        fig_risk = px.pie(
            risk_counts,
            names="Risk Level",
            values="Records",
            title="Risk level distribution",
            hole=0.4,
        )
        st.plotly_chart(fig_risk, use_container_width=True)
    elif risk_score_col:
        fig_risk = px.histogram(
            all_data,
            x=risk_score_col,
            title="Risk score distribution",
        )
        st.plotly_chart(fig_risk, use_container_width=True)
    else:
        st.info("No recognized risk column exists in the report.")


# ============================================================
# Existing transaction filters and report download
# ============================================================

st.divider()
st.header("Transaction Explorer")

with st.sidebar:
    st.header("Project Report Filters")

    if status_col:
        available_statuses = sorted(
            all_data[status_col].dropna().astype(str).unique().tolist()
        )
        chosen_statuses = st.multiselect(
            "Reconciliation status",
            available_statuses,
            default=available_statuses,
        )
    else:
        chosen_statuses = []

    if risk_col:
        available_risks = sorted(
            all_data[risk_col].dropna().astype(str).unique().tolist()
        )
        chosen_risks = st.multiselect(
            "Risk level",
            available_risks,
            default=available_risks,
        )
    else:
        chosen_risks = []

filtered = all_data.copy()

if status_col:
    filtered = filtered[
        filtered[status_col].astype(str).isin(chosen_statuses)
    ]

if risk_col:
    filtered = filtered[
        filtered[risk_col].astype(str).isin(chosen_risks)
    ]

st.write(f"Showing **{len(filtered):,}** of **{total_records:,}** records.")
st.dataframe(filtered, use_container_width=True, hide_index=True)

st.download_button(
    "Download filtered project report (CSV)",
    data=safe_download_csv(filtered),
    file_name="reconcileai_filtered_report.csv",
    mime="text/csv",
    key="download_project_report",
)


# ============================================================
# Existing business impact summary
# ============================================================

st.divider()
st.header("Business Impact Summary")

if amount_col:
    amount_values = numeric_series(all_data, amount_col)
    total_amount = float(amount_values.sum())
    st.metric("Total transaction amount", format_inr(total_amount))
else:
    st.info(
        "A recognized transaction amount column was not found, "
        "so the total transaction amount cannot be calculated."
    )

if status_col:
    mismatch_mask = all_data[status_col].astype(str).str.upper().str.contains(
        "MISMATCH", na=False
    )
    missing_mask = all_data[status_col].astype(str).str.upper().str.contains(
        "MISSING", na=False
    )

    st.write(f"Amount-mismatch records: **{int(mismatch_mask.sum()):,}**")
    st.write(f"Missing-record exceptions: **{int(missing_mask.sum()):,}**")

if not duplicates.empty:
    with st.expander("View existing duplicate-payment report"):
        st.dataframe(duplicates, use_container_width=True, hide_index=True)


# ============================================================
# Existing investigation workflow
# ============================================================

st.divider()
st.header("Transaction Investigation")

investigation_log = read_investigation_log()

if not all_data.empty:
    id_col = first_existing_column(
        all_data,
        ["transaction_id", "transaction_reference", "transaction_ref",
         "order_id", "reference", "transaction_id"],
    )

    if id_col:
        transaction_ids = all_data[id_col].dropna().astype(str).unique().tolist()

        if transaction_ids:
            selected_transaction = st.selectbox(
                "Select a transaction",
                transaction_ids,
                key="investigation_transaction",
            )

            selected_rows = all_data[
                all_data[id_col].astype(str) == selected_transaction
            ]

            st.dataframe(
                selected_rows,
                use_container_width=True,
                hide_index=True,
            )

            with st.form("investigation_form"):
                investigator = st.text_input(
                    "Investigator / team",
                    max_chars=100,
                )
                investigation_status = st.selectbox(
                    "Investigation status",
                    [
                        "Open",
                        "Under Review",
                        "Resolved",
                        "False Positive",
                    ],
                )
                notes = st.text_area(
                    "Investigation notes",
                    max_chars=2000,
                )

                save_investigation = st.form_submit_button(
                    "Save Investigation"
                )

            if save_investigation:
                new_entry = pd.DataFrame([{
                    "transaction_id": selected_transaction,
                    "investigator": investigator.strip(),
                    "status": investigation_status,
                    "notes": notes.strip(),
                    "updated_at": pd.Timestamp.now().isoformat(),
                }])

                if investigation_log.empty:
                    investigation_log = new_entry
                else:
                    investigation_log = pd.concat(
                        [investigation_log, new_entry],
                        ignore_index=True,
                    )

                try:
                    save_investigation_log(investigation_log)
                    st.success("Investigation entry saved.")
                    st.rerun()
                except OSError as exc:
                    st.error(f"Could not save the investigation: {exc}")
    else:
        st.info(
            "A recognized transaction ID/reference column was not found. "
            "The investigation form is unavailable for this report."
        )

if not investigation_log.empty:
    st.subheader("Investigation History")
    st.dataframe(
        investigation_log,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download investigation log (CSV)",
        data=safe_download_csv(investigation_log),
        file_name="reconcileai_investigation_log.csv",
        mime="text/csv",
        key="download_investigation_log",
    )


# ============================================================
# Company data upload and reconciliation
# ============================================================

st.divider()
st.header("Company Data Upload & Reconciliation")

st.markdown(
    """
Upload your payment export and bank statement to reconcile them.

- Supported files: CSV, XLSX, XLS
- Maximum file size: 20 MB per file
- Select the reference and amount columns in each file
- Uploaded source files are processed in memory and are not written
  to your project's reports folder
- Company reconciliation results are held in the current Streamlit
  session and can be downloaded as a CSV
"""
)

st.warning(
    "Privacy note: this feature does not save uploaded source files to disk, "
    "but Streamlit temporarily handles file contents in memory. Do not use "
    "sensitive production data until authentication, HTTPS, hosting access "
    "controls, and your company's data-retention requirements are configured."
)

with st.expander("Upload and reconcile company files", expanded=True):
    payment_file = st.file_uploader(
        "1. Payment records",
        type=["csv", "xlsx", "xls"],
        key="company_payment_file",
    )

    bank_file = st.file_uploader(
        "2. Bank statement",
        type=["csv", "xlsx", "xls"],
        key="company_bank_file",
    )

    if payment_file is not None and bank_file is not None:
        try:
            payment_preview = read_company_file(payment_file)
            bank_preview = read_company_file(bank_file)

            st.subheader("Payment file preview")
            st.dataframe(
                payment_preview.head(5),
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Bank file preview")
            st.dataframe(
                bank_preview.head(5),
                use_container_width=True,
                hide_index=True,
            )

            payment_columns = payment_preview.columns.tolist()
            bank_columns = bank_preview.columns.tolist()

            st.subheader("Map columns")

            map_left, map_right = st.columns(2)

            with map_left:
                payment_ref = st.selectbox(
                    "Payment reference column",
                    payment_columns,
                    key="company_payment_reference",
                )
                payment_amount = st.selectbox(
                    "Payment amount column",
                    payment_columns,
                    key="company_payment_amount",
                )

            with map_right:
                bank_ref = st.selectbox(
                    "Bank reference column",
                    bank_columns,
                    key="company_bank_reference",
                )
                bank_amount = st.selectbox(
                    "Bank amount column",
                    bank_columns,
                    key="company_bank_amount",
                )

            if st.button(
                "Reconcile Company Records",
                type="primary",
                key="run_company_reconciliation",
            ):
                try:
                    company_results = reconcile_company_files(
                        payment_preview,
                        bank_preview,
                        payment_ref,
                        payment_amount,
                        bank_ref,
                        bank_amount,
                    )

                    # Results are session-scoped, not written to disk.
                    st.session_state["company_results"] = company_results
                    st.session_state["company_file_names"] = (
                        payment_file.name,
                        bank_file.name,
                    )
                    st.session_state["company_results_ready"] = True

                except (ValueError, KeyError) as exc:
                    st.error(f"Reconciliation could not run: {exc}")

        except ImportError:
            st.error(
                "Excel support is missing. Run: "
                "python -m pip install openpyxl"
            )
        except (
            ValueError,
            KeyError,
            OSError,
            pd.errors.ParserError,
            ImportError,
        ) as exc:
            st.error(f"Could not read the uploaded files: {exc}")
        except Exception as exc:
            st.error(
                f"File processing failed: {exc}. "
                "Check that both files are valid and not password-protected."
            )


# Display results only when the currently selected filenames match
# the filenames used for the last reconciliation.
current_company_files = (
    (payment_file.name, bank_file.name)
    if payment_file is not None and bank_file is not None
    else None
)

if (
    current_company_files is not None
    and st.session_state.get("company_results_ready", False)
    and st.session_state.get("company_file_names") == current_company_files
):
    company_results = st.session_state["company_results"]

    st.subheader("Company Reconciliation Results")

    company_status_col = "Reconciliation Status"
    statuses = company_results[company_status_col]

    total_company_records = len(company_results)
    matched_company = int((statuses == "MATCHED").sum())
    exceptions_company = total_company_records - matched_company
    mismatches_company = int((statuses == "AMOUNT_MISMATCH").sum())
    missing_company = int(
        statuses.isin([
            "MISSING_BANK_RECORD",
            "MISSING_PAYMENT",
        ]).sum()
    )
    duplicates_company = int(
        statuses.isin([
            "DUPLICATE_PAYMENT_REFERENCE",
            "DUPLICATE_BANK_REFERENCE",
        ]).sum()
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Records assessed", f"{total_company_records:,}")
    c2.metric("Matched", f"{matched_company:,}")
    c3.metric("Exceptions", f"{exceptions_company:,}")
    c4.metric("Amount mismatches", f"{mismatches_company:,}")

    c5, c6 = st.columns(2)
    c5.metric("Missing records", f"{missing_company:,}")
    c6.metric("Duplicate references", f"{duplicates_company:,}")

    company_status_options = sorted(statuses.unique().tolist())

    chosen_company_statuses = st.multiselect(
        "Filter company results",
        options=company_status_options,
        default=company_status_options,
        key="company_status_filter",
    )

    company_filtered = company_results[
        company_results[company_status_col].isin(chosen_company_statuses)
    ]

    st.dataframe(
        company_filtered,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download company reconciliation report (CSV)",
        data=safe_download_csv(company_results),
        file_name="company_reconciliation_results.csv",
        mime="text/csv",
        key="download_company_results",
    )

    st.caption(
        "The downloaded report contains reconciliation outcomes. "
        "The original uploaded files are not included."
    )

st.divider()
st.caption(
    "ReconcileAI • Company uploads are separate from the project's "
    "existing reconciliation reports."
)
