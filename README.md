# DOKUMIND-AI

**AI-Powered Document Intelligence & Invoice Analysis Platform**

DocuMind AI is an AI-powered document Q&A system that allows users to upload PDF documents, extract important information, generate summaries, and ask questions using Retrieval-Augmented Generation (RAG).

The platform also provides invoice data extraction, multi-document invoice comparison, currency-wise financial analysis, and downloadable PDF and Excel reports.

## 🚀 Features

- **PDF Upload & Indexing:** Upload and index PDF documents.
- **AI Document Q&A:** Ask questions about uploaded documents using RAG.
- **Semantic Search:** Retrieve relevant document content using Sentence Transformers.
- **Document Summarization:** Generate summaries of indexed documents.
- **Invoice Extraction:** Extract invoice numbers, vendors, dates, subtotal, tax, and total amounts.
- **Multi-Document Search:** Search across multiple indexed PDFs.
- **Invoice Comparison:** Compare financial information from multiple invoices.
- **Currency Analysis:** Generate currency-wise financial summaries.
- **Duplicate Detection:** Identify duplicate invoice numbers.
- **Data Validation:** Identify incomplete documents and validate invoice totals.
- **PDF Export:** Download invoice comparison reports as PDF.
- **Excel Export:** Export invoice details and financial summaries into Excel.

## 🛠️ Technology Stack

| Category | Technologies |
|---|---|
| Programming Language | Python |
| Backend | FastAPI |
| Frontend | React.js |
| AI / NLP | Sentence Transformers |
| Embedding Model | all-MiniLM-L6-v2 |
| Retrieval | Retrieval-Augmented Generation (RAG) |
| HTTP Client | Axios |
| PDF Processing | Python PDF extraction libraries |
| PDF Reports | jsPDF, jspdf-autotable |
| Excel Reports | SheetJS (xlsx) |
| Icons | Lucide React |

## 🏗️ Project Structure

```text
DOKUMIND-AI/
│
├── backend/
│   ├── main.py
│   ├── rag_index.json
│   └── ...
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   └── ...
│   ├── package.json
│   └── ...
│
└── README.md
```

## ⚙️ Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/CodewithNeel20/DokuMind-AI.git
cd DokuMind-AI
```

### 2. Backend Setup

Navigate to the backend folder:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the backend dependencies:

```bash
pip install -r requirements.txt
```

Start the FastAPI server:

```bash
python -m uvicorn main:app --reload
```

Backend URL:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

### 3. Frontend Setup

Open another terminal and navigate to the frontend:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the React development server:

```bash
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Check backend health |
| POST | `/index-pdf` | Upload and index a PDF |
| POST | `/extract-invoice` | Extract invoice information |
| POST | `/ask` | Ask questions about documents |
| GET | `/documents` | Retrieve indexed documents |
| GET | `/documents/{filename}/summary` | Generate or retrieve a document summary |
| DELETE | `/documents/{filename}` | Remove an indexed document |
| POST | `/compare-invoices` | Compare multiple invoices |

## 🧠 How It Works

1. **Document Upload:** The user uploads a PDF through the React interface.
2. **Text Extraction:** The FastAPI backend extracts text from the PDF.
3. **Text Chunking:** Extracted text is divided into smaller overlapping chunks.
4. **Embedding Generation:** Sentence Transformers converts text chunks into numerical embeddings.
5. **Indexing:** Document embeddings are stored in the local RAG index.
6. **Question Processing:** The user's question is converted into an embedding.
7. **Retrieval:** Relevant document chunks are retrieved for answering.
8. **Response Generation:** The backend returns relevant information and source references.
9. **Invoice Analysis:** Invoice information can be extracted, compared, validated, and exported.

## 📊 Invoice Comparison

DocuMind AI can compare multiple invoices and provide:

- Combined financial totals by currency.
- Average, highest, and lowest invoice totals.
- Duplicate invoice number detection.
- Incomplete document identification.
- Invoice-level financial details.
- Downloadable PDF and Excel reports.

## 🔐 Privacy

DocuMind AI is designed to process documents through a locally running backend. Uploaded documents and the RAG index are handled by the local application rather than requiring a hosted AI API.

## 🔮 Future Improvements

- Advanced invoice anomaly and risk detection.
- Interactive financial analytics and charts.
- Support for additional document formats.
- Improved OCR for scanned PDFs.
- User authentication and access control.

## 👨‍💻 Developer

**Neel Patel**

GitHub: https://github.com/CodewithNeel20

---

*DocuMind AI — Making document processing smarter with AI.*