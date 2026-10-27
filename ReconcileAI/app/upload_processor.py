
"""CSV upload processing for ReconcileAI.

Processes payment and bank statement CSV data in memory.
Does not save uploaded data to disk or send it to an external service.
"""

from __future__ import annotations

from io import BytesIO, StringIO
from typing import Any

import pandas as pd


PAYMENT_COLUMNS = {
    "payment_reference",
    "payment_amount",
    "customer",
    "payment_date",
}

BANK_COLUMNS = {
    "bank_reference",
    "bank_amount",
    "bank_date",
    "description",
}


def _read_csv(file: Any) -> pd.DataFrame:
    """Read a CSV from a path, bytes, file-like object, or uploaded file."""
    if isinstance(file, pd.DataFrame):
        return file.copy()

    if isinstance(file, bytes):
        return pd.read_csv(BytesIO(file))

    if isinstance(file, str):
        # Treat a string containing CSV text as CSV content.
        return pd.read_csv(StringIO(file))

    if hasattr(file, "getvalue"):
        content = file.getvalue()
        if isinstance(content, bytes):
            return pd.read_csv(BytesIO(content))
        return pd.read_csv(StringIO(content))

    if hasattr(file, "read"):
        content = file.read()
        if isinstance(content, bytes):
            return pd.read_csv(BytesIO(content))
        return pd.read_csv(StringIO(content))

    raise TypeError(
        "Unsupported CSV input. Provide CSV bytes, text, a DataFrame, "
        "a file-like object, or an uploaded file."
    )


def _clean_reference(series: pd.Series) -> pd.Series:
    """Normalize references and treat blank values as missing."""
    result = series.astype("string").str.strip()
    return result.mask(result.eq(""))


def _prepare(
    file: Any,
    required_columns: set[str],
    reference_column: str,
    amount_column: str,
) -> pd.DataFrame:
    """Load, validate, and normalize one transaction file."""
    df = _read_csv(file)
    df.columns = [str(column).strip().lower() for column in df.columns]

    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(
            "CSV is missing required columns: "
            + ", ".join(sorted(missing))
        )

    df = df.copy()
    df[reference_column] = _clean_reference(df[reference_column])

    amounts = pd.to_numeric(df[amount_column], errors="coerce")
    invalid_amounts = amounts.isna()

    if invalid_amounts.any():
        rows = (df.index[invalid_amounts] + 2).tolist()
        raise ValueError(
            f"Invalid or missing values in '{amount_column}' "
            f"at CSV row(s): {rows[:20]}"
        )

    df[amount_column] = amounts.round(2)

    return df


def process_reconciliation(
    payment_file: Any,
    bank_file: Any,
    amount_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Reconcile payment records against bank statement records.

    Matching policy:
    - A reference appearing once in each file is compared by amount.
    - Repeated references are flagged as duplicates and are not
      automatically matched, to avoid ambiguous reconciliation.
    - Blank references are flagged as missing references.
    - Records with no counterpart are classified as missing in bank
      or bank-only.

    Returns a dictionary containing transaction results, summary KPIs,
    and the payment and bank dataframes.
    """
    if amount_tolerance < 0:
        raise ValueError("amount_tolerance cannot be negative.")

    payments = _prepare(
        payment_file,
        PAYMENT_COLUMNS,
        "payment_reference",
        "payment_amount",
    )
    bank = _prepare(
        bank_file,
        BANK_COLUMNS,
        "bank_reference",
        "bank_amount",
    )

    payments = payments.reset_index(drop=True)
    bank = bank.reset_index(drop=True)

    payments["_payment_row"] = range(len(payments))
    bank["_bank_row"] = range(len(bank))

    payment_counts = payments["payment_reference"].value_counts()
    bank_counts = bank["bank_reference"].value_counts()

    payment_duplicate_refs = set(
        payment_counts[payment_counts > 1].index
    )
    bank_duplicate_refs = set(
        bank_counts[bank_counts > 1].index
    )

    all_references = set(payments["payment_reference"].dropna()) | set(
        bank["bank_reference"].dropna()
    )

    results: list[dict[str, Any]] = []

    def add_result(
        reference: Any,
        payment: pd.Series | None,
        bank_record: pd.Series | None,
        status: str,
        issue: str = "",
    ) -> None:
        payment_amount = (
            round(float(payment["payment_amount"]), 2)
            if payment is not None
            else None
        )
        bank_amount = (
            round(float(bank_record["bank_amount"]), 2)
            if bank_record is not None
            else None
        )

        difference = (
            round(payment_amount - bank_amount, 2)
            if payment_amount is not None and bank_amount is not None
            else None
        )

        results.append(
            {
                "payment_reference": (
                    payment["payment_reference"]
                    if payment is not None
                    else None
                ),
                "bank_reference": (
                    bank_record["bank_reference"]
                    if bank_record is not None
                    else None
                ),
                "reference": reference,
                "customer": (
                    payment["customer"]
                    if payment is not None
                    else None
                ),
                "payment_date": (
                    payment["payment_date"]
                    if payment is not None
                    else None
                ),
                "bank_date": (
                    bank_record["bank_date"]
                    if bank_record is not None
                    else None
                ),
                "description": (
                    bank_record["description"]
                    if bank_record is not None
                    else None
                ),
                "payment_amount": payment_amount,
                "bank_amount": bank_amount,
                "difference": difference,
                "status": status,
                "issue": issue,
            }
        )

    # References that occur on both sides or only one side.
    for reference in sorted(all_references, key=str):
        p_rows = payments[
            payments["payment_reference"].eq(reference)
        ]
        b_rows = bank[bank["bank_reference"].eq(reference)]

        is_duplicate = (
            reference in payment_duplicate_refs
            or reference in bank_duplicate_refs
        )

        if is_duplicate:
            issue = "Duplicate reference"
            if reference in payment_duplicate_refs:
                issue += " in payment file"
            if reference in bank_duplicate_refs:
                issue += " in bank file"

            # Preserve each original row instead of silently collapsing it.
            for _, payment in p_rows.iterrows():
                add_result(
                    reference,
                    payment,
                    None,
                    "Duplicate",
                    issue,
                )
            for _, bank_record in b_rows.iterrows():
                add_result(
                    reference,
                    None,
                    bank_record,
                    "Duplicate",
                    issue,
                )
            continue

        if len(p_rows) == 1 and len(b_rows) == 1:
            payment = p_rows.iloc[0]
            bank_record = b_rows.iloc[0]

            difference = round(
                float(payment["payment_amount"])
                - float(bank_record["bank_amount"]),
                2,
            )

            if abs(difference) <= amount_tolerance:
                add_result(reference, payment, bank_record, "Matched")
            else:
                add_result(
                    reference,
                    payment,
                    bank_record,
                    "Amount Mismatch",
                    "Payment and bank amounts differ",
                )

        elif len(p_rows) == 1:
            add_result(
                reference,
                p_rows.iloc[0],
                None,
                "Missing in Bank",
                "Payment record has no bank counterpart",
            )

        elif len(b_rows) == 1:
            add_result(
                reference,
                None,
                b_rows.iloc[0],
                "Bank Only",
                "Bank record has no payment counterpart",
            )

    # Preserve rows whose references are blank.
    for _, payment in payments[
        payments["payment_reference"].isna()
    ].iterrows():
        add_result(
            None,
            payment,
            None,
            "Missing Reference",
            "Payment reference is blank",
        )

    for _, bank_record in bank[
        bank["bank_reference"].isna()
    ].iterrows():
        add_result(
            None,
            None,
            bank_record,
            "Missing Reference",
            "Bank reference is blank",
        )

    results_df = pd.DataFrame(results)

    payment_total = round(float(payments["payment_amount"].sum()), 2)
    bank_total = round(float(bank["bank_amount"].sum()), 2)

    status_counts = (
        results_df["status"].value_counts().to_dict()
        if not results_df.empty
        else {}
    )

    summary = {
        "payment_rows": len(payments),
        "bank_rows": len(bank),
        "result_rows": len(results_df),
        "matched": int(status_counts.get("Matched", 0)),
        "unmatched": int(
            len(results_df) - status_counts.get("Matched", 0)
        ),
        "amount_mismatches": int(
            status_counts.get("Amount Mismatch", 0)
        ),
        "missing_in_bank": int(status_counts.get("Missing in Bank", 0)),
        "bank_only": int(status_counts.get("Bank Only", 0)),
        "duplicate_flags": int(status_counts.get("Duplicate", 0)),
        "missing_references": int(
            status_counts.get("Missing Reference", 0)
        ),
        "payment_total": payment_total,
        "bank_total": bank_total,
        "total_difference": round(payment_total - bank_total, 2),
    }

    return {
        "summary": summary,
        "results": results_df,
        "payments": payments.drop(
            columns=["_payment_row"], errors="ignore"
        ),
        "bank": bank.drop(columns=["_bank_row"], errors="ignore"),
    }


# Backwards-friendly alias for callers using a shorter function name.
reconcile = process_reconciliation
