"""
Validator module for the Invoice QC project.

This contains the main validation logic used by:
- the CLI
- the API
- and (optionally) the UI

Rules are grouped as:
- required / completeness checks
- basic business rules
- a couple of anomaly-style checks
"""

from typing import List, Dict
from datetime import datetime, date
from collections import defaultdict
import logging

from .models import Invoice, ValidationError, ValidationResult, ValidationSummary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InvoiceValidator:
    """
    Main validation class with a small set of rules.

    Rough grouping:
    - completeness: required fields, date types, valid currency
    - business: line items sum vs net, gross vs net+tax, due date ordering
    - anomaly: duplicate invoices, negative amounts
    """

    REQUIRED_FIELDS = [
        "invoice_number",
        "invoice_date",
        "seller_name",
        "buyer_name",
        "currency",
        "net_total",
        "tax_amount",
        "gross_total",
    ]

    def __init__(self) -> None:
        # Used to track duplicates during a single batch run
        self.seen_invoices: set = set()

    # ------------------------------------------------------------------
    # Batch validation
    # ------------------------------------------------------------------
    def validate_batch(self, invoices: List[Invoice]) -> Dict:
        """Validate multiple invoices and return per-invoice results + a summary."""

        results: List[ValidationResult] = []
        error_counts = defaultdict(int)

        # reset duplicate tracking for each batch
        self.seen_invoices.clear()

        for inv in invoices:
            result = self.validate_invoice(inv)
            results.append(result)

            for err in result.errors:
                error_counts[err.rule] += 1

        valid_count = sum(1 for r in results if r.is_valid)

        summary = ValidationSummary(
            total_invoices=len(invoices),
            valid_invoices=valid_count,
            invalid_invoices=len(invoices) - valid_count,
            error_counts=dict(error_counts),
            validation_timestamp=datetime.utcnow(),
        )

        return {"results": results, "summary": summary}

    # ------------------------------------------------------------------
    # Single invoice validation
    # ------------------------------------------------------------------
    def validate_invoice(self, invoice: Invoice) -> ValidationResult:
        """Run all checks for one invoice."""

        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        # Completeness
        errors.extend(self._check_required_fields(invoice))
        errors.extend(self._check_dates(invoice))
        errors.extend(self._check_currency(invoice))

        # Business
        errors.extend(self._check_line_items_sum(invoice))
        errors.extend(self._check_gross_calculation(invoice))
        errors.extend(self._check_due_date(invoice))

        # Anomaly
        errors.extend(self._check_duplicates(invoice))
        errors.extend(self._check_non_negative(invoice))

        # Non-blocking warnings
        warnings.extend(self._check_warnings(invoice))

        invoice_id = invoice.invoice_number or "UNKNOWN"

        return ValidationResult(
            invoice_id=invoice_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Individual rule implementations
    # ------------------------------------------------------------------
    def _check_required_fields(self, invoice: Invoice) -> List[ValidationError]:
        """Required fields must be present and non-empty."""
        errors: List[ValidationError] = []

        for field_name in self.REQUIRED_FIELDS:
            value = getattr(invoice, field_name, None)

            if value is None:
                errors.append(
                    ValidationError(
                        rule="required_field_missing",
                        message=f"Missing required field: {field_name}",
                        severity="error",
                    )
                )
            elif isinstance(value, str) and not value.strip():
                errors.append(
                    ValidationError(
                        rule="required_field_empty",
                        message=f"Required field is empty: {field_name}",
                        severity="error",
                    )
                )

        return errors

    def _check_dates(self, invoice: Invoice) -> List[ValidationError]:
        """Basic date format and range checks."""
        errors: List[ValidationError] = []

        # invoice_date checks
        if invoice.invoice_date:
            if not isinstance(invoice.invoice_date, date):
                errors.append(
                    ValidationError(
                        rule="invalid_date_format",
                        message=f"invoice_date has invalid type/value: {invoice.invoice_date}",
                        severity="error",
                    )
                )
            else:
                today = date.today()
                # simple sanity check: not more than ~10 years away from today
                if abs((today - invoice.invoice_date).days) > 3650:
                    errors.append(
                        ValidationError(
                            rule="date_out_of_range",
                            message=f"invoice_date looks unrealistic: {invoice.invoice_date}",
                            severity="error",
                        )
                    )

        # due_date checks
        if invoice.due_date and not isinstance(invoice.due_date, date):
            errors.append(
                ValidationError(
                    rule="invalid_date_format",
                    message=f"due_date has invalid type/value: {invoice.due_date}",
                    severity="error",
                )
            )

        return errors

    def _check_currency(self, invoice: Invoice) -> List[ValidationError]:
        """Currency must be part of the Currency enum."""
        from .models import Currency

        errors: List[ValidationError] = []
        allowed = [c.value for c in Currency]

        if invoice.currency not in allowed:
            errors.append(
                ValidationError(
                    rule="invalid_currency",
                    message=f"Currency '{invoice.currency}' is not in {allowed}",
                    severity="error",
                )
            )

        return errors

    def _check_line_items_sum(self, invoice: Invoice) -> List[ValidationError]:
        """Sum of line items should roughly match net_total (with a tolerance)."""
        errors: List[ValidationError] = []

        if not invoice.line_items:
            # No line items → nothing to validate here
            return errors

        computed_sum = sum(item.line_total for item in invoice.line_items)
        tolerance = invoice.net_total * 0.01  # 1% tolerance
        diff = abs(computed_sum - invoice.net_total)

        if diff > tolerance:
            errors.append(
                ValidationError(
                    rule="line_items_sum_mismatch",
                    message=(
                        f"Line items total {computed_sum:.2f} does not match "
                        f"net_total {invoice.net_total:.2f}. Diff = {diff:.2f}"
                    ),
                    severity="error",
                )
            )

        return errors

    def _check_gross_calculation(self, invoice: Invoice) -> List[ValidationError]:
        """net_total + tax_amount should be close to gross_total."""
        errors: List[ValidationError] = []

        expected_gross = invoice.net_total + invoice.tax_amount
        tolerance = invoice.gross_total * 0.005  # 0.5%
        diff = abs(expected_gross - invoice.gross_total)

        if diff > tolerance:
            errors.append(
                ValidationError(
                    rule="gross_calculation_mismatch",
                    message=(
                        f"net_total ({invoice.net_total:.2f}) + tax_amount "
                        f"({invoice.tax_amount:.2f}) = {expected_gross:.2f}, "
                        f"but gross_total is {invoice.gross_total:.2f}"
                    ),
                    severity="error",
                )
            )

        return errors

    def _check_due_date(self, invoice: Invoice) -> List[ValidationError]:
        """due_date should not be earlier than invoice_date."""
        errors: List[ValidationError] = []

        if invoice.due_date and invoice.invoice_date:
            if invoice.due_date < invoice.invoice_date:
                errors.append(
                    ValidationError(
                        rule="due_date_before_invoice_date",
                        message=(
                            f"due_date ({invoice.due_date}) is before "
                            f"invoice_date ({invoice.invoice_date})"
                        ),
                        severity="error",
                    )
                )

        return errors

    def _check_duplicates(self, invoice: Invoice) -> List[ValidationError]:
        """Detects duplicates within this validation run."""
        errors: List[ValidationError] = []

        key = (invoice.invoice_number, invoice.seller_name, str(invoice.invoice_date))

        if key in self.seen_invoices:
            errors.append(
                ValidationError(
                    rule="duplicate_invoice",
                    message=(
                        f"Duplicate invoice detected: {invoice.invoice_number} "
                        f"from {invoice.seller_name} on {invoice.invoice_date}"
                    ),
                    severity="error",
                )
            )
        else:
            self.seen_invoices.add(key)

        return errors

    def _check_non_negative(self, invoice: Invoice) -> List[ValidationError]:
        """All monetary and quantity fields should be >= 0."""
        errors: List[ValidationError] = []

        amount_fields = {
            "net_total": invoice.net_total,
            "tax_amount": invoice.tax_amount,
            "gross_total": invoice.gross_total,
        }

        for name, value in amount_fields.items():
            if value < 0:
                errors.append(
                    ValidationError(
                        rule="negative_amount",
                        message=f"{name} cannot be negative (value: {value})",
                        severity="error",
                    )
                )

        for idx, item in enumerate(invoice.line_items):
            if item.quantity < 0:
                errors.append(
                    ValidationError(
                        rule="negative_quantity",
                        message=f"Line item {idx + 1} has negative quantity: {item.quantity}",
                        severity="error",
                    )
                )
            if item.unit_price < 0:
                errors.append(
                    ValidationError(
                        rule="negative_unit_price",
                        message=f"Line item {idx + 1} has negative unit_price: {item.unit_price}",
                        severity="error",
                    )
                )

        return errors

    # ------------------------------------------------------------------
    # Warnings only (non-blocking)
    # ------------------------------------------------------------------
    def _check_warnings(self, invoice: Invoice) -> List[ValidationError]:
        """Extra checks that produce warnings, not hard errors."""
        warnings: List[ValidationError] = []

        if not invoice.line_items:
            warnings.append(
                ValidationError(
                    rule="no_line_items",
                    message="Invoice has no line items",
                    severity="warning",
                )
            )

        if not invoice.seller_tax_id:
            warnings.append(
                ValidationError(
                    rule="missing_seller_tax_id",
                    message="Seller tax ID is missing",
                    severity="warning",
                )
            )

        if not invoice.due_date:
            warnings.append(
                ValidationError(
                    rule="missing_due_date",
                    message="Due date is missing",
                    severity="warning",
                )
            )

        if invoice.invoice_date and isinstance(invoice.invoice_date, date):
            age_days = (date.today() - invoice.invoice_date).days
            if age_days > 365:
                warnings.append(
                    ValidationError(
                        rule="old_invoice",
                        message=f"Invoice is {age_days} days old (over 1 year)",
                        severity="warning",
                    )
                )

        return warnings
