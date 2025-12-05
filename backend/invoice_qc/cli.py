"""
CLI entrypoint for the Invoice QC project.

Commands:
- extract    → read PDFs from a folder and dump JSON
- validate   → validate an existing JSON file
- full-run   → extract + validate in one go
"""

import json
from pathlib import Path
from typing import List

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from .extractor import PDFInvoiceExtractor
from .validator import InvoiceValidator
from .models import Invoice

app = typer.Typer(help="Invoice QC - extract and validate invoices from PDFs")
console = Console()


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def _extract_from_directory(pdf_dir: Path) -> List[Invoice]:
    """Loop through all PDFs in a folder and extract them into Invoice objects."""
    extractor = PDFInvoiceExtractor()
    invoices: List[Invoice] = []

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        try:
            inv = extractor.extract(str(pdf_path))
            invoices.append(inv)
        except Exception as exc:
            console.print(f"[red]Failed to extract {pdf_path.name}: {exc}[/red]")

    return invoices


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
@app.command()
def extract(
    pdf_dir: Path = typer.Option(..., "--pdf-dir", help="Directory containing PDF files"),
    output: Path = typer.Option(
        "extracted_invoices.json",
        "--output",
        help="Where to write the extracted JSON",
    ),
):
    """
    Extract invoice data from all PDFs in a directory and save as JSON.

    Example:
      python -m invoice_qc.cli extract --pdf-dir pdfs --output invoices.json
    """
    if not pdf_dir.exists() or not pdf_dir.is_dir():
        console.print(f"[red]✗ Directory not found:[/red] {pdf_dir}")
        raise typer.Exit(code=1)

    console.print(f"\n[cyan]📄 Extracting invoices from: {pdf_dir}[/cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Reading PDFs...", total=None)
        invoices = _extract_from_directory(pdf_dir)
        progress.update(task, completed=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(
            [inv.model_dump(mode="json") for inv in invoices],
            f,
            indent=2,
            default=str,
        )

    console.print(f"[green]✓ Extracted {len(invoices)} invoices → {output}\n")


@app.command()
def validate(
    input: Path = typer.Option(..., "--input", help="JSON file with invoice data"),
    report: Path = typer.Option(
        "validation_report.json", "--report", help="Where to write the validation report"
    ),
):
    """
    Validate a JSON file containing invoices.

    Example:
      python -m invoice_qc.cli validate --input invoices.json --report report.json
    """
    if not input.exists():
        console.print(f"[red]✗ File not found:[/red] {input}")
        raise typer.Exit(code=1)

    with input.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    invoices = [Invoice(**inv) for inv in raw]

    console.print(f"\n[cyan]🔍 Validating {len(invoices)} invoices...[/cyan]\n")

    validator = InvoiceValidator()
    result = validator.validate_batch(invoices)

    # Pretty table
    table = Table(title="Validation Results", show_header=True, header_style="bold magenta")
    table.add_column("Invoice ID", style="cyan", width=20)
    table.add_column("Status", width=10)
    table.add_column("Errors (first few)", style="yellow")

    for r in result["results"]:
        status = "[green]PASS[/green]" if r.is_valid else "[red]FAIL[/red]"
        error_rules = ", ".join(e.rule for e in r.errors[:3])
        if len(r.errors) > 3:
            error_rules += f" (+{len(r.errors) - 3})"
        table.add_row(r.invoice_id, status, error_rules)

    console.print(table)

    summary = result["summary"]
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Total:  {summary.total_invoices}")
    console.print(f"  [green]Valid:   {summary.valid_invoices}[/green]")
    console.print(f"  [red]Invalid: {summary.invalid_invoices}[/red]")

    if summary.error_counts:
        console.print("\n[bold]Top errors:[/bold]")
        for rule, count in sorted(summary.error_counts.items(), key=lambda x: -x[1])[:5]:
            console.print(f"  • {rule}: {count}")

    # Save raw report JSON
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "results": [r.model_dump(mode="json") for r in result["results"]],
                "summary": result["summary"].model_dump(mode="json"),
            },
            f,
            indent=2,
            default=str,
        )

    console.print(f"\n[green]✓ Report saved to {report}[/green]\n")

    if summary.invalid_invoices > 0:
        raise typer.Exit(code=1)


@app.command(name="full-run")
def full_run(
    pdf_dir: Path = typer.Option(..., "--pdf-dir", help="Directory containing PDF files"),
    report: Path = typer.Option(
        "validation_report.json", "--report", help="Where to save the validation report"
    ),
    save_extracted: bool = typer.Option(
        False, "--save-extracted", help="If set, also save extracted JSON next to the report"
    ),
):
    """
    Run the full pipeline in one command: extract from PDFs and validate.

    Example:
      python -m invoice_qc.cli full-run --pdf-dir pdfs --report report.json
    """
    if not pdf_dir.exists() or not pdf_dir.is_dir():
        console.print(f"[red]✗ Directory not found:[/red] {pdf_dir}")
        raise typer.Exit(code=1)

    console.print("\n[bold cyan]=== Invoice QC: Full run ===[/bold cyan]\n")

    # Step 1: extract
    console.print("[cyan]Step 1/2: Extracting from PDFs...[/cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Reading PDFs...", total=None)
        invoices = _extract_from_directory(pdf_dir)
        progress.update(task, completed=True)

    console.print(f"[green]✓ Extracted {len(invoices)} invoices[/green]\n")

    # Optionally save extracted JSON
    if save_extracted:
        extracted_file = report.parent / "extracted_invoices.json"
        extracted_file.parent.mkdir(parents=True, exist_ok=True)
        with extracted_file.open("w", encoding="utf-8") as f:
            json.dump(
                [inv.model_dump(mode="json") for inv in invoices],
                f,
                indent=2,
                default=str,
            )
        console.print(f"[dim]Saved extracted data to {extracted_file}[/dim]\n")

    # Step 2: validate
    console.print("[cyan]Step 2/2: Validating invoices...[/cyan]\n")

    validator = InvoiceValidator()
    result = validator.validate_batch(invoices)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Invoice ID", style="cyan", width=20)
    table.add_column("Status", width=10)
    table.add_column("Errors (first few)", style="yellow")

    for r in result["results"]:
        status = "[green]PASS[/green]" if r.is_valid else "[red]FAIL[/red]"
        error_rules = ", ".join(e.rule for e in r.errors[:2])
        if len(r.errors) > 2:
            error_rules += f" (+{len(r.errors) - 2})"
        table.add_row(r.invoice_id, status, error_rules)

    console.print(table)

    summary = result["summary"]
    console.print("\n[bold cyan]=== Summary ===[/bold cyan]")
    console.print(f"Total: {summary.total_invoices}")
    console.print(f"[green]Valid:   {summary.valid_invoices}[/green]")
    console.print(f"[red]Invalid: {summary.invalid_invoices}[/red]")

    if summary.error_counts:
        console.print("\n[bold]Top validation errors:[/bold]")
        for rule, count in sorted(summary.error_counts.items(), key=lambda x: -x[1])[:5]:
            console.print(f"  • {rule}: {count}")

    # Save report
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "results": [r.model_dump(mode="json") for r in result["results"]],
                "summary": result["summary"].model_dump(mode="json"),
            },
            f,
            indent=2,
            default=str,
        )

    console.print(f"\n[green]✓ Validation report saved to {report}[/green]\n")

    if summary.invalid_invoices > 0:
        console.print("[yellow]Some invoices failed validation[/yellow]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
