
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

BANK_FILE = DATA_DIR / "bank_transactions.csv"
PAYMENT_FILE = DATA_DIR / "payment_transactions.csv"


def reconcile_transactions():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load both datasets.
    bank = pd.read_csv(BANK_FILE)
    payments = pd.read_csv(PAYMENT_FILE)

    # Validate required columns.
    required_bank = {
        "transaction_id", "transaction_date",
        "amount", "payment_method", "status"
    }
    required_payments = required_bank | {"payment_id"}

    if not required_bank.issubset(bank.columns):
        raise ValueError("Bank dataset is missing required columns.")

    if not required_payments.issubset(payments.columns):
        raise ValueError("Payment dataset is missing required columns.")

    # Detect duplicate transaction IDs in the payment system.
    duplicate_mask = payments.duplicated(
        subset=["transaction_id"], keep="first"
    )
    duplicate_count = int(duplicate_mask.sum())

    duplicate_report = payments.loc[duplicate_mask].copy()
    duplicate_report["issue"] = "DUPLICATE_PAYMENT"
    duplicate_report.to_csv(
        REPORTS_DIR / "duplicate_payments.csv", index=False
    )

    # Keep one record per transaction ID for reconciliation.
    payments_unique = payments.drop_duplicates(
        subset=["transaction_id"], keep="first"
    ).copy()

    # Prefix source-specific columns to make comparisons clear.
    bank = bank.rename(
        columns={
            "transaction_date": "bank_date",
            "amount": "bank_amount",
            "payment_method": "bank_method",
            "status": "bank_status",
        }
    )

    payments_unique = payments_unique.rename(
        columns={
            "transaction_date": "payment_date",
            "amount": "payment_amount",
            "payment_method": "payment_method",
            "status": "payment_status",
        }
    )

    # Match records using transaction_id.
    result = bank.merge(
        payments_unique,
        on="transaction_id",
        how="outer",
        indicator=True,
        validate="one_to_one",
    )

    # Assign one primary reconciliation status to every row.
    conditions = [
        result["_merge"].eq("left_only"),
        result["_merge"].eq("right_only"),
        result["bank_amount"].notna()
        & result["payment_amount"].notna()
        & ~result["bank_amount"].eq(result["payment_amount"]),
    ]

    labels = [
        "MISSING_PAYMENT",
        "MISSING_BANK_RECORD",
        "AMOUNT_MISMATCH",
    ]

    result["reconciliation_status"] = "MATCHED"
    result.loc[conditions[0], "reconciliation_status"] = labels[0]
    result.loc[conditions[1], "reconciliation_status"] = labels[1]
    result.loc[conditions[2], "reconciliation_status"] = labels[2]

    result["amount_difference"] = (
        result["payment_amount"] - result["bank_amount"]
    ).round(2)

    result = result.drop(columns=["_merge"])

    # Save complete reconciliation results.
    result.to_csv(
        REPORTS_DIR / "reconciliation_results.csv", index=False
    )

    # Build a concise summary report.
    counts = result["reconciliation_status"].value_counts()

    summary = pd.DataFrame(
        [
            {"metric": "bank_transactions", "count": len(bank)},
            {"metric": "payment_records", "count": len(payments)},
            {
                "metric": "unique_payment_transactions",
                "count": len(payments_unique),
            },
            {"metric": "duplicate_payment_records", "count": duplicate_count},
            {
                "metric": "matched",
                "count": int(counts.get("MATCHED", 0)),
            },
            {
                "metric": "missing_payment",
                "count": int(counts.get("MISSING_PAYMENT", 0)),
            },
            {
                "metric": "missing_bank_record",
                "count": int(counts.get("MISSING_BANK_RECORD", 0)),
            },
            {
                "metric": "amount_mismatch",
                "count": int(counts.get("AMOUNT_MISMATCH", 0)),
            },
        ]
    )

    summary.to_csv(REPORTS_DIR / "reconciliation_summary.csv", index=False)

    print("\nRECONCILIATION COMPLETED")
    print("-" * 35)
    print(summary.to_string(index=False))
    print(f"\nDetailed results: {REPORTS_DIR / 'reconciliation_results.csv'}")
    print(f"Summary report: {REPORTS_DIR / 'reconciliation_summary.csv'}")
    print(f"Duplicate report: {REPORTS_DIR / 'duplicate_payments.csv'}")

    return result, summary


if __name__ == "__main__":
    reconcile_transactions()
