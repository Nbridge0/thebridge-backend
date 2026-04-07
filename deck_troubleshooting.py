from supabase import create_client
import os
from dotenv import load_dotenv, find_dotenv

# ---------------------------------------
# LOAD ENV
# ---------------------------------------
load_dotenv(find_dotenv("env.txt"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print("🔍 SUPABASE_URL:", SUPABASE_URL)  # debug

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

PARTNER_ID = "1666e8d1-a560-4026-8de4-f34d7204902f"

# ---------------------------------------
# STEPS DATA
# ---------------------------------------
steps = [

# ---------------- CAULK ISSUES ----------------
{
    "system": "deck_troubleshooting",
    "step_order": 1,
    "question": "Are you experiencing caulk issues (adhesion, cracking, curing, or rub-off)?",
    "yes": "Let's diagnose the caulk issue.",
    "no": "Moving to surface-related checks."
},
{
    "system": "deck_troubleshooting",
    "step_order": 2,
    "question": "Is the caulk rubbing off (especially black SIS 440)?",
    "yes": "This is a normal UV effect. Light sanding will restore appearance.",
    "no": "Continuing diagnosis."
},
{
    "system": "deck_troubleshooting",
    "step_order": 3,
    "question": "Is the caulk failing to adhere properly?",
    "yes": "Check for dirty or oily seams or moisture above 14%. Clean with acetone and reapply.",
    "no": "Continuing diagnosis."
},
{
    "system": "deck_troubleshooting",
    "step_order": 4,
    "question": "Is the caulk cracking or shrinking?",
    "yes": "Likely caused by insufficient seam depth or sanding too early.",
    "no": "Continuing diagnosis."
},
{
    "system": "deck_troubleshooting",
    "step_order": 5,
    "question": "Is the caulk curing slowly or turning white/gray?",
    "yes": "Use a toothpick test and allow more curing time.",
    "no": "Moving to teak surface checks."
},

# ---------------- TEAK ----------------
{
    "system": "deck_troubleshooting",
    "step_order": 6,
    "question": "Is the teak surface ridged or weathered?",
    "yes": "Sand with 100–120 grit, then finish with 150 grit.",
    "no": "Continuing teak checks."
},
{
    "system": "deck_troubleshooting",
    "step_order": 7,
    "question": "Is there dark staining or mold on the teak?",
    "yes": "Clean with ECO-100 or diluted bleach (stains only), then apply white vinegar to kill spores.",
    "no": "Continuing teak checks."
},
{
    "system": "deck_troubleshooting",
    "step_order": 8,
    "question": "Is there oil contamination on the teak?",
    "yes": "Clean thoroughly with ECO-100 and red Scotch-Brite before applying sealer or caulk.",
    "no": "Moving to composite deck checks."
},

# ---------------- COMPOSITE ----------------
{
    "system": "deck_troubleshooting",
    "step_order": 9,
    "question": "Is this a composite deck with staining or discoloration?",
    "yes": "Apply Composite Sealer immediately.",
    "no": "Continuing composite checks."
},
{
    "system": "deck_troubleshooting",
    "step_order": 10,
    "question": "Has the deck lost its non-slip surface?",
    "yes": "Clean lightly with ECO-300 and reapply sealer if water no longer beads.",
    "no": "Moving to cork deck checks."
},

# ---------------- CORK ----------------
{
    "system": "deck_troubleshooting",
    "step_order": 11,
    "question": "Is this a cork deck with compression or wear?",
    "yes": "Reapply Composite Sealer every 12–18 months.",
    "no": "Continuing cork checks."
},
{
    "system": "deck_troubleshooting",
    "step_order": 12,
    "question": "Is there moisture-related swelling?",
    "yes": "Ensure proper ventilation and avoid standing water.",
    "no": "Final diagnostic check."
},

# ---------------- FINAL ----------------
{
    "system": "deck_troubleshooting",
    "step_order": 13,
    "question": "Do seams remain wet after the rest of the deck dries?",
    "yes": "This indicates a failed seam or water intrusion. Immediate repair is required.",
    "no": "No major issues detected."
}

]

# ---------------------------------------
# RUN SCRIPT
# ---------------------------------------
if __name__ == "__main__":
    print("🚀 Running deck troubleshooting upload...")

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("❌ Missing Supabase credentials. Check env.txt")
        exit()

    for step in steps:
        print(f"📤 Uploading step {step['step_order']}...")

        res = supabase.table("partner_troubleshooting").insert({
            "partner_id": PARTNER_ID,
            "partner_name": "Teakdecking Systems",
            **step
        }).execute()

        # Debug response
        if hasattr(res, "data"):
            print("✅ Inserted:", step["step_order"])
        else:
            print("⚠️ Unexpected response:", res)

    print("🎉 Deck troubleshooting uploaded successfully.")