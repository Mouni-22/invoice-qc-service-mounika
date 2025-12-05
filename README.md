🌟 Invoice QC Service – Mounika

A lightweight and modular Invoice Extraction & Quality Control (QC) system built as part of the Software Engineer Intern – Data & Development assignment.

🚀 1. Overview

This project implements a complete backend pipeline for processing B2B invoice PDFs:

📄 PDF → JSON Extraction

🛡️ Validation Engine (rules-based)

🧪 CLI for running extraction + validation

🌐 FastAPI backend with /validate-json & /extract-and-validate-pdfs endpoints

UI was optional (bonus), so I focused on a polished backend with clean structure, good documentation, and real extraction + validation logic.

🧱 2. Schema & Validation Design
📌 Schema Fields (Invoice-Level)

The system extracts and fills these core fields:

Field	Description
invoice_number	Unique invoice ID
invoice_date	Date invoice was issued
due_date	Payment due date
seller_name	Seller’s legal name
seller_address	Seller address
seller_tax_id	GST/VAT ID
buyer_name	Buyer’s legal name
buyer_address	Buyer address
buyer_tax_id	GST/VAT ID
currency	Invoice currency (EUR/INR/USD/GBP)
net_total	Amount before tax
tax_amount	Tax charged
gross_total	Final payable amount
payment_terms	Optional terms
notes	Optional notes
line_items	Description, qty, price, line_total
Why this schema?

It covers the core financial + legal info required for real B2B invoice processing and ensures meaningful validation.

✔️ 3. Validation Rules
🔹 Completeness & Format Rules

Required fields must not be empty

Dates must be valid & within reasonable range

Currency must be in a known list (EUR, USD, INR, GBP)

🔹 Business Rules

Sum(line items) ≈ net_total

net_total + tax_amount ≈ gross_total

due_date ≥ invoice_date

🔹 Anomaly Rules

No duplicate invoices (invoice_number + seller + date)

No negative amounts or quantities

These rules ensure the invoice is structurally correct, financially accurate, and safe to process.

🏗️ 4. Architecture
backend/
  invoice_qc/
    models.py
    extractor.py
    validator.py
    cli.py
    __init__.py
  server.py
  requirements.txt

🔁 5. System Flow (Mermaid Diagram)
flowchart LR
    A[📄 PDF Files] --> B[🧮 Extraction Module]
    B --> C[🗂️ JSON Output]
    C --> D[🛡️ Validation Engine]
    D --> E[🖥️ CLI Output]
    D --> F[🌐 FastAPI Endpoints]

🛠️ 6. Setup & Installation
Create virtual environment
python -m venv venv
venv\Scripts\activate

Install dependencies
pip install -r backend/requirements.txt

💻 7. Running the Project
🔹 CLI Commands
Extract PDFs → JSON
python -m invoice_qc.cli extract --pdf-dir pdfs --output extracted.json

Validate JSON
python -m invoice_qc.cli validate --input extracted.json --report report.json

Full Pipeline
python -m invoice_qc.cli full-run --pdf-dir pdfs --report validation_report.json

🔹 Run FastAPI Server
uvicorn server:app --reload


📍 API Docs:
➡️ http://127.0.0.1:8000/docs

🌐 8. API Endpoints
GET /api/health

Check service status.

POST /api/validate-json

Validate invoice JSON array.

POST /api/extract-and-validate-pdfs

Upload multiple PDFs → extract + validate.

🤖 9. AI Usage Notes

AI tools (ChatGPT) were used for:

Exploring extraction strategies

Boilerplate for Typer & FastAPI

Drafting the README formatting

Testing ideas for structure

Where AI was wrong / needed correction:

Some regex patterns didn’t match actual invoices

Typer CLI examples produced click errors → fixed manually

Extractor logic needed custom rules for seller/buyer names

I used AI as a helper, not as the final source — all logic was tested and rewritten where needed.

⚠️ 10. Assumptions & Limitations

Extraction is simplified to work for the sample invoices

Does not support extremely complex invoice layouts

Line item detection is heuristic-based

No database storage (kept simple for assignment)

🎥 11. Demo Video

A 10–20 min walkthrough will be uploaded here:

👉 Video Link: Coming soon
   12. My understanding 
   ![Rough Sketch](https://github.com/Mouni-22/invoice-qc-service-mounika/blob/main/rough_sketch.jpg)

   13. 🧪 How to Run the Project Locally

This project is designed to run fully locally — no deployment required.

Follow these simple steps:

✅ 1. Clone the Repository
git clone https://github.com/Mouni-22/invoice-qc-service-mounika.git
cd invoice-qc-service-mounika/backend

✅ 2. Create & Activate Virtual Environment
Windows:
python -m venv venv
venv\Scripts\activate

Mac/Linux:
python3 -m venv venv
source venv/bin/activate

✅ 3. Install Dependencies
pip install -r requirements.txt

📄 Running the CLI
Extract PDFs → JSON
python -m invoice_qc.cli extract --pdf-dir pdfs --output extracted.json

Validate JSON
python -m invoice_qc.cli validate --input extracted.json --report report.json

Full Pipeline (Extract + Validate)
python -m invoice_qc.cli full-run --pdf-dir pdfs --report validation_report.json

🌐 Running the API Locally
Start FastAPI server
uvicorn server:app --reload

Open API docs in browser:

👉 http://127.0.0.1:8000/docs

Here you can test all endpoints interactively.
