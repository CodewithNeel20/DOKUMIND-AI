
import re


CATEGORY_RULES = {
    "Invoice": {
        "strong": {
            "invoice number": 6,
            "invoice no": 6,
            "invoice #": 6,
            "bill to": 5,
            "amount due": 6,
            "grand total": 6,
            "subtotal": 4,
            "sub total": 4,
            "tax amount": 4,
            "payment due": 4,
            "unit price": 3,
            "quantity": 2,
            "ship to": 3,
        },
        "support": {
            "invoice": 2,
            "vendor": 2,
            "supplier": 2,
            "purchase order": 3,
            "payment terms": 3,
            "description": 1,
            "total": 1,
            "gst": 2,
            "vat": 2,
            "currency": 1,
        },
    },

    "Resume": {
        "strong": {
            "work experience": 7,
            "professional experience": 7,
            "technical skills": 6,
            "career objective": 6,
            "professional summary": 6,
            "curriculum vitae": 8,
            "education": 4,
            "internship experience": 6,
            "academic projects": 5,
            "personal projects": 4,
            "certifications": 4,
            "programming languages": 5,
            "core competencies": 5,
            "career summary": 5,
        },
        "support": {
            "resume": 3,
            "linkedin": 2,
            "github": 2,
            "skills": 2,
            "projects": 2,
            "bachelor": 2,
            "b.tech": 2,
            "diploma": 2,
            "university": 2,
            "college": 2,
            "experience": 2,
            "objective": 2,
            "achievements": 2,
            "languages": 1,
            "email": 1,
            "phone": 1,
        },
    },

    "Contract": {
        "strong": {
            "hereby agree": 7,
            "terms and conditions": 6,
            "governing law": 6,
            "confidentiality agreement": 6,
            "agreement between": 5,
            "termination clause": 5,
            "parties agree": 5,
            "effective date": 3,
        },
        "support": {
            "contract": 3,
            "agreement": 3,
            "obligations": 3,
            "confidentiality": 2,
            "termination": 2,
            "signature": 2,
            "whereas": 3,
            "liability": 2,
            "jurisdiction": 2,
        },
    },

    "Report": {
        "strong": {
            "executive summary": 6,
            "methodology": 5,
            "research findings": 6,
            "annual report": 7,
            "financial report": 7,
            "conclusion": 4,
            "recommendations": 4,
            "results and discussion": 5,
        },
        "support": {
            "report": 2,
            "introduction": 2,
            "analysis": 2,
            "findings": 3,
            "research": 2,
            "results": 2,
            "discussion": 2,
            "data analysis": 3,
            "observations": 2,
        },
    },
}


def normalize_text(text):
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains_phrase(text, phrase):
    pattern = (
        r"(?<!\w)"
        + re.escape(phrase.lower())
        + r"(?!\w)"
    )
    return re.search(pattern, text) is not None


def calculate_category_score(text, rules):
    score = 0
    strong_matches = []
    support_matches = []

    for keyword, weight in rules["strong"].items():
        if contains_phrase(text, keyword):
            score += weight
            strong_matches.append(keyword)

    for keyword, weight in rules["support"].items():
        if contains_phrase(text, keyword):
            score += weight
            support_matches.append(keyword)

    return score, strong_matches, support_matches


def classify_document(text):
    if not isinstance(text, str) or not text.strip():
        return {
            "category": "Other",
            "confidence": 0.0,
            "matched_keywords": [],
            "scores": {},
            "message": "No readable text found for classification."
        }

    normalized_text = normalize_text(text)

    scores = {}
    matches = {}

    for category, rules in CATEGORY_RULES.items():
        score, strong, support = calculate_category_score(
            normalized_text,
            rules
        )

        scores[category] = score
        matches[category] = {
            "strong": strong,
            "support": support
        }

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True
    )

    best_category, best_score = ranked[0]
    second_score = ranked[1][1]

    strong_matches = matches[best_category]["strong"]
    support_matches = matches[best_category]["support"]

    # Minimum evidence requirements
    if best_category == "Invoice":
        valid_evidence = (
            len(strong_matches) >= 2
            or (
                len(strong_matches) >= 1
                and len(support_matches) >= 2
            )
        )

    elif best_category == "Resume":
        valid_evidence = (
            len(strong_matches) >= 2
            or (
                len(strong_matches) >= 1
                and len(support_matches) >= 3
            )
        )

    elif best_category == "Contract":
        valid_evidence = (
            len(strong_matches) >= 1
            and len(support_matches) >= 1
        )

    else:
        valid_evidence = (
            len(strong_matches) >= 1
            and len(support_matches) >= 1
        )

    if best_score < 6 or not valid_evidence:
        return {
            "category": "Other",
            "confidence": 0.0,
            "matched_keywords": [],
            "scores": scores,
            "message": "Not enough evidence to identify the document type."
        }

    if best_score == second_score:
        return {
            "category": "Other",
            "confidence": 0.0,
            "matched_keywords": [],
            "scores": scores,
            "message": "Document classification is ambiguous."
        }

    margin = best_score - second_score

    confidence = 0.60 + min(
        best_score * 0.012 + margin * 0.015,
        0.35
    )

    matched_keywords = strong_matches + support_matches

    return {
        "category": best_category,
        "confidence": round(min(confidence, 0.95), 2),
        "matched_keywords": matched_keywords,
        "scores": scores,
        "message": "Document classified successfully."
    }
