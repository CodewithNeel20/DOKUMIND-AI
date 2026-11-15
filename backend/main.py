
import io
import os
import re
from collections import OrderedDict
from typing import Optional
from urllib.parse import unquote

import pymupdf
import pytesseract
from PIL import Image

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from invoice_extractor import extract_invoice_fields
from rag_engine import (
    index_document,
    answer_question,
    load_index,
    save_index,
)
from comparison_engine import compare_invoices
from classification_engine import classify_document


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

app = FastAPI(
    title="DocuMind AI",
    description=(
        "AI-powered document intelligence, OCR, invoice extraction, "
        "document classification, RAG and invoice comparison."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_PDF_SIZE = 15 * 1024 * 1024

TESSERACT_PATH = os.getenv(
    "TESSERACT_PATH",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

OCR_LANGUAGE = "eng"
OCR_DPI = 200
OCR_MIN_TEXT_LENGTH = 20


# ============================================================
# REQUEST MODELS
# ============================================================

class QuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    filename: Optional[str] = None


class CompareInvoicesRequest(BaseModel):
    filenames: list[str] = Field(min_length=2)


# ============================================================
# PDF VALIDATION
# ============================================================

def validate_pdf(file: UploadFile, contents: bytes):

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF file.",
        )

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    if len(contents) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail="PDF must be 15 MB or smaller.",
        )

    if not contents.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF file.",
        )


# ============================================================
# OCR UTILITIES
# ============================================================

def extract_text_with_ocr(page):

    try:
        matrix = pymupdf.Matrix(
            OCR_DPI / 72,
            OCR_DPI / 72,
        )

        pixmap = page.get_pixmap(
            matrix=matrix,
            alpha=False,
        )

        image_bytes = pixmap.tobytes("png")

        image = Image.open(
            io.BytesIO(image_bytes)
        )

        text = pytesseract.image_to_string(
            image,
            lang=OCR_LANGUAGE,
            config="--psm 6",
        )

        return text.strip()

    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="Tesseract OCR was not found. Check its installation path.",
        ) from exc

    except pytesseract.TesseractError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Tesseract OCR failed: {str(exc)}",
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"OCR processing failed: {str(exc)}",
        ) from exc


# ============================================================
# PDF TEXT EXTRACTION
# ============================================================

def read_pdf(contents: bytes):

    try:
        with pymupdf.open(
            stream=contents,
            filetype="pdf",
        ) as document:

            if document.is_encrypted:
                raise HTTPException(
                    status_code=400,
                    detail="Password-protected PDFs are not supported.",
                )

            pages = []

            for page_number, page in enumerate(document, start=1):

                text = page.get_text("text").strip()
                extraction_method = "text"

                if len(text) < OCR_MIN_TEXT_LENGTH:
                    text = extract_text_with_ocr(page)
                    extraction_method = "ocr"

                pages.append({
                    "page": page_number,
                    "text": text,
                    "extraction_method": extraction_method,
                })

            return pages

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not read the PDF. Please check that it is valid.",
        ) from exc


# ============================================================
# DOCUMENT MANAGEMENT HELPERS
# ============================================================

def get_indexed_documents():

    documents = OrderedDict()

    for record in load_index():

        filename = record.get("filename")

        if filename:
            documents.setdefault(filename, []).append(record)

    return documents


def get_selected_document(filename: Optional[str] = None):

    documents = get_indexed_documents()

    if not documents:
        raise HTTPException(
            status_code=400,
            detail="No documents are indexed. Upload a PDF first.",
        )

    if filename:
        if filename not in documents:
            raise HTTPException(
                status_code=404,
                detail="Selected document is not indexed.",
            )

        return filename, documents[filename]

    selected_filename = next(reversed(documents))

    return selected_filename, documents[selected_filename]


def get_document_text(records):

    return "\n".join(
        record.get("text", "")
        for record in records
    ).strip()


# ============================================================
# DOCUMENT CLASSIFICATION
# ============================================================

def get_document_classification(text: str):

    if not text.strip():
        return {
            "category": "Other",
            "confidence": 0,
            "matched_keywords": [],
            "message": "Not enough text to classify this document.",
        }

    return classify_document(text)


# ============================================================
# INVOICE QUESTION IDENTIFICATION
# ============================================================

def identify_invoice_field(question: str):

    q = re.sub(
        r"[^a-z0-9# ]",
        " ",
        question.lower(),
    )

    q = re.sub(
        r"\s+",
        " ",
        q,
    ).strip()

    patterns = [

        ("invoice_number", [
            "invoice number",
            "invoice no",
            "invoice num",
            "invoice id",
            "invoice #",
        ]),

        ("order_number", [
            "order number",
            "order no",
            "order num",
            "order id",
            "order #",
        ]),

        ("invoice_date", [
            "invoice date",
            "date of invoice",
            "issue date",
            "date issued",
            "date was issued",
            "when was this invoice issued",
            "when was the invoice issued",
            "when was this issued",
            "when was it issued",
            "when did they issue this invoice",
        ]),

        ("due_date", [
            "due date",
            "payment due date",
        ]),

        ("payment_status", [
            "payment status",
            "status of payment",
            "is it paid",
            "has it been paid",
            "whether it is paid",
        ]),

        ("vendor", [
            "vendor",
            "supplier",
            "who issued",
            "issued by",
            "seller name",
            "seller",
            "who is the vendor",
            "who is the seller",
        ]),

        ("subtotal", [
            "subtotal",
            "sub total",
            "amount before tax",
        ]),

        ("tax", [
            "tax amount",
            "gst amount",
            "how much tax",
            "tax rate",
            "gst",
        ]),

        ("total", [
            "total due",
            "grand total",
            "invoice total",
            "total amount",
            "amount due",
            "total",
        ]),
    ]

    for field, phrases in patterns:
        if any(phrase in q for phrase in phrases):
            return field

    return None


# ============================================================
# INVOICE TEXT NORMALIZATION
# ============================================================

def normalize_invoice_text(text: str):

    label_pattern = (
        r"(?i)\s+(?="
        r"INVOICE\s*(?:NO\.?(?=\s|:|\[|$)|NUMBER\b|DATE\b)|"
        r"FROM\b|EMAIL\s*:|ADDRESS\s*:|PHONE\s*:|GSTIN\s*:|"
        r"BILL\s+TO\b|PROJECT\s+DETAILS\b|DESCRIPTION\b|"
        r"SUBTOTAL\b|GST\s*\(|GRAND\s+TOTAL\b|"
        r"PAYMENT\s+STATUS\b|PAYMENT\s+TERMS\b"
        r")"
    )

    normalized = re.sub(
        label_pattern,
        "\n",
        text,
    )

    return re.sub(
        r"[ \t]+",
        " ",
        normalized,
    ).strip()


# ============================================================
# INVOICE EXTRACTION HELPERS
# ============================================================

def _extract_invoice_payload(text: str):

    extracted = extract_invoice_fields(text)

    if not isinstance(extracted, dict):
        return {
            "invoice": {},
            "missing_fields": [],
            "total_validation": None,
        }

    nested_invoice = extracted.get("invoice")

    if isinstance(nested_invoice, dict):
        return {
            "invoice": nested_invoice,
            "missing_fields": extracted.get("missing_fields", []),
            "total_validation": extracted.get("total_validation"),
        }

    return {
        "invoice": extracted,
        "missing_fields": [
            key
            for key in (
                "invoice_number",
                "vendor",
                "invoice_date",
                "subtotal",
                "tax",
                "total",
            )
            if not extracted.get(key)
        ],
        "total_validation": extracted.get("total_validation"),
    }


def _extract_fallback_value(text: str, field: str):

    patterns = {

        "invoice_number":
            r"\bINVOICE\s*(?:NO\.?|NUMBER|NUM|ID|#)\s*:?\s*\[?([A-Z0-9][A-Z0-9/_-]*)",

        "order_number":
            r"\bORDER\s*(?:NO\.?|NUMBER|NUM|ID|#)\s*:?\s*([A-Z0-9][A-Z0-9/_-]*)",

        "invoice_date":
            r"\bINVOICE\s*DATE\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,4}[/-]\d{1,2}[/-]\d{2,4})",

        "due_date":
            r"\bDUE\s*DATE\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,4}[/-]\d{1,2}[/-]\d{2,4})",

        "vendor":
            r"\bFROM\s*\n?\s*([^\n]+)",

        "payment_status":
            r"\bPAYMENT\s+STATUS\s*:?\s*([A-Z][A-Z -]{1,30}?)(?=\s+(?:AMOUNT RECEIVED|BALANCE DUE|PAYMENT TERMS)\b|[\n.]|$)",
    }

    pattern = patterns.get(field)

    if not pattern:
        return None

    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    value = match.group(1).strip().strip("[]").strip()

    if field == "vendor":
        value = re.sub(
            r"^(?:Email|Address|Phone|GSTIN)\s*:.*$",
            "",
            value,
            flags=re.I,
        ).strip()

    return value or None


# ============================================================
# STRUCTURED INVOICE QUESTION ANSWERING
# ============================================================

def answer_invoice_question(
    field: str,
    selected_filename: Optional[str] = None,
):

    filename, records = get_selected_document(
        selected_filename,
    )

    text = normalize_invoice_text(
        get_document_text(records),
    )

    payload = _extract_invoice_payload(text)
    invoice = payload["invoice"]

    value = invoice.get(field)

    if value is None or not str(value).strip():
        value = _extract_fallback_value(text, field)

    page_number = records[0].get("page", 1)

    label_patterns = {

        "invoice_number": r"invoice\s*(?:no\.?|number|num|id|#)",
        "order_number": r"order\s*(?:no\.?|number|num|id|#)",
        "invoice_date": r"invoice\s*date",
        "due_date": r"due\s*date",
        "payment_status": r"\bpayment\s+status\b",
        "vendor": r"\bfrom\b",
        "subtotal": r"\bsubtotal\b|\bsub\s*total\b",
        "tax": r"\bGST\b|\btax\b",
        "total": r"\bgrand\s*total\b|\btotal\b",
    }

    label_pattern = label_patterns.get(field)

    if label_pattern:
        for record in records:
            if re.search(
                label_pattern,
                record.get("text", ""),
                re.IGNORECASE,
            ):
                page_number = record.get("page", 1)
                break

    if value is None or not str(value).strip():
        return {
            "answer": (
                f"I couldn't find the {field.replace('_', ' ')} "
                "in the selected document."
            ),
            "answer_type": "structured_extraction",
            "sources": [
                {
                    "filename": filename,
                    "page": page_number,
                }
            ],
        }

    display_labels = {
        "invoice_number": "Invoice number",
        "order_number": "Order number",
        "invoice_date": "Invoice date",
        "due_date": "Due date",
        "payment_status": "Payment status",
        "vendor": "Vendor",
        "subtotal": "Subtotal",
        "tax": "Tax",
        "total": "Grand total",
    }

    return {
        "answer": (
            f"{display_labels.get(field, field.replace('_', ' ').title())}: "
            f"{str(value).strip()}"
        ),
        "answer_type": "structured_extraction",
        "sources": [
            {
                "filename": filename,
                "page": page_number,
            }
        ],
    }


# ============================================================
# BASIC ENDPOINTS
# ============================================================

@app.get("/")
def home():

    return {
        "message": "Welcome to DocuMind AI",
        "status": "running",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():

    return {
        "status": "ok",
        "application": "DocuMind AI",
    }


# ============================================================
# PDF EXTRACTION
# ============================================================

@app.post("/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)):

    try:
        contents = await file.read()
        validate_pdf(file, contents)

        pages = read_pdf(contents)

        extracted_text = "\n".join(
            page["text"] for page in pages
        )

        if not extracted_text.strip():
            raise HTTPException(
                status_code=422,
                detail="No text could be extracted from this PDF, even with OCR.",
            )

        return {
            "filename": file.filename,
            "total_pages": len(pages),
            "pages": pages,
            "extracted_text": extracted_text,
            "needs_ocr": any(
                page["extraction_method"] == "ocr"
                for page in pages
            ),
            "extraction_methods": [
                {
                    "page": page["page"],
                    "method": page["extraction_method"],
                }
                for page in pages
            ],
        }

    finally:
        await file.close()


# ============================================================
# INVOICE EXTRACTION
# ============================================================

@app.post("/extract-invoice")
async def extract_invoice(file: UploadFile = File(...)):

    try:
        contents = await file.read()
        validate_pdf(file, contents)

        pages = read_pdf(contents)

        extracted_text = "\n".join(
            page["text"] for page in pages
        )

        if not extracted_text.strip():
            raise HTTPException(
                status_code=422,
                detail="No text could be extracted from this invoice.",
            )

        payload = _extract_invoice_payload(extracted_text)

        return {
            "filename": file.filename,
            "total_pages": len(pages),
            "invoice": payload["invoice"],
            "missing_fields": payload["missing_fields"],
            "total_validation": payload["total_validation"],
            "ocr_used": any(
                page["extraction_method"] == "ocr"
                for page in pages
            ),
        }

    finally:
        await file.close()


# ============================================================
# PDF INDEXING AND CLASSIFICATION
# ============================================================

@app.post("/index-pdf")
async def index_pdf(file: UploadFile = File(...)):

    try:
        contents = await file.read()
        validate_pdf(file, contents)

        pages = read_pdf(contents)

        extracted_text = "\n".join(
            page["text"] for page in pages
        ).strip()

        if not extracted_text:
            raise HTTPException(
                status_code=422,
                detail="No text could be extracted from this PDF.",
            )

        classification = get_document_classification(extracted_text)

        chunk_count = index_document(
            file.filename,
            pages,
        )

        ocr_pages = [
            page["page"]
            for page in pages
            if page["extraction_method"] == "ocr"
        ]

        return {
            "message": "Document indexed and classified successfully.",
            "filename": file.filename,
            "total_pages": len(pages),
            "chunks_indexed": chunk_count,
            "ocr_used": bool(ocr_pages),
            "ocr_pages": ocr_pages,
            "classification": classification,
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        print(f"Indexing error: {exc}")

        raise HTTPException(
            status_code=500,
            detail="Failed to index document. Check the backend terminal.",
        ) from exc

    finally:
        await file.close()


# ============================================================
# DOCUMENT LIBRARY
# ============================================================

@app.get("/documents")
def list_documents():

    documents = get_indexed_documents()
    result = []

    for filename, records in documents.items():

        pages = {
            record.get("page", 1)
            for record in records
        }

        document_text = get_document_text(records)

        classification = get_document_classification(
            document_text
        )

        result.append({
            "filename": filename,
            "chunks": len(records),
            "pages": len(pages),
            "status": "indexed",
            "category": classification["category"],
            "confidence": classification["confidence"],
        })

    return {
        "count": len(result),
        "documents": result,
    }


# ============================================================
# DOCUMENT CLASSIFICATION DETAILS
# ============================================================

@app.get("/documents/{filename}/classification")
def get_document_classification_endpoint(filename: str):

    decoded = unquote(filename)

    _, records = get_selected_document(decoded)

    document_text = get_document_text(records)

    classification = get_document_classification(
        document_text
    )

    return {
        "filename": decoded,
        "classification": classification,
    }


# ============================================================
# DELETE DOCUMENT
# ============================================================

@app.delete("/documents/{filename}")
def delete_document(filename: str):

    decoded = unquote(filename)

    records = load_index()

    filtered = [
        record
        for record in records
        if record.get("filename") != decoded
    ]

    if len(filtered) == len(records):
        raise HTTPException(
            status_code=404,
            detail=f"Document '{decoded}' not found in index.",
        )

    save_index(filtered)

    return {
        "message": f"'{decoded}' removed from index.",
        "filename": decoded,
        "chunks_removed": len(records) - len(filtered),
    }


# ============================================================
# DOCUMENT SUMMARY
# ============================================================

@app.get("/documents/{filename}/summary")
def get_document_summary(filename: str):

    decoded = unquote(filename)

    _, records = get_selected_document(decoded)

    text = get_document_text(records)

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if len(sentence.strip()) > 40
    ]

    summary_text = (
        " ".join(sentences[:6])
        if sentences
        else text[:400]
    )

    return {
        "filename": decoded,
        "summary": summary_text[:700].strip(),
        "pages": len({
            record.get("page", 1)
            for record in records
        }),
        "chunks": len(records),
    }


# ============================================================
# MULTI-INVOICE COMPARISON
# ============================================================

@app.post("/compare-invoices")
def compare_documents(request: CompareInvoicesRequest):

    try:
        documents = get_indexed_documents()

        if not documents:
            raise HTTPException(
                status_code=400,
                detail="No documents are indexed. Upload invoices first.",
            )

        selected_filenames = list(
            dict.fromkeys(request.filenames)
        )

        if len(selected_filenames) < 2:
            raise HTTPException(
                status_code=400,
                detail="Select at least two different invoices to compare.",
            )

        missing_documents = [
            filename
            for filename in selected_filenames
            if filename not in documents
        ]

        if missing_documents:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "Some selected documents are not indexed.",
                    "missing_documents": missing_documents,
                },
            )

        result = compare_invoices(
            documents,
            selected_filenames=selected_filenames,
        )

        return result

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        print(f"Invoice comparison error: {exc}")

        raise HTTPException(
            status_code=500,
            detail=(
                "Invoice comparison failed. "
                "Check comparison_engine.py and the backend terminal."
            ),
        ) from exc


# ============================================================
# QUESTION ANSWERING
# ============================================================

@app.post("/ask")
def ask_document(request: QuestionRequest):

    question = request.question.strip()

    try:
        documents = get_indexed_documents()

        if not documents:
            raise HTTPException(
                status_code=400,
                detail="No documents are indexed. Upload a PDF first.",
            )

        field = identify_invoice_field(question)

        # SINGLE DOCUMENT MODE

        if request.filename:

            filename, _records = get_selected_document(
                request.filename
            )

            if field:
                return answer_invoice_question(
                    field,
                    selected_filename=filename,
                )

            return answer_question(
                question,
                top_k=3,
                filename=filename,
            )

        # ALL DOCUMENTS MODE

        if field:

            answers = []
            sources = []

            for filename in documents:

                result = answer_invoice_question(
                    field,
                    selected_filename=filename,
                )

                answer_text = result.get("answer", "")

                if "couldn't find" not in answer_text.lower():

                    answers.append({
                        "filename": filename,
                        "answer": answer_text,
                    })

                    sources.extend(
                        result.get("sources", [])
                    )

            if not answers:
                return {
                    "answer": (
                        f"I couldn't find the {field.replace('_', ' ')} "
                        "in any indexed document."
                    ),
                    "answer_type": "structured_extraction",
                    "sources": [],
                    "documents_searched": len(documents),
                }

            return {
                "answer": "\n".join(
                    f"{item['filename']}: {item['answer']}"
                    for item in answers
                ),
                "answer_type": "structured_extraction",
                "sources": sources,
                "documents_searched": len(documents),
            }

        # GENERAL RAG QUESTION

        return answer_question(
            question,
            top_k=6,
            filename=None,
        )

    except HTTPException:
        raise

    except Exception as exc:
        print(f"Question answering error: {exc}")

        raise HTTPException(
            status_code=500,
            detail="Question answering failed. Check the backend terminal.",
        ) from exc
