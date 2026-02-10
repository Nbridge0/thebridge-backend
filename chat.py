import os
import random
import string
import secrets
import requests
import openai
from supabase import create_client, Client
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI
from typing import Optional


# -------------------------------
# ENV
# -------------------------------
load_dotenv(find_dotenv("env.txt"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

FROM_EMAIL = os.getenv("FROM_EMAIL")

openai.api_key = OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

# -------------------------------
# CLIENTS
# -------------------------------
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def get_user_name_by_email(email: str) -> str:
    try:
        resp = supabase_admin.table("user_profiles") \
            .select("name") \
            .eq("email", email.lower().strip()) \
            .single() \
            .execute()

        if resp.data and resp.data.get("name"):
            return resp.data["name"]
    except Exception:
        pass

    return email.split("@")[0].capitalize()

def get_experts_by_role(role: str):
    try:
        resp = supabase_admin.table("experts") \
            .select("name, email") \
            .eq("role", role) \
            .eq("is_active", True) \
            .execute()

        return resp.data or []
    except Exception:
        return []

# -------------------------------
# CONSTANTS
# -------------------------------
NO_ANSWER_FALLBACK = (
    "Oops! You caught us.\n"
    "We don't have the answer just yet, but TheBridge is always growing.\n"
    "Try Ask AI, Ask a Specialist or Ask an Ambassador."
)



HELP_EMAIL_SUBJECT = "A User From TheBridge Needs Your Help"

HELP_EMAIL_BODY = """Dear {expert_name},

We hope you are doing well!

{name} whilst using TheBridge has asked a question and selected you as their go-to {role} for help. Your insight would be greatly valued.

Question:
{question}

When you are ready, please provide a detailed answer and remember to hit Reply All.

Thank you for sharing your knowledge and helping our community grow.

Warm regards,
TheBridge Team
"""

# -------------------------------
# UTILITIES
# -------------------------------
def normalize(text: str) -> str:
    return text.strip().lower().translate(
        str.maketrans("", "", string.punctuation)
    )

def semantic_partner_match(question: str):
    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=question
    ).data[0].embedding

    resp = supabase_admin.rpc(
        "match_partner_qa",
        {
            "query_embedding": embedding,
            "match_threshold": 0.72,
            "match_count": 1
        }
    ).execute()

    if resp.data:
        return resp.data[0]

    return None


# -------------------------------
# PARTNER CACHE
# -------------------------------
def load_partner_cache():
    try:
        resp = supabase_admin.table("partner_qa") \
            .select("question, answer") \
            .execute()
        return resp.data or []
    except Exception:
        return []

PARTNER_CACHE = load_partner_cache()

# -------------------------------
# EMAIL (RESEND)
# -------------------------------
def send_email(to_emails, subject, body):
    url = "https://api.brevo.com/v3/smtp/email"

    # force list
    if not isinstance(to_emails, list):
        to_emails = [to_emails]

    ref = secrets.token_hex(6)  # unique per email (prevents threading)

    payload = {
        "sender": {
            "name": "TheBridge",
            "email": FROM_EMAIL
        },
        "to": [{"email": e} for e in to_emails],  # ✅ ALL IN TO
        "subject": f"{subject} [Ref {ref}]",
        "textContent": f"{body}\n\nReference ID: {ref}",
        "headers": {
            "X-Entity-Ref-ID": ref,
            "Message-ID": f"<{ref}@askthebridge.com>"
        }
    }

    headers = {
        "accept": "application/json",
        "api-key": os.getenv("BREVO_API_KEY"),
        "content-type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers, timeout=10)

    if response.status_code >= 400:
        print("❌ BREVO API ERROR:", response.status_code, response.text)
        raise Exception("Email send failed")


# -------------------------------
# OPENAI
# -------------------------------
def ask_openai(question: str) -> str:
    r = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant about yachting."},
            {"role": "user", "content": question},
        ],
    )
    return r.choices[0].message.content.strip()

def ask_ai_only(question: str) -> str:
    r = openai.chat.completions.create(
        model="gpt-4o-mini",  # SAME as Streamlit
        messages=[
            {
                "role": "system",
                "content": (
                    "You are TheBridge AI assistant for superyachting. "
                    "Answer fully and clearly. Do NOT use stored or database answers."
                )
            },
            {"role": "user", "content": question},
        ],
        temperature=0.7,
    )
    return r.choices[0].message.content.strip()


# -------------------------------
# CORE CHAT LOGIC
# -------------------------------
def get_answer(message: str, user_role: str = "guest"):
    user_norm = normalize(message)

    # 1️⃣ EXACT MATCH (fast, cheap)
    for row in PARTNER_CACHE:
        if normalize(row["question"]) == user_norm:
            return {
                "answer": row["answer"],
                "source": "db_exact",
                "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
                "requires_auth": False,
            }

    # 2️⃣ SEMANTIC MATCH (embeddings)
    semantic = semantic_partner_match(message)
    if semantic:
        return {
            "answer": semantic["answer"],
            "source": "db_semantic",
            "similarity": round(semantic["similarity"], 3),
            "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
            "requires_auth": False,
        }

    # 3️⃣ YACHTING FALLBACK
    yachting_keywords = [
        "yacht", "crew", "captain", "flag", "port state", "psc",
        "manning", "inspection", "maritime", "ism", "isps",
        "engine", "bridge", "deck", "charter", "mca", "class",
        "minimum crew", "safe manning"
    ]

    if any(k in user_norm for k in yachting_keywords):
        return {
            "answer": NO_ANSWER_FALLBACK,
            "source": "no_answer",
            "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
            "requires_auth": user_role == "guest",
        }

    # 4️⃣ GENERAL AI
    return {
        "answer": ask_openai(message),
        "source": "openai_general",
        "actions": [],
        "requires_auth": False,
    }


def save_message(chat_id, role, content, source, user_email=None):
    supabase_admin.table("chat_messages").insert({
        "chat_id": chat_id,
        "user_email": user_email,
        "role": role,
        "content": content,
        "source": source
    }).execute()


def track_click(
    chat_id: Optional[int],
    button: str,
    question: str,
    user_email: str = None,
    user_role: str = "guest"
):
    try:
        resp = supabase_admin.table("user_clicks").insert({
            "chat_id": chat_id,
            "user_email": user_email,
            "user_type": "user" if user_role != "guest" else "guest",
            "button": button,
            "question": question
        }).execute()

        print("✅ CLICK TRACKED:", resp.data)

    except Exception as e:
        print("❌ CLICK TRACK FAILED:", str(e))



# -------------------------------
# HELP REQUESTS (FIXED)
# -------------------------------
def send_help_request(role: str, question: str, user_email: str, expert_email: str):
    user_name = get_user_name_by_email(user_email)

    expert = supabase_admin.table("experts") \
        .select("name, email") \
        .eq("email", expert_email) \
        .single() \
        .execute()

    if not expert.data:
        return {"status": "expert_not_found"}

    body = HELP_EMAIL_BODY.format(
        expert_name=expert.data["name"],
        name=user_name,
        role=role,
        question=question
    )


    send_email(
        to_emails=[expert.data["email"], user_email],  # ✅ BOTH IN TO
        subject=HELP_EMAIL_SUBJECT,
        body=body
    )


    return {"status": "email_sent"}