# troubleshooting.py

from typing import Dict, Any

# -------------------------------
# SESSIONS (IN MEMORY)
# -------------------------------
TROUBLESHOOTING_SESSIONS = {}


# -------------------------------
# SYSTEM DETECTION
# -------------------------------
def detect_system_type(message: str):
    msg = message.lower()

    if "power" in msg:
        return "power"
    elif "transducer" in msg:
        return "transducer"
    elif "network" in msg or "ethernet" in msg:
        return "network"
    elif "computer" in msg or "software" in msg:
        return "computer"

    return None


# -------------------------------
# INTENT DETECTION
# -------------------------------
def detect_troubleshooting_intent(message: str) -> bool:
    keywords = [
        "not working", "issue", "problem", "fault",
        "error", "not detecting", "not responding",
        "troubleshoot", "debug", "failure"
    ]

    msg = message.lower()
    return any(k in msg for k in keywords)


# -------------------------------
# FETCH FROM DATABASE
# -------------------------------
def get_troubleshooting_steps(supabase_admin):
    try:
        resp = supabase_admin.table("partner_troubleshooting") \
            .select("*") \
            .order("step_order") \
            .execute()

        return resp.data or []

    except Exception as e:
        print("TROUBLESHOOTING FETCH ERROR:", e)
        return []


# -------------------------------
# CORE LOGIC
# -------------------------------
def handle_troubleshooting(user_id: str, message: str, supabase_admin):

    session = TROUBLESHOOTING_SESSIONS.get(user_id)

    # -------------------------------
    # START SESSION
    # -------------------------------
    if not session:

        system = detect_system_type(message)

        if not system:
            return (
                "I can help troubleshoot, but I need to know which system you're referring to.\n\n"
                "Please specify:\n"
                "- Power Module\n"
                "- Transducer\n"
                "- Network\n"
                "- Bridge Computer"
            )

        steps = get_troubleshooting_steps(supabase_admin)

        if not steps:
            return "⚠️ Troubleshooting data not available."

        TROUBLESHOOTING_SESSIONS[user_id] = {
            "step_index": 0,
            "steps": steps,
            "system": system
        }

        return (
            f"🛠 Starting troubleshooting for {system.upper()} system.\n"
            "Please answer yes or no.\n\n"
            f"{steps[0]['question']}"
        )

    # -------------------------------
    # CONTINUE SESSION
    # -------------------------------
    step_index = session["step_index"]
    steps = session["steps"]

    if step_index >= len(steps):
        TROUBLESHOOTING_SESSIONS.pop(user_id, None)
        return "✅ Troubleshooting complete."

    step = steps[step_index]

    answer = message.strip().lower()

    # -------------------------------
    # YES
    # -------------------------------
    if answer in ["yes", "y"]:
        session["step_index"] += 1

        if session["step_index"] >= len(steps):
            TROUBLESHOOTING_SESSIONS.pop(user_id, None)
            return "✅ System check complete."

        next_step = steps[session["step_index"]]

        return f"{step['yes']}\n\n➡️ {next_step['question']}"

    # -------------------------------
    # NO
    # -------------------------------
    elif answer in ["no", "n"]:
        return f"{step['no']}\n\nPlease fix this and reply 'yes' when done."

    # -------------------------------
    # INVALID
    # -------------------------------
    else:
        return "Please answer with yes or no."


# -------------------------------
# ENTRY FUNCTION (USED BY chat.py)
# -------------------------------
def run_troubleshooting(user_id: str, message: str, supabase_admin) -> Dict[str, Any]:

    # EXIT
    if "exit troubleshooting" in message.lower():
        TROUBLESHOOTING_SESSIONS.pop(user_id, None)
        return {
            "answer": "🛑 Troubleshooting session ended.",
            "source": "troubleshooting"
        }

    # CONTINUE
    if user_id in TROUBLESHOOTING_SESSIONS:
        return {
            "answer": handle_troubleshooting(user_id, message, supabase_admin),
            "source": "troubleshooting"
        }

    # START ONLY IF INTENT
    if detect_troubleshooting_intent(message):
        return {
            "answer": handle_troubleshooting(user_id, message, supabase_admin),
            "source": "troubleshooting"
        }

    return None