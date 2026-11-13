
"""
DocuMind AI - Multi-document invoice comparison engine.
Uses deterministic extraction and calculations, not a generative LLM.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from invoice_extractor import extract_invoice_fields

COMPARISON_FIELDS = (
    "invoice_number",
    "vendor",
    "invoice_date",
    "subtotal",
    "tax",
    "total",
)


def _document_text(records: list[dict[str, Any]]) -> str:
    ordered = sorted(
        records,
        key=lambda item: (
            item.get("page", 1),
            item.get("chunk_index", 0),
        ),
    )

    return "\n".join(
        str(record.get("text", "")).strip()
        for record in ordered
        if record.get("text")
    ).strip()


def _unwrap_invoice_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}

    nested = result.get("invoice")
    return nested if isinstance(nested, dict) else result


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None

    raw = str(value).strip()

    if not raw or "%" in raw:
        return None

    negative = raw.startswith("(") and raw.endswith(")")

    cleaned = raw.replace(",", "")
    cleaned = re.sub(r"(?i)\bINR\b", "", cleaned)
    cleaned = re.sub(r"(?i)\bRS\.?\b", "", cleaned)
    cleaned = re.sub(r"[₹$€£]", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned).strip("()")
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)

    if not cleaned or cleaned in {".", "-", "-."}:
        return None

    try:
        amount = Decimal(cleaned)

        if negative:
            amount = -abs(amount)

        return amount.quantize(Decimal("0.01"))

    except (InvalidOperation, ValueError):
        return None


def _format_decimal(value: Decimal | None) -> str | None:
    return f"{value:,.2f}" if value is not None else None


def _page_numbers(records: list[dict[str, Any]]) -> list[int]:
    return sorted({
        record["page"]
        for record in records
        if isinstance(record.get("page"), int)
    })


def _normalize_invoice_number(value: Any) -> str | None:
    if value is None:
        return None

    normalized = re.sub(r"[^A-Z0-9]", "", str(value).upper())

    return normalized or None


def _detect_currency(text: str) -> dict[str, str]:
    """
    Detect currency from invoice text.

    Explicit currency codes take priority over symbols.
    A bare dollar symbol is ambiguous and is not assumed to be USD.
    """

    upper_text = text.upper()

    explicit_currencies = [
        (r"\bINR\b", "INR", "₹", "Indian Rupee"),
        (r"\bUSD\b", "USD", "$", "US Dollar"),
        (r"\bAUD\b", "AUD", "$", "Australian Dollar"),
        (r"\bCAD\b", "CAD", "$", "Canadian Dollar"),
        (r"\bSGD\b", "SGD", "$", "Singapore Dollar"),
        (r"\bEUR\b", "EUR", "€", "Euro"),
        (r"\bGBP\b", "GBP", "£", "British Pound"),
        (r"\bAED\b", "AED", "د.إ", "UAE Dirham"),
        (r"\bJPY\b", "JPY", "¥", "Japanese Yen"),
    ]

    for pattern, code, symbol, name in explicit_currencies:
        if re.search(pattern, upper_text):
            return {
                "currency_code": code,
                "currency_symbol": symbol,
                "currency_name": name,
            }

    if "₹" in text or re.search(r"(?i)\bRS\.?", text):
        return {
            "currency_code": "INR",
            "currency_symbol": "₹",
            "currency_name": "Indian Rupee",
        }

    # The invoice PDF extraction may represent ₹ as capital I.
    if re.search(r"(?m)(?:^|\s)I\s?\d", text):
        return {
            "currency_code": "INR",
            "currency_symbol": "₹",
            "currency_name": "Indian Rupee",
        }

    if "$" in text:
        return {
            "currency_code": "DOLLAR_UNSPECIFIED",
            "currency_symbol": "$",
            "currency_name": "Dollar (currency unspecified)",
        }

    if "€" in text:
        return {
            "currency_code": "EUR",
            "currency_symbol": "€",
            "currency_name": "Euro",
        }

    if "£" in text:
        return {
            "currency_code": "GBP",
            "currency_symbol": "£",
            "currency_name": "British Pound",
        }

    if "¥" in text:
        return {
            "currency_code": "YEN_UNSPECIFIED",
            "currency_symbol": "¥",
            "currency_name": "Yen (currency unspecified)",
        }

    return {
        "currency_code": "UNKNOWN",
        "currency_symbol": "",
        "currency_name": "Unknown currency",
    }


def _compare_one_document(
    filename: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:

    text = _document_text(records)

    extracted = extract_invoice_fields(text) if text else {}

    invoice_data = _unwrap_invoice_result(extracted)

    invoice = {
        field: invoice_data.get(field)
        for field in COMPARISON_FIELDS
    }

    missing_fields = [
        field
        for field in COMPARISON_FIELDS
        if invoice.get(field) is None
        or not str(invoice.get(field)).strip()
    ]

    parsed_total = _parse_decimal(invoice.get("total"))
    currency = _detect_currency(text)

    return {
        "filename": filename,
        "invoice": invoice,
        "currency": currency,
        "missing_fields": missing_fields,
        "total_numeric": (
            str(parsed_total)
            if parsed_total is not None
            else None
        ),
        "source_pages": _page_numbers(records),
    }


def _calculate_currency_summary(
    currency_code: str,
    currency_documents: list[dict[str, Any]],
) -> dict[str, Any]:

    valid_totals = []

    for item in currency_documents:
        value = item["total_numeric"]

        if value is not None:
            try:
                valid_totals.append(
                    (item["filename"], Decimal(value))
                )
            except InvalidOperation:
                continue

    combined = sum(
        (amount for _, amount in valid_totals),
        start=Decimal("0.00"),
    )

    average = (
        combined / Decimal(len(valid_totals))
        if valid_totals
        else None
    )

    highest = (
        max(valid_totals, key=lambda row: row[1])
        if valid_totals
        else None
    )

    lowest = (
        min(valid_totals, key=lambda row: row[1])
        if valid_totals
        else None
    )

    currency = currency_documents[0]["currency"]

    return {
        "currency_code": currency_code,
        "currency_symbol": currency["currency_symbol"],
        "currency_name": currency["currency_name"],
        "document_count": len(currency_documents),
        "documents_with_valid_total": len(valid_totals),
        "combined_total": (
            _format_decimal(combined)
            if valid_totals
            else None
        ),
        "average_total": _format_decimal(average),
        "highest_total": {
            "filename": highest[0],
            "amount": _format_decimal(highest[1]),
        } if highest else None,
        "lowest_total": {
            "filename": lowest[0],
            "amount": _format_decimal(lowest[1]),
        } if lowest else None,
    }


def compare_invoices(
    documents: dict[str, list[dict[str, Any]]],
    selected_filenames: list[str] | None = None,
) -> dict[str, Any]:

    if selected_filenames is None:
        filenames = list(documents.keys())
    else:
        filenames = list(dict.fromkeys(selected_filenames))

    if len(filenames) < 2:
        raise ValueError(
            "Select at least two documents to compare."
        )

    missing_documents = [
        name for name in filenames
        if name not in documents
    ]

    if missing_documents:
        raise ValueError(
            "These documents are not indexed: "
            + ", ".join(missing_documents)
        )

    comparisons = [
        _compare_one_document(name, documents[name])
        for name in filenames
    ]

    # Group documents by detected currency.
    currency_groups: dict[str, list[dict[str, Any]]] = {}

    for item in comparisons:
        code = item["currency"]["currency_code"]

        currency_groups.setdefault(code, []).append(item)

    currency_summaries = [
        _calculate_currency_summary(code, items)
        for code, items in currency_groups.items()
    ]

    total_valid_documents = sum(
        item["documents_with_valid_total"]
        for item in currency_summaries
    )

    # A combined total is meaningful only when all valid
    # invoice totals belong to one currency group.
    if len(currency_summaries) == 1:
        only_group = currency_summaries[0]

        combined_total = only_group["combined_total"]
        average_total = only_group["average_total"]
        highest_total = only_group["highest_total"]
        lowest_total = only_group["lowest_total"]

    else:
        combined_total = None
        average_total = None
        highest_total = None
        lowest_total = None

    # Detect duplicate invoice numbers.
    number_groups = {}

    for item in comparisons:
        original = item["invoice"].get("invoice_number")
        normalized = _normalize_invoice_number(original)

        if normalized:
            group = number_groups.setdefault(
                normalized,
                {
                    "invoice_number": original,
                    "filenames": [],
                },
            )

            group["filenames"].append(item["filename"])

    duplicates = [
        group
        for group in number_groups.values()
        if len(group["filenames"]) > 1
    ]

    # Detect missing invoice fields.
    incomplete = [
        {
            "filename": item["filename"],
            "missing_fields": item["missing_fields"],
        }
        for item in comparisons
        if item["missing_fields"]
    ]

    mixed_currencies = len(currency_groups) > 1

    notes = [
        "Amounts are calculated only when a monetary total can be parsed.",
        "Percentage-only tax values are not treated as tax amounts.",
        "Check extracted values against the original PDFs.",
    ]

    if mixed_currencies:
        notes.append(
            "Different currencies were detected. "
            "Combined and average totals across currencies "
            "have not been calculated."
        )

    if "DOLLAR_UNSPECIFIED" in currency_groups:
        notes.append(
            "A dollar symbol ($) was detected without an explicit "
            "currency code. It may represent USD, AUD, CAD, or "
            "another dollar currency. Verify the original invoice."
        )

    if "UNKNOWN" in currency_groups:
        notes.append(
            "Currency could not be identified for one or more invoices."
        )

    return {
        "document_count": len(comparisons),

        "documents": comparisons,

        "financial_summary": {
            "documents_with_valid_total": total_valid_documents,

            "currency_count": len(currency_groups),

            "mixed_currencies": mixed_currencies,

            "combined_total": combined_total,

            "average_total": average_total,

            "highest_total": highest_total,

            "lowest_total": lowest_total,

            "currency_summaries": currency_summaries,
        },

        "duplicate_invoice_numbers": duplicates,

        "incomplete_documents": incomplete,

        "notes": notes,
    }
