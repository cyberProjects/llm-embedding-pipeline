import psycopg2
import os
import json
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import uuid
import time
import tiktoken
from collections import defaultdict

client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))

DB_CONFIG = {
    "host": os.environ.get("DB_HOST"),
    "dbname": os.environ.get("DB_NAME"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "port": int(os.environ.get("DB_PORT", 5432))
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

def fetch_federal_register_documents(date, max_results=20, per_page=5, page=1, keywords=None, allowed_types=None):
    limiter = 50
    url = "https://www.federalregister.gov/api/v1/documents.json"
    all_results = {}
    keyword_string = "|".join(keywords) if keywords else None
    while len(all_results) < limiter:
        params = defaultdict(list)
        params["per_page"] = per_page
        params["page"] = page
        params["order"] = "newest"
        params["conditions[publication_date][gte]"] = date
        if keyword_string:
            params["conditions[term]"] = keyword_string
        if allowed_types:
            for doc_type in allowed_types:
                params["conditions[type][]"].append(doc_type)
        try:
            response = requests.get(url, params=params, timeout=10)
            # print(f"Request URL: {response.url}")
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            count = data.get("count")
            print(f"Found {count if count is not None else 'unknown'} results.")
            for r in results:
                doc_id = r.get("document_number")
                if doc_id and doc_id not in all_results:
                    all_results[doc_id] = r
                    if len(all_results) >= limiter:
                        break
            if len(results) < per_page or len(all_results) >= limiter:
                break
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"[Page {page}] Error: {e}")
            break
    final_results = list(all_results.values())[:limiter]
    print(f"\nFetched {len(final_results)} document(s).")
    # print(json.dumps(final_results, indent=2, ensure_ascii=False))
    return final_results

def get_full_text_from_xml(doc):
    xml_url = doc.get("full_text_xml_url")
    if not xml_url:
        print("No XML URL found.")
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.get(xml_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "xml")
        paragraphs = [elem.get_text(strip=True) for elem in soup.find_all(["P", "HD", "FTNT"])]
        return "\n\n".join(paragraphs)
    except Exception as e:
        print(f"Error fetching XML: {e}")
        return ""

def fetch_document_details(document_number):
    url = f"https://www.federalregister.gov/api/v1/documents/{document_number}.json"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Failed to fetch metadata for {document_number}: {e}")
        return None


def document_exists(document_number):
    query = """
        SELECT 1 FROM bedrock_integration.bedrock_kb
        WHERE metadata ->> 'document_number' = %s
        LIMIT 1;
    """
    cursor.execute(query, (document_number,))
    return cursor.fetchone() is not None

def chunk_text(text, max_tokens=512, overlap=50, model="text-embedding-ada-002"):
    encoding = tiktoken.encoding_for_model(model)
    tokens = encoding.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append(chunk_text)
        start += max_tokens - overlap
    return chunks

def get_embedding(text, model="text-embedding-ada-002"):
    response = client.embeddings.create(input=[text], model=model)
    return response.data[0].embedding

def save_chunks_to_db(chunks, table="bedrock_integration.bedrock_kb"):
    for chunk in chunks:
        try:
            insert_query = f"""
            INSERT INTO {table} (id, embedding, chunks, metadata)
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(
                insert_query,
                (
                    chunk["id"],
                    chunk["embedding"],  # vector(n) column
                    chunk["content"],
                    json.dumps(chunk["metadata"])
                )
            )
        except Exception as e:
            print(f"Failed to insert chunk {chunk['chunk_index']}: {e}")
    conn.commit()

def process_document(doc):
    if document_exists(doc["document_number"]):
        print(f"Document {doc['document_number']} already exists. Skipping.")
        return None
    details = fetch_document_details(doc["document_number"])
    if not details or "full_text_xml_url" not in details:
        print("No full_text_xml_url available.")
        return None
    full_text = get_full_text_from_xml(details)
    if not full_text:
        return None
    chunks = chunk_text(full_text)
    processed_chunks = []
    for i, chunk in enumerate(chunks):
        try:
            embedding = get_embedding(chunk)
            processed_chunks.append({
                "id": str(uuid.uuid4()),
                "title": doc["title"],
                "chunk_index": i,
                "publication_date": doc["publication_date"],
                "url": doc["html_url"],
                "agency": doc["agencies"][0]["name"] if doc["agencies"] else None,
                "content": chunk,
                "embedding": embedding,
                "metadata": {
                    "source": doc["html_url"],
                    "document_number": doc["document_number"]
                }
            })
        except Exception as e:
            print(f"Failed embedding chunk {i}: {e}")
            continue
    return processed_chunks if processed_chunks else None

def lambda_handler(event, context):
    try:
        TARGET_DATE = "2025-3-01"
        MAX_RESULTS = 500
        PER_PAGE = 500
        PAGE = 1
        KEYWORDS = []
        ALLOWED_TYPES = ["RULE", "PRORULE"]
        # ALLOWED_TYPES = ["RULE", "PRORULE", "NOTICE", "PRESDOCU"]
        documents = fetch_federal_register_documents(
            date=TARGET_DATE,
            max_results=MAX_RESULTS,
            per_page=PER_PAGE,
            page=PAGE,
            keywords=KEYWORDS,
            allowed_types=ALLOWED_TYPES
        )
        processed_docs = []
        for doc in documents:
            print(f"Processing: {doc['title'][:80]}...")
            processed = process_document(doc)
            if processed:
                processed_docs.append(processed)
                save_chunks_to_db(processed)
            time.sleep(1.2)  # To stay below OpenAI rate limits
        cursor.close()
        conn.close()
        print(f"\nEmbedded and saved {len(processed_docs)} documents.")
        return {
            "statusCode": 200,
            "body": "Query ran successfully"
        }
    except Exception as e:
        print(f"Database connection failed: {str(e)}")
        cursor.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": "Database connection failed"
        }
