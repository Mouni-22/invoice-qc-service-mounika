"""
FastAPI server for the Invoice QC project.

Main endpoints:
- GET  /health                → quick health check
- POST /validate-json         → validate already-structured invoice JSON
- POST /extract-and-validate  → (optional) upload PDFs, extract + validate in one go
"""

from typing import List
from datetime import datetime
from pathlib import Path
import tempfile
import shutil
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from invoice_qc.models import Invoice
from invoice_qc.validator import InvoiceValidator
from invoice_qc.extractor import PDFInvoiceExtractor

# basic logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Invoice QC API",
    description="Simple service to validate invoice JSON and (optionally) extract from PDFs",
    version="1.0.0",
)

# CORS – open for assignment/demo purposes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in a real app this should be restricted
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

validator = InvoiceValidator()
extractor = PDFInvoiceExtractor()


# ----------------------------------------------------------------------
# Basic endpoints
# ----------------------------------------------------------------------
@app.get("/")
async def root():
    """Root endpoint with a bit of info."""
    return {
        "service": "invoice-qc",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "validate_json": "/validate-json",
            "extract_and_validate": "/extract-and-validate-pdfs",
        },
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Simple health check used by tests/monitoring."""
    return {
        "status": "ok",
        "service": "invoice-qc",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ----------------------------------------------------------------------
# JSON validation
# ----------------------------------------------------------------------
@app.post("/validate-json")
async def validate_json(invoices: List[Invoice]):
    """
    Validate one or more invoices passed as JSON.

    Request body: list of Invoice objects
    Response:
      {
        "results": [...],
        "summary": {...}
      }
    """
    try:
        logger.info("Validating %d invoices", len(invoices))
        result = validator.validate_batch(invoices)

        return {
            "results": [r.model_dump(mode="json") for r in result["results"]],
            "summary": result["summary"].model_dump(mode="json"),
        }
    except Exception as exc:
        logger.exception("Validation failed")
        raise HTTPException(status_code=400, detail=str(exc))


# ----------------------------------------------------------------------
# Optional: PDF upload → extract + validate
# ----------------------------------------------------------------------
@app.post("/extract-and-validate-pdfs")
async def extract_and_validate_pdfs(files: List[UploadFile] = File(...)):
    """
    Upload one or more PDF files, extract invoice data and run validation.

    This is a "nice to have" endpoint for the assignment.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type for {f.filename}. Only PDF files are accepted.",
            )

    try:
        invoices: List[Invoice] = []

        # Use a temp directory for saving the uploaded PDFs
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            for upload in files:
                dest = tmp_path / upload.filename
                with dest.open("wb") as buffer:
                    shutil.copyfileobj(upload.file, buffer)

                # extract a single invoice from this PDF
                inv = extractor.extract(str(dest))
                invoices.append(inv)

        # run validation on what we extracted
        result = validator.validate_batch(invoices)

        return {
            "extracted": [inv.model_dump(mode="json") for inv in invoices],
            "validation_results": [
                r.model_dump(mode="json") for r in result["results"]
            ],
            "summary": result["summary"].model_dump(mode="json"),
        }

    except HTTPException:
        # just re-raise those
        raise
    except Exception as exc:
        logger.exception("Error during extract + validate")
        raise HTTPException(status_code=500, detail=str(exc))


# ----------------------------------------------------------------------
# Global error handler
# ----------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch-all exception handler to avoid leaking stack traces."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": str(exc),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
