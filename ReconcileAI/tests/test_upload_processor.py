from io import StringIO
from app.upload_processor import process_reconciliation

payments = StringIO(
    "payment_reference,payment_amount,customer,payment_date\n"
    "TXN001,100.00,Customer A,2026-10-20\n"
    "TXN002,250.00,Customer B,2026-10-20\n"
)

bank = StringIO(
    "bank_reference,bank_amount,bank_date,description\n"
    "TXN001,100.00,2026-10-20,Settlement A\n"
    "TXN002,260.00,2026-10-20,Settlement B\n"
)

result = process_reconciliation(payments, bank)

print("\nSummary:")
print(result["summary"])

print("\nTransaction results:")
print(result["results"][
    ["reference", "payment_amount", "bank_amount", "status"]
].to_string(index=False))

assert result["summary"]["matched"] == 1
assert result["summary"]["amount_mismatches"] == 1

print("\nTEST PASSED")
