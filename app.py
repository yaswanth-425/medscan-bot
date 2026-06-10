import os
import io
import logging
import requests
import pandas as pd
from flask import Flask, request
from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse
from groq import Groq
from dotenv import load_dotenv

# ─────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER      = "whatsapp:+14155238886"

if not GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY is not set. Add it to Railway Variables.")

groq_client   = Groq(api_key=GROQ_API_KEY)
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
log.info("✅ MedScan bot started successfully.")

# ─────────────────────────────────────────
#  Indian Medicine Database
# ─────────────────────────────────────────
MEDICINE_DB_URL = "https://raw.githubusercontent.com/junioralive/Indian-Medicine-Dataset/main/DATA/indian_medicine_data.csv"
medicine_df = None

def load_medicine_database():
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
    if medicine_df is None:
        return None
    try:
        query_lower = query.lower().strip()
        # Exact match first
        match = medicine_df[medicine_df["name_lower"] == query_lower]
        # Partial match fallback
        if match.empty:
            match = medicine_df[medicine_df["name_lower"].str.contains(query_lower, na=False)]
        if not match.empty:
            row = match.iloc[0]
            return {
                "name":         row.get("name", query),
                "composition1": row.get("short_composition1", ""),
                "composition2": row.get("short_composition2", ""),
                "manufacturer": row.get("manufacturer_name", ""),
                "price":        row.get("price(₹)", ""),
                "type":         row.get("type", ""),
                "pack_size":    row.get("pack_size_label", "")
            }
        return None
    except Exception as e:
        log.error(f"Search error: {e}")
        return None

# Load database at startup
load_medicine_database()

# ─────────────────────────────────────────
#  Prompts & Messages
# ─────────────────────────────────────────
SINGLE_PROMPT = """You are MedScan, an expert Indian medicine assistant.
ALWAYS reply in ALL 3 languages combined in ONE single message in this EXACT format.
Keep each section SHORT — max 2 bullet points per field.

🇮🇳 *MedScan — Medicine Info*
━━━━━━━━━━━━━━━━━━━

🔵 *తెలుగు:*
💊 *మందు:* [name]
🏭 *తయారీదారు:* [manufacturer]
🔍 *వాడకం:*
• [use 1]
• [use 2]
⏰ *సమయం:* [when to take]
🍽️ *ఎలా:* [before/after food]
⚠️ *జాగ్రత్త:*
• [warning 1]
• [warning 2]

━━━━━━━━━━━━━━━━━━━
🔴 *English:*
💊 *Medicine:* [name]
🏭 *Manufacturer:* [manufacturer]
🔍 *Used for:*
• [use 1]
• [use 2]
⏰ *When:* [timing]
🍽️ *How:* [before/after food]
⚠️ *Warnings:*
• [warning 1]
• [warning 2]

━━━━━━━━━━━━━━━━━━━
🟠 *हिंदी:*
💊 *दवा:* [name]
🏭 *निर्माता:* [manufacturer]
🔍 *उपयोग:*
• [use 1]
• [use 2]
⏰ *समय:* [timing]
🍽️ *कैसे:* [before/after food]
⚠️ *चेतावनी:*
• [warning 1]
• [warning 2]

━━━━━━━━━━━━━━━━━━━
_డాక్టర్‌ను సంప్రదించండి | Consult doctor | डॉक्टर से मिलें_ 🙏"""

WELCOME_MESSAGE = """🇮🇳 *MedScan కి స్వాగతం | Welcome | स्वागत है*

మందుల సమాచారం తెలుగు, English & Hindi లో పొందండి.
Get medicine info in Telugu, English & Hindi.
दवाओं की जानकारी तीनों भाषाओं में पाएं।

మీరు చేయగలిగేది | You can | आप कर सकते हैं:
📸 మందు ఫోటో పంపండి | Send medicine photo | दवा की फोटो भेजें
💊 మందు పేరు టైప్ చేయండి | Type medicine name | दवा का नाम टाइप करें
🔵 మాత్ర రంగు వర్ణించండి | Describe tablet color | गोली का रंग बताएं

*ఉదాహరణ | Example | उदाहरण:* Paracetamol"""

PHOTO_MESSAGE = """📸 *ఫోటో అందింది! | Photo received! | फोटो मिली!*

మందు పేరు కూడా టైప్ చేయండి.
Please also type the medicine name.
दवा का नाम भी टाइप करें। 💊"""

ERROR_MESSAGE = "⚠️ సేవ తాత్కాలికంగా అందుబాటులో లేదు | Service unavailable | सेवा उपलब्ध नहीं. కొద్దిసేపు తర్వాత మళ్ళీ ప్రయత్నించండి 🙏"

GREETINGS = {
    "hi", "hello", "hey", "హాయ్", "హలో", "నమస్కారం",
    "నమస్తే", "namaste", "start", "help", "hai", "helo"
}

# ─────────────────────────────────────────
#  AI Helper — single message, all 3 languages
# ─────────────────────────────────────────
def build_medicine_context(medicine_name: str, db_info: dict | None) -> str:
    if db_info:
        composition = db_info["composition1"]
        if db_info["composition2"]:
            composition += f" + {db_info['composition2']}"
        return f"""Medicine details from Indian database:
Name: {db_info['name']}
Composition: {composition}
Manufacturer: {db_info['manufacturer']}
Type: {db_info['type']}
Pack size: {db_info['pack_size']}
Price: ₹{db_info['price']}

Give complete information based on this composition."""
    else:
        return f"""Medicine name: {medicine_name}
This is likely an Indian brand name. Identify the composition and give complete information."""

def ask_ai_single(user_content: str) -> str | None:
    """Single Groq call — returns all 3 languages in one message."""
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SINGLE_PROMPT},
                {"role": "user",   "content": user_content}
            ],
            max_tokens=700,
            temperature=0.3
        )
        reply = response.choices[0].message.content.strip()
        log.info("AI replied successfully")
        return reply
    except Exception as e:
        log.error(f"Groq error: {type(e).__name__}: {e}")
        return None

# ─────────────────────────────────────────
#  WhatsApp Message Sender
# ─────────────────────────────────────────
def send_whatsapp_message(to: str, body: str):
    try:
        twilio_client.messages.create(
            from_=TWILIO_NUMBER,
            to=to,
            body=body
        )
        log.info(f"Message sent to {to}")
    except Exception as e:
        log.error(f"Failed to send message: {e}")

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

    # ── Greeting ──────────────────────────
    if incoming_msg.lower() in GREETINGS:
        send_whatsapp_message(sender, WELCOME_MESSAGE)
        return str(resp)

    # ── Photo received ────────────────────
    if media_url and "image" in media_type:
        send_whatsapp_message(sender, PHOTO_MESSAGE)
        return str(resp)

    # ── Medicine query ────────────────────
    if incoming_msg:
        db_info = search_medicine(incoming_msg)
        if db_info:
            log.info(f"Found in DB: {db_info['name']} | {db_info['composition1']}")
        else:
            log.info(f"Not in DB — using AI knowledge for: {incoming_msg}")

        context = build_medicine_context(incoming_msg, db_info)
        reply   = ask_ai_single(context)

        send_whatsapp_message(sender, reply if reply else ERROR_MESSAGE)
        return str(resp)

    # ── Empty message ─────────────────────
    send_whatsapp_message(
        sender,
        "మందు పేరు లేదా ఫోటో పంపండి | Type medicine name | दवा का नाम टाइप करें 💊"
    )
    return str(resp)

# ─────────────────────────────────────────
#  Health Check
# ─────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health_check():
    db_status = len(medicine_df) if medicine_df is not None else 0
    return {
        "status":           "ok",
        "bot":              "MedScan",
        "version":          "5.0",
        "medicines_loaded": db_status
    }, 200

# ─────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info(f"🚀 Starting MedScan v5.0 on port {port}")
    app.run(host="0.0.0.0", port=port)