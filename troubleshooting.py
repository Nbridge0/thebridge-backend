# troubleshooting.py

TROUBLESHOOTING_SESSIONS = {}


def run_troubleshooting(user_id, message, supabase):
    msg = message.lower().strip()
    session = TROUBLESHOOTING_SESSIONS.get(user_id)

    # ---------------------------------------
    # STEP 1: START SESSION (ONLY IF NONE EXISTS)
    # ---------------------------------------
    if not session:

        system = detect_system_from_message(msg)

        if not system:
            return None

        # 🔥 Detect failure type
        failure_key = detect_failure_from_message(msg)

        if not failure_key:
            return {
                "answer": (
                    "Which issue are you experiencing?\n\n"
                    "- No power\n"
                    "- No signal\n"
                    "- Network issue\n\n"
                    "Please specify."
                ),
                "source": "troubleshooting"
            }

        # 🔥 Fetch ONLY correct failure path
        resp = supabase.table("partner_troubleshooting") \
            .select("*") \
            .eq("system", system) \
            .eq("failure_key", failure_key) \
            .order("step_order") \
            .execute()

        steps = resp.data or []

        if not steps:
            return None

        partner_name = steps[0].get("partner_name", "Partner")

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

    if step_index >= len(steps):
        TROUBLESHOOTING_SESSIONS.pop(user_id, None)
        return {
            "answer": (
                "✅ Troubleshooting step completed.\n\n"
                "If the issue persists, further investigation may be required."
            ),
            "source": "troubleshooting",
            "badge": partner_name
        }

    step = steps[step_index]

    answer = msg.strip()

    # EXIT
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

        if session["step_index"] >= len(steps):
            TROUBLESHOOTING_SESSIONS.pop(user_id, None)
            return {
                "answer": (
                    "✅ Troubleshooting step completed.\n\n"
                    "If the issue persists, further investigation may be required."
                ),
                "source": "troubleshooting",
                "badge": partner_name
            }

        next_step = steps[session["step_index"]]

        return {
            "answer": (
                f"{step.get('yes', 'Proceed.')}\n\n"
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
# SYSTEM DETECTION
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


# ---------------------------------------
# FAILURE DETECTION (CRITICAL)
# ---------------------------------------
def detect_failure_from_message(msg: str):

    mapping = {
        "power_led_not_lit": ["no power", "power not working", "led off"],
        "transducer_not_detected": ["no signal", "transducer not working"],
        "ip_not_reachable": ["cannot connect", "network", "ping", "ip"],
    }

    for key, keywords in mapping.items():
        if any(k in msg for k in keywords):
            return key

    return None