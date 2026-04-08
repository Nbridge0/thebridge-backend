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
from troubleshooting import run_troubleshooting, TROUBLESHOOTING_SESSIONS

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

def adjust_plurality(text: str, question: str) -> str:
    q_words = question.lower().split()

    # detect plural (simple heuristic: any word ending in "s")
    is_plural = any(
        word.endswith("s") and len(word) > 3
        for word in q_words
    )

    if not is_plural:
        return text

    replacements = {
        "A yacht must": "Yachts must",
        "A yacht crew must": "Yacht crews must",
        "A yacht": "Yachts",
        "The yacht": "Yachts",
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    return text

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

def clean_chunks(chunks):
    seen = set()
    cleaned = []

    for c in chunks:
        c = c.strip()

        # remove duplicates
        if c.lower() in seen:
            continue

        # remove very short useless chunks
        if len(c) < 40:
            continue

        seen.add(c.lower())
        cleaned.append(c)

    return cleaned

def filter_chunks(chunks, question):
    keywords = question.lower().split()

    scored = []
    for c in chunks:
        score = sum(1 for k in keywords if k in c.lower())

        # 🔥 BOOST "WHY / IMPORTANCE" CONTENT
        if any(w in question.lower() for w in ["why", "important"]):
            if any(w in c.lower() for w in ["important", "because", "helps", "ensures", "critical", "benefit"]):
                score += 3

        scored.append((score, c))

    scored.sort(reverse=True)
    return [c for _, c in scored[:5]]
    
def remove_redundant_prefixes(text: str) -> str:
    lines = text.split("\n\n")
    cleaned = []

    first_line = True

    for line in lines:
        words = line.split()

        # detect repeated prefix (first 3–5 words)
        if not first_line and len(words) > 5:
            prefix = " ".join(words[:5]).lower()

            # compare with previous line prefix
            prev_words = cleaned[-1].split() if cleaned else []
            prev_prefix = " ".join(prev_words[:5]).lower() if prev_words else ""

            if prefix == prev_prefix:
                # remove prefix
                line = " ".join(words[5:])

        cleaned.append(line)
        first_line = False

    return "\n\n".join(cleaned)

def lightly_format_partner_answer(question: str, answer: str) -> str:
    q = question.lower().strip()
    a = answer.strip()
    a_lower = a.lower()

    # 1️⃣ Only consider YES/NO questions (STRICT)
    is_yes_no = any(q.startswith(w + " ") for w in [
        "is", "are", "does", "do", "can", "should", "will"
    ])

    if not is_yes_no:
        return a

    # 2️⃣ If answer already starts naturally → DON'T TOUCH
    natural_starts = [
        "yes", "no",
        "fortunately", "typically", "generally",
        "in most", "many", "some", "often"
    ]

    if any(a_lower.startswith(w) for w in natural_starts):
        return a

    # 3️⃣ Only add Yes/No if it's CLEAR
    negative_signals = [" not ", " no ", "does not", "cannot", "may not"]

    if any(w in a_lower for w in negative_signals):
        return "No, " + a
    else:
        return "Yes, " + a
def generate_contextual_answer(question: str, context_chunks: list, history: list):
    context = context_chunks[0]

    messages = [
        {
            "role": "system",
            "content": (
                "You are TheBridge AI.\n\n"

                "Use the provided context to answer the question.\n\n"

                "STRICT RULES:\n"
                "- DO NOT add 'Yes' or 'No' unless the context already clearly implies it\n"
                "- DO NOT force Yes/No answers\n"
                "- DO NOT change the meaning of the text\n"
                "- Keep wording as close as possible to the original context\n"
                "- Only slightly adapt the first sentence if needed\n"
            )
        },
        {
            "role": "user",
            "content": f"""
Question:
{question}

Context:
{context}
"""
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0
    )

    return response.choices[0].message.content.strip()
def is_troubleshooting_candidate(message: str) -> bool:
    msg = message.lower()

    problem_signals = [
        "not working",
        "doesn't work",
        "no power",
        "no signal",
        "cannot connect",
        "failed",
        "error",
        "issue"
    ]

    return any(p in msg for p in problem_signals)


def detect_system(message: str):
    msg = message.lower()

    systems = {
        "power_module": ["power module", "power", "led", "fuse"],
        "transducer": ["transducer", "sonar", "capacitance"],
        "network": ["network", "ip", "ping", "ethernet"],
        "computer": ["computer", "software", "sonasoft"]
    }

    for system, keywords in systems.items():
        if any(k in msg for k in keywords):
            return system

    return None

def get_answer(message: str, user_role: str = "guest", chat_id: int = None, history: list = None):

    user_norm = normalize(message)

    # =====================================================
    # 1️⃣ HISTORY
    # =====================================================
    if not chat_id:
        history = history or []
    else:
        history = get_chat_history(chat_id)

    print("HISTORY DEBUG:", history)
    answer_found = False

    # =====================================================
    # 2️⃣ EMBEDDING
    # =====================================================
    try:
        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=message
        ).data[0].embedding
    except Exception as e:
        print("EMBEDDING ERROR:", e)
        embedding = None

    # =====================================================
    # 3️⃣ PARTNER QA (FIRST PRIORITY)
    # =====================================================
    if embedding:
        try:
            qa_results = supabase_admin.rpc(
                "match_partner_qa",
                {
                    "query_embedding": embedding,
                    "match_threshold": 0.70,  # slightly lower for better trigger
                    "match_count": 1
                }
            ).execute().data
        except Exception as e:
            print("PARTNER QA ERROR:", e)
            qa_results = []

        if qa_results:
            row = qa_results[0]

            try:
                partner = supabase_admin.table("partners") \
                    .select("badge_label") \
                    .eq("id", row["partner_id"]) \
                    .single() \
                    .execute()

                partner_name = partner.data["badge_label"] if partner.data else "Partner"
            except Exception as e:
                print("PARTNER FETCH ERROR:", e)
                partner_name = "Partner"

            return {
                "answer": row["answer"],
                "source": "partner_qa",
                "badge": partner_name,
                "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
                "requires_auth": False,
                "new_title": None
            }

    # =====================================================
    # 4️⃣ THEBRIDGE QA
    # =====================================================
    if embedding:
        try:
            bridge_qa = supabase_admin.rpc(
                "match_bridge_qa",
                {
                    "query_embedding": embedding,
                    "match_threshold": 0.65,
                    "match_count": 5
                }
            ).execute().data
        except Exception as e:
            print("BRIDGE QA ERROR:", e)
            bridge_qa = []

        if bridge_qa:
            chunks = [row["answer"] for row in bridge_qa]
            cleaned = clean_chunks(chunks)
            filtered = filter_chunks(cleaned, message)
            filtered = [remove_redundant_prefixes(c) for c in filtered]

            answer = generate_contextual_answer(message, filtered, history)
            answer = adjust_plurality(answer, message)

            return {
                "answer": answer,
                "source": "bridge_semantic_raw",
                "badge": "TheBridge",
                "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
                "requires_auth": False,
                "new_title": None
            }

    # =====================================================
    # 5️⃣ PARTNER DOCS
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
                grouped.setdefault(row["partner_id"], []).append(row["content"])

            formatted_answers = []

            for partner_id, chunks in grouped.items():
                try:
                    partner = supabase_admin.table("partners") \
                        .select("badge_label") \
                        .eq("id", partner_id) \
                        .single() \
                        .execute()

                    partner_name = partner.data["badge_label"] if partner.data else "Partner"
                except Exception as e:
                    print("PARTNER FETCH ERROR:", e)
                    partner_name = "Partner"

                cleaned = clean_chunks(chunks)
                filtered = filter_chunks(cleaned, message)

                raw = filtered[0] if filtered else chunks[0]
                answer = lightly_format_partner_answer(message, raw)

                formatted_answers.append({
                    "partner_name": partner_name,
                    "answer": answer
                })

            if formatted_answers:
                return {
                    "answers": formatted_answers,
                    "source": "partner_docs_raw",
                    "badge": "Partners",
                    "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
                    "requires_auth": False,
                    "new_title": None
                }

    # =====================================================
    # 6️⃣ THEBRIDGE DOCS
    # =====================================================
    if embedding:
        try:
            bridge_results = supabase_admin.rpc(
                "match_bridge_chunks",
                {
                    "query_embedding": embedding,
                    "match_threshold": 0.65,
                    "match_count": 8
                }
            ).execute().data
        except Exception as e:
            print("BRIDGE DOC ERROR:", e)
            bridge_results = []

        if bridge_results:
            chunks = [row["content"] for row in bridge_results]
            cleaned = clean_chunks(chunks)
            filtered = filter_chunks(cleaned, message)

            answer = generate_contextual_answer(message, filtered, history)

            return {
                "answer": answer,
                "source": "bridge_docs_raw",
                "badge": "TheBridge",
                "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
                "requires_auth": False,
                "new_title": None
            }

    # =====================================================
    # 7️⃣ TROUBLESHOOTING + FALLBACK + AI
    # =====================================================
    user_id = str(chat_id) if chat_id else "guest_session"

    if user_id in TROUBLESHOOTING_SESSIONS:
        if not is_troubleshooting_candidate(message):
            TROUBLESHOOTING_SESSIONS.pop(user_id, None)
        else:
            troubleshoot = run_troubleshooting(user_id, message, supabase_admin)
            if troubleshoot:
                return {
                    "answer": troubleshoot["answer"],
                    "source": troubleshoot["source"],
                    "badge": troubleshoot.get("badge"),
                    "actions": [],
                    "requires_auth": False,
                    "new_title": None
                }

    yachting_keywords = [
        "yacht", "crew", "captain", "flag", "port state",
        "manning", "inspection", "maritime"
    ]

    if any(k in user_norm for k in yachting_keywords):
        return {
            "answer": NO_ANSWER_FALLBACK,
            "source": "no_answer",
            "actions": ["ask_ai", "ask_specialist", "ask_ambassador"],
            "requires_auth": user_role == "guest",
            "new_title": None
        }

    # AI fallback
    messages = [{"role": "system", "content": BASE_SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

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

    return {
        "answer": answer,
        "source": "openai_general",
        "actions": [],
        "requires_auth": False,
        "new_title": None
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
        .select("name, email, contact_name") \
        .eq("email", expert_email) \
        .single() \
        .execute()

    if not expert.data:
        return {"status": "expert_not_found"}

    body = HELP_EMAIL_BODY.format(
        expert_name=expert.data.get("contact_name") or expert.data["name"],
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
