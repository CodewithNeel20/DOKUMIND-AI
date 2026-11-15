
import json
import re
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_PATH = Path(__file__).parent / "rag_index.json"

_model = None


def get_model():
    global _model

    if _model is None:
        _model = SentenceTransformer(MODEL_NAME, device="cpu")

    return _model


def normalize_document_text(text: str) -> str:
    if not text:
        return ""

    cleaned_lines = []

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()

        if line:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def chunk_text(text: str, chunk_size=900, overlap=150):
    text = normalize_document_text(text)

    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        if end < text_length:
            boundary = text.rfind("\n", start, end)

            if boundary <= start + int(chunk_size * 0.45):
                boundary = text.rfind(" ", start, end)

            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = max(start + 1, end - overlap)

    return chunks


def load_index():
    if not INDEX_PATH.exists():
        return []

    try:
        with INDEX_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, list) else []

    except (json.JSONDecodeError, OSError):
        return []


def save_index(records):
    temp_path = INDEX_PATH.with_suffix(".tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False)

    temp_path.replace(INDEX_PATH)


def index_document(filename: str, pages: list[dict]):
    if not filename or not filename.strip():
        raise ValueError("A valid filename is required.")

    records = [
        item for item in load_index()
        if item.get("filename") != filename
    ]

    chunks = []

    for page in pages:
        page_number = page.get("page", 1)
        page_text = page.get("text", "")

        for chunk in chunk_text(page_text):
            chunks.append({
                "filename": filename,
                "page": page_number,
                "text": chunk,
            })

    if not chunks:
        raise ValueError("No text could be indexed.")

    model = get_model()

    vectors = model.encode(
        [item["text"] for item in chunks],
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    for item, vector in zip(chunks, vectors):
        item["embedding"] = vector.tolist()

    records.extend(chunks)
    save_index(records)

    return len(chunks)


def retrieve(question: str, top_k=3, filename=None):
    if not question or not question.strip():
        return []

    records = load_index()

    if filename:
        records = [
            record for record in records
            if record.get("filename") == filename
        ]

    valid_records = [
        record for record in records
        if isinstance(record.get("text"), str)
        and record.get("text").strip()
        and isinstance(record.get("embedding"), list)
    ]

    if not valid_records:
        return []

    model = get_model()

    query_vector = model.encode(
        [question.strip()],
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]

    try:
        matrix = np.asarray(
            [record["embedding"] for record in valid_records],
            dtype=np.float32,
        )

        if (
            matrix.ndim != 2
            or matrix.shape[1] != len(query_vector)
            or not np.isfinite(matrix).all()
        ):
            raise ValueError

    except (ValueError, TypeError):
        raise ValueError(
            "Invalid document embeddings. Please re-index the PDF."
        )

    scores = matrix @ query_vector

    count = min(max(1, int(top_k)), len(valid_records))
    ranked_indices = np.argsort(scores)[::-1][:count]

    results = []

    for index in ranked_indices:
        record = valid_records[int(index)]

        results.append({
            "filename": record.get("filename", "Unknown"),
            "page": record.get("page", 1),
            "text": record["text"],
            "score": round(float(scores[index]), 4),
        })

    return results


def detect_question_intent(question: str):
    q = question.lower()

    patterns = {
        "account_number": [
            r"\bacc(?:ount)?\s*(?:number|no\.?)\b",
            r"\baccount\s+number\b",
            r"\bbank\s+account\b",
            r"\ba/?c\s+number\b",
        ],
        "bsb_number": [
            r"\bbsb\b",
        ],
        "invoice_number": [
            r"\binvoice\s*(?:number|no\.?|#)\b",
            r"\binv\s+number\b",
        ],
        "order_number": [
            r"\border\s*(?:number|no\.?|#)\b",
        ],
        "vendor": [
            r"\bvendor\b",
            r"\bsupplier\b",
            r"\bissued\s+by\b",
            r"\bfrom\s+which\s+(?:company|business)\b",
        ],
        "total": [
            r"\bgrand\s+total\b",
            r"\btotal\s+(?:amount|due|cost|value)\b",
            r"\bhow\s+much\s+(?:is\s+)?(?:the\s+)?total\b",
            r"\binvoice\s+total\b",
        ],
        "subtotal": [
            r"\bsub\s*total\b",
            r"\bsubtotal\b",
        ],
        "tax": [
            r"\btax\s+(?:amount|value)\b",
            r"\bhow\s+much\s+tax\b",
        ],
        "invoice_date": [
            r"\binvoice\s+date\b",
            r"\bdate\s+of\s+(?:the\s+)?invoice\b",
        ],
        "due_date": [
            r"\bdue\s+date\b",
            r"\bpayment\s+deadline\b",
        ],
        "payment_status": [
            r"\bpayment\s+status\b",
            r"\bpaid\s+or\s+unpaid\b",
            r"\bpartially\s+paid\b",
        ],
        "bank_name": [
            r"\bbank\s+name\b",
            r"\bwhich\s+bank\b",
        ],
    }

    for intent, expressions in patterns.items():
        if any(re.search(pattern, q) for pattern in expressions):
            return intent

    return None


def extract_field_value(text: str, intent: str):
    text = normalize_document_text(text)

    patterns = {
        "account_number": [
            r"(?im)^\s*(?:ACC(?:OUNT)?(?:\s*(?:NO|NUMBER))?|A/C)\s*[#:. -]*([A-Z0-9][A-Z0-9 -]{2,})\s*$",
        ],
        "bsb_number": [
            r"(?im)^\s*BSB\s*[#:. -]*([0-9][0-9 -]{2,})\s*$",
        ],
        "invoice_number": [
            r"(?im)^\s*INVOICE\s*(?:NUMBER|NO\.?|#)\s*:?\s*([A-Z0-9/-]+)\s*$",
            r"(?im)^\s*INVOICE\s*(?:NUMBER|NO\.?|#)\s*$\n^\s*([A-Z0-9/-]+)\s*$",
        ],
        "order_number": [
            r"(?im)^\s*ORDER\s*(?:NUMBER|NO\.?|#)\s*:?\s*([A-Z0-9/-]+)\s*$",
            r"(?im)^\s*ORDER\s*(?:NUMBER|NO\.?|#)\s*$\n^\s*([A-Z0-9/-]+)\s*$",
        ],
        "total": [
            r"(?im)^\s*(?:GRAND\s+TOTAL|TOTAL\s+DUE|TOTAL)\s*:?\s*[$₹€£]?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\s*$",
            r"(?im)^\s*(?:GRAND\s+TOTAL|TOTAL\s+DUE|TOTAL)\s*$\n^\s*[$₹€£]?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\s*$",
        ],
        "subtotal": [
            r"(?im)^\s*SUB\s*TOTAL\s*:?\s*[$₹€£]?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\s*$",
            r"(?im)^\s*SUB\s*TOTAL\s*$\n^\s*[$₹€£]?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\s*$",
        ],
        "tax": [
            r"(?im)^\s*TAX\s*:?\s*[$₹€£]?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\s*$",
            r"(?im)^\s*TAX\s*$\n^\s*[$₹€£]?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\s*$",
        ],
        "invoice_date": [
            r"(?im)^\s*INVOICE\s+DATE\s*:?\s*(.+?)\s*$",
            r"(?im)^\s*INVOICE\s+DATE\s*$\n^\s*(.+?)\s*$",
        ],
        "due_date": [
            r"(?im)^\s*DUE\s+DATE\s*:?\s*(.+?)\s*$",
            r"(?im)^\s*DUE\s+DATE\s*$\n^\s*(.+?)\s*$",
        ],
        "payment_status": [
            r"(?im)^\s*PAYMENT\s+STATUS\s*:?\s*(.+?)\s*$",
            r"(?im)^\s*PAYMENT\s+STATUS\s*$\n^\s*(.+?)\s*$",
        ],
        "bank_name": [
            r"(?im)^\s*(ANZ\s+Bank|HDFC\s+Bank|ICICI\s+Bank|SBI|State\s+Bank\s+of\s+India|Axis\s+Bank|Kotak\s+Mahindra\s+Bank)\s*$",
        ],
    }

    for pattern in patterns.get(intent, []):
        match = re.search(pattern, text)

        if match:
            value = match.group(1).strip()

            if intent in {"account_number", "bsb_number"}:
                value = re.sub(r"\s+", " ", value).strip()

            return value

    if intent == "vendor":
        match = re.search(
            r"(?im)^\s*From:\s*$\n^\s*(.+?)\s*$",
            text,
        )

        if match:
            return match.group(1).strip()

        match = re.search(
            r"(?im)^\s*Vendor\s*:\s*(.+?)\s*$",
            text,
        )

        if match:
            return match.group(1).strip()

    return None


def _question_terms(question: str):
    stop_words = {
        "what", "when", "where", "which", "who", "whom", "whose",
        "how", "why", "the", "and", "for", "from", "this", "that",
        "with", "tell", "about", "document", "does", "did", "are",
        "was", "is", "can", "you", "please", "give", "show", "of",
        "in", "on", "to", "a", "an", "it", "its", "mentioned",
        "number",
    }

    terms = {
        word.lower()
        for word in re.findall(r"\b[a-zA-Z0-9]+\b", question)
        if len(word) > 2
    }

    terms -= stop_words

    synonyms = {
        "purpose": {"description", "objective", "goal", "aim"},
        "vendor": {"seller", "supplier", "from"},
        "seller": {"vendor", "supplier"},
        "cost": {"amount", "price", "total", "charge"},
        "paid": {"payment", "received", "amount"},
        "account": {"acc", "bank"},
        "acc": {"account"},
        "total": {"grand", "amount", "due"},
    }

    expanded = set(terms)

    for term in terms:
        expanded.update(synonyms.get(term, set()))

    return terms, expanded


def _split_into_candidates(text: str):
    text = normalize_document_text(text)

    label_pattern = (
        r"(?i)(?<!\w)(?="
        r"(?:PROJECT\s*:|DESCRIPTION\s*:|PROJECT DESCRIPTION\s*:|"
        r"PAYMENT\s+STATUS\b|AMOUNT RECEIVED\s*:|BALANCE DUE\s*:|"
        r"PAYMENT TERMS(?:\s*&\s*NOTES)?\b|PROJECT DETAILS\b|"
        r"GRAND TOTAL\b|SUB\s*TOTAL\b|TOTAL DUE\b|TAX\b|GST\b|"
        r"INVOICE NO\.?\b|INVOICE NUMBER\b|INVOICE DATE\b|"
        r"ORDER NUMBER\b|VENDOR\s*:|SUPPLIER\s*:|BILL TO\b|"
        r"ACC(?:OUNT)?(?:\s*(?:NO|NUMBER))?\s*[#:.]|"
        r"BSB\s*[#:.])"
        r")"
    )

    text = re.sub(label_pattern, "\n", text)

    candidates = []

    for line in text.split("\n"):
        line = line.strip()

        if not line:
            continue

        pieces = re.split(
            r"(?<=[.!?])\s+(?=[A-Z0-9])",
            line,
        )

        candidates.extend(
            piece.strip(" \t·|")
            for piece in pieces
            if piece.strip(" \t·|")
        )

    return candidates


def _candidate_relevance(sentence: str, original_terms: set, expanded_terms: set):
    words = {
        word.lower()
        for word in re.findall(r"\b[a-zA-Z0-9]+\b", sentence)
    }

    direct_overlap = len(original_terms & words)
    expanded_overlap = len(expanded_terms & words)

    return direct_overlap * 3 + expanded_overlap


def answer_question(question: str, top_k=3, filename=None):
    if not question or not question.strip():
        return {
            "answer": "Please enter a valid question.",
            "answer_type": "extractive",
            "sources": [],
        }

    intent = detect_question_intent(question)

    # Retrieve additional chunks for better field matching.
    retrieval_count = max(top_k, 8) if intent else top_k

    results = retrieve(
        question,
        top_k=retrieval_count,
        filename=filename,
    )

    if not results:
        return {
            "answer": (
                "No indexed text was found for the selected document. "
                "Please upload and index a PDF first."
            ),
            "answer_type": "extractive",
            "sources": [],
        }

    # First try exact field extraction for specific questions.
    if intent:
        field_matches = []

        for result in results:
            value = extract_field_value(result["text"], intent)

            if value:
                field_matches.append({
                    "value": value,
                    "filename": result["filename"],
                    "page": result["page"],
                    "score": result["score"],
                })

        if field_matches:
            field_matches.sort(
                key=lambda item: item["score"],
                reverse=True,
            )

            best = field_matches[0]

            sources = [{
                "filename": best["filename"],
                "page": best["page"],
                "excerpt": next(
                    result["text"][:500]
                    for result in results
                    if result["filename"] == best["filename"]
                    and result["page"] == best["page"]
                ),
                "similarity": best["score"],
            }]

            return {
                "answer": best["value"],
                "answer_type": "structured_extraction",
                "sources": sources,
            }

    # Fall back to normal extractive RAG.
    original_terms, expanded_terms = _question_terms(question)

    candidates = []

    for result in results:
        sentences = _split_into_candidates(result["text"])

        for sentence in sentences:
            relevance = _candidate_relevance(
                sentence,
                original_terms,
                expanded_terms,
            )

            candidates.append({
                "text": sentence,
                "filename": result["filename"],
                "page": result["page"],
                "chunk_score": result["score"],
                "relevance": relevance,
                "length": len(sentence),
            })

    if not candidates:
        return {
            "answer": "I couldn't find an answer in the indexed text.",
            "answer_type": "extractive",
            "sources": [],
        }

    candidates.sort(
        key=lambda item: (
            item["relevance"],
            item["chunk_score"],
            -item["length"],
        ),
        reverse=True,
    )

    best = candidates[0]

    if best["relevance"] == 0 and best["chunk_score"] < 0.30:
        return {
            "answer": (
                "I couldn't find a sufficiently relevant answer "
                "in the selected document."
            ),
            "answer_type": "extractive",
            "sources": [],
        }

    sources = []
    seen = set()

    for result in results:
        key = (result["filename"], result["page"])

        if key not in seen:
            sources.append({
                "filename": result["filename"],
                "page": result["page"],
                "excerpt": result["text"][:500],
                "similarity": result["score"],
            })

            seen.add(key)

    return {
        "answer": best["text"][:500],
        "answer_type": "extractive",
        "sources": sources,
    }
