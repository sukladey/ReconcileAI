
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re

import pandas as pd
import plotly.express as px
import streamlit as st


# ================================================================
# 1. PATHS AND CONFIGURATION
# ================================================================
ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"

RECONCILIATION_FILE = REPORTS_DIR / "reconciliation_results.csv"
RISK_FILE = REPORTS_DIR / "risk_scored_transactions.csv"
DUPLICATE_FILE = REPORTS_DIR / "duplicate_payments.csv"
INVESTIGATION_FILE = REPORTS_DIR / "investigation_log.csv"

MAX_UPLOAD_MB = 20
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_ROWS = 250_000

INVESTIGATION_STATUSES = [
    "Open",
    "Under Review",
    "Resolved",
    "False Positive",
]

st.set_page_config(
    page_title="ReconcileAI | Financial Intelligence",
    page_icon="💳",
    layout="wide",
)


# ================================================================
# 2. GENERAL HELPERS
# ================================================================
def numeric_series(frame, column):
    """Return a numeric series, using zero when a column is unavailable."""
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype=float)

    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def normalize_reference(series):
    """Normalize transaction references for matching."""
    values = series.astype("string").str.strip().str.upper()

    # Treat blank strings and common missing-value strings as missing.
    values = values.replace(
        ["", "NAN", "NONE", "NULL", "<NA>"],
        pd.NA,
    )

    # Normalize references accidentally imported as values like ABC123.0.
    values = values.str.replace(r"(?<=\d)\.0$", "", regex=True)

    return values


def normalize_amount(series):
    """Convert currency-like values into numbers."""
    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("€", "", regex=False)
        .str.replace("£", "", regex=False)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    )

    return pd.to_numeric(cleaned, errors="coerce")


def suggest_column(columns, candidates):
    """Suggest a likely column using common financial-file headers."""
    normalized = {
        str(column).strip().lower().replace(" ", "_"): column
        for column in columns
    }

    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]

    for name, original_name in normalized.items():
        if any(candidate in name for candidate in candidates):
            return original_name

    return columns[0] if columns else None


def safe_download_csv(frame):
    """Reduce spreadsheet-formula injection risk when exporting text."""
    safe_frame = frame.copy()

    dangerous_prefixes = ("=", "+", "-", "@")

    for column in safe_frame.columns:
        if (
            pd.api.types.is_object_dtype(safe_frame[column])
            or pd.api.types.is_string_dtype(safe_frame[column])
        ):
            safe_frame[column] = safe_frame[column].map(
                lambda value: (
                    "'" + value
                    if isinstance(value, str)
                    and value.lstrip().startswith(dangerous_prefixes)
                    else value
                )
            )

    return safe_frame.to_csv(index=False).encode("utf-8-sig")


def format_inr(value):
    """Format a numeric value as Indian rupees."""
    return f"₹{float(value):,.2f}"


def fingerprint_upload(uploaded_file):
    """Identify the current upload using its content hash."""
    if uploaded_file is None:
        return None

    return sha256(uploaded_file.getvalue()).hexdigest()


# ================================================================
# 3. LOAD EXISTING DEMO REPORTS
# ================================================================
@st.cache_data
def load_data():
    """
    Load existing demo reports.

    Missing demo reports do not prevent company uploads from working.
    """
    empty_reconciliation = pd.DataFrame(
        columns=[
            "transaction_id",
            "reconciliation_status",
            "bank_amount",
            "payment_amount",
            "amount_difference",
        ]
    )

    empty_risk = pd.DataFrame(
        columns=[
            "transaction_id",
            "risk_score",
            "risk_level",
            "risk_reasons",
        ]
    )

    if not RECONCILIATION_FILE.exists():
        return empty_reconciliation, empty_risk

    reconciliation = pd.read_csv(RECONCILIATION_FILE)

    required_reconciliation = {
        "transaction_id",
        "reconciliation_status",
    }

    missing = required_reconciliation - set(reconciliation.columns)

    if missing:
        raise ValueError(
            "reconciliation_results.csv is missing required columns: "
            + ", ".join(sorted(missing))
        )

    if RISK_FILE.exists():
        risk = pd.read_csv(RISK_FILE)
    else:
        risk = empty_risk.copy()

    if "risk_score" not in risk.columns:
        risk["risk_score"] = 0

    if "risk_level" not in risk.columns:
        risk["risk_level"] = "UNKNOWN"

    if "risk_reasons" not in risk.columns:
        risk["risk_reasons"] = ""

    risk_columns = [
        "transaction_id",
        "risk_score",
        "risk_level",
        "risk_reasons",
    ]

    risk = risk[risk_columns].copy()

    if risk["transaction_id"].duplicated().any():
        raise ValueError(
            "risk_scored_transactions.csv contains duplicate "
            "transaction_id values."
        )

    return reconciliation, risk


def read_investigation_log():
    """Read the persistent investigation log for demo transactions."""
    columns = [
        "transaction_id",
        "reconciliation_status",
        "risk_score",
        "risk_level",
        "investigation_status",
        "analyst_notes",
        "updated_at",
    ]

    if not INVESTIGATION_FILE.exists():
        return pd.DataFrame(columns=columns)

    try:
        log = pd.read_csv(INVESTIGATION_FILE)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=columns)

    for column in columns:
        if column not in log.columns:
            log[column] = ""

    return log[columns]


# ================================================================
# 4. READ AND VALIDATE COMPANY FILES
# ================================================================
def read_company_file(uploaded_file):
    """
    Read a company CSV or Excel file in memory.

    No uploaded file is intentionally written to disk by this function.
    """
    if uploaded_file is None:
        raise ValueError("Please select a file.")

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:
        raise ValueError(f"{uploaded_file.name} is empty.")

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"{uploaded_file.name} exceeds the "
            f"{MAX_UPLOAD_MB} MB upload limit."
        )

    suffix = Path(uploaded_file.name).suffix.lower()

    try:
        if suffix == ".csv":
            frame = pd.read_csv(
                BytesIO(file_bytes),
                dtype=object,
            )
        elif suffix in [".xlsx", ".xls"]:
            frame = pd.read_excel(
                BytesIO(file_bytes),
                dtype=object,
            )
        else:
            raise ValueError(
                "Unsupported file format. Upload CSV, XLSX, or XLS."
            )
    except ImportError as exc:
        raise ValueError(
            "Excel support is missing. Install the required Excel reader "
            "package in your active virtual environment."
        ) from exc
    except Exception as exc:
        raise ValueError(
            f"Could not read {uploaded_file.name}: {exc}"
        ) from exc

    if frame.empty:
        raise ValueError(f"{uploaded_file.name} contains no data rows.")

    if len(frame) > MAX_ROWS:
        raise ValueError(
            f"{uploaded_file.name} contains more than "
            f"{MAX_ROWS:,} rows."
        )

    if len(frame.columns) < 2:
        raise ValueError(
            f"{uploaded_file.name} must contain at least two columns."
        )

    frame.columns = [
        str(column).strip()
        for column in frame.columns
    ]

    if any(not column for column in frame.columns):
        raise ValueError(
            f"{uploaded_file.name} contains a blank column name."
        )

    if frame.columns.duplicated().any():
        raise ValueError(
            f"{uploaded_file.name} contains duplicate column names. "
            "Rename them before uploading."
        )

    return frame


# ================================================================
# 5. RECONCILIATION ENGINE FOR COMPANY FILES
# ================================================================
def reconcile_company_files(
    payments,
    bank,
    payment_reference_col,
    payment_amount_col,
    bank_reference_col,
    bank_amount_col,
):
    """
    Compare payment records against bank records.

    The reference is used as the primary matching key. Amount differences
    are reported rather than silently treated as exact matches.
    """
    payment_data = payments.copy().reset_index(drop=True)
    bank_data = bank.copy().reset_index(drop=True)

    payment_data["_reference"] = normalize_reference(
        payment_data[payment_reference_col]
    )
    bank_data["_reference"] = normalize_reference(
        bank_data[bank_reference_col]
    )

    payment_data["_amount"] = normalize_amount(
        payment_data[payment_amount_col]
    )
    bank_data["_amount"] = normalize_amount(
        bank_data[bank_amount_col]
    )

    payment_counts = payment_data["_reference"].value_counts(
        dropna=True
    )
    bank_counts = bank_data["_reference"].value_counts(
        dropna=True
    )

    bank_groups = {
        reference: group
        for reference, group in bank_data.groupby(
            "_reference",
            dropna=True,
            sort=False,
        )
    }

    output_rows = []
    matched_bank_indexes = set()

    # Process each payment row.
    for payment_index, payment_row in payment_data.iterrows():
        reference = payment_row["_reference"]
        payment_amount = payment_row["_amount"]

        result = {
            "transaction_id": (
                str(reference) if pd.notna(reference)
                else f"PAYMENT_ROW_{payment_index + 1}"
            ),
            "reference": (
                str(reference) if pd.notna(reference) else ""
            ),
            "payment_amount": payment_amount,
            "bank_amount": None,
            "amount_difference": None,
            "reconciliation_status": "",
            "notes": "",
            "payment_row_number": payment_index + 2,
            "bank_row_number": None,
        }

        if pd.isna(reference):
            result["reconciliation_status"] = "MISSING_REFERENCE"
            result["notes"] = "Payment reference is blank."

        elif payment_counts.get(reference, 0) > 1:
            result["reconciliation_status"] = (
                "DUPLICATE_PAYMENT_REFERENCE"
            )
            result["notes"] = (
                "The payment reference occurs more than once."
            )

            if reference in bank_groups:
                matched_bank_indexes.update(
                    bank_groups[reference].index.tolist()
                )

        elif reference not in bank_groups:
            result["reconciliation_status"] = "MISSING_BANK_RECORD"
            result["notes"] = (
                "No bank record has this payment reference."
            )

        else:
            bank_group = bank_groups[reference]
            matched_bank_indexes.update(bank_group.index.tolist())

            if bank_counts.get(reference, 0) > 1:
                result["bank_amount"] = bank_group["_amount"].iloc[0]
                result["bank_row_number"] = (
                    int(bank_group.index[0]) + 2
                )
                result["reconciliation_status"] = (
                    "DUPLICATE_BANK_REFERENCE"
                )
                result["notes"] = (
                    "The bank reference occurs more than once; "
                    "manual review is required."
                )

            else:
                bank_row = bank_group.iloc[0]
                bank_amount = bank_row["_amount"]

                result["bank_amount"] = bank_amount
                result["bank_row_number"] = (
                    int(bank_group.index[0]) + 2
                )

                if pd.isna(payment_amount) or pd.isna(bank_amount):
                    result["reconciliation_status"] = (
                        "INVALID_AMOUNT"
                    )
                    result["notes"] = (
                        "A payment or bank amount is blank or invalid."
                    )

                else:
                    difference = float(bank_amount - payment_amount)
                    result["amount_difference"] = difference

                    if abs(difference) < 0.005:
                        result["reconciliation_status"] = "MATCHED"
                        result["notes"] = (
                            "Reference and amount match."
                        )
                    else:
                        result["reconciliation_status"] = (
                            "AMOUNT_MISMATCH"
                        )
                        result["notes"] = (
                            "Reference matches, but amounts differ."
                        )

        output_rows.append(result)

    # Add bank rows that did not correspond to any payment reference.
    for bank_index, bank_row in bank_data.iterrows():
        reference = bank_row["_reference"]

        if bank_index in matched_bank_indexes:
            continue

        if pd.isna(reference):
            status = "MISSING_REFERENCE"
            notes = "Bank reference is blank."
        elif bank_counts.get(reference, 0) > 1:
            status = "DUPLICATE_BANK_REFERENCE"
            notes = (
                "Duplicate bank reference has no corresponding "
                "payment record."
            )
        else:
            status = "MISSING_PAYMENT"
            notes = "Bank record has no corresponding payment record."

        output_rows.append(
            {
                "transaction_id": (
                    str(reference) if pd.notna(reference)
                    else f"BANK_ROW_{bank_index + 1}"
                ),
                "reference": (
                    str(reference) if pd.notna(reference) else ""
                ),
                "payment_amount": None,
                "bank_amount": bank_row["_amount"],
                "amount_difference": None,
                "reconciliation_status": status,
                "notes": notes,
                "payment_row_number": None,
                "bank_row_number": bank_index + 2,
            }
        )

    result = pd.DataFrame(output_rows)

    if not result.empty:
        result["payment_amount"] = pd.to_numeric(
            result["payment_amount"], errors="coerce"
        )
        result["bank_amount"] = pd.to_numeric(
            result["bank_amount"], errors="coerce"
        )
        result["amount_difference"] = pd.to_numeric(
            result["amount_difference"], errors="coerce"
        )

    return result


# ================================================================
# 6. COMPANY UPLOAD AND RECONCILIATION
# ================================================================
st.title("💳 ReconcileAI")

st.caption(
    "Financial reconciliation, discrepancy detection, risk "
    "prioritization, and investigation tracking."
)

st.info(
    "Company uploads are processed in this Streamlit session and are not "
    "intentionally saved to the demo report files. This prototype is not "
    "a production-secure financial system."
)

st.header("🏢 Reconcile Your Company's Files")

st.write(
    "Upload your payment export and bank statement. Select the transaction "
    "reference and amount columns, then run reconciliation."
)

upload_left, upload_right = st.columns(2)

with upload_left:
    payment_file = st.file_uploader(
        "1. Upload payment records",
        type=["csv", "xlsx", "xls"],
        key="company_payment_upload",
        help=f"Maximum size: {MAX_UPLOAD_MB} MB.",
    )

with upload_right:
    bank_file = st.file_uploader(
        "2. Upload bank statement",
        type=["csv", "xlsx", "xls"],
        key="company_bank_upload",
        help=f"Maximum size: {MAX_UPLOAD_MB} MB.",
    )

current_fingerprints = (
    fingerprint_upload(payment_file),
    fingerprint_upload(bank_file),
)

# Invalidate old results if the contents of either upload changes.
if (
    "company_fingerprints" in st.session_state
    and st.session_state["company_fingerprints"] != current_fingerprints
):
    st.session_state.pop("company_results", None)
    st.session_state.pop("company_fingerprints", None)
    st.session_state.pop("company_notes", None)

if payment_file is not None and bank_file is not None:
    try:
        payment_preview = read_company_file(payment_file)
        bank_preview = read_company_file(bank_file)

        st.subheader("Payment File Preview")
        st.caption(
            f"{payment_file.name} — {len(payment_preview):,} rows"
        )
        st.dataframe(
            payment_preview.head(5),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Bank File Preview")
        st.caption(
            f"{bank_file.name} — {len(bank_preview):,} rows"
        )
        st.dataframe(
            bank_preview.head(5),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Map Your Columns")

        map_payment, map_bank = st.columns(2)

        with map_payment:
            st.markdown("**Payment file columns**")

            payment_reference_col = st.selectbox(
                "Payment reference / transaction ID",
                options=payment_preview.columns.tolist(),
                index=payment_preview.columns.tolist().index(
                    suggest_column(
                        payment_preview.columns.tolist(),
                        [
                            "transaction_id",
                            "transaction_reference",
                            "reference_number",
                            "reference",
                            "payment_id",
                            "order_id",
                            "txn_id",
                            "utr",
                            "rrn",
                        ],
                    )
                ),
                key="payment_reference_column",
            )

            payment_amount_col = st.selectbox(
                "Payment amount",
                options=payment_preview.columns.tolist(),
                index=payment_preview.columns.tolist().index(
                    suggest_column(
                        payment_preview.columns.tolist(),
                        [
                            "payment_amount",
                            "amount",
                            "transaction_amount",
                            "paid_amount",
                            "total_amount",
                            "debit",
                            "value",
                        ],
                    )
                ),
                key="payment_amount_column",
            )

        with map_bank:
            st.markdown("**Bank file columns**")

            bank_reference_col = st.selectbox(
                "Bank reference / transaction ID",
                options=bank_preview.columns.tolist(),
                index=bank_preview.columns.tolist().index(
                    suggest_column(
                        bank_preview.columns.tolist(),
                        [
                            "transaction_id",
                            "transaction_reference",
                            "reference_number",
                            "reference",
                            "payment_id",
                            "order_id",
                            "txn_id",
                            "utr",
                            "rrn",
                        ],
                    )
                ),
                key="bank_reference_column",
            )

            bank_amount_col = st.selectbox(
                "Bank transaction amount",
                options=bank_preview.columns.tolist(),
                index=bank_preview.columns.tolist().index(
                    suggest_column(
                        bank_preview.columns.tolist(),
                        [
                            "bank_amount",
                            "amount",
                            "transaction_amount",
                            "settlement_amount",
                            "credit",
                            "debit",
                            "value",
                        ],
                    )
                ),
                key="bank_amount_column",
            )

        st.caption(
            "Automatic suggestions are only suggestions. Confirm that the "
            "selected columns contain matching reference IDs and amounts."
        )

        process_col, clear_col = st.columns(2)

        with process_col:
            process_company_files = st.button(
                "🔍 Reconcile Company Files",
                type="primary",
                use_container_width=True,
            )

        with clear_col:
            clear_company_files = st.button(
                "Clear Company Results",
                use_container_width=True,
            )

        if clear_company_files:
            st.session_state.pop("company_results", None)
            st.session_state.pop("company_fingerprints", None)
            st.session_state.pop("company_notes", None)
            st.rerun()

        if process_company_files:
            result = reconcile_company_files(
                payments=payment_preview,
                bank=bank_preview,
                payment_reference_col=payment_reference_col,
                payment_amount_col=payment_amount_col,
                bank_reference_col=bank_reference_col,
                bank_amount_col=bank_amount_col,
            )

            st.session_state["company_results"] = result
            st.session_state["company_fingerprints"] = (
                current_fingerprints
            )
            st.session_state["company_notes"] = {}

            st.success("Company-file reconciliation completed.")

    except (ValueError, pd.errors.ParserError) as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(
            "Could not process the uploaded files. "
            f"Check the file format and selected columns. Details: {exc}"
        )

elif payment_file is not None or bank_file is not None:
    st.warning(
        "Upload both the payment file and bank statement to continue."
    )

# ================================================================
# 7. COMPANY RESULTS
# ================================================================
company_results = st.session_state.get("company_results")

if (
    company_results is not None
    and st.session_state.get("company_fingerprints")
    == current_fingerprints
):
    st.divider()
    st.header("📊 Company Reconciliation Results")

    total_company_rows = len(company_results)
    matched_company_rows = int(
        (
            company_results["reconciliation_status"] == "MATCHED"
        ).sum()
    )
    company_exception_rows = total_company_rows - matched_company_rows

    match_rate = (
        matched_company_rows / total_company_rows * 100
        if total_company_rows
        else 0
    )

    mismatch_mask = (
        company_results["reconciliation_status"] == "AMOUNT_MISMATCH"
    )
    mismatch_exposure = numeric_series(
        company_results.loc[mismatch_mask],
        "amount_difference",
    ).abs().sum()

    metric1, metric2, metric3, metric4 = st.columns(4)

    metric1.metric(
        "Records assessed",
        f"{total_company_rows:,}",
    )
    metric2.metric(
        "Matched",
        f"{matched_company_rows:,}",
    )
    metric3.metric(
        "Exceptions",
        f"{company_exception_rows:,}",
    )
    metric4.metric(
        "Match rate",
        f"{match_rate:.1f}%",
    )

    metric5, metric6 = st.columns(2)
    metric5.metric(
        "Amount mismatch exposure",
        format_inr(mismatch_exposure),
    )
    metric6.metric(
        "Unresolved records",
        f"{company_exception_rows:,}",
    )

    st.caption(
        "Mismatch exposure is the sum of absolute amount differences. "
        "It is an estimate for investigation, not a confirmed loss."
    )

    st.subheader("Exception Breakdown")

    status_counts = (
        company_results["reconciliation_status"]
        .fillna("UNKNOWN")
        .value_counts()
        .rename_axis("Status")
        .reset_index(name="Records")
    )

    chart_left, chart_right = st.columns(2)

    with chart_left:
        fig_company_status = px.bar(
            status_counts,
            x="Status",
            y="Records",
            color="Status",
            text="Records",
            title="Reconciliation status",
        )
        fig_company_status.update_layout(showlegend=False)
        st.plotly_chart(
            fig_company_status,
            use_container_width=True,
        )

    with chart_right:
        fig_company_pie = px.pie(
            status_counts,
            names="Status",
            values="Records",
            hole=0.45,
            title="Matched versus exception records",
        )
        st.plotly_chart(
            fig_company_pie,
            use_container_width=True,
        )

    st.subheader("Filter and Review Company Records")

    available_company_statuses = sorted(
        company_results["reconciliation_status"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    selected_company_statuses = st.multiselect(
        "Show reconciliation statuses",
        options=available_company_statuses,
        default=available_company_statuses,
        key="company_status_filter",
    )

    show_exceptions_only = st.checkbox(
        "Show exceptions only",
        value=False,
        key="company_exceptions_only",
    )

    filtered_company_results = company_results[
        company_results["reconciliation_status"].isin(
            selected_company_statuses
        )
    ].copy()

    if show_exceptions_only:
        filtered_company_results = filtered_company_results[
            filtered_company_results["reconciliation_status"] != "MATCHED"
        ]

    st.caption(
        f"Showing {len(filtered_company_results):,} of "
        f"{len(company_results):,} company records."
    )

    st.dataframe(
        filtered_company_results,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download Company Reconciliation CSV",
        data=safe_download_csv(filtered_company_results),
        file_name="reconcileai_company_reconciliation.csv",
        mime="text/csv",
        key="company_results_download",
    )

    st.subheader("Company Exception Investigation")

    company_exceptions = company_results[
        company_results["reconciliation_status"] != "MATCHED"
    ].copy()

    if company_exceptions.empty:
        st.success("No exceptions were found in this reconciliation.")
    else:
        selected_company_case = st.selectbox(
            "Select an exception to investigate",
            options=company_exceptions.index.tolist(),
            format_func=lambda index: (
                f"{company_exceptions.loc[index, 'transaction_id']} — "
                f"{company_exceptions.loc[index, 'reconciliation_status']}"
            ),
            key="company_case_selector",
        )

        selected_case = company_exceptions.loc[selected_company_case]
        case_id = str(selected_case["transaction_id"])

        st.write(
            f"**Reference:** {selected_case['reference'] or 'Missing'}"
        )
        st.write(
            "**Issue:** "
            f"{selected_case['reconciliation_status']}"
        )
        st.write(
            "**Payment amount:** "
            f"{selected_case['payment_amount']}"
        )
        st.write(
            "**Bank amount:** "
            f"{selected_case['bank_amount']}"
        )
        st.write(
            "**Difference:** "
            f"{selected_case['amount_difference']}"
        )
        st.write(f"**Explanation:** {selected_case['notes']}")

        company_notes = st.session_state.get("company_notes", {})
        previous_company_note = company_notes.get(case_id, "")

        with st.form("company_investigation_form"):
            company_case_status = st.selectbox(
                "Case status",
                options=INVESTIGATION_STATUSES,
                key="company_case_status",
            )

            company_case_note = st.text_area(
                "Analyst notes",
                value=previous_company_note,
                placeholder=(
                    "Example: Compared settlement reference with "
                    "the bank statement; confirmation is pending."
                ),
                key="company_case_note",
            )

            save_company_case = st.form_submit_button(
                "Save company investigation note"
            )

        if save_company_case:
            company_notes[case_id] = (
                f"Status: {company_case_status}\n"
                f"Notes: {company_case_note}\n"
                f"Updated: {datetime.now().isoformat(timespec='seconds')}"
            )
            st.session_state["company_notes"] = company_notes
            st.success(
                "Investigation note saved for this browser session."
            )

    st.caption(
        "Company investigation notes are session-only. They are not "
        "written to reports/investigation_log.csv."
    )


# ================================================================
# 8. EXISTING DEMO DASHBOARD
# ================================================================
st.divider()
st.header("🧪 Demo Dataset Dashboard")
st.caption(
    "This section displays the project's existing generated reports, "
    "when available. Company uploads are handled separately above."
)

try:
    reconciliation, risk = load_data()
except (FileNotFoundError, ValueError, pd.errors.ParserError) as exc:
    reconciliation = pd.DataFrame()
    risk = pd.DataFrame()
    st.warning(f"Demo reports could not be loaded: {exc}")

if reconciliation.empty:
    st.info(
        "No demo reconciliation report is available yet. "
        "Company-file reconciliation above can still be used."
    )

else:
    risk_columns = [
        "transaction_id",
        "risk_score",
        "risk_level",
        "risk_reasons",
    ]

    all_data = reconciliation.merge(
        risk[risk_columns],
        on="transaction_id",
        how="left",
        validate="one_to_one",
    )

    all_data["risk_score"] = pd.to_numeric(
        all_data["risk_score"], errors="coerce"
    ).fillna(0)

    all_data["risk_level"] = (
        all_data["risk_level"].fillna("UNKNOWN")
    )
    all_data["risk_reasons"] = (
        all_data["risk_reasons"].fillna("")
    )

    # ------------------------------------------------------------
    # Demo sidebar filters
    # ------------------------------------------------------------
    st.sidebar.header("Demo Investigation Filters")

    available_statuses = sorted(
        all_data["reconciliation_status"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    available_risk_levels = sorted(
        all_data["risk_level"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    selected_statuses = st.sidebar.multiselect(
        "Demo reconciliation status",
        options=available_statuses,
        default=available_statuses,
        key="demo_status_filter",
    )

    selected_risk_levels = st.sidebar.multiselect(
        "Demo risk level",
        options=available_risk_levels,
        default=available_risk_levels,
        key="demo_risk_filter",
    )

    search_text = st.sidebar.text_input(
        "Search demo transaction ID",
        placeholder="Example: TXN00001",
        key="demo_transaction_search",
    )

    if st.sidebar.button(
        "Clear cached data and reload",
        key="clear_demo_cache",
    ):
        st.cache_data.clear()
        st.rerun()

    # ------------------------------------------------------------
    # Demo KPIs
    # ------------------------------------------------------------
    total_transactions = len(all_data)

    matched_count = int(
        (
            all_data["reconciliation_status"] == "MATCHED"
        ).sum()
    )

    exception_count = total_transactions - matched_count

    duplicate_count = 0

    if DUPLICATE_FILE.exists():
        try:
            duplicate_count = len(pd.read_csv(DUPLICATE_FILE))
        except (
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ):
            duplicate_count = 0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    kpi1.metric(
        "Transactions assessed",
        f"{total_transactions:,}",
    )
    kpi2.metric(
        "Matched transactions",
        f"{matched_count:,}",
    )
    kpi3.metric(
        "Reconciliation exceptions",
        f"{exception_count:,}",
    )
    kpi4.metric(
        "Duplicate payment records",
        f"{duplicate_count:,}",
    )

    # ------------------------------------------------------------
    # Demo charts
    # ------------------------------------------------------------
    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.subheader("Demo Reconciliation Status")

        status_counts = (
            all_data["reconciliation_status"]
            .fillna("UNKNOWN")
            .value_counts()
            .rename_axis("Status")
            .reset_index(name="Transactions")
        )

        fig_status = px.bar(
            status_counts,
            x="Status",
            y="Transactions",
            color="Status",
            title="Transaction classification",
            text="Transactions",
        )
        fig_status.update_layout(showlegend=False)

        st.plotly_chart(
            fig_status,
            use_container_width=True,
        )

    with chart_right:
        st.subheader("Demo Investigation Risk")

        risk_counts = (
            all_data["risk_level"]
            .fillna("UNKNOWN")
            .value_counts()
            .rename_axis("Risk Level")
            .reset_index(name="Transactions")
        )

        fig_risk = px.pie(
            risk_counts,
            names="Risk Level",
            values="Transactions",
            hole=0.45,
            title="Risk-level distribution",
        )

        st.plotly_chart(
            fig_risk,
            use_container_width=True,
        )

    # ------------------------------------------------------------
    # Demo filtered transaction table
    # ------------------------------------------------------------
    display_data = all_data[
        all_data["reconciliation_status"].isin(selected_statuses)
        & all_data["risk_level"].isin(selected_risk_levels)
    ].copy()

    if search_text.strip():
        display_data = display_data[
            display_data["transaction_id"]
            .astype(str)
            .str.contains(
                search_text.strip(),
                case=False,
                na=False,
            )
        ]

    st.subheader("Demo Transaction Investigation Table")

    st.caption(
        f"Showing {len(display_data):,} of {len(all_data):,} "
        "records after filtering."
    )

    preferred_columns = [
        "transaction_id",
        "reconciliation_status",
        "bank_amount",
        "payment_amount",
        "amount_difference",
        "risk_score",
        "risk_level",
        "risk_reasons",
    ]

    visible_columns = [
        column
        for column in preferred_columns
        if column in display_data.columns
    ]

    if display_data.empty:
        st.info("No demo transactions match the current filters.")
    else:
        st.dataframe(
            display_data[visible_columns],
            use_container_width=True,
            hide_index=True,
        )

    st.download_button(
        "Download filtered demo report (CSV)",
        data=safe_download_csv(display_data),
        file_name="reconcileai_demo_investigation_report.csv",
        mime="text/csv",
        key="demo_report_download",
    )

    # ------------------------------------------------------------
    # Demo business impact analysis
    # ------------------------------------------------------------
    st.divider()
    st.header("Demo Business Impact Analysis")

    all_exceptions = all_data[
        all_data["reconciliation_status"] != "MATCHED"
    ].copy()

    amount_mismatch_count = int(
        (
            all_exceptions["reconciliation_status"]
            == "AMOUNT_MISMATCH"
        ).sum()
    )

    missing_payment_count = int(
        (
            all_exceptions["reconciliation_status"]
            == "MISSING_PAYMENT"
        ).sum()
    )

    missing_bank_count = int(
        (
            all_exceptions["reconciliation_status"]
            == "MISSING_BANK_RECORD"
        ).sum()
    )

    high_risk_count = int(
        (all_exceptions["risk_level"] == "HIGH").sum()
    )

    mismatch_mask = (
        all_exceptions["reconciliation_status"] == "AMOUNT_MISMATCH"
    )

    mismatch_exposure = numeric_series(
        all_exceptions.loc[mismatch_mask],
        "amount_difference",
    ).abs().sum()

    missing_payment_mask = (
        all_exceptions["reconciliation_status"] == "MISSING_PAYMENT"
    )

    missing_bank_mask = (
        all_exceptions["reconciliation_status"] == "MISSING_BANK_RECORD"
    )

    missing_payment_exposure = numeric_series(
        all_exceptions.loc[missing_payment_mask],
        "bank_amount",
    ).abs().sum()

    missing_bank_exposure = numeric_series(
        all_exceptions.loc[missing_bank_mask],
        "payment_amount",
    ).abs().sum()

    impact1, impact2, impact3 = st.columns(3)

    impact1.metric(
        "Amount mismatches",
        f"{amount_mismatch_count:,}",
    )
    impact2.metric(
        "Missing payment records",
        f"{missing_payment_count:,}",
    )
    impact3.metric(
        "Missing bank records",
        f"{missing_bank_count:,}",
    )

    impact4, impact5, impact6 = st.columns(3)

    impact4.metric(
        "High-risk exceptions",
        f"{high_risk_count:,}",
    )
    impact5.metric(
        "Mismatch difference",
        format_inr(mismatch_exposure),
    )
    impact6.metric(
        "Combined missing-record amount",
        format_inr(
            missing_payment_exposure + missing_bank_exposure
        ),
    )

    st.caption(
        "Exposure figures are estimates based on missing or differing "
        "transaction amounts, not confirmed financial losses."
    )

    # ------------------------------------------------------------
    # Persistent investigation workflow for demo transactions
    # ------------------------------------------------------------
    st.divider()
    st.header("Demo Transaction Investigation")

    st.write(
        "Saved demo investigation cases are written to "
        "reports/investigation_log.csv."
    )

    investigation_log = read_investigation_log()

    investigatable = display_data[
        display_data["reconciliation_status"] != "MATCHED"
    ].copy()

    if investigatable.empty:
        st.info(
            "No demo exceptions match your filters. "
            "Change the filters to investigate an exception."
        )

    else:
        transaction_options = (
            investigatable["transaction_id"].astype(str).tolist()
        )

        selected_transaction = st.selectbox(
            "Select demo transaction",
            options=transaction_options,
            key="demo_investigation_transaction",
        )

        selected_row = investigatable[
            investigatable["transaction_id"].astype(str)
            == selected_transaction
        ].iloc[0]

        previous = investigation_log[
            investigation_log["transaction_id"].astype(str)
            == selected_transaction
        ]

        if not previous.empty:
            previous_record = previous.iloc[-1]

            default_status = str(
                previous_record["investigation_status"]
            )

            if default_status not in INVESTIGATION_STATUSES:
                default_status = "Open"

            default_notes = previous_record["analyst_notes"]

        else:
            default_status = "Open"
            default_notes = ""

        st.write(
            f"**Issue:** {selected_row['reconciliation_status']}  \n"
            f"**Risk:** {selected_row['risk_level']} "
            f"({selected_row['risk_score']}/100)"
        )

        with st.form("demo_investigation_form"):
            new_status = st.selectbox(
                "Investigation status",
                options=INVESTIGATION_STATUSES,
                index=INVESTIGATION_STATUSES.index(default_status),
            )

            analyst_notes = st.text_area(
                "Investigation notes",
                value=(
                    "" if pd.isna(default_notes)
                    else str(default_notes)
                ),
                placeholder=(
                    "Example: Checked settlement report; "
                    "awaiting bank confirmation."
                ),
            )

            submitted = st.form_submit_button(
                "Save demo investigation"
            )

        if submitted:
            new_record = {
                "transaction_id": selected_transaction,
                "reconciliation_status": selected_row[
                    "reconciliation_status"
                ],
                "risk_score": selected_row["risk_score"],
                "risk_level": selected_row["risk_level"],
                "investigation_status": new_status,
                "analyst_notes": analyst_notes,
                "updated_at": datetime.now().isoformat(
                    timespec="seconds"
                ),
            }

            investigation_log = investigation_log[
                investigation_log["transaction_id"].astype(str)
                != selected_transaction
            ]

            investigation_log = pd.concat(
                [
                    investigation_log,
                    pd.DataFrame([new_record]),
                ],
                ignore_index=True,
            )

            REPORTS_DIR.mkdir(
                parents=True,
                exist_ok=True,
            )

            investigation_log.to_csv(
                INVESTIGATION_FILE,
                index=False,
            )

            st.success(
                f"Investigation saved for {selected_transaction}."
            )
            st.rerun()

    # ------------------------------------------------------------
    # Demo investigation overview
    # ------------------------------------------------------------
    st.subheader("Demo Investigation Overview")

    investigation_log = read_investigation_log()

    if investigation_log.empty:
        open_cases = 0
        review_cases = 0
        resolved_cases = 0
        false_positive_cases = 0

    else:
        case_statuses = (
            investigation_log["investigation_status"].astype(str)
        )

        open_cases = int((case_statuses == "Open").sum())
        review_cases = int(
            (case_statuses == "Under Review").sum()
        )
        resolved_cases = int(
            (case_statuses == "Resolved").sum()
        )
        false_positive_cases = int(
            (case_statuses == "False Positive").sum()
        )

    case1, case2, case3, case4 = st.columns(4)

    case1.metric("Open", open_cases)
    case2.metric("Under Review", review_cases)
    case3.metric("Resolved", resolved_cases)
    case4.metric("False Positive", false_positive_cases)

    st.subheader("Saved Demo Investigation Cases")

    if investigation_log.empty:
        st.info("No demo investigation cases have been saved.")
    else:
        saved_cases = investigation_log.sort_values(
            by="updated_at",
            ascending=False,
            na_position="last",
        )

        st.dataframe(
            saved_cases,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download demo investigation log",
            data=safe_download_csv(saved_cases),
            file_name="reconcileai_investigation_log.csv",
            mime="text/csv",
            key="demo_investigation_download",
        )

    # ------------------------------------------------------------
    # Executive summary
    # ------------------------------------------------------------
    st.divider()
    st.subheader("Demo Executive Summary Export")

    summary_rows = [
        {
            "Metric": "Transactions Assessed",
            "Value": total_transactions,
        },
        {
            "Metric": "Matched Transactions",
            "Value": matched_count,
        },
        {
            "Metric": "Reconciliation Exceptions",
            "Value": exception_count,
        },
        {
            "Metric": "Duplicate Payment Records",
            "Value": duplicate_count,
        },
        {
            "Metric": "Amount Mismatches",
            "Value": amount_mismatch_count,
        },
        {
            "Metric": "Missing Payment Records",
            "Value": missing_payment_count,
        },
        {
            "Metric": "Missing Bank Records",
            "Value": missing_bank_count,
        },
        {
            "Metric": "High-Risk Exceptions",
            "Value": high_risk_count,
        },
        {
            "Metric": "Mismatch Difference (INR)",
            "Value": round(float(mismatch_exposure), 2),
        },
        {
            "Metric": "Missing-Record Exposure (INR)",
            "Value": round(
                float(
                    missing_payment_exposure
                    + missing_bank_exposure
                ),
                2,
            ),
        },
        {
            "Metric": "Saved Investigation Cases",
            "Value": len(investigation_log),
        },
    ]

    summary_df = pd.DataFrame(summary_rows)

    st.dataframe(
        summary_df,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download demo executive summary (CSV)",
        data=safe_download_csv(summary_df),
        file_name="reconcileai_executive_summary.csv",
        mime="text/csv",
        key="demo_summary_download",
    )


# ================================================================
# 9. FOOTER
# ================================================================
st.divider()

st.caption(
    "ReconcileAI is a decision-support prototype. Matching is based on "
    "the selected reference and amount columns; it does not establish "
    "fraud or prove that a transaction is legitimate. Validate results "
    "against the original records before making financial decisions."
)
