from openai import OpenAI
from supabase import create_client
import os

client = OpenAI()
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

def embed(text):
    return client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    ).data[0].embedding

rows = supabase.table("partner_qa").select("id, question").execute().data

for row in rows:
    emb = embed(row["question"])
    supabase.table("partner_qa").update(
        {"embedding": emb}
    ).eq("id", row["id"]).execute()
