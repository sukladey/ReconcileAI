
import pandas as pd
import pytest

from app.generate_data import generate_datasets
from app.reconcile import reconcile_transactions


@pytest.fixture(scope="module")
def reconciliation_output():
    # Rebuild deterministic sample data and run the engine.
    generate_datasets()
    result, summary = reconcile_transactions()
    return result, summary


def test_expected_reconciliation_counts(reconciliation_output):
    _, summary = reconciliation_output

    counts = dict(zip(summary["metric"], summary["count"]))

    assert counts["bank_transactions"] == 1000
    assert counts["payment_records"] == 1005
    assert counts["unique_payment_transactions"] == 990
    assert counts["duplicate_payment_records"] == 15
    assert counts["matched"] == 945
    assert counts["missing_payment"] == 30
    assert counts["missing_bank_record"] == 20
    assert counts["amount_mismatch"] == 25


def test_all_transactions_have_a_status(reconciliation_output):
    result, _ = reconciliation_output

    assert result["reconciliation_status"].notna().all()


def test_transaction_ids_are_unique_in_reconciliation(reconciliation_output):
    result, _ = reconciliation_output

    assert result["transaction_id"].is_unique


def test_duplicate_report_contains_15_records():
    duplicates = pd.read_csv("reports/duplicate_payments.csv")

    assert len(duplicates) == 15
    assert (duplicates["issue"] == "DUPLICATE_PAYMENT").all()


def test_amount_mismatches_have_nonzero_difference(reconciliation_output):
    result, _ = reconciliation_output

    mismatches = result[
        result["reconciliation_status"] == "AMOUNT_MISMATCH"
    ]

    assert len(mismatches) == 25
    assert mismatches["amount_difference"].notna().all()
    assert (mismatches["amount_difference"] != 0).all()
