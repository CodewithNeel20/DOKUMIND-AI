import json
import re
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_PATH = Path(__file__).parent / "rag_index.json"

_model = None


def get_model():
    """Load the embedding model once, locally on the CPU."""
    global _model

    if _model is None:
        _model = SentenceTransformer(MODEL_NAME, device="cpu")

    return _model


def normalize_document_text(text: str) -> str:
    """Clean PDF text while preserving useful line boundaries."""
    if not text:
        return ""

    cleaned_lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def chunk_text(text: str, chunk_size=900, overlap=150):
    """
    Split text into overlapping chunks while preserving line breaks.
    Prefer splitting at line boundaries, then spaces.
    """
    text = normalize_document_text(text)

    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        if end < text_length:
            # Prefer a line boundary so labels and values stay readable.
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
    """Load saved chunks and embeddings."""
    if not INDEX_PATH.exists():
        return []

    try:
        with INDEX_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_index(records):
    """Save the index using a temporary file."""
    temp_path = INDEX_PATH.with_suffix(".tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False)

    temp_path.replace(INDEX_PATH)


def index_document(filename: str, pages: list[dict]):
    """Index a PDF, replacing any previous index with the same filename."""
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
        raise ValueError(
            "No text could be indexed. The PDF may be empty or scanned."
        )

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
    """Retrieve relevant chunks from all PDFs or one selected PDF."""
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
            "The document index has invalid embeddings. "
            "Please re-index the PDF."
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


def _question_terms(question: str):
    """Create useful question terms, including simple intent synonyms."""
    stop_words = {
        "what", "when", "where", "which", "who", "whom", "whose",
        "how", "why", "the", "and", "for", "from", "this", "that",
        "with", "tell", "about", "document", "does", "did", "are",
        "was", "is", "can", "you", "please", "give", "show", "of",
        "in", "on", "to", "a", "an", "it", "its", "mentioned",
    }

    terms = {
        word.lower()
        for word in re.findall(r"\b[a-zA-Z0-9]+\b", question)
        if len(word) > 2
    }
    terms -= stop_words

    expanded = set(terms)
    synonyms = {
        "purpose": {"description", "objective", "goal", "aim", "designed"},
        "describe": {"description", "purpose", "overview"},
        "objective": {"purpose", "goal", "aim", "description"},
        "goal": {"purpose", "objective", "aim", "description"},
        "vendor": {"seller", "supplier", "from"},
        "seller": {"vendor", "supplier"},
        "cost": {"amount", "price", "total", "charge"},
        "paid": {"payment", "received", "amount"},
    }

    for term in terms:
        expanded.update(synonyms.get(term, set()))

    return terms, expanded


def _split_into_candidates(text: str):
    """
    Split retrieved PDF text at known field labels as well as line and
    sentence boundaries. This handles PDFs where PyMuPDF joins many fields
    into one long line.
    """
    text = normalize_document_text(text)

    # Insert boundaries before common invoice/document labels even when
    # the PDF extractor has joined them together on a single line.
    label_pattern = (
        r"(?i)(?<!\w)(?="
        r"(?:PROJECT\s*:|DESCRIPTION\s*:|PROJECT DESCRIPTION\s*:|"
        r"PAYMENT\s+STATUS\b|AMOUNT RECEIVED\s*:|BALANCE DUE\s*:|"
        r"PAYMENT TERMS(?:\s*&\s*NOTES)?\b|PROJECT DETAILS\b|GRAND TOTAL\b|"
        r"SUBTOTAL\b|TAX\b|GST\b|INVOICE NO\.?\s*:|"
        r"INVOICE NUMBER\s*:|INVOICE DATE\s*:|"
        r"VENDOR\s*:|SUPPLIER\s*:|BILL TO\b)"
        r")"
    )
    text = re.sub(label_pattern, "\n", text)

    candidates = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Separate adjacent sentence-like fields without breaking decimals.
        pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line)
        candidates.extend(
            piece.strip(" \t·|") for piece in pieces if piece.strip(" \t·|")
        )

    return candidates


def _candidate_relevance(sentence: str, original_terms: set, expanded_terms: set):
    """Score a candidate using lexical overlap and useful field synonyms."""
    words = {
        word.lower()
        for word in re.findall(r"\b[a-zA-Z0-9]+\b", sentence)
    }

    direct_overlap = len(original_terms & words)
    expanded_overlap = len(expanded_terms & words)

    # Give a useful boost when a question asks for a purpose/goal
    # and the document labels the relevant text as a description.
    purpose_boost = 0
    if "purpose" in original_terms and re.search(
        r"\b(description|objective|goal|aim|designed)\b",
        sentence,
        re.IGNORECASE,
    ):
        purpose_boost = 3

    return direct_overlap * 2 + expanded_overlap + purpose_boost


def answer_question(question: str, top_k=3, filename=None):
    """Return a concise extractive answer with source citations."""
    results = retrieve(
        question,
        top_k=top_k,
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

    original_terms, expanded_terms = _question_terms(question)
    candidates = []

    for result in results:
        sentences = _split_into_candidates(result["text"])

        for position, sentence in enumerate(sentences):
            relevance = _candidate_relevance(
                sentence,
                original_terms,
                expanded_terms,
            )

            # If a description follows a project label, include that
            # label as context in the answer.
            answer_text = sentence
            if position > 0 and re.match(
                r"^(?:description|project description)\s*:",
                sentence,
                re.IGNORECASE,
            ):
                previous = sentences[position - 1]
                if re.match(r"^project\s*:", previous, re.IGNORECASE):
                    answer_text = f"{previous} — {sentence}"

            candidates.append({
                "text": answer_text,
                "filename": result["filename"],
                "page": result["page"],
                "chunk_score": result["score"],
                "relevance": relevance,
                "length": len(answer_text),
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

    # If no candidate has lexical relevance, use a conservative
    # semantic fallback only when the retrieved chunk is reasonably close.
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
