from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from chat import get_answer, send_help_request, ask_ai_only, save_message
from supabase import create_client
import os
from dotenv import load_dotenv, find_dotenv
import secrets
import requests
from datetime import datetime, timedelta, timezone
from typing import List
# -------------------------
# ENV
# -------------------------
load_dotenv(find_dotenv("env.txt"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

FROM_EMAIL = os.getenv("FROM_EMAIL")


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


def get_user_by_email(email: str):
    users = supabase_admin.auth.admin.list_users()
    for u in users:
        if u.email == email:
            return u
    return None


VERIFICATION_EMAIL_SUBJECT = "Almost There! Verify Your TheBridge Account"

VERIFICATION_EMAIL_BODY = """Hi {name},

Thanks for joining TheBridge — we are glad you´re here!

To finish setting up your account, please use the verification code below:

{code}

This verification code is valid for 5 minutes.

Enter the code on our website to verify your account and get started. 
If you didn´t request this, you can safely ignore this email.

Welcome aboard,
TheBridge Team
"""

WELCOME_EMAIL_SUBJECT = "Welcome to The Bridge – Your AI-Powered Superyacht Knowledge Platform"

WELCOME_EMAIL_BODY = """Hi {name},

Welcome aboard!

Thank you for signing up and joining The Bridge community. We're thrilled to have you as part of the first trusted source of verified insight built exclusively for the superyachting industry.

Your account is now active and ready for use.

If we do not have the answer yet, you have options:
• Ask AI: Get an instant reply from our integrated Open AI feature.
• Ask a Specialist: Connect with one of our industry specialists via email and receive a reply in your inbox. 
• Ask an Ambassador: Get in touch with a fellow captain or crew member who will send a reply to your inbox. 

Please allow them some time to reply.
We look forward to seeing you on The Bridge!

Kind regards,
The Bridge Team
"""


PASSWORD_RESET_EMAIL_SUBJECT = "Your Password Reset Code for TheBridge"

PASSWORD_RESET_EMAIL_BODY = """Hi {name},

We received a request to reset your TheBridge password.

Use the verification code below to continue:

{code}

This verification code is valid for 5 minutes.

Enter the code on our website to reset your password and regain access to your account.
If you didn´t request this, you can safely ignore this email.

Kind regards,
TheBridge Team
"""

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


# -------------------------
# EMAIL
# -------------------------
def send_email(to_email, subject, body):
    url = "https://api.brevo.com/v3/smtp/email"

    if isinstance(to_email, list):
        to = [{"email": e} for e in to_email]
    else:
        to = [{"email": to_email}]

    payload = {
        "sender": {
            "name": "TheBridge",
            "email": FROM_EMAIL
        },
        "to": to,
        "subject": subject,
        "textContent": body
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
# -------------------------
# APP
# -------------------------
app = FastAPI(title="TheBridge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # ✅ correct for ngrok/browser
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/experts")
def list_experts(role: str):
    experts = supabase_admin.table("experts") \
        .select("id, name, email, description") \
        .eq("role", role) \
        .eq("is_active", True) \
        .execute()

    return experts.data


# -------------------------
# MODELS
# -------------------------
class ChatRequest(BaseModel):
    chat_id: Optional[int] = None
    message: str
    user_role: str = "guest"
    user_email: Optional[str] = None


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str


class ResetRequest(BaseModel):
    email: EmailStr


class ResetVerifyRequest(BaseModel):
    email: EmailStr
    code: str


class ResetConfirmRequest(BaseModel):
    email: EmailStr
    new_password: str

class CreateChatRequest(BaseModel):
    user_email: EmailStr
    title: str

class HelpRequest(BaseModel):
    message: str
    user_email: EmailStr
    expert_emails: List[EmailStr]
    role: str


@app.post("/help/send")
def help_send(req: HelpRequest):

    # 🔒 Re-fetch valid experts by role
    valid_experts = supabase_admin.table("experts") \
        .select("email") \
        .eq("role", req.role) \
        .eq("is_active", True) \
        .in_("email", req.expert_emails) \
        .execute()

    if not valid_experts.data:
        raise HTTPException(400, "Invalid expert selection")

    for expert in valid_experts.data:
        send_help_request(
            req.role,
            req.message,
            req.user_email,
            expert["email"]
        )

    return {"status": "emails_sent"}


# -------------------------
# HEALTH
# -------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# -------------------------
# CHAT
# -------------------------
@app.post("/chat/message")
def chat_message(req: ChatRequest):
    result = get_answer(req.message, req.user_role)

    if req.chat_id:
        save_message(req.chat_id, "user", req.message, "user", req.user_email)
        save_message(req.chat_id, "assistant", result["answer"], result["source"], req.user_email)

    return result


@app.post("/chat/ask-ai")
def chat_ask_ai(req: ChatRequest):
    answer = ask_ai_only(req.message)


    if req.chat_id:
        save_message(
            req.chat_id,
            "assistant",
            answer,
            "openai_only",
            req.user_email
        )


    return {
        "answer": answer,
        "source": "openai_only",
    }


# -------------------------
# AUTH
# -------------------------
@app.post("/auth/signup")
def signup(req: SignupRequest):
    email = req.email.lower().strip()
    code = secrets.token_hex(3)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)

    supabase_admin.table("email_verifications").upsert({
        "email": email,
        "name": req.name,
        "password": req.password,
        "code": code,
        "expires_at": expiry.isoformat()
    }).execute()

    send_email(
         email,
         VERIFICATION_EMAIL_SUBJECT,
         VERIFICATION_EMAIL_BODY.format(
             name=req.name,
             code=code
        )
    )


    return {"status": "verification_sent"}

@app.post("/auth/verify")
def verify(req: VerifyRequest):
    email = req.email.lower().strip()
    code = req.code.strip()

    resp = supabase_admin.table("email_verifications") \
        .select("*") \
        .eq("email", email) \
        .execute()

    if not resp.data:
        raise HTTPException(400, "No verification request found")

    record = resp.data[0]

    expires_at = datetime.fromisoformat(record["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "Verification code expired")

    if code != record["code"]:
        raise HTTPException(400, "Invalid verification code")

    # ✅ delete verification record FIRST
    supabase_admin.table("email_verifications") \
        .delete() \
        .eq("email", email) \
        .execute()

    # ✅ create or update user — PASSWORD WRITTEN ONLY ON CREATE
    user = get_user_by_email(email)

    if user:
        # ❌ DO NOT TOUCH PASSWORD
        supabase_admin.auth.admin.update_user_by_id(
            user.id,
            {
                "email_confirm": True
            }
        )
        user_id = user.id
    else:
        user = supabase_admin.auth.admin.create_user({
            "email": email,
            "password": record["password"],
            "email_confirm": True
        })
        user_id = user.user.id

    # ✅ upsert profile
    supabase_admin.table("user_profiles").upsert({
        "id": user_id,
        "email": email,
        "name": record["name"]
    }).execute()

    # ✅ SEND WELCOME EMAIL (EXACT CONTENT)
    send_email(
        email,
        WELCOME_EMAIL_SUBJECT,
        WELCOME_EMAIL_BODY.format(name=record["name"])
    )

    return {"status": "verified"}

@app.post("/auth/login")
def login(req: LoginRequest):
    try:
        auth = supabase.auth.sign_in_with_password({
            "email": req.email.lower().strip(),
            "password": req.password
        })
        return {"status": "ok", "user": auth.user}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

# -------------------------
# PASSWORD RESET (BASIC)
# -------------------------
@app.post("/auth/password-reset/request")
def reset_request(req: ResetRequest):
    email = req.email.lower().strip()

    user = get_user_by_email(email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Email not registered with us. Please create an account."
        )

    code = secrets.token_hex(3)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)

    supabase_admin.table("password_resets").upsert({
        "email": email,
        "code": code,
        "expires_at": expiry.isoformat()
    }).execute()

    name = get_user_name_by_email(email)

    send_email(
        email,
        PASSWORD_RESET_EMAIL_SUBJECT,
        PASSWORD_RESET_EMAIL_BODY.format(name=name, code=code)
        
    )

    return {"status": "code_sent"}


@app.post("/auth/password-reset/verify")
def reset_verify(req: ResetVerifyRequest):
    resp = supabase_admin.table("password_resets") \
        .select("*") \
        .eq("email", req.email.lower()) \
        .single() \
        .execute()

    if not resp.data:
        raise HTTPException(400, "No reset request found")

    record = resp.data
    expires_at = datetime.fromisoformat(record["expires_at"])

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "Code expired")

    if req.code != record["code"]:
        raise HTTPException(400, "Invalid code")

    return {"status": "verified"}



@app.post("/auth/password-reset/confirm")
def reset_confirm(req: ResetConfirmRequest):
    email = req.email.lower().strip()

    # 1. Ensure reset was requested
    reset = supabase_admin.table("password_resets") \
        .select("*") \
        .eq("email", email) \
        .single() \
        .execute()

    if not reset.data:
        raise HTTPException(400, "Reset not verified")

    expires_at = datetime.fromisoformat(reset.data["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "Reset expired")

    # 2. Update password
    user = get_user_by_email(email)
    if not user:
         raise HTTPException(404, "User not found")


    supabase_admin.auth.admin.update_user_by_id(
        user.id,
        {
         "password": req.new_password,
         "email_confirmed_at": datetime.now(timezone.utc).isoformat()
        }
    )

    # 3. DELETE reset record (ONLY HERE)
    supabase_admin.table("password_resets") \
        .delete() \
        .eq("email", email) \
        .execute()

    return {"status": "password_updated"}



# -------------------------
# CHATS
# -------------------------
@app.get("/chats")
def list_chats(user_email: EmailStr):
    resp = supabase_admin.table("user_chats") \
        .select("*") \
        .eq("user_email", user_email) \
        .execute()
    return resp.data 


@app.post("/chats")
async def create_chat(payload: CreateChatRequest):
    res = supabase_admin.table("user_chats").insert({
        "user_email": payload.user_email,
        "title": payload.title
    }).execute()

    return {"chat_id": res.data[0]["id"]}



@app.post("/chats/{chat_id}/messages")
def save_chat_messages(chat_id: int, messages: list):
    supabase_admin.table("user_chats") \
        .update({"messages": messages}) \
        .eq("id", chat_id) \
        .execute()
    return {"status": "saved"}


@app.get("/chats/{chat_id}/messages")
def get_chat_messages(chat_id: int):
    resp = supabase_admin.table("chat_messages") \
        .select("*") \
        .eq("chat_id", chat_id) \
        .order("id") \
        .execute()

    return resp.data


# -------------------------
# GUEST → USER
# -------------------------
@app.post("/guest/attach")
def attach_guest(user_email: EmailStr, guest_chats: list):
    for chat in guest_chats:
        supabase_admin.table("user_chats").insert({
            "user_email": user_email,
            "title": chat["title"],
            "messages": chat["messages"]
        }).execute()

    return {"status": "attached"}
