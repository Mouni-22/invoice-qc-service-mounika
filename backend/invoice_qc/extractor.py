"""
PDF extraction utilities for the Invoice QC project.

I kept this module fairly simple on purpose:
- read PDF text using pdfplumber
- pull out basic fields (invoice_number, dates, totals, etc.)
- try to detect line items if a table exists
- return structured data that matches the Invoice model
"""

import re
import pdfplumber
from datetime import datetime
from typing import Optional, List

from .models import Invoice, LineItem


class PDFInvoiceExtractor:
    """
    Helper class for turning PDF invoices into structured Invoice objects.
    The extraction logic is intentionally lightweight because invoice layouts vary a lot.
    """

    # Basic regex patterns for fields commonly found in invoices
    FIELD_PATTERNS = {
        "invoice_number": r"(Invoice Number|Invoice No\.?|Rechnung\s*Nr\.?)[:\s]*([\w\-\/]+)",
        "invoice_date": r"(Invoice Date|Rechnungsdatum)[:\s]*([\d\.\-/]+)",
        "due_date": r"(Due Date|Faelligkeitsdatum)[:\s]*([\d\.\-/]+)",
        "net_total": r"(Net Total|Netto)[:\s]*([\d\.,]+)",
        "tax_amount": r"(Tax Amount|MwSt)[:\s]*([\d\.,]+)",
        "gross_total": r"(Total|Gesamtbetrag|Brutto)[:\s]*([\d\.,]+)",
        "seller_name": r"(From|Seller|Lieferant)[:\s]*(.*)",
        "buyer_name": r"(To|Buyer|Kunde)[:\s]*(.*)",
    }

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def extract(self, pdf_path: str) -> Invoice:
        """
        Extracts invoice data from a PDF file and returns an Invoice model.
        Not all fields will be present—any missing fields will fall back to None.
        """

        text = self._read_pdf_text(pdf_path)
        parsed = self._extract_basic_fields(text)
        line_items = self._extract_line_items(pdf_path)

        # Combine everything into a structured Invoice object
        invoice = Invoice(
            invoice_number=parsed.get("invoice_number", "UNKNOWN"),
            external_reference=None,
            seller_name=parsed.get("seller_name", "").strip(),
            seller_address=None,
            seller_tax_id=None,
            buyer_name=parsed.get("buyer_name", "").strip(),
            buyer_address=None,
            buyer_tax_id=None,
            invoice_date=parsed.get("invoice_date"),
            due_date=parsed.get("due_date"),
            currency="EUR",  # default
            net_total=parsed.get("net_total", 0.0),
            tax_amount=parsed.get("tax_amount", 0.0),
            gross_total=parsed.get("gross_total", 0.0),
            line_items=line_items,
            payment_terms=None,
            notes=None,
            source_file=pdf_path,
        )

        return invoice

    # ------------------------------------------------------------------
    # PDF → text
    # ------------------------------------------------------------------
    def _read_pdf_text(self, pdf_path: str) -> str:
        """Reads all text from a PDF using pdfplumber."""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return full_text
        except Exception as e:
            print(f"Failed to read PDF: {e}")
            return ""

    # ------------------------------------------------------------------
    # Regex-based field extraction
    # ------------------------------------------------------------------
    def _extract_basic_fields(self, text: str) -> dict:
        """Extract invoice_number, dates, totals, seller/buyer names."""
        data = {}

        for key, pattern in self.FIELD_PATTERNS.items():
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                raw_value = match.group(2).strip()
                data[key] = self._clean_value(key, raw_value)

        return data

    def _clean_value(self, key: str, value: str):
        """Convert matched text into proper Python types."""
        if key in ("invoice_date", "due_date"):
            return self._parse_date(value)

        if key in ("net_total", "tax_amount", "gross_total"):
            return self._parse_number(value)

        return value

    def _parse_date(self, s: str):
        """Handles common date formats found on invoices."""
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except:
                pass
        return None

    def _parse_number(self, s: str) -> float:
        """
        Convert currency formats to floats.
        Handles: "1,234.56", "1.234,56" (German), "1234.56"
        """
        cleaned = s.replace(" ", "")

        # Convert German style 1.234,56 → 1234.56
        if "," in cleaned and "." in cleaned and cleaned.find(",") > cleaned.find("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")

        # Convert 1.234 → 1.234 or 1234 depending on invoice style
        cleaned = cleaned.replace(",", "")

        try:
            return float(cleaned)
        except:
            return 0.0

    # ------------------------------------------------------------------
    # Line items extraction
    # ------------------------------------------------------------------
    def _extract_line_items(self, pdf_path: str) -> List[LineItem]:
        """
        Attempt to detect line item tables from PDF pages.
        This is best-effort only and depends on how clean the PDF is.
        """
        items = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    if not tables:
                        continue

                    for table in tables:
                        # Expecting something like:
                        # desc | qty | price | total
                        if len(table[0]) < 4:
                            continue

                        for row in table[1:]:
                            try:
                                desc = row[0].strip()
                                qty = float(row[1].replace(",", "."))
                                price = float(row[2].replace(",", "."))
                                total = float(row[3].replace(",", "."))

                                items.append(
                                    LineItem(
                                        description=desc,
                                        quantity=qty,
                                        unit_price=price,
                                        line_total=total,
                                    )
                                )
                            except:
                                continue
        except:
            pass

        return items
