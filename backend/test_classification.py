
from classification_engine import classify_document


sample_documents = {
    "Invoice": """
        INVOICE
        Invoice Number: INV-2026-001
        Bill To: ABC Company
        Subtotal: 1000
        Tax: 180
        Grand Total: 1180
        Payment Due: 30 days
    """,

    "Resume": """
        RESUME
        Professional Summary
        Technical Skills: Python, Java, SQL
        Work Experience
        Education
        Projects
        Certifications
    """,

    "Contract": """
        AGREEMENT
        The parties hereby agree to the following terms and conditions.
        Confidentiality and obligations apply.
        Termination and governing law are specified.
    """,

    "Report": """
        ANNUAL REPORT
        Executive Summary
        Introduction
        Methodology
        Findings and Analysis
        Results and Recommendations
        Conclusion
    """
}


for expected_category, document_text in sample_documents.items():
    result = classify_document(document_text)

    print("\nExpected:", expected_category)
    print("Predicted:", result["category"])
    print("Confidence:", result["confidence"])
    print("Matched Keywords:", result["matched_keywords"])
    print("Status:", result["message"])

    if result["category"] == expected_category:
        print("TEST: PASSED")
    else:
        print("TEST: FAILED")
