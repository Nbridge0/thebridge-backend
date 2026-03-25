# troubleshooting.py

TROUBLESHOOTING_SESSIONS = {}


def run_troubleshooting(user_id, message, supabase):

    msg = message.lower()
    session = TROUBLESHOOTING_SESSIONS.get(user_id)

    # ---------------------------------------
    # STEP 1: START SESSION
    # ---------------------------------------
    if not session:

        if "transducer" in msg:
            system = "transducer"

        elif "power" in msg:
            system = "power_module"

        elif "network" in msg:
            system = "network"

        elif "computer" in msg or "software" in msg:
            system = "computer"

        elif any(k in msg for k in ["not working", "issue", "problem", "error"]):
            return {
                "answer": (
                    "I can help troubleshoot, but I need to know which system you're referring to.\n\n"
                    "Please specify:\n"
                    "- Power Module\n"
                    "- Transducer\n"
                    "- Network"
                ),
                "source": "troubleshooting"
            }

        else:
            return None

        # ✅ fetch ONLY this system
        resp = supabase.table("partner_troubleshooting") \
            .select("*") \
            .eq("system", system) \
            .order("step_order") \
            .execute()

        steps = resp.data or []

        if not steps:
            return None

        TROUBLESHOOTING_SESSIONS[user_id] = {
            "step_index": 0,
            "steps": steps,
            "system": system
        }

        return {
            "answer": (
                f"🛠 Starting {system.replace('_',' ').title()} troubleshooting.\n\n"
                f"{steps[0]['question']}"
            ),
            "source": "troubleshooting"
        }

    # ---------------------------------------
    # STEP 2: CONTINUE SESSION
    # ---------------------------------------
    step_index = session["step_index"]
    steps = session["steps"]

    if step_index >= len(steps):
        TROUBLESHOOTING_SESSIONS.pop(user_id, None)
        return {
            "answer": "✅ Troubleshooting complete.",
            "source": "troubleshooting"
        }

    step = steps[step_index]
    answer = msg.strip()

    # 🚨 RESET SESSION if user breaks flow
    if answer not in ["yes", "y", "no", "n"]:
        TROUBLESHOOTING_SESSIONS.pop(user_id, None)
        return None

    if answer in ["yes", "y"]:
        session["step_index"] += 1

        if session["step_index"] >= len(steps):
            TROUBLESHOOTING_SESSIONS.pop(user_id, None)
            return {
                "answer": "✅ System check complete.",
                "source": "troubleshooting"
            }

        next_step = steps[session["step_index"]]

        return {
            "answer": f"{step['yes']}\n\n➡️ {next_step['question']}",
            "source": "troubleshooting"
        }

    elif answer in ["no", "n"]:
        return {
            "answer": f"{step['no']}\n\nPlease fix this and reply 'yes' when done.",
            "source": "troubleshooting"
        }

    return {
        "answer": "Please answer with yes or no.",
        "source": "troubleshooting"
    }