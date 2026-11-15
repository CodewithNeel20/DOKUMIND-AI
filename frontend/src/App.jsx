
import { useEffect, useState } from "react";
import axios from "axios";
import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import * as XLSX from "xlsx";

import {
  BrainCircuit,
  FileText,
  Upload,
  MessageSquare,
  LayoutDashboard,
  LoaderCircle,
  CheckCircle2,
  AlertCircle,
  Send,
  Files,
  ShieldCheck,
  RefreshCw,
  Trash2,
  Sparkles,
  Globe,
  GitCompare,
  BarChart3,
  AlertTriangle,
  Download,
  Tag,
} from "lucide-react";

import "./App.css";

const API = "http://127.0.0.1:8000";

function getCategoryClass(category) {
  const value = (category || "Other").toLowerCase();

  if (value === "invoice") return "category-invoice";
  if (value === "resume") return "category-resume";
  if (value === "contract") return "category-contract";
  if (value === "report") return "category-report";

  return "category-other";
}

function normalizeClassification(data) {
  const result = data?.classification || data;

  if (!result || typeof result !== "object") {
    return null;
  }

  return {
    category: result.category || "Other",
    confidence: Number(result.confidence) || 0,
    matched_keywords: Array.isArray(result.matched_keywords)
      ? result.matched_keywords
      : [],
    scores: result.scores || {},
    message: result.message || "Classification completed.",
  };
}

function formatAmount(value, symbol = "") {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  return `${symbol}${value}`;
}

function getInvoiceAnswer(question, invoice) {
  if (!invoice?.invoice) return null;

  const q = question.toLowerCase().replace(/\s+/g, " ").trim();
  const data = invoice.invoice;

  if (/\b(subtotal|sub-total|amount before tax)\b/.test(q)) {
    return data.subtotal != null ? `Subtotal: ${data.subtotal}` : null;
  }

  if (/\b(invoice number|invoice no\.?|invoice #|invoice id)\b/.test(q)) {
    return data.invoice_number
      ? `Invoice number: ${data.invoice_number}`
      : null;
  }

  if (/\b(order number|order no\.?|order #|order id)\b/.test(q)) {
    return data.order_number != null
      ? `Order number: ${data.order_number}`
      : null;
  }

  if (/\b(invoice date|date of invoice)\b/.test(q)) {
    return data.invoice_date
      ? `Invoice date: ${data.invoice_date}`
      : null;
  }

  if (/\b(due date|payment due date)\b/.test(q)) {
    return data.due_date ? `Due date: ${data.due_date}` : null;
  }

  if (
    /\b(vendor|supplier)\b/.test(q) ||
    /\bwho (issued|created|sent) (the )?invoice\b/.test(q)
  ) {
    return data.vendor ? `Vendor: ${data.vendor}` : null;
  }

  if (/\b(tax|vat|gst)\b/.test(q)) {
    return data.tax != null ? `Tax: ${data.tax}` : null;
  }

  if (
    /\b(total due|grand total|invoice total|amount due|total amount|total)\b/.test(q)
  ) {
    return data.total != null ? `Total: ${data.total}` : null;
  }

  return null;
}

export default function App() {
  const [file, setFile] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedFilename, setSelectedFilename] = useState("");

  const [invoice, setInvoice] = useState(null);
  const [classification, setClassification] = useState(null);
  const [classificationLoading, setClassificationLoading] = useState(false);

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);

  const [loading, setLoading] = useState(false);
  const [libraryLoading, setLibraryLoading] = useState(false);

  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const [searchAllDocs, setSearchAllDocs] = useState(false);

  const [summary, setSummary] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(false);

  const [comparisonFiles, setComparisonFiles] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);

  const selectedDocument = documents.find(
    (doc) => doc.filename === selectedFilename
  );

  const indexed = Boolean(selectedDocument);

  const chatReady = searchAllDocs
    ? documents.length > 0
    : indexed;

  const invoiceFields = invoice?.invoice
    ? [
        ["Invoice number", invoice.invoice.invoice_number],
        ["Vendor", invoice.invoice.vendor],
        ["Invoice date", invoice.invoice.invoice_date],
        ["Subtotal", invoice.invoice.subtotal],
        ["Tax", invoice.invoice.tax],
        ["Total", invoice.invoice.total],
      ]
    : [];

  const comparisonDocuments = comparison?.documents || [];
  const financialSummary = comparison?.financial_summary || {};
  const currencySummaries = financialSummary.currency_summaries || [];
  const duplicateInvoices = comparison?.duplicate_invoice_numbers || [];
  const incompleteDocuments = comparison?.incomplete_documents || [];
  const comparisonNotes = comparison?.notes || [];

  // Load documents and their classifications
  async function loadDocuments(preferredFilename = "") {
    setLibraryLoading(true);

    try {
      const result = await axios.get(`${API}/documents`);
      const rawDocuments = result.data.documents || [];

      const enrichedDocuments = await Promise.all(
        rawDocuments.map(async (doc) => {
          try {
            const response = await axios.get(
              `${API}/documents/${encodeURIComponent(doc.filename)}/classification`
            );

            const detected = normalizeClassification(response.data);

            return {
              ...doc,
              category: detected?.category || doc.category || "Other",
              confidence:
                detected?.confidence ?? doc.confidence ?? 0,
            };
          } catch {
            return {
              ...doc,
              category: doc.category || "Other",
              confidence: doc.confidence ?? 0,
            };
          }
        })
      );

      setDocuments(enrichedDocuments);

      setSelectedFilename((current) => {
        if (
          preferredFilename &&
          enrichedDocuments.some(
            (doc) => doc.filename === preferredFilename
          )
        ) {
          return preferredFilename;
        }

        if (
          current &&
          enrichedDocuments.some((doc) => doc.filename === current)
        ) {
          return current;
        }

        return enrichedDocuments.length
          ? enrichedDocuments[enrichedDocuments.length - 1].filename
          : "";
      });

      setComparisonFiles((current) => {
        const validFiles = current.filter((filename) =>
          enrichedDocuments.some((doc) => doc.filename === filename)
        );

        return validFiles.length
          ? validFiles
          : enrichedDocuments.map((doc) => doc.filename);
      });
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Could not load the document library. Check the backend."
      );
    } finally {
      setLibraryLoading(false);
    }
  }

  useEffect(() => {
    loadDocuments();
  }, []);

  // Load classification for selected document
  useEffect(() => {
    if (!selectedFilename) {
      setClassification(null);
      setClassificationLoading(false);
      return;
    }

    let active = true;

    async function loadClassification() {
      setClassificationLoading(true);
      setClassification(null);

      try {
        const result = await axios.get(
          `${API}/documents/${encodeURIComponent(
            selectedFilename
          )}/classification`
        );

        if (active) {
          setClassification(normalizeClassification(result.data));
        }
      } catch {
        if (active) {
          setClassification(null);
        }
      } finally {
        if (active) {
          setClassificationLoading(false);
        }
      }
    }

    loadClassification();

    return () => {
      active = false;
    };
  }, [selectedFilename]);

  // Upload and index PDF
  async function uploadAndIndex() {
    if (!file) {
      setError("Please select a PDF first.");
      return;
    }

    setLoading(true);
    setError("");
    setStatus("Extracting, classifying and indexing your PDF...");
    setInvoice(null);
    setClassification(null);

    const form = new FormData();
    form.append("file", file);

    try {
      const result = await axios.post(`${API}/index-pdf`, form);

      const uploadedFilename = result.data.filename;

      if (result.data.classification) {
        setClassification(
          normalizeClassification(result.data)
        );
      }

      await loadDocuments(uploadedFilename);

      setStatus(
        `${uploadedFilename} indexed successfully. ${
          result.data.chunks_indexed ?? 0
        } chunks created.`
      );

      try {
        const invoiceForm = new FormData();
        invoiceForm.append("file", file);

        const invoiceResult = await axios.post(
          `${API}/extract-invoice`,
          invoiceForm
        );

        setInvoice(invoiceResult.data);
      } catch {
        setInvoice(null);
      }

      setMessages([]);
      setFile(null);

      const input = document.getElementById("pdf-upload");
      if (input) input.value = "";
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Upload failed. Check whether the backend is running."
      );

      setStatus("");
    } finally {
      setLoading(false);
    }
  }

  // Change selected document
  function changeDocument(filename) {
    setSelectedFilename(filename);
    setInvoice(null);
    setClassification(null);
    setMessages([]);
    setQuestion("");
    setError("");

    setStatus(filename ? `Selected document: ${filename}` : "");
  }

  // Delete document
  async function deleteDocument(filename) {
    if (!window.confirm(`Remove "${filename}" from your library?`)) {
      return;
    }

    setError("");
    setLoading(true);

    try {
      await axios.delete(
        `${API}/documents/${encodeURIComponent(filename)}`
      );

      if (selectedFilename === filename) {
        setSelectedFilename("");
        setInvoice(null);
        setClassification(null);
        setMessages([]);
        setSummary("");
      }

      setComparison(null);

      await loadDocuments();

      setStatus(`"${filename}" removed from library.`);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Failed to remove document."
      );
    } finally {
      setLoading(false);
    }
  }

  // Load document summary
  useEffect(() => {
    if (!selectedFilename) {
      setSummary("");
      return;
    }

    let active = true;

    setSummaryLoading(true);
    setSummary("");

    axios
      .get(
        `${API}/documents/${encodeURIComponent(
          selectedFilename
        )}/summary`
      )
      .then((res) => {
        if (active) {
          setSummary(res.data.summary || "");
        }
      })
      .catch(() => {
        if (active) setSummary("");
      })
      .finally(() => {
        if (active) setSummaryLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedFilename]);

  // Ask AI document question
  async function askQuestion(e) {
    e.preventDefault();

    const text = question.trim();

    if (!text || loading) return;

    if (!selectedFilename && !searchAllDocs) {
      setError("Please select an indexed document first.");
      return;
    }

    setError("");
    setQuestion("");

    setMessages((old) => [
      ...old,
      { role: "user", text },
    ]);

    setLoading(true);

    try {
      const result = await axios.post(`${API}/ask`, {
        question: text,
        filename: searchAllDocs ? null : selectedFilename,
      });

      const invoiceAnswer = getInvoiceAnswer(text, invoice);

      setMessages((old) => [
        ...old,
        {
          role: "assistant",
          text:
            invoiceAnswer ||
            result.data.answer ||
            "No answer was returned.",
          sources: result.data.sources || [],
        },
      ]);
    } catch (err) {
      setMessages((old) => [
        ...old,
        {
          role: "assistant",
          text:
            err.response?.data?.detail ||
            "I couldn't answer that question. Please try again.",
          sources: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  // Comparison selection
  function toggleComparisonFile(filename) {
    setComparisonFiles((current) =>
      current.includes(filename)
        ? current.filter((item) => item !== filename)
        : [...current, filename]
    );

    setComparison(null);
  }

  function selectAllComparisonFiles() {
    setComparisonFiles(documents.map((doc) => doc.filename));
    setComparison(null);
  }

  function clearComparisonFiles() {
    setComparisonFiles([]);
    setComparison(null);
  }

  // Compare invoices
  async function compareInvoices() {
    if (comparisonFiles.length < 2) {
      setError("Select at least two documents to compare.");
      return;
    }

    setComparisonLoading(true);
    setError("");
    setComparison(null);

    try {
      const result = await axios.post(
        `${API}/compare-invoices`,
        { filenames: comparisonFiles }
      );

      setComparison(result.data);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Invoice comparison failed. Please try again."
      );
    } finally {
      setComparisonLoading(false);
    }
  }

  // Export comparison report as PDF
  function exportComparisonPDF() {
    if (!comparison) return;

    const pdf = new jsPDF({
      orientation: "landscape",
      unit: "mm",
      format: "a4",
    });

    const pageWidth = pdf.internal.pageSize.getWidth();

    pdf.setFontSize(22);
    pdf.text("DocuMind AI", 14, 18);

    pdf.setFontSize(15);
    pdf.text("Invoice Comparison Report", 14, 28);

    pdf.setFontSize(9);
    pdf.text(`Generated: ${new Date().toLocaleString()}`, 14, 36);
    pdf.text(`Documents analyzed: ${comparisonDocuments.length}`, 14, 42);
    pdf.text(`Currency groups: ${currencySummaries.length}`, 14, 48);
    pdf.text(`Duplicate invoices: ${duplicateInvoices.length}`, 14, 54);
    pdf.text(`Incomplete documents: ${incompleteDocuments.length}`, 14, 60);

    pdf.setFontSize(13);
    pdf.text("Currency-wise Financial Summary", 14, 70);

    autoTable(pdf, {
      startY: 75,
      head: [[
        "Currency",
        "Invoices",
        "Combined Total",
        "Average",
        "Highest",
        "Lowest",
      ]],
      body: currencySummaries.map((item) => [
        `${item.currency_name || ""} (${item.currency_code || ""})`,
        item.document_count ?? "—",
        formatAmount(item.combined_total, item.currency_symbol),
        formatAmount(item.average_total, item.currency_symbol),
        formatAmount(item.highest_total?.amount, item.currency_symbol),
        formatAmount(item.lowest_total?.amount, item.currency_symbol),
      ]),
      theme: "grid",
      styles: { fontSize: 8 },
      headStyles: { fillColor: [38, 54, 85] },
    });

    pdf.addPage();

    pdf.setFontSize(15);
    pdf.text("Invoice Details", 14, 20);

    autoTable(pdf, {
      startY: 27,
      head: [[
        "Document",
        "Invoice Number",
        "Vendor",
        "Date",
        "Currency",
        "Subtotal",
        "Tax",
        "Total",
      ]],
      body: comparisonDocuments.map((doc) => [
        doc.filename || "—",
        doc.invoice?.invoice_number || "—",
        doc.invoice?.vendor || "—",
        doc.invoice?.invoice_date || "—",
        doc.currency?.currency_code || "—",
        formatAmount(doc.invoice?.subtotal, doc.currency?.currency_symbol),
        formatAmount(doc.invoice?.tax, doc.currency?.currency_symbol),
        formatAmount(doc.invoice?.total, doc.currency?.currency_symbol),
      ]),
      theme: "grid",
      styles: { fontSize: 7, cellPadding: 2 },
      headStyles: { fillColor: [38, 54, 85] },
    });

    const warnings = [
      ...duplicateInvoices.map((item) =>
        `Duplicate invoice: ${
          typeof item === "string" ? item : JSON.stringify(item)
        }`
      ),
      ...incompleteDocuments.map((item) =>
        `Incomplete document: ${
          typeof item === "string" ? item : JSON.stringify(item)
        }`
      ),
      ...comparisonNotes.map((note) => `Note: ${note}`),
    ];

    if (warnings.length > 0) {
      pdf.addPage();
      pdf.setFontSize(15);
      pdf.text("Warnings and Observations", 14, 20);

      autoTable(pdf, {
        startY: 27,
        head: [["No.", "Warning / Observation"]],
        body: warnings.map((warning, index) => [
          index + 1,
          warning,
        ]),
        theme: "grid",
        styles: { fontSize: 9 },
        headStyles: { fillColor: [160, 75, 45] },
      });
    }

    const pageCount = pdf.internal.getNumberOfPages();

    for (let page = 1; page <= pageCount; page++) {
      pdf.setPage(page);
      pdf.setFontSize(8);

      pdf.text(
        `DocuMind AI | Page ${page} of ${pageCount}`,
        pageWidth - 14,
        pdf.internal.pageSize.getHeight() - 8,
        { align: "right" }
      );
    }

    pdf.save("DocuMind_AI_Invoice_Comparison_Report.pdf");
  }

  // Export comparison data as Excel
  function exportComparisonExcel() {
    if (!comparison) return;

    const invoiceRows = comparisonDocuments.map((doc) => ({
      Document: doc.filename || "",
      "Invoice Number": doc.invoice?.invoice_number || "",
      Vendor: doc.invoice?.vendor || "",
      Date: doc.invoice?.invoice_date || "",
      Currency: doc.currency?.currency_code || "",
      Subtotal: doc.invoice?.subtotal ?? "",
      Tax: doc.invoice?.tax ?? "",
      Total: doc.invoice?.total ?? "",
    }));

    const summaryRows = currencySummaries.map((item) => ({
      Currency: item.currency_code || "",
      "Currency Name": item.currency_name || "",
      Invoices: item.document_count ?? "",
      "Combined Total": item.combined_total ?? "",
      "Average Total": item.average_total ?? "",
      "Highest Total": item.highest_total?.amount ?? "",
      "Lowest Total": item.lowest_total?.amount ?? "",
    }));

    const workbook = XLSX.utils.book_new();

    XLSX.utils.book_append_sheet(
      workbook,
      XLSX.utils.json_to_sheet(invoiceRows),
      "Invoice Details"
    );

    XLSX.utils.book_append_sheet(
      workbook,
      XLSX.utils.json_to_sheet(summaryRows),
      "Financial Summary"
    );

    XLSX.writeFile(
      workbook,
      "DocuMind_AI_Invoice_Comparison.xlsx"
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <BrainCircuit size={25} />
          </div>

          <div>
            <h2>DocuMind AI</h2>
            <span>Intelligent documents</span>
          </div>
        </div>

        <p className="nav-label">WORKSPACE</p>

        <div className="nav-item active">
          <LayoutDashboard size={18} />
          Dashboard
        </div>

        <div className="nav-item">
          <Files size={18} />
          Document library
        </div>

        <div className="nav-item">
          <GitCompare size={18} />
          Invoice comparison
        </div>

        <div className="nav-item">
          <MessageSquare size={18} />
          AI assistant
        </div>

        <div className="sidebar-bottom">
          <ShieldCheck size={20} />
          <div>
            <strong>Local processing</strong>
            <p>Your API runs on your computer.</p>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <span className="eyebrow">AI DOCUMENT WORKSPACE</span>
            <h1>Document Intelligence</h1>
            <p>
              Manage PDFs, classify documents, extract invoice data and
              compare documents.
            </p>
          </div>

          <div className="status-pill">
            <span className="status-dot" />
            DocuMind workspace
          </div>
        </header>

        {error && (
          <div className="alert error-alert">
            <AlertCircle size={19} />
            {error}
          </div>
        )}

        <section className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon blue">
              <Files size={21} />
            </div>
            <span>Document library</span>
            <strong className="stat-value">{documents.length} PDFs</strong>
            <small>Indexed documents</small>
          </div>

          <div className="stat-card">
            <div className="stat-icon green">
              <CheckCircle2 size={21} />
            </div>
            <span>Selected document</span>
            <strong className="stat-value">
              {indexed ? "Ready" : "None"}
            </strong>
            <small>{selectedFilename || "Select a document below"}</small>
          </div>

          <div className="stat-card">
            <div className="stat-icon purple">
              <MessageSquare size={21} />
            </div>
            <span>Questions asked</span>
            <strong className="stat-value">
              {messages.filter((m) => m.role === "user").length}
            </strong>
            <small>In this conversation</small>
          </div>
        </section>

        <section className="content-grid">
          <div className="panel upload-panel">
            <div className="panel-heading">
              <div>
                <span className="section-tag">STEP 01</span>
                <h2>Add a document</h2>
                <p>Upload and index another PDF into your library.</p>
              </div>

              <div className="heading-icon">
                <Upload size={22} />
              </div>
            </div>

            <label className="dropzone">
              <input
                id="pdf-upload"
                type="file"
                accept=".pdf,application/pdf"
                onChange={(e) => {
                  setFile(e.target.files?.[0] || null);
                  setStatus("");
                  setError("");
                }}
              />

              <div className="upload-circle">
                <Upload size={25} />
              </div>

              <strong>
                {file ? file.name : "Choose a PDF document"}
              </strong>

              <span>PDF files up to 15 MB</span>
              <span className="browse-text">Browse files</span>
            </label>

            <button
              className="primary-button full-button"
              onClick={uploadAndIndex}
              disabled={!file || loading}
              type="button"
            >
              {loading ? (
                <LoaderCircle className="spin" size={19} />
              ) : (
                <BrainCircuit size={19} />
              )}

              {loading ? "Processing..." : "Add & index PDF"}
            </button>

            {status && (
              <div className="success-message">
                <CheckCircle2 size={18} />
                <span>{status}</span>
              </div>
            )}

            <div className="privacy-note">
              <ShieldCheck size={17} />
              <span>Processed through your local backend API.</span>
            </div>
          </div>

          <div className="panel invoice-panel">
            <div className="panel-heading">
              <div>
                <span className="section-tag">DOCUMENT LIBRARY</span>
                <h2>Your PDFs</h2>
                <p>Choose which document to query.</p>
              </div>

              <button
                className="library-refresh"
                onClick={() => loadDocuments()}
                disabled={libraryLoading || loading}
                title="Refresh document library"
                type="button"
              >
                {libraryLoading ? (
                  <LoaderCircle className="spin" size={18} />
                ) : (
                  <RefreshCw size={18} />
                )}
              </button>
            </div>

            <div className="document-library">
              <label htmlFor="document-select">Selected document</label>

              <select
                id="document-select"
                value={selectedFilename}
                onChange={(e) => changeDocument(e.target.value)}
                disabled={loading || documents.length === 0}
              >
                {documents.length === 0 && (
                  <option value="">No indexed documents</option>
                )}

                {documents.map((doc) => (
                  <option key={doc.filename} value={doc.filename}>
                    {doc.filename}
                  </option>
                ))}
              </select>

              <small>{documents.length} indexed document(s)</small>
            </div>

            {documents.length > 0 ? (
              <div className="library-list">
                {documents.map((doc) => (
                  <div
                    key={doc.filename}
                    className={`library-document ${
                      doc.filename === selectedFilename ? "selected" : ""
                    }${loading ? " disabled" : ""}`}
                    onClick={() =>
                      !loading && changeDocument(doc.filename)
                    }
                    role="button"
                    tabIndex={loading ? -1 : 0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        if (!loading) changeDocument(doc.filename);
                      }
                    }}
                  >
                    <FileText size={21} />

                    <span className="library-document-info">
                      <strong>{doc.filename}</strong>
                      <small>
                        {doc.pages ?? 0} pages · {doc.chunks ?? 0} chunks
                      </small>
                    </span>

                    <span
                      className={`document-category-badge ${getCategoryClass(
                        doc.category
                      )}`}
                    >
                      {doc.category || "Other"}
                      {doc.confidence > 0 &&
                        ` · ${Math.round(doc.confidence * 100)}%`}
                    </span>

                    {doc.filename === selectedFilename && (
                      <CheckCircle2 size={18} className="doc-check" />
                    )}

                    <button
                      type="button"
                      className="delete-doc-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteDocument(doc.filename);
                      }}
                      disabled={loading}
                      title={`Remove "${doc.filename}"`}
                      aria-label={`Delete ${doc.filename}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-icon">
                  <Files size={27} />
                </div>
                <strong>Your library is empty</strong>
                <p>
                  Upload and index a PDF to add it to your library.
                </p>
              </div>
            )}

            {(summary || summaryLoading) && (
              <div className="summary-card">
                <div className="summary-header">
                  <Sparkles size={14} />
                  <span>AI Summary</span>

                  {summaryLoading && (
                    <LoaderCircle
                      className="spin summary-spinner"
                      size={13}
                    />
                  )}
                </div>

                {summary && <p>{summary}</p>}
              </div>
            )}

            <div className="classification-card">
              <div className="classification-header">
                <div>
                  <span className="section-tag">AI ANALYSIS</span>
                  <h3>Document Classification</h3>
                </div>

                <div className="classification-icon">
                  <Tag size={21} />
                </div>
              </div>

              {classificationLoading ? (
                <div className="classification-loading">
                  <LoaderCircle size={18} className="spin" />
                  Analyzing document type...
                </div>
              ) : classification ? (
                <>
                  <div className="classification-result">
                    <div>
                      <span>Detected document type</span>
                      <strong>{classification.category}</strong>
                    </div>

                    <span
                      className={`document-category-badge ${getCategoryClass(
                        classification.category
                      )}`}
                    >
                      {classification.category}
                    </span>
                  </div>

                  <div className="classification-confidence">
                    <div className="confidence-label">
                      <span>Confidence score</span>
                      <strong>
                        {Math.round(classification.confidence * 100)}%
                      </strong>
                    </div>

                    <div className="confidence-track">
                      <div
                        className="confidence-fill"
                        style={{
                          width: `${Math.max(
                            0,
                            Math.min(
                              100,
                              classification.confidence * 100
                            )
                          )}%`,
                        }}
                      />
                    </div>
                  </div>

                  {classification.matched_keywords.length > 0 && (
                    <div className="matched-keywords">
                      <strong>Matched keywords</strong>

                      <div className="keyword-list">
                        {classification.matched_keywords.map(
                          (keyword, index) => (
                            <span key={`${keyword}-${index}`}>
                              {keyword}
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  )}

                  <p className="classification-message">
                    {classification.message}
                  </p>
                </>
              ) : (
                <p className="classification-empty">
                  {selectedFilename
                    ? "Classification information is unavailable."
                    : "Select a document to view its classification."}
                </p>
              )}
            </div>

            {invoiceFields.length > 0 && (
              <div className="invoice-fields">
                <h3>Invoice insights</h3>

                {invoiceFields.map(([label, value]) => (
                  <div className="field-row" key={label}>
                    <span>{label}</span>
                    <strong>{value ?? "Not found"}</strong>
                  </div>
                ))}

                {invoice.total_validation && (
                  <div
                    className={`validation ${
                      invoice.total_validation.matches
                        ? "validation-good"
                        : "validation-warning"
                    }`}
                  >
                    {invoice.total_validation.matches ? (
                      <CheckCircle2 size={17} />
                    ) : (
                      <AlertCircle size={17} />
                    )}

                    {invoice.total_validation.matches
                      ? "Subtotal and tax match the total."
                      : "Subtotal and tax do not match the total."}
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        <section className="panel comparison-panel">
          <div className="panel-heading">
            <div>
              <span className="section-tag">STEP 02</span>
              <h2>Invoice comparison</h2>
              <p>
                Select two or more indexed PDFs to compare their extracted
                financial information.
              </p>
            </div>

            <div className="heading-icon">
              <GitCompare size={22} />
            </div>
          </div>

          <div className="comparison-selection">
            <div className="comparison-selection-heading">
              <strong>Select invoices</strong>

              <div className="comparison-selection-actions">
                <button
                  type="button"
                  onClick={selectAllComparisonFiles}
                  disabled={documents.length === 0}
                >
                  Select all
                </button>

                <button
                  type="button"
                  onClick={clearComparisonFiles}
                  disabled={comparisonFiles.length === 0}
                >
                  Clear
                </button>
              </div>
            </div>

            {documents.length === 0 ? (
              <p className="comparison-empty">
                Upload and index PDFs before comparing invoices.
              </p>
            ) : (
              <div className="comparison-file-list">
                {documents.map((doc) => (
                  <label className="comparison-file" key={doc.filename}>
                    <input
                      type="checkbox"
                      checked={comparisonFiles.includes(doc.filename)}
                      onChange={() => toggleComparisonFile(doc.filename)}
                    />
                    <FileText size={18} />
                    <span>{doc.filename}</span>
                  </label>
                ))}
              </div>
            )}

            <div className="comparison-action-row">
              <span>
                {comparisonFiles.length} document(s) selected
              </span>

              <button
                className="primary-button"
                type="button"
                onClick={compareInvoices}
                disabled={
                  comparisonLoading || comparisonFiles.length < 2
                }
              >
                {comparisonLoading ? (
                  <LoaderCircle className="spin" size={18} />
                ) : (
                  <BarChart3 size={18} />
                )}

                {comparisonLoading
                  ? "Comparing invoices..."
                  : "Compare invoices"}
              </button>
            </div>
          </div>

          {comparison && (
            <div className="comparison-results">
              <div className="comparison-results-heading">
                <div>
                  <span className="section-tag">COMPARISON REPORT</span>
                  <h3>Financial overview</h3>
                </div>

                <div className="comparison-export-actions">
                  <span className="comparison-count">
                    {comparison.document_count ??
                      comparisonDocuments.length} documents analyzed
                  </span>

                  <button
                    type="button"
                    className="export-pdf"
                    onClick={exportComparisonPDF}
                  >
                    <FileText size={17} />
                    Export PDF
                  </button>

                  <button
                    type="button"
                    className="export-excel"
                    onClick={exportComparisonExcel}
                  >
                    <Download size={17} />
                    Export Excel
                  </button>
                </div>
              </div>

              <div className="comparison-stats">
                <div className="comparison-stat">
                  <span>Invoices analyzed</span>
                  <strong>{comparisonDocuments.length}</strong>
                </div>

                <div className="comparison-stat">
                  <span>Currency groups</span>
                  <strong>{financialSummary.currency_count ?? 0}</strong>
                </div>

                <div className="comparison-stat">
                  <span>Duplicate invoices</span>
                  <strong>{duplicateInvoices.length}</strong>
                </div>

                <div className="comparison-stat">
                  <span>Incomplete documents</span>
                  <strong>{incompleteDocuments.length}</strong>
                </div>
              </div>

              <div className="comparison-subheading">
                <BarChart3 size={19} />
                <h3>Currency-wise financial summary</h3>
              </div>

              {financialSummary.mixed_currencies && (
                <div className="comparison-warning">
                  <AlertTriangle size={18} />
                  <span>
                    Multiple currencies detected. Totals are kept separate
                    and are not combined across different currencies.
                  </span>
                </div>
              )}

              {currencySummaries.length > 0 ? (
                <div className="currency-summary-grid">
                  {currencySummaries.map((item) => (
                    <div
                      className="currency-summary-card"
                      key={item.currency_code}
                    >
                      <div className="currency-card-heading">
                        <span className="currency-symbol">
                          {item.currency_symbol}
                        </span>

                        <div>
                          <strong>{item.currency_name}</strong>
                          <small>{item.currency_code}</small>
                        </div>
                      </div>

                      <div className="currency-total">
                        <span>Combined total</span>
                        <strong>
                          {formatAmount(
                            item.combined_total,
                            item.currency_symbol
                          )}
                        </strong>
                      </div>

                      <div className="currency-detail-row">
                        <span>Invoices</span>
                        <strong>{item.document_count}</strong>
                      </div>

                      <div className="currency-detail-row">
                        <span>Average total</span>
                        <strong>
                          {formatAmount(
                            item.average_total,
                            item.currency_symbol
                          )}
                        </strong>
                      </div>

                      <div className="currency-detail-row">
                        <span>Highest total</span>
                        <strong>
                          {formatAmount(
                            item.highest_total?.amount,
                            item.currency_symbol
                          )}
                        </strong>
                      </div>

                      <div className="currency-detail-row">
                        <span>Lowest total</span>
                        <strong>
                          {formatAmount(
                            item.lowest_total?.amount,
                            item.currency_symbol
                          )}
                        </strong>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="comparison-empty">
                  No currency summary is available.
                </p>
              )}

              <div className="comparison-subheading">
                <Files size={19} />
                <h3>Invoice details</h3>
              </div>

              <div className="comparison-table-wrapper">
                <table className="comparison-table">
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Invoice number</th>
                      <th>Vendor</th>
                      <th>Date</th>
                      <th>Currency</th>
                      <th>Subtotal</th>
                      <th>Tax</th>
                      <th>Total</th>
                    </tr>
                  </thead>

                  <tbody>
                    {comparisonDocuments.map((doc) => (
                      <tr key={doc.filename}>
                        <td>{doc.filename}</td>
                        <td>{doc.invoice?.invoice_number || "—"}</td>
                        <td>{doc.invoice?.vendor || "—"}</td>
                        <td>{doc.invoice?.invoice_date || "—"}</td>
                        <td>{doc.currency?.currency_code || "—"}</td>
                        <td>
                          {formatAmount(
                            doc.invoice?.subtotal,
                            doc.currency?.currency_symbol
                          )}
                        </td>
                        <td>
                          {formatAmount(
                            doc.invoice?.tax,
                            doc.currency?.currency_symbol
                          )}
                        </td>
                        <td>
                          <strong>
                            {formatAmount(
                              doc.invoice?.total,
                              doc.currency?.currency_symbol
                            )}
                          </strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {(duplicateInvoices.length > 0 ||
                incompleteDocuments.length > 0 ||
                comparisonNotes.length > 0) && (
                <div className="comparison-alerts">
                  <div className="comparison-subheading">
                    <AlertTriangle size={19} />
                    <h3>Warnings and observations</h3>
                  </div>

                  {duplicateInvoices.length > 0 && (
                    <div className="comparison-warning">
                      <AlertTriangle size={18} />
                      <div>
                        <strong>
                          Duplicate invoice numbers detected
                        </strong>

                        {duplicateInvoices.map((item, index) => (
                          <p key={index}>
                            {typeof item === "string"
                              ? item
                              : JSON.stringify(item)}
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  {incompleteDocuments.length > 0 && (
                    <div className="comparison-warning">
                      <AlertTriangle size={18} />
                      <div>
                        <strong>Incomplete documents</strong>

                        {incompleteDocuments.map((item, index) => (
                          <p key={index}>
                            {typeof item === "string"
                              ? item
                              : JSON.stringify(item)}
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  {comparisonNotes.length > 0 && (
                    <div className="comparison-notes">
                      <strong>Important notes</strong>
                      <ul>
                        {comparisonNotes.map((note, index) => (
                          <li key={index}>{note}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </section>

        <section className="panel chat-panel">
          <div className="panel-heading chat-heading">
            <div>
              <span className="section-tag">STEP 03</span>
              <h2>Ask your documents</h2>
              <p>
                {searchAllDocs
                  ? `Searching across all ${documents.length} indexed PDFs.`
                  : "Answers are searched from your selected PDF."}
              </p>
            </div>

            <div className="chat-heading-controls">
              <div className="multidoc-toggle">
                <Globe size={14} />
                <span>All docs</span>

                <button
                  type="button"
                  className={`toggle-btn${
                    searchAllDocs ? " toggle-on" : ""
                  }`}
                  onClick={() => {
                    setSearchAllDocs((v) => !v);
                    setMessages([]);
                  }}
                  aria-label="Toggle multi-document search"
                >
                  <span className="toggle-thumb" />
                </button>
              </div>

              <div className="chat-ready">
                <span
                  className={`status-dot${
                    searchAllDocs ? " dot-purple" : ""
                  }`}
                />

                {searchAllDocs
                  ? `All ${documents.length} docs`
                  : indexed
                  ? "Document ready"
                  : "Waiting for document"}
              </div>
            </div>
          </div>

          <div
            className={`active-document${
              searchAllDocs ? " active-document-all" : ""
            }`}
          >
            {searchAllDocs ? <Globe size={17} /> : <FileText size={17} />}

            <span>
              Chatting with:{" "}
              <strong>
                {searchAllDocs
                  ? `All documents (${documents.length} PDFs)`
                  : selectedFilename || "No document selected"}
              </strong>
            </span>
          </div>

          <div className="chat-messages">
            {messages.length === 0 ? (
              <div className="chat-empty">
                <div className="chat-empty-icon">
                  <MessageSquare size={25} />
                </div>

                <strong>Your document assistant is ready</strong>

                <p>
                  {chatReady
                    ? searchAllDocs
                      ? "Ask anything across all your indexed PDFs."
                      : "Choose a suggested question or type your own."
                    : "Upload a PDF and select it from your library to start."}
                </p>

                {chatReady && (
                  <div className="suggestion-list">
                    {(searchAllDocs
                      ? [
                          "What are the total amounts across all invoices?",
                          "Who are the vendors in my documents?",
                          "What are the invoice dates?",
                        ]
                      : [
                          "What is the invoice number?",
                          "What is the total due?",
                          "Who is the vendor?",
                        ]
                    ).map((item) => (
                      <button
                        key={item}
                        className="suggestion"
                        onClick={() => setQuestion(item)}
                        disabled={loading}
                        type="button"
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              messages.map((message, index) => (
                <div
                  className={`message ${
                    message.role === "user" ? "user-message" : ""
                  }`}
                  key={`${index}-${message.role}`}
                >
                  <div className="message-avatar">
                    {message.role === "user" ? (
                      "Y"
                    ) : (
                      <BrainCircuit size={19} />
                    )}
                  </div>

                  <div className="message-body">
                    <strong>
                      {message.role === "user" ? "You" : "DocuMind AI"}
                    </strong>

                    <p>{message.text}</p>

                    {message.sources?.length > 0 && (
                      <div className="sources">
                        <span>Sources</span>

                        {message.sources.map((source, sourceIndex) => (
                          <div
                            className="source-item"
                            key={`${source.filename}-${source.page}-${sourceIndex}`}
                          >
                            <FileText size={15} />
                            <span>{source.filename}</span>
                            <span className="page-badge">
                              Page {source.page}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          <form className="chat-form" onSubmit={askQuestion}>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={
                searchAllDocs
                  ? "Ask across all your PDFs..."
                  : indexed
                  ? "Ask about the selected PDF..."
                  : "Upload and select a PDF first..."
              }
              disabled={!chatReady || loading}
            />

            <button
              type="submit"
              className="send-button"
              disabled={!chatReady || !question.trim() || loading}
              aria-label="Send question"
            >
              {loading ? (
                <LoaderCircle className="spin" size={19} />
              ) : (
                <Send size={19} />
              )}
            </button>
          </form>

          <p className="chat-disclaimer">
            Answers are based on indexed document content. Verify important
            details against the original PDF.
          </p>
        </section>

        <footer className="footer">
          <span>DocuMind AI · Intelligent document processing</span>
          <span>Local API · FastAPI + React</span>
        </footer>
      </main>
    </div>
  );
}
