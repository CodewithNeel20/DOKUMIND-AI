
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


# ============================================================
# CONSTANTS
# ============================================================

CENT = Decimal("0.01")

INVOICE_LABELS = (
    r"INVOICE\s*(?:NUMBER|NO\.?|NUM|ID|#)",
    r"ORDER\s*(?:NUMBER|NO\.?|NUM|ID|#)",
    r"INVOICE\s+DATE",
    r"DATE\s+OF\s+INVOICE",
    r"DUE\s+DATE",
    r"PAYMENT\s+DUE\s+DATE",
    r"FROM",
    r"VENDOR",
    r"SUPPLIER",
    r"BILL\s+TO",
    r"SUB\s*TOTAL",
    r"GST",
    r"TAX",
    r"VAT",
    r"GRAND\s+TOTAL",
    r"TOTAL\s+DUE",
    r"INVOICE\s+TOTAL",
    r"AMOUNT\s+DUE",
    r"TOTAL\s+AMOUNT",
    r"PAYMENT\s+STATUS",
    r"PAYMENT\s+TERMS",
    r"EMAIL",
    r"ADDRESS",
    r"PHONE",
    r"GSTIN",
)


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_lines(text: str) -> list[str]:
    """
    Convert PDF text into clean lines.

    Preserves existing line breaks because they are important
    for identifying invoice labels and their corresponding values.
    """

    if not text:
        return []

    text = str(text)
    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Restore line boundaries if labels were flattened into text.
    label_pattern = "|".join(INVOICE_LABELS)

    text = re.sub(
        rf"(?i)\s+(?=(?:{label_pattern})\s*:?\s*$)",
        "\n",
        text,
    )

    lines = []

    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()

        if line:
            lines.append(line)

    return lines


# ============================================================
# MONEY PARSING
# ============================================================

def parse_amount(value):
    """
    Parse monetary amounts, including Indian number formatting.

    Examples:
        I1,00,06,000.00 -> 10006000.00
        I18,01,080.00   -> 1801080.00
        ₹85.00          -> 85.00
        $93.50          -> 93.50
        1,234.50        -> 1234.50

    The leading I/l correction is intended for the OCR-like
    rupee symbol found in the supplied DocuMind PDF.
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Reject percentages. A tax rate is not a tax amount.
    if "%" in value:
        return None

    negative = (
        value.startswith("(")
        and value.endswith(")")
    )

    if negative:
        value = value[1:-1].strip()

    # Remove currency symbols and currency abbreviations.
    value = re.sub(
        r"(?i)\b(?:INR|USD|EUR|GBP|RS|RUPEES?)\b",
        "",
        value,
    )

    value = re.sub(r"[₹$€£]", "", value)

    # Correct OCR confusion of I/l with the rupee symbol.
    value = re.sub(r"^[Il](?=\d)", "", value)

    value = value.replace(",", "")
    value = value.replace(" ", "")

    # Require the entire remaining string to be a valid amount.
    if not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", value):
        return None

    try:
        amount = Decimal(value)

        if negative:
            amount = -abs(amount)

        return amount.quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

    except InvalidOperation:
        return None


def format_amount(value):
    if value is None:
        return None

    return str(
        Decimal(value).quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )
    )


def extract_amount_from_line(line):
    """
    Extract a complete amount token from one line.

    Does not accidentally extract a percentage.
    """

    if not line or "%" in line:
        return None

    pattern = (
        r"(?<![A-Za-z0-9])"
        r"(?:₹|\$|€|£|Rs\.?|INR|USD)?\s*"
        r"[Il]?\d[\d,]*(?:\.\d{1,2})?"
        r"(?![A-Za-z0-9])"
    )

    matches = re.findall(
        pattern,
        line,
        flags=re.IGNORECASE,
    )

    for match in matches:
        amount = parse_amount(match)

        if amount is not None:
            return amount

    return None


# ============================================================
# LABEL MATCHING
# ============================================================

def label_matches(line, patterns):
    return bool(
        re.match(
            patterns,
            line.strip(),
            flags=re.IGNORECASE,
        )
    )


def find_labeled_value(lines, patterns, lookahead=2):
    """
    Extract a value following a label.

    Supports both:
        Invoice Number: INV-001

    And:
        Invoice Number
        INV-001
    """

    for index, line in enumerate(lines):

        match = re.match(
            patterns,
            line.strip(),
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        remaining = line[match.end():].strip()

        remaining = re.sub(
            r"^[\s:=-]+",
            "",
            remaining,
        ).strip()

        if remaining:
            return remaining

        for offset in range(1, lookahead + 1):

            next_index = index + offset

            if next_index >= len(lines):
                break

            candidate = lines[next_index].strip()

            if not candidate:
                continue

            if re.match(
                r"(?i)^(?:invoice|order|subtotal|sub total|"
                r"gst|tax|vat|grand total|total due|"
                r"amount due|invoice date|due date|"
                r"payment status|email|address|phone)\b",
                candidate,
            ):
                break

            return candidate

    return None


# ============================================================
# MONETARY LABEL EXTRACTION
# ============================================================

def find_amount_after_label(
    lines,
    patterns,
    lookahead=5,
    use_last_label=False,
):
    """
    Find an amount after a specific label.

    use_last_label=True is important for invoices such as
    the WordPress sample, which has two Sub Total labels.

    It selects the final matching subtotal label so that
    the table quantity 1.00 is not mistaken for the subtotal.
    """

    matching_indices = []

    for index, line in enumerate(lines):

        if label_matches(line, patterns):
            matching_indices.append(index)

    if not matching_indices:
        return None

    if use_last_label:
        matching_indices = list(reversed(matching_indices))

    for index in matching_indices:

        # Check the label line itself first.
        candidates = [lines[index]]

        # Then check following lines.
        for offset in range(1, lookahead + 1):

            next_index = index + offset

            if next_index >= len(lines):
                break

            candidates.append(lines[next_index])

        for candidate in candidates:

            # Never treat a percentage as a monetary amount.
            if "%" in candidate:
                continue

            amount = extract_amount_from_line(candidate)

            if amount is not None:
                return amount

    return None


# ============================================================
# INVOICE NUMBER
# ============================================================

def clean_invoice_number(value):
    if not value:
        return None

    value = str(value).strip()

    value = re.sub(
        r"(?i)^(?:invoice\s*)?(?:no\.?|number|num|id|#)\s*:?",
        "",
        value,
    )

    value = value.strip(" :#[]")

    match = re.search(
        r"[A-Z0-9][A-Z0-9/_-]*",
        value,
        flags=re.IGNORECASE,
    )

    return match.group(0) if match else None


# ============================================================
# DATE EXTRACTION
# ============================================================

DATE_PATTERN = re.compile(
    r"(?i)"
    r"(?:"
    r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"
    r"|"
    r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}"
    r"|"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|"
    r"\d{4}[/-]\d{1,2}[/-]\d{1,2}"
    r")"
)


def extract_date(lines, patterns):
    value = find_labeled_value(
        lines,
        patterns,
        lookahead=1,
    )

    if not value:
        return None

    match = DATE_PATTERN.search(value)

    return match.group(0).strip() if match else None


# ============================================================
# VENDOR EXTRACTION
# ============================================================

def clean_vendor(value):
    if not value:
        return None

    value = str(value).strip()

    # Remove contact details if they appear on the same line.
    value = re.split(
        r"(?i)\b(?:EMAIL|ADDRESS|PHONE|GSTIN)\s*:",
        value,
    )[0]

    value = value.strip(" :,-|")

    if not value:
        return None

    if value.lower() in {
        "vendor",
        "supplier",
        "from",
        "unknown",
        "none",
        "n/a",
    }:
        return None

    if len(value) > 100:
        return None

    return value


def extract_vendor(lines):
    value = find_labeled_value(
        lines,
        r"^\s*(?:FROM|VENDOR|SUPPLIER)\s*:?\s*",
        lookahead=1,
    )

    if value:
        return clean_vendor(value)

    # Fallback for invoices where the vendor name is at the top.
    for line in lines[:5]:

        candidate = line.strip()

        if not candidate:
            continue

        if re.search(
            r"(?i)\b(invoice|date|bill to|description|"
            r"subtotal|total|tax|gst|payment)\b",
            candidate,
        ):
            continue

        if "@" in candidate:
            continue

        if re.search(r"\d{4,}", candidate):
            continue

        if len(candidate) <= 80:
            return clean_vendor(candidate)

    return None


# ============================================================
# TAX RATE
# ============================================================

def extract_tax_rate(lines):
    patterns = [
        r"GST\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*\)",
        r"\bGST\s*(?:RATE)?\s*:?\s*(\d+(?:\.\d+)?)\s*%",
        r"\bVAT\s*(?:RATE)?\s*:?\s*(\d+(?:\.\d+)?)\s*%",
        r"\bTAX\s*(?:RATE)?\s*:?\s*(\d+(?:\.\d+)?)\s*%",
    ]

    for line in lines:

        for pattern in patterns:

            match = re.search(
                pattern,
                line,
                flags=re.IGNORECASE,
            )

            if match:
                try:
                    return Decimal(match.group(1))
                except InvalidOperation:
                    continue

    return None


# ============================================================
# PAYMENT STATUS
# ============================================================

def extract_payment_status(lines):
    value = find_labeled_value(
        lines,
        r"^\s*PAYMENT\s+STATUS\s*:?\s*",
        lookahead=1,
    )

    # Some invoices show "Paid" at the bottom without a label.
    if not value:
        for line in reversed(lines):
            if line.strip().lower() in {
                "paid",
                "unpaid",
                "pending",
                "overdue",
            }:
                return line.strip().title()

        return None

    match = re.match(
        r"(?i)(partially\s+paid|part-paid|part paid|"
        r"paid|unpaid|pending|overdue)",
        value.strip(),
    )

    return match.group(1).title() if match else None


# ============================================================
# MAIN EXTRACTION FUNCTION
# ============================================================

def extract_invoice_fields(text: str) -> dict:
    """
    Extract structured invoice fields from PDF text.

    Compatible with the existing main.py response handling.
    """

    lines = clean_lines(text)

    invoice = {
        "invoice_number": None,
        "order_number": None,
        "vendor": None,
        "invoice_date": None,
        "due_date": None,
        "payment_status": None,
        "subtotal": None,
        "tax": None,
        "tax_rate": None,
        "total": None,
    }

    if not lines:
        return {
            "invoice": invoice,
            "missing_fields": [
                "invoice_number",
                "vendor",
                "invoice_date",
                "subtotal",
                "tax",
                "total",
            ],
            "total_validation": None,
        }

    # Invoice number
    invoice_number_raw = find_labeled_value(
        lines,
        r"^\s*INVOICE\s*(?:NUMBER|NO\.?|NUM|ID|#)\s*:?\s*",
        lookahead=1,
    )

    invoice["invoice_number"] = clean_invoice_number(
        invoice_number_raw
    )

    # Order number
    order_number_raw = find_labeled_value(
        lines,
        r"^\s*ORDER\s*(?:NUMBER|NO\.?|NUM|ID|#)\s*:?\s*",
        lookahead=1,
    )

    invoice["order_number"] = clean_invoice_number(
        order_number_raw
    )

    # Vendor
    invoice["vendor"] = extract_vendor(lines)

    # Invoice date
    invoice["invoice_date"] = extract_date(
        lines,
        r"^\s*(?:INVOICE\s+DATE|DATE\s+OF\s+INVOICE)\s*:?\s*",
    )

    # Due date
    invoice["due_date"] = extract_date(
        lines,
        r"^\s*(?:DUE\s+DATE|PAYMENT\s+DUE\s+DATE)\s*:?\s*",
    )

    # Subtotal:
    # Use the last matching label to avoid the table heading
    # followed by quantity 1.00 in the WordPress sample.
    subtotal = find_amount_after_label(
        lines,
        r"^\s*(?:SUB\s*TOTAL|SUBTOTAL|"
        r"NET\s+AMOUNT|AMOUNT\s+BEFORE\s+TAX)\b",
        lookahead=5,
        use_last_label=True,
    )

    # Tax amount:
    # GST (18%) is a rate, so the next line is inspected
    # for the actual amount.
    tax = find_amount_after_label(
        lines,
        r"^\s*(?:TAX\s+AMOUNT|GST\s+AMOUNT|"
        r"VAT\s+AMOUNT|TAX|GST|VAT)\b",
        lookahead=3,
    )

    # Tax rate
    tax_rate = extract_tax_rate(lines)

    # Calculate tax only when the actual tax amount is absent.
    if (
        tax is None
        and subtotal is not None
        and tax_rate is not None
    ):
        tax = (
            subtotal * tax_rate / Decimal("100")
        ).quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

    # Total:
    # Prefer explicit grand total / total due labels.
    total = find_amount_after_label(
        lines,
        r"^\s*(?:GRAND\s+TOTAL|TOTAL\s+DUE|"
        r"INVOICE\s+TOTAL|AMOUNT\s+DUE|TOTAL\s+AMOUNT)\b",
        lookahead=3,
    )

    # Fallback to a plain Total label.
    if total is None:
        total = find_amount_after_label(
            lines,
            r"^\s*TOTAL\b",
            lookahead=2,
            use_last_label=True,
        )

    # Payment status
    invoice["payment_status"] = extract_payment_status(lines)

    # Store formatted amounts.
    invoice["subtotal"] = format_amount(subtotal)
    invoice["tax"] = format_amount(tax)
    invoice["tax_rate"] = (
        str(tax_rate) if tax_rate is not None else None
    )
    invoice["total"] = format_amount(total)

    # Required fields
    required_fields = [
        "invoice_number",
        "vendor",
        "invoice_date",
        "subtotal",
        "tax",
        "total",
    ]

    missing_fields = [
        field
        for field in required_fields
        if invoice.get(field) is None
    ]

    # Financial validation
    total_validation = None

    if (
        subtotal is not None
        and tax is not None
        and total is not None
    ):
        expected_total = (
            subtotal + tax
        ).quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

        actual_total = total.quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

        difference = abs(
            expected_total - actual_total
        )

        total_validation = {
            "expected_total": format_amount(expected_total),
            "actual_total": format_amount(actual_total),
            "difference": format_amount(difference),
            "matches": difference <= Decimal("0.02"),
        }

    return {
        "invoice": invoice,
        "missing_fields": missing_fields,
        "total_validation": total_validation,
    }
