# troubleshooting.py
TROUBLESHOOTING_SESSIONS = {}


def run_troubleshooting(user_id, message, supabase):
    msg = message.lower().strip()
    session = TROUBLESHOOTING_SESSIONS.get(user_id)

    # ---------------------------------------
    # STEP 1: START SESSION (ONLY IF NONE EXISTS)
    # ---------------------------------------
    if not session:

        from chat import detect_system
        system = detect_system(msg)

        # If we can't detect system → don't start
        if not system:
            return None

        # Fetch steps from DB
        resp = supabase.table("partner_troubleshooting") \
            .select("*") \
            .eq("system", system) \
            .order("step_order") \
            .execute()

        steps = resp.data or []

        if not steps:
            return None

        partner_name = steps[0].get("partner_name", "Partner")

        # Create session
        TROUBLESHOOTING_SESSIONS[user_id] = {
            "step_index": 0,
            "steps": steps,
            "system": system,
            "partner_name": partner_name
        }

        first_step = steps[0]

        return {
            "answer": (
                f"🛠 Starting {system.replace('_',' ').title()} troubleshooting.\n\n"
                f"{first_step['question']}\n\n"
                "Please answer: yes / no"
            ),
            "source": "troubleshooting",
            "badge": partner_name
        }

    # ---------------------------------------
    # STEP 2: CONTINUE SESSION
    # ---------------------------------------
    step_index = session["step_index"]
    steps = session["steps"]
    partner_name = session.get("partner_name", "Partner")

    # If session finished
    if step_index >= len(steps):
        TROUBLESHOOTING_SESSIONS.pop(user_id, None)
        return {
            "answer": "✅ Troubleshooting complete.",
            "source": "troubleshooting",
            "badge": partner_name
        }

    step = steps[step_index]

    # Normalize answer
    answer = msg.strip()
    if answer == "exit":
        TROUBLESHOOTING_SESSIONS.pop(user_id, None)
        return {
            "answer": "Troubleshooting stopped. How else can I help?",
            "source": "troubleshooting"
        }

    # ---------------------------------------
    # HANDLE YES
    # ---------------------------------------
    if answer in ["yes", "y"]:

        session["step_index"] += 1

        # If finished after increment
        if session["step_index"] >= len(steps):
            TROUBLESHOOTING_SESSIONS.pop(user_id, None)
            return {
                "answer": "✅ System check complete. Everything looks good.",
                "source": "troubleshooting",
                "badge": partner_name
            }

        next_step = steps[session["step_index"]]

        return {
            "answer": (
                f"{step.get('yes', 'Great.')}\n\n"
                f"➡️ {next_step['question']}\n\n"
                "Please answer: yes / no"
            ),
            "source": "troubleshooting",
            "badge": partner_name
        }

    # ---------------------------------------
    # HANDLE NO
    # ---------------------------------------
    elif answer in ["no", "n"]:

        return {
            "answer": (
                f"{step.get('no', 'Please fix this issue.')}\n\n"
                "Once done, reply 'yes' to continue."
            ),
            "source": "troubleshooting",
            "badge": partner_name
        }

    # ---------------------------------------
    # INVALID INPUT
    # ---------------------------------------
    else:
        return {
            "answer": (
                "Please answer with 'yes' or 'no'.\n\n"
                "Or type 'exit' to stop troubleshooting."
            ),
            "source": "troubleshooting",
            "badge": partner_name
        }


# ---------------------------------------
# SYSTEM DETECTION (USED INTERNALLY)
# ---------------------------------------
def detect_system_from_message(msg: str):

    systems = {
        "power_module": ["power module", "no power", "led", "fuse"],
        "transducer": ["transducer", "sonar", "capacitance"],
        "network": ["network", "ip", "ping", "ethernet"],
        "computer": ["computer", "software", "sonasoft"]
    }

    for system, keywords in systems.items():
        if any(k in msg for k in keywords):
            return system

    return None