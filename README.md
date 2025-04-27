# Federal Register Embedding Pipeline

## 🛠️ Project Overview

Built a serverless data ingestion and embedding pipeline that:

- Scrapes the **Federal Register** for recent government rules and regulations.
- Extracts full text content from XML sources.
- Chunks and embeds the content using **OpenAI embeddings**.
- Stores vectorized representations and metadata into a **PostgreSQL** (RDS) database for future semantic search and retrieval.

---

## 🌐 Technologies Used

- **AWS Lambda** (serverless compute)
- **PostgreSQL (AWS RDS)** (vector storage using `vector(n)` columns)
- **OpenAI API** (`text-embedding-ada-002` model)
- **Federal Register Public API** (document metadata and XML downloads)
- **Python 3.8** (runtime)
- **Libraries**:
  - `psycopg2` (PostgreSQL client)
  - `requests` (API interactions)
  - `beautifulsoup4` (XML parsing)
  - `tiktoken` (token counting and chunking)
  - `openai` (embedding generation)
  - `uuid` (chunk ID generation)

---

## 🔂 Code Structure Overview

```plaintext
/ (single file script)
    - Database connection setup (PostgreSQL)
    - Document fetching (Federal Register API)
    - XML full text extraction
    - Text chunking and token control
    - Embedding generation (OpenAI API)
    - Database insert of embeddings and metadata
```

---

## 📊 Functional Breakdown

### 1. **Database Connection**

- Uses environment variables to configure:
  - `DB_HOST`
  - `DB_NAME`
  - `DB_USER`
  - `DB_PASSWORD`
  - `DB_PORT`
- Connects once at start, reused across all inserts.

### 2. **Federal Register Document Fetching**

- Pulls documents using the Federal Register API.
- Supports:
  - Keyword filtering
  - Date-based filtering
  - Type filtering (`RULE`, `PRORULE`, etc.)
- Fetches up to **50 documents** per run with pagination.

### 3. **Full Text Extraction**

- Downloads the `full_text_xml_url` if available.
- Parses XML with BeautifulSoup to extract text from tags:
  - `<P>`, `<HD>`, `<FTNT>`

### 4. **Text Chunking**

- Tokenizes text using OpenAI's `tiktoken` encoder.
- Chunks text into **512 token blocks** with **50 token overlap** to maintain semantic coherence.
- Prepares chunks for embedding generation.

### 5. **Embedding Generation**

- Sends each chunk to OpenAI's `text-embedding-ada-002` model.
- Handles OpenAI rate limits gracefully with `time.sleep(1.2)` between API calls.

### 6. **Database Saving**

- Saves each chunk with:
  - Unique `UUID`
  - `content` (chunk text)
  - `embedding` vector
  - Metadata including `document_number`, `publication_date`, `title`, `source URL`, and `agency`
- Inserts into `bedrock_integration.bedrock_kb` table in PostgreSQL.

---

## 🚀 Key Features

- **Full text extraction** from Federal Register XML feeds.
- **High-efficiency chunking** to comply with token limits.
- **Semantic embedding generation** using OpenAI.
- **Optimized batch inserts** into a structured PostgreSQL vector table.
- **Duplicate document check** before embedding (avoiding redundant work).

---

## 📅 Future Enhancements

- Migrate to a fully event-driven Lambda with scheduled triggers.
- Add DynamoDB or S3 backup of all processed metadata.
- Extend to support additional document types (e.g., NOTICES, PRESIDENTIAL DOCUMENTS).
- Add full OpenAI API key rotation and multi-region redundancy.
- Enable real-time semantic search API over stored vectors.

---

## 🔍 Project Outcome

Delivered a **cloud-native, serverless ingestion and vectorization pipeline** that automatically collects government regulatory text, processes it, embeds it semantically, and stores it for downstream applications such as LLM retrieval-augmented generation (RAG) and compliance monitoring systems.
