import os
import re
from dotenv import load_dotenv, find_dotenv
from pypdf import PdfReader
from openai import OpenAI
from supabase import create_client

# =====================================================
# LOAD ENV (same as chat.py / main.py)
# =====================================================
load_dotenv(find_dotenv("env.txt"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY or not OPENAI_API_KEY:
    raise Exception("❌ Missing environment variables in env.txt")

client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# =====================================================
# CONFIG — EDIT ONLY THIS SECTION
# =====================================================

PDF_PATH = "reg_yc_guidance_information_2024_01_a3.pdf"

# 🔥 YOUR REAL PARTNER UUID
PARTNER_ID = "de8bf1a4-7e7c-44f5-b865-7ac27b8a84b4"

DOCUMENT_TITLE = "REG Yacht Code Guidance Information 2024"

# =====================================================
# 1️⃣ EXTRACT TEXT
# =====================================================
print("📄 Reading PDF...")

reader = PdfReader(PDF_PATH)
full_text = ""

for page in reader.pages:
    text = page.extract_text()
    if text:
        full_text += text + "\n"

if not full_text.strip():
    raise Exception("❌ No extractable text found. PDF may be scanned.")

print("✅ Text extracted")

# =====================================================
# 2️⃣ CLEAN TEXT
# =====================================================
def clean_text(text):
    text = re.sub(r'\r', '\n', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

full_text = clean_text(full_text)

# =====================================================
# 3️⃣ SMART CHUNKING
# =====================================================
def smart_chunk(text, max_chars=1200, overlap=150):
    """
    Smart semantic chunking:
    - Splits by headings and paragraphs
    - Keeps logical grouping
    - Adds slight overlap
    """

    # Split by headings OR paragraph breaks
    sections = re.split(r'\n(?=[A-Z][A-Z\s\d\-\.]{5,})', text)

    chunks = []

    for section in sections:
        paragraphs = section.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) < max_chars:
                current_chunk += para + "\n\n"
            else:
                chunks.append(current_chunk.strip())

                # overlap tail
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else ""
                current_chunk = overlap_text + para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

    # Remove tiny chunks
    final_chunks = [c for c in chunks if len(c) > 200]

    return final_chunks

chunks = smart_chunk(full_text)

print(f"✅ {len(chunks)} smart chunks created")

# =====================================================
# 4️⃣ CREATE DOCUMENT ENTRY
# =====================================================
print("📝 Creating document record...")

doc = supabase.table("partner_documents").insert({
    "partner_id": PARTNER_ID,
    "title": DOCUMENT_TITLE
}).execute()

if not doc.data:
    raise Exception("❌ Failed to create document record")

document_id = doc.data[0]["id"]

print("✅ Document created:", document_id)

# =====================================================
# 5️⃣ EMBED + INSERT
# =====================================================
print("🧠 Generating embeddings and inserting...")

inserted = 0

for i, chunk in enumerate(chunks):

    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=chunk
    ).data[0].embedding

    supabase.table("partner_chunks").insert({
        "partner_id": PARTNER_ID,
        "document_id": document_id,
        "content": chunk,
        "embedding": embedding
    }).execute()

    inserted += 1
    print(f"Inserted chunk {inserted}")

print("🚀 PDF ingestion complete.")
print(f"Total chunks inserted: {inserted}")
