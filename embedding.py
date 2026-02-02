from supabase import create_client
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
import os

# Load env.txt explicitly
load_dotenv(find_dotenv("env.txt"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print("SUPABASE_URL:", bool(SUPABASE_URL))
print("SUPABASE_SERVICE_ROLE_KEY:", bool(SUPABASE_SERVICE_ROLE_KEY))
print("OPENAI_API_KEY:", bool(OPENAI_API_KEY))

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)

rows = supabase.table("partner_qa") \
    .select("id, question") \
    .is_("embedding_vec", None) \
    .execute().data

print(f"Found {len(rows)} rows")

for row in rows:
    print("Embedding row id:", row["id"])

    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=row["question"]
    ).data[0].embedding

    res = supabase.table("partner_qa") \
        .update({"embedding_vec": embedding}) \
        .eq("id", row["id"]) \
        .execute()

print("Update response:", res)


print("✅ Embeddings written to embedding_vec")
print("OPENAI_API_KEY starts with:", OPENAI_API_KEY[:8])

