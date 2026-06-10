import os
import io
import logging
import requests
import pandas as pd
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from groq import Groq
from dotenv import load_dotenv
from functools import lru_cache

# ─────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")

if not GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY is not set.")

client = Groq(api_key=GROQ_API_KEY)
log.info("✅ MedScan bot started successfully.")

# ─────────────────────────────────────────
#  Indian Medicine Database
# ─────────────────────────────────────────
MEDICINE_DB_URL = "https://raw.githubusercontent.com/junioralive/Indian-Medicine-Dataset/main/DATA/indian_medicine_data.csv"
medicine_df = None

def load_medicine_database():
    """Load Indian medicine CSV database from GitHub."""
    global medicine_df
    try:
        log.info("Loading Indian medicine database...")
        response = requests.get(MEDICINE_DB_URL, timeout=30)
        medicine_df = pd.read_csv(io.StringIO(response.text))
        medicine_df["name_lower"] = medicine_df["name"].str.lower().str.strip()
        log.info(f"✅ Medicine database loaded: {len(medicine_df)} medicines")
    except Exception as e:
        log.error(f"Failed to load medicine database: {e}")
        medicine_df = None

def search_medicine(query: str) -> dict | None:
    """Search medicine in Indian database by name."""
    if medicine_df is None:
        return None
    try:
        query_lower = query.lower().strip()
        # Exact match first
        match = medicine_df[medicine_df["name_lower"] == query_lower]
        # Partial match if no exact
        if match.empty:
            match = medicine_df[medicine_df["name_lower"].str.contains(query_lower, na=False)]
        if not match.empty:
            row = match.iloc[0]
            return {
                "name": row.get("name", query),
                "composition1": row.get("short_composition1", ""),
                "composition2": row.get("short_composition2", ""),
                "manufacturer": row.get("manufacturer_name", ""),
                "price": row.get("price(₹)", ""),
                "type": row.get("type", ""),
                "pack_size": row.get("pack_size_label", "")
            }
        return None
    except Exception as e:
        log.error(f"Search error: {e}")
        return None

# Load database on startup
load_medicine_database()

# ─────────────────────────────────────────
#  Prompts & Messages
# ─────────────────────────────────────────
SYSTEM_PROMPT = """You are MedScan, an expert Indian medicine assistant.
You help Indian patients understand their medicines clearly and safely.

STRICT RULE — ALWAYS reply in ALL 3 languages together in this exact order:
1. Telugu first
2. English second
3. Hindi third

When given medicine details, reply in this EXACT detailed format:

🇮🇳 *MedScan — మందు సమాచారం | Medicine Info | दवा की जानकारी*
━━━━━━━━━━━━━━━━━━━━━━

💊 *మందు పేరు:* [name in Telugu]

🔍 *దేనికి వాడతారు:*
- [use 1 in Telugu]
- [use 2 in Telugu]
- [use 3 in Telugu]

⏰ *ఎప్పుడు తీసుకోవాలి:*
- [timing detail 1 in Telugu]
- [timing detail 2 in Telugu]

🍽️ *ఎలా తీసుకోవాలి:*
- [how to take 1 in Telugu]
- [how to take 2 in Telugu]

⚠️ *జాగ్రత్తలు:*
- [warning 1 in Telugu]
- [warning 2 in Telugu]
- [warning 3 in Telugu]

━━━━━━━━━━━━━━━━━━━━━━

💊 *Medicine:* [name in English]

🔍 *Used for:*
- [use 1 in English]
- [use 2 in English]
- [use 3 in English]

⏰ *When to take:*
- [timing 1 in English]
- [timing 2 in English]

🍽️ *How to take:*
- [how to take 1 in English]
- [how to take 2 in English]

⚠️ *Warnings:*
- [warning 1 in English]
- [warning 2 in English]
- [warning 3 in English]

━━━━━━━━━━━━━━━━━━━━━━

💊 *दवा का नाम:* [name in Hindi]

🔍 *उपयोग:*
- [use 1 in Hindi]
- [use 2 in Hindi]
- [use 3 in Hindi]

⏰ *कब लें:*
- [timing 1 in Hindi]
- [timing 2 in Hindi]

🍽️ *कैसे लें:*
- [how to take 1 in Hindi]
- [how to take 2 in Hindi]

⚠️ *चेतावनी:*
- [warning 1 in Hindi]
- [warning 2 in Hindi]
- [warning 3 in Hindi]

━━━━━━━━━━━━━━━━━━━━━━
_సందేహాలు ఉంటే అడగండి | Ask doubts | सवाल पूछें_ 💊

For serious symptoms always add:
డాక్టర్‌ను సంప్రదించండి | Consult a doctor | डॉक्टर से मिलें"""

WELCOME_MESSAGE = """🇮🇳 *MedScan కి స్వాగతం | Welcome to MedScan | MedScan में आपका स्वागत*

మందుల సమాచారం తెలుగు, English, Hindi లో పొందండి.
Get medicine info in Telugu, English & Hindi.
दवाओं की जानकारी तेलुगु, अंग्रेजी और हिंदी में पाएं।

మీరు చేయగలిగేది | You can | आप कर सकते हैं:
📸 మందు ఫోటో పంపండి | Send medicine photo | दवा की फोटो भेजें
💊 మందు పేరు టైప్ చేయండి | Type medicine name | दवा का नाम टाइप करें
🔵 మాత్ర రంగు వర్ణించండి | Describe tablet color | गोली का रंग बताएं

*ఉదాహరణ | Example | उदाहरण:* Paracetamol"""

PHOTO_MESSAGE = """📸 *ఫోటో అందింది! | Photo received! | फोटो मिली!*

మందు పేరు కూడా టైప్ చేయండి.
Please also type the medicine name.
दवा का नाम भी टाइप करें। 💊"""

ERROR_MESSAGE = "⚠️ సేవ తాత్కాలికంగా అందుబాటులో లేదు | Service temporarily unavailable | सेवा अस्थायी रूप से उपलब्ध नहीं 🙏"

GREETINGS = {"hi", "hello", "hey", "నమస్కారం", "హలో", "నమస్తే", "start", "help", "హాయ్", "namaste"}

# ─────────────────────────────────────────
#  AI Helper
# ─────────────────────────────────────────
def ask_ai(medicine_name: str, db_info: dict | None) -> str | None:
    """Send medicine details to Groq and return trilingual response."""
    try:
        # Build context from real database if found
        if db_info:
            composition = db_info["composition1"]
            if db_info["composition2"]:
                composition += f" + {db_info['composition2']}"
            user_content = f"""Medicine from Indian database:
Name: {db_info['name']}
Composition: {composition}
Manufacturer: {db_info['manufacturer']}
Type: {db_info['type']}
Pack: {db_info['pack_size']}
Price: ₹{db_info['price']}

Give complete detailed information about this medicine based on its composition."""
        else:
            user_content = f"""Medicine name: {medicine_name}
This may be an Indian brand name. Identify the composition and give complete information."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content}
            ],
            max_tokens=1800,
            temperature=0.3
        )
        reply = response.choices[0].message.content.strip()
        log.info(f"AI replied for: {medicine_name} | DB found: {db_info is not None}")
        return reply

    except Exception as e:
        log.error(f"Groq error: {type(e).__name__}: {e}")
        return None

# ─────────────────────────────────────────
#  WhatsApp Webhook
# ─────────────────────────────────────────
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    media_url    = request.form.get("MediaUrl0")
    media_type   = request.form.get("MediaContentType0", "")
    sender       = request.form.get("From", "unknown")

    log.info(f"Message from {sender}: '{incoming_msg[:50]}' | media={bool(media_url)}")

    resp = MessagingResponse()
    msg  = resp.message()

    # ── Greeting ──────────────────────────
    if incoming_msg.lower() in GREETINGS:
        msg.body(WELCOME_MESSAGE)
        return str(resp)

    # ── Photo received ────────────────────
    if media_url and "image" in media_type:
        msg.body(PHOTO_MESSAGE)
        return str(resp)

    # ── Medicine query ────────────────────
    if incoming_msg:
        # Search real Indian medicine database first
        db_info = search_medicine(incoming_msg)
        if db_info:
            log.info(f"Found in DB: {db_info['name']} | {db_info['composition1']}")
        else:
            log.info(f"Not in DB, using AI knowledge for: {incoming_msg}")

        reply = ask_ai(incoming_msg, db_info)
        msg.body(reply if reply else ERROR_MESSAGE)
        return str(resp)

    # ── Empty message ─────────────────────
    msg.body("మందు పేరు లేదా ఫోటో పంపండి | Type medicine name | दवा का नाम टाइप करें 💊")
    return str(resp)

# ─────────────────────────────────────────
#  Health Check
# ─────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health_check():
    db_status = len(medicine_df) if medicine_df is not None else 0
    return {
        "status": "ok",
        "bot": "MedScan",
        "version": "3.0",
        "medicines_loaded": db_status
    }, 200

# ─────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info(f"🚀 Starting MedScan v3.0 on port {port}")
    app.run(host="0.0.0.0", port=port)