
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 42


def generate_datasets():
    rng = np.random.default_rng(RANDOM_SEED)
    transaction_count = 1000

    transaction_ids = [
        f"TXN{i:05d}" for i in range(1, transaction_count + 1)
    ]

    dates = pd.Timestamp("2026-09-01") + pd.to_timedelta(
        rng.integers(0, 30, transaction_count), unit="D"
    )

    amounts = np.round(rng.uniform(100, 15000, transaction_count), 2)

    payment_methods = rng.choice(
        ["UPI", "CARD", "NEFT", "IMPS"],
        size=transaction_count,
        p=[0.45, 0.25, 0.15, 0.15],
    )

    bank = pd.DataFrame(
        {
            "transaction_id": transaction_ids,
            "transaction_date": dates,
            "amount": amounts,
            "payment_method": payment_methods,
            "status": "SETTLED",
        }
    )

    # Payment system initially mirrors bank transactions.
    payments = bank.copy()
    payments["payment_id"] = [
        f"PAY{i:05d}" for i in range(1, transaction_count + 1)
    ]
    payments = payments[
        [
            "payment_id",
            "transaction_id",
            "transaction_date",
            "amount",
            "payment_method",
            "status",
        ]
    ]

    # Inject realistic reconciliation problems.
    # 1. Remove 30 payment records: bank-only transactions.
    missing_indices = rng.choice(
        payments.index, size=30, replace=False
    )
    payments = payments.drop(index=missing_indices)

    # 2. Alter the amount on 25 remaining payment records.
    mismatch_indices = rng.choice(
        payments.index, size=25, replace=False
    )
    payments.loc[mismatch_indices, "amount"] = np.round(
        payments.loc[mismatch_indices, "amount"] + rng.choice(
            [-50, -20, 20, 50], size=25
        ),
        2,
    )

    # 3. Add 20 payment records not found in the bank dataset.
    extra_count = 20
    extra_payments = pd.DataFrame(
        {
            "payment_id": [
                f"PAYX{i:05d}" for i in range(1, extra_count + 1)
            ],
            "transaction_id": [
                f"EXT{i:05d}" for i in range(1, extra_count + 1)
            ],
            "transaction_date": pd.Timestamp("2026-09-01")
            + pd.to_timedelta(
                rng.integers(0, 30, extra_count), unit="D"
            ),
            "amount": np.round(
                rng.uniform(100, 15000, extra_count), 2
            ),
            "payment_method": rng.choice(
                ["UPI", "CARD", "NEFT", "IMPS"], extra_count
            ),
            "status": "SETTLED",
        }
    )

    payments = pd.concat(
        [payments, extra_payments], ignore_index=True
    )

    # 4. Duplicate 15 payment records to test duplicate detection.
    duplicate_records = payments.sample(
        n=15, random_state=RANDOM_SEED
    ).copy()
    duplicate_records["payment_id"] = [
        f"DUP{i:05d}" for i in range(1, 16)
    ]
    payments = pd.concat(
        [payments, duplicate_records], ignore_index=True
    )

    bank.to_csv(DATA_DIR / "bank_transactions.csv", index=False)
    payments.to_csv(DATA_DIR / "payment_transactions.csv", index=False)

    print("Dataset generation successful.")
    print(f"Bank transactions: {len(bank)}")
    print(f"Payment records: {len(payments)}")
    print(f"Bank file: {DATA_DIR / 'bank_transactions.csv'}")
    print(f"Payment file: {DATA_DIR / 'payment_transactions.csv'}")


if __name__ == "__main__":
    generate_datasets()
