import os
from pypdf import PdfReader
from openai import OpenAI
from supabase import create_client

# -----------------------
# CONFIG
# -----------------------
SUPABASE_URL = "YOUR_URL"
SUPABASE_SERVICE_KEY = "YOUR_SERVICE_ROLE_KEY"
OPENAI_KEY = "YOUR_OPENAI_KEY"

PARTNER_ID = "PASTE_PARTNER_UUID"
DOCUMENT_TITLE = "Crew Regulations PDF"

PDF_PATH = "yourfile.pdf"

# -----------------------
# CLIENTS
# -----------------------
client = OpenAI(api_key=OPENAI_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# -----------------------
# 1️⃣ Extract Text
# -----------------------
reader = PdfReader(PDF_PATH)
full_text = ""

for page in reader.pages:
    full_text += page.extract_text() + "\n"

# -----------------------
# 2️⃣ Create Document Row
# -----------------------
doc = supabase.table("partner_documents").insert({
    "partner_id": PARTNER_ID,
    "title": DOCUMENT_TITLE
}).execute()

document_id = doc.data[0]["id"]

# -----------------------
# 3️⃣ Split Into Chunks
# -----------------------
def chunk_text(text, size=800):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end
    return chunks

chunks = chunk_text(full_text)

# -----------------------
# 4️⃣ Embed + Insert
# -----------------------
for chunk in chunks:

    if len(chunk.strip()) < 40:
        continue

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

print("✅ PDF Ingested Successfully")
