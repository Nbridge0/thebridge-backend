# troubleshooting.py

TROUBLESHOOTING_SESSIONS = {}


def run_troubleshooting(user_id, message, supabase):
    msg = message.lower().strip()
    session = TROUBLESHOOTING_SESSIONS.get(user_id)

    # ---------------------------------------
    # STEP 1: START SESSION
    # ---------------------------------------
    if not session:

        system = detect_system_from_message(msg)

        if not system:
            return None

        failure_key = detect_failure_from_message(msg)

        # DEBUG (optional - remove later)
        print("DEBUG SYSTEM:", system)
        print("DEBUG FAILURE:", failure_key)

        if not failure_key:
            return {
                "answer": (
                    "Please specify the issue more clearly:\n\n"
                    "- No power\n"
                    "- No signal\n"
                    "- Network issue\n"
                    "- Software issue"
                ),
                "source": "troubleshooting"
            }

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
            "failure_key": failure_key,
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
                "✅ Troubleshooting complete.\n\n"
                "If the issue persists, further investigation is required."
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
    # YES
    # ---------------------------------------
    if answer in ["yes", "y"]:

        session["step_index"] += 1

        if session["step_index"] >= len(steps):
            TROUBLESHOOTING_SESSIONS.pop(user_id, None)
            return {
                "answer": (
                    "✅ Troubleshooting complete.\n\n"
                    "System checks passed."
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
    # NO
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
    # INVALID
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
# SYSTEM DETECTION (FIXED)
# ---------------------------------------
def detect_system_from_message(msg: str):

    msg = msg.lower()

    # 🔥 HARD OVERRIDES (CRITICAL)
    if "transducer" in msg:
        return "transducer"

    if "power" in msg:
        return "power_module"

    if "network" in msg or "ip" in msg:
        return "network"

    if "computer" in msg or "software" in msg:
        return "computer"

    return None

# ---------------------------------------
# FAILURE DETECTION (FIXED)
# ---------------------------------------
def detect_failure_from_message(msg: str):

    msg = msg.lower()

    # 🔥 HARD OVERRIDES (CRITICAL FIX)
    if "transducer" in msg and "not working" in msg:
        return "transducer_not_detected"

    if "power" in msg and "not working" in msg:
        return "power_led_not_lit"

    if "network" in msg and ("not working" in msg or "cannot connect" in msg):
        return "ip_not_reachable"

    if "computer" in msg and "not working" in msg:
        return "software_not_responding"

    # ---------------------------------------
    # FALLBACK KEYWORD MATCHING
    # ---------------------------------------
    mapping = {

        "power_led_not_lit": [
            "no power",
            "power not working",
            "led off"
        ],

        "transducer_not_detected": [
            "no signal",
            "not detecting",
            "no seabed"
        ],

        "ip_not_reachable": [
            "cannot connect",
            "network issue",
            "ping failed"
        ],

        "software_not_responding": [
            "software issue",
            "app crash",
            "not responding"
        ],
    }

    for key, keywords in mapping.items():
        for k in keywords:
            if k in msg:
                return key

    return None