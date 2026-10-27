
import pandas as pd

from app.risk_scoring import calculate_risk, run_risk_scoring


def test_missing_payment_receives_medium_risk():
    row = pd.Series({
        "reconciliation_status": "MISSING_PAYMENT",
        "amount_difference": float("nan"),
    })

    result = calculate_risk(row)

    assert result["risk_score"] == 50
    assert result["risk_level"] == "MEDIUM"


def test_missing_bank_record_receives_medium_risk():
    row = pd.Series({
        "reconciliation_status": "MISSING_BANK_RECORD",
        "amount_difference": float("nan"),
    })

    result = calculate_risk(row)

    assert result["risk_score"] == 60
    assert result["risk_level"] == "MEDIUM"


def test_large_amount_mismatch_gets_additional_score():
    row = pd.Series({
        "reconciliation_status": "AMOUNT_MISMATCH",
        "amount_difference": 1500.00,
    })

    result = calculate_risk(row)

    assert result["risk_score"] == 60
    assert result["risk_level"] == "MEDIUM"
    assert "Large amount discrepancy" in result["risk_reasons"]


def test_risk_report_has_complete_scores():
    scored = run_risk_scoring()

    assert len(scored) == 1020
    assert scored["risk_score"].notna().all()
    assert scored["risk_level"].notna().all()
    assert scored["risk_score"].between(0, 100).all()


def test_risk_report_is_sorted_highest_first():
    scored = run_risk_scoring()

    scores = scored["risk_score"].tolist()

    assert scores == sorted(scores, reverse=True)
