"""
Data models for the Invoice QC project.

I designed this schema to cover the common fields needed for:
- extracting invoice data from PDFs
- validating basic business rules
- running some simple checks on totals and tax

This is meant for general B2B invoices (multi-currency, with line items).
"""

from typing import Optional, List
from datetime import datetime, date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Currency(str, Enum):
    """Supported invoice currencies."""
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"
    INR = "INR"


class LineItem(BaseModel):
    """
    Single line item on an invoice.

    Fields:
    - description: what was sold (product/service)
    - quantity: how many units
    - unit_price: price per unit
    - line_total: quantity * unit_price
    - tax_rate: optional % tax for this line (e.g. 19.0 means 19%)
    """

    description: str
    quantity: float
    unit_price: float
    line_total: float
    tax_rate: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "description": "Consulting services",
                "quantity": 10.0,
                "unit_price": 150.0,
                "line_total": 1500.0,
                "tax_rate": 19.0,
            }
        }


class Invoice(BaseModel):
    """
    Main invoice model used across extraction, validation and the API.

    Breakdown of the fields:

    1) Identifiers
       - invoice_number: unique ID from the seller
       - external_reference: buyer's internal reference / PO number

    2) Parties
       - seller_*: who issued the invoice
       - buyer_*: who is paying

    3) Dates
       - invoice_date: when invoice was created
       - due_date: when payment is expected

    4) Money fields
       - currency: invoicing currency
       - net_total: amount before tax
       - tax_amount: total tax value
       - gross_total: net + tax

    5) Items and extra info
       - line_items: detailed breakdown
       - payment_terms / notes: free text
       - source_file / extracted_at: useful to trace back the PDF and run history
    """

    # Identifiers
    invoice_number: str = Field(..., description="Unique invoice number from the seller")
    external_reference: Optional[str] = Field(
        None, description="Buyer's PO number or other reference"
    )

    # Seller information
    seller_name: str = Field(..., description="Legal name of the seller")
    seller_address: Optional[str] = Field(None, description="Seller address")
    seller_tax_id: Optional[str] = Field(None, description="Seller tax/VAT ID")

    # Buyer information
    buyer_name: str = Field(..., description="Legal name of the buyer")
    buyer_address: Optional[str] = Field(None, description="Buyer address")
    buyer_tax_id: Optional[str] = Field(None, description="Buyer tax/VAT ID")

    # Dates
    invoice_date: date = Field(..., description="Date when the invoice was issued")
    due_date: Optional[date] = Field(None, description="Payment due date")

    # Financial details
    currency: Currency = Field(
        default=Currency.EUR,
        description="Invoice currency (defaults to EUR)",
    )
    net_total: float = Field(..., description="Total amount before tax")
    tax_amount: float = Field(..., description="Total tax amount")
    gross_total: float = Field(..., description="Total including tax")

    # Line items
    line_items: List[LineItem] = Field(
        default_factory=list,
        description="List of individual invoice lines",
    )

    # Extra metadata
    payment_terms: Optional[str] = Field(
        None, description="Payment terms (e.g. 'Net 30')"
    )
    notes: Optional[str] = Field(
        None, description="Any additional notes or comments"
    )

    # Extraction metadata (filled by the extractor)
    source_file: Optional[str] = Field(
        None, description="Original PDF filename (for traceability)"
    )
    extracted_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        description="When this invoice was parsed from PDF",
    )

    @field_validator("net_total", "tax_amount", "gross_total")
    @classmethod
    def non_negative_amounts(cls, v: float) -> float:
        """Basic guard: totals should not be negative."""
        if v < 0:
            raise ValueError("Amounts cannot be negative")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "invoice_number": "INV-2024-001",
                "external_reference": "PO-12345",
                "seller_name": "Tech Solutions GmbH",
                "seller_address": "Hauptstraße 123, 10115 Berlin",
                "seller_tax_id": "DE123456789",
                "buyer_name": "Example Corp AG",
                "buyer_address": "Musterstraße 45, 80331 München",
                "buyer_tax_id": "DE987654321",
                "invoice_date": "2024-01-15",
                "due_date": "2024-02-14",
                "currency": "EUR",
                "net_total": 1500.00,
                "tax_amount": 285.00,
                "gross_total": 1785.00,
                "payment_terms": "Net 30",
                "line_items": [
                    {
                        "description": "Consulting Services",
                        "quantity": 10.0,
                        "unit_price": 150.0,
                        "line_total": 1500.0,
                        "tax_rate": 19.0,
                    }
                ],
            }
        }


class ValidationError(BaseModel):
    """Represents a single validation problem found on an invoice."""

    rule: str = Field(..., description="Identifier of the rule that failed")
    message: str = Field(..., description="Human-readable explanation of the issue")
    severity: str = Field(
        default="error", description="Severity level: error, warning, or info"
    )


class ValidationResult(BaseModel):
    """Validation output for one invoice."""

    invoice_id: str = Field(..., description="Invoice identifier (usually invoice_number)")
    is_valid: bool = Field(..., description="Overall pass/fail flag for this invoice")
    errors: List[ValidationError] = Field(
        default_factory=list, description="All failed rules treated as errors"
    )
    warnings: List[ValidationError] = Field(
        default_factory=list, description="Non-blocking issues or soft checks"
    )


class ValidationSummary(BaseModel):
    """
    Aggregated overview when validating multiple invoices in one go.

    Useful for the CLI summary and UI dashboards.
    """

    total_invoices: int
    valid_invoices: int
    invalid_invoices: int
    error_counts: dict[str, int] = Field(
        default_factory=dict,
        description="How many times each rule failed across all invoices",
    )
    validation_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this summary was generated",
    )
