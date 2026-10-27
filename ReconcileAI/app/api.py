

from pathlib import Path
import json

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.upload_processor import process_reconciliation

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="ReconcileAI API",
    description="Payment and bank reconciliation service",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "ReconcileAI"}


@app.post("/api/reconcile")
async def reconcile_files(
    payments_file: UploadFile = File(...),
    bank_file: UploadFile = File(...),
):
    for upload in (payments_file, bank_file):
        if not upload.filename or not upload.filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=400,
                detail="Both uploaded files must be CSV files.",
            )

    try:
        payment_bytes = await payments_file.read()
        bank_bytes = await bank_file.read()

        if not payment_bytes or not bank_bytes:
            raise HTTPException(
                status_code=400,
                detail="Both CSV files must contain data.",
            )

        result = process_reconciliation(
            payment_file=payment_bytes,
            bank_file=bank_bytes,
        )

        records = json.loads(
            result["results"].to_json(
                orient="records",
                date_format="iso",
                force_ascii=False,
            )
        )

        return {
            "summary": result["summary"],
            "results": records,
        }

    except HTTPException:
        raise
    except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print(f"Reconciliation error: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Reconciliation failed. Check the server terminal.",
        ) from exc
    finally:
        await payments_file.close()
        await bank_file.close()


@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")


app.mount(
    "/",
    StaticFiles(directory=BASE_DIR),
    name="frontend",
)
# '@ | Set-Content -Path .\app\api.py -Encoding utf8
