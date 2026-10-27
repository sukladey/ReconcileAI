
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"

INPUT_FILE = REPORTS_DIR / "reconciliation_results.csv"
OUTPUT_FILE = REPORTS_DIR / "risk_scored_transactions.csv"



def calculate_risk(row):
    score = 0
    reasons = []

    status = row["reconciliation_status"]

    if status == "MISSING_PAYMENT":
        score += 50
        reasons.append("Bank transaction missing in payment system")

    elif status == "MISSING_BANK_RECORD":
        score += 60
        reasons.append("Payment transaction missing in bank records")

    elif status == "AMOUNT_MISMATCH":
        score += 40
        reasons.append("Transaction amount mismatch")

    # Use the larger available transaction amount.
    bank_amount = row.get("bank_amount", 0)
    payment_amount = row.get("payment_amount", 0)

    bank_amount = (
        float(bank_amount) if pd.notna(bank_amount) else 0.0
    )
    payment_amount = (
        float(payment_amount) if pd.notna(payment_amount) else 0.0
    )

    transaction_value = max(abs(bank_amount), abs(payment_amount))

    # Prioritize high-value transactions for investigation.
    if transaction_value >= 10000 and score > 0:
        score += 20
        reasons.append("High-value transaction")

    # Prioritize large amount discrepancies.
    difference = row.get("amount_difference", 0)

    if pd.notna(difference) and abs(float(difference)) >= 1000:
        score += 20
        reasons.append("Large amount discrepancy")

    score = min(score, 100)

    if score >= 70:
        risk_level = "HIGH"
    elif score >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return pd.Series(
        {
            "risk_score": score,
            "risk_level": risk_level,
            "risk_reasons": (
                "; ".join(reasons) if reasons else "No rule triggered"
            ),
        }
    )


def run_risk_scoring():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found. Run python -m app.reconcile first."
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    data = pd.read_csv(INPUT_FILE)

    risk_columns = data.apply(calculate_risk, axis=1)
    scored = pd.concat([data, risk_columns], axis=1)

    scored = scored.sort_values(
        by=["risk_score", "transaction_id"],
        ascending=[False, True],
    )

    scored.to_csv(OUTPUT_FILE, index=False)

    print("\nRISK SCORING COMPLETED")
    print("-" * 35)
    print(f"Transactions assessed: {len(scored)}")
    print("\nRisk levels:")
    print(scored["risk_level"].value_counts().to_string())

    print("\nHighest-priority transactions:")
    print(
        scored[
            [
                "transaction_id",
                "reconciliation_status",
                "risk_score",
                "risk_level",
                "risk_reasons",
            ]
        ].head(10).to_string(index=False)
    )

    print(f"\nSaved report: {OUTPUT_FILE}")

    return scored


if __name__ == "__main__":
    run_risk_scoring()
