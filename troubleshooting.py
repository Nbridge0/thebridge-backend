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

    systems = {
        "power_module": [
            "power module",
            "no power",
            "power issue",
            "power not working",
            "led",
            "fuse"
        ],
        "transducer": [
            "transducer",
            "sonar",
            "no signal",
            "not detecting"
        ],
        "network": [
            "network",
            "ip",
            "ping",
            "ethernet",
            "cannot connect",
            "network issue"
        ],
        "computer": [
            "computer",
            "software",
            "sonasoft",
            "crash",
            "not responding",
            "app not working"
        ]
    }

    for system, keywords in systems.items():
        if any(all(word in msg for word in k.split()) for k in keywords):
            return system

    return None


# ---------------------------------------
# FAILURE DETECTION (FIXED)
# ---------------------------------------
def detect_failure_from_message(msg: str):

    mapping = {

        # 🔌 POWER
        "power_led_not_lit": [
            "no power",
            "power not working",
            "led off",
            "power module dead",
            "power stopped working"
        ],

        # 🌊 TRANSDUCER
        "transducer_not_detected": [
            "no signal",
            "transducer not working",
            "transducer not detecting",
            "transducer issue",
            "transducer failure",
            "not detecting bottom",
            "no seabed"
        ],

        # 🌐 NETWORK
        "ip_not_reachable": [
            "cannot connect",
            "network issue",
            "ping failed",
            "ip not reachable",
            "ethernet not working",
            "network failure"
        ],

        # 💻 COMPUTER
        "software_not_responding": [
            "software issue",
            "sonasoft not working",
            "computer not responding",
            "app crash",
            "program not opening",
            "app not working"
        ],
    }

    for key, keywords in mapping.items():
        for k in keywords:
            if all(word in msg for word in k.split()):
                return key

    return None