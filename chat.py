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
    "Try Ask AI or Ask a Specialist."
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

BASE_SYSTEM_PROMPT = (
    "You are TheBridge AI.\n\n"

    "You are a continuous conversational intelligence.\n"
    "You ALWAYS use previous messages as context.\n\n"

    "If the user says things like:\n"
    "'more', 'tell me more', 'continue', 'go on', "
    "'expand', 'elaborate', etc —\n"
    "you MUST continue the previous answer naturally.\n\n"

    "DO NOT ask for clarification if a previous answer exists.\n"
    "DO NOT reset the conversation.\n\n"

    "Maintain a confident, natural, human tone."
)

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
        "match_partner_chunks",
        {
            "query_embedding": embedding,
            "match_threshold": 0.72,
            "match_count": 8
        }
    ).execute()

    return resp.data or []

def semantic_bridge_match(question: str):

    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=question
    ).data[0].embedding

    resp = supabase_admin.rpc(
        "match_bridge_chunks",
        {
            "query_embedding": embedding,
            "match_threshold": 0.72,
            "match_count": 5
        }
    ).execute()

    return resp.data or []

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

def ask_ai_only(question: str, chat_id: int = None, history: list = None) -> str:

    if not chat_id:
        history = history or []
    else:
        history = get_chat_history(chat_id)


    messages = [
    {
        "role": "system",
        "content": (
            "You are TheBridge AI.\n\n"

            "You are a continuous conversational intelligence.\n"
            "You always use the previous assistant message as context.\n\n"

            "If the user says things like:\n"
            "'more', 'tell me more', 'two more', 'three more', "
            "'continue', 'go on', or similar short follow-ups —\n"
            "you MUST continue the exact same content type and format "
            "as your previous response.\n\n"

            "You are NOT allowed to ask what they mean.\n"
            "You are NOT allowed to request clarification "
            "when a previous assistant message exists.\n\n"

            "Only ask for clarification if there is truly no previous "
            "assistant response to continue from.\n\n"

            "Maintain a natural, confident, human tone."
        )
    }
]


    messages.extend(history)

    messages.append({
        "role": "user",
        "content": question
    })

    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
    )

    return r.choices[0].message.content.strip()


# -------------------------------
# CORE CHAT LOGIC (UPDATED)
# -------------------------------

def get_chat_history(chat_id: int, limit: int = 15):
    """
    Fetches previous chat messages for context memory.
    Limits history to prevent token overflow.
    """
    try:
        resp = supabase_admin.table("chat_messages") \
            .select("role, content") \
            .eq("chat_id", chat_id) \
            .order("id") \
            .execute()

        if not resp.data:
            return []

        history = []

        for msg in resp.data:
            if msg["role"] in ["user", "assistant"]:
                history.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        # Keep only last N messages for token control
        return history[-20:]

    except Exception as e:
        print("HISTORY ERROR:", e)
        return []


def get_answer(message: str, user_role: str = "guest", chat_id: int = None, history: list = None):

    user_norm = normalize(message)

    # ✅ ALWAYS TRUST FRONTEND HISTORY FOR GUESTS
    if not chat_id:
       history = history or []
    else:
       history = get_chat_history(chat_id)

    print("HISTORY DEBUG:", history)

    try:
        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=message
        ).data[0].embedding
    except Exception as e:
        print("EMBEDDING ERROR:", e)
        embedding = None

    # =====================================================
    # 1️⃣ THEBRIDGE QA (ENRICHED WITH AI + MEMORY)
    # =====================================================
    if embedding:
        try:
            bridge_qa = supabase_admin.rpc(
                "match_bridge_qa",
                {
                    "query_embedding": embedding,
                    "match_threshold": 0.75,
                    "match_count": 3
                }
            ).execute().data
        except Exception as e:
            print("BRIDGE QA ERROR:", e)
            bridge_qa = []

        if bridge_qa:

            answers = [row["answer"] for row in bridge_qa]
            combined_context = "\n\n".join(answers)

         
           
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                BASE_SYSTEM_PROMPT +
                                "\n\nUse the provided database answers as the source of truth. "
                                "You may expand but must not contradict."
                                "You may expand, clarify, and improve it slightly.\n"
                                "If the user asks a follow-up (like 'more', 'continue', etc.), continue naturally.\n"
                                "Do NOT contradict the database answer.\n"
                                "Keep answers clear, structured, and helpful."
                            )
                        },
                        *history,
                        {
                            "role": "user",
                            "content": f"""
User question:
{message}

Database answers:
{combined_context}

Combine these into ONE clear, consistent answer.
Remove duplicates and keep structure clean.
"""
                        }
                    ],
                    temperature=0.5
                )

                final_answer = response.choices[0].message.content.strip()

            except Exception as e:
                print("BRIDGE QA ENRICH ERROR:", e)
                final_answer = combined_context

            return {
                "answer": final_answer,
                "source": "bridge_semantic_enriched",
                "badge": "TheBridge",
                "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
                "requires_auth": False,
                "new_title": None
            }

    # 👇 THEN your existing sections continue normally
    # =====================================================
    # 2️⃣ PARTNER QA
    # =====================================================
    if embedding:
        try:
            qa_results = supabase_admin.rpc(
                "match_partner_qa",
                {
                    "query_embedding": embedding,
                    "match_threshold": 0.75,
                    "match_count": 1
                }
            ).execute().data
        except Exception as e:
            print("PARTNER QA ERROR:", e)
            qa_results = []

        if qa_results:
            return {
                "answers": [
                    {
                        "partner_name": qa_results[0]["partner_name"],
                        "answer": qa_results[0]["answer"]
                    }
                ],
                "source": "partner_qa",
                "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
                "requires_auth": False,
                "new_title": None
            }

    # =====================================================
    # 3️⃣ THEBRIDGE DOCUMENT SEARCH
    # =====================================================
    if embedding:
        try:
            bridge_results = supabase_admin.rpc(
                "match_bridge_chunks",
                {
                    "query_embedding": embedding,
                    "match_threshold": 0.72,
                    "match_count": 8
                }
            ).execute().data
        except Exception as e:
            print("BRIDGE DOC ERROR:", e)
            bridge_results = []

        if bridge_results:

            context = "\n\n".join([row["content"] for row in bridge_results])


        

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": BASE_SYSTEM_PROMPT + "\n\nAnswer ONLY using the provided documentation."
                        },
                        *history,
                        {
                            "role": "user",
                            "content": f"""

Question:
{message}

Documentation:
{context}

Provide a clear and complete answer using only this information.
"""
                        }
                    ],
                    temperature=0.2
                )

                combined_answer = response.choices[0].message.content.strip()

            except Exception as e:
                print("DOC AI ERROR:", e)
                combined_answer = context

            return {
                "answer": combined_answer,
                "source": "bridge_docs",
                "badge": "TheBridge",
                "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
                "requires_auth": False,
                "new_title": None
            }

    # =====================================================
    # 4️⃣ PARTNER DOCUMENT SEARCH
    # =====================================================
    if embedding:
        try:
            semantic_results = supabase_admin.rpc(
                "match_partner_chunks",
                {
                    "query_embedding": embedding,
                    "match_threshold": 0.72,
                    "match_count": 8
                }
            ).execute().data
        except Exception as e:
            print("PARTNER DOC ERROR:", e)
            semantic_results = []

        if semantic_results:
    
 
            grouped = {}

            for row in semantic_results:
                pid = row["partner_id"]
                grouped.setdefault(pid, []).append(row["content"])

            formatted_answers = []

            for partner_id, chunks in grouped.items():

                partner = supabase_admin.table("partners") \
                    .select("badge_label") \
                    .eq("id", partner_id) \
                    .single() \
                    .execute()

                if not partner.data:
                    continue

                context = "\n\n".join(chunks)

                try:
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    BASE_SYSTEM_PROMPT + "\n\nAnswer ONLY using the provided partner documentation."
                                )
                            },
                            *history,
                            {
                                "role": "user",
                                "content": f"""
Question:
{message}

Partner documentation:
{context}

Provide a clear answer using only this information.
"""
                            }
                        ],
                        temperature=0.2
                    )

                    combined_answer = response.choices[0].message.content.strip()

                except Exception as e:
                    print("PARTNER DOC SYNTHESIS ERROR:", e)
                    combined_answer = context

                formatted_answers.append({
                    "partner_name": partner.data["badge_label"],
                    "answer": combined_answer
                })

            if formatted_answers:
                return {
                    "answers": formatted_answers,
                    "source": "db_semantic_multi",
                    "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
                    "requires_auth": False,
                    "new_title": None
                }

    # =====================================================
    # 5️⃣ YACHTING FALLBACK
    # =====================================================
    yachting_keywords = [
        "yacht", "crew", "captain", "flag", "port state", "psc",
        "manning", "inspection", "maritime", "ism", "isps",
        "engine", "bridge", "deck", "charter", "mca", "class"
    ]

    if any(k in user_norm for k in yachting_keywords):
        return {
            "answer": NO_ANSWER_FALLBACK,
            "source": "no_answer",
            "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
            "requires_auth": user_role == "guest",
            "new_title": None
        }

    # =====================================================
    # 6️⃣ AI RESPONSE
    # =====================================================

 
    messages = [
        {
            "role": "system",
            "content": BASE_SYSTEM_PROMPT
        }
    ]

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": message
    })

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7
        )

        answer = response.choices[0].message.content.strip()

    except Exception as e:
        print("OPENAI ERROR:", e)
        answer = "⚠️ AI temporary error. Please try again."

    # =====================================================
    # 7️⃣ AUTO TITLE GENERATION
    # =====================================================
    new_title = None

    if chat_id:
        try:
            existing_messages = get_chat_history(chat_id)

            if len(existing_messages) <= 1:

                title_resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "Create a short 4-6 word title summarizing this topic."
                        },
                        {
                            "role": "user",
                            "content": message
                        }
                    ],
                    temperature=0.3
                )

                new_title = title_resp.choices[0].message.content.strip()

                supabase_admin.table("user_chats") \
                    .update({"title": new_title}) \
                    .eq("id", chat_id) \
                    .execute()

        except Exception as e:
            print("TITLE ERROR:", e)

    return {
        "answer": answer,
        "source": "openai_general",
        "actions": [],
        "requires_auth": False,
        "new_title": new_title
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

    """
    Stores button click analytics in user_clicks table
    """
    try:
        supabase_admin.table("user_clicks").insert({
            "chat_id": chat_id,
            "user_email": user_email,
            "user_type": "user" if user_role != "guest" else "guest",
            "button": button,
            "question": question
        }).execute()
    except Exception as e:
        print("❌ CLICK TRACK ERROR:", e)


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