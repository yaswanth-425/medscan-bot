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

GROQ_API_KEY      = os.environ.get("GROQ_API_KEY")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER      = "whatsapp:+14155238886"

if not GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY is not set.")

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
        match = medicine_df[medicine_df["name_lower"] == query_lower]
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

load_medicine_database()

# ─────────────────────────────────────────
#  Prompts & Messages
# ─────────────────────────────────────────
TELUGU_PROMPT = """You are MedScan, an expert Indian medicine assistant.
Reply ONLY in Telugu language.

For the given medicine, reply in this format:
🇮🇳 *MedScan — మందు సమాచారం*
━━━━━━━━━━━━━━━━━━━

💊 *మందు పేరు:* [name]
🏭 *తయారీదారు:* [manufacturer]

🔍 *దేనికి వాడతారు:*
• [use 1]
• [use 2]
• [use 3]

⏰ *ఎప్పుడు తీసుకోవాలి:*
• [timing 1]
• [timing 2]

🍽️ *ఎలా తీసుకోవాలి:*
• [how to take]

⚠️ *జాగ్రత్తలు:*
• [warning 1]
• [warning 2]

డాక్టర్‌ను సంప్రదించండి అవసరమైతే 🙏"""

ENGLISH_PROMPT = """You are MedScan, an expert Indian medicine assistant.
Reply ONLY in English language.

For the given medicine, reply in this format:
🇬🇧 *MedScan — Medicine Info*
━━━━━━━━━━━━━━━━━━━

💊 *Medicine:* [name]
🏭 *Manufacturer:* [manufacturer]

🔍 *Used for:*
• [use 1]
• [use 2]
• [use 3]

⏰ *When to take:*
• [timing 1]
• [timing 2]

🍽️ *How to take:*
• [how to take]

⚠️ *Warnings:*
• [warning 1]
• [warning 2]

Consult a doctor if symptoms are serious 🙏"""

HINDI_PROMPT = """You are MedScan, an expert Indian medicine assistant.
Reply ONLY in Hindi language.

For the given medicine, reply in this format:
🇮🇳 *MedScan — दवा की जानकारी*
━━━━━━━━━━━━━━━━━━━

💊 *दवा का नाम:* [name]
🏭 *निर्माता:* [manufacturer]

🔍 *उपयोग:*
• [use 1]
• [use 2]
• [use 3]

⏰ *कब लें:*
• [timing 1]
• [timing 2]

🍽️ *कैसे लें:*
• [how to take]

⚠️ *चेतावनी:*
• [warning 1]
• [warning 2]

गंभीर लक्षण होने पर डॉक्टर से मिलें 🙏"""

WELCOME_MESSAGE = """🇮🇳 *MedScan కి స్వాగతం | Welcome | स्वागत है*

మందుల సమాచారం తెలుగు, English & Hindi లో పొందండి.

మీరు చేయగలిగేది:
📸 మందు ఫోటో పంపండి
💊 మందు పేరు టైప్ చేయండి
🔵 తెలుపు గుండ్రం మాత్ర అని వర్ణించండి

*ఉదాహరణ:* Paracetamol"""

PHOTO_MESSAGE = """📸 *ఫోటో అందింది! | Photo received!*

మందు పేరు కూడా టైప్ చేయండి.
Please also type the medicine name. 💊"""

ERROR_MESSAGE = "⚠️ సేవ తాత్కాలికంగా అందుబాటులో లేదు. కొద్దిసేపు తర్వాత మళ్ళీ ప్రయత్నించండి 🙏"

GREETINGS = {"hi", "hello", "hey", "నమస్కారం", "హలో", "నమస్తే", "start", "help", "హాయ్", "namaste", "hai"}

# ─────────────────────────────────────────
#  AI Helper — separate call per language
# ─────────────────────────────────────────
def ask_ai_in_language(user_content: str, system_prompt: str) -> str | None:
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content}
            ],
            max_tokens=500,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"Groq error: {type(e).__name__}: {e}")
        return None

def build_medicine_context(medicine_name: str, db_info: dict | None) -> str:
    if db_info:
        composition = db_info["composition1"]
        if db_info["composition2"]:
            composition += f" + {db_info['composition2']}"
        return f"""Medicine: {db_info['name']}
Composition: {composition}
Manufacturer: {db_info['manufacturer']}
Type: {db_info['type']}
Pack: {db_info['pack_size']}
Price: ₹{db_info['price']}"""
    else:
        return f"Medicine name: {medicine_name} (Indian brand — use your knowledge)"

# ─────────────────────────────────────────
#  Send multiple WhatsApp messages
# ─────────────────────────────────────────
def send_whatsapp_message(to: str, body: str):
    try:
        twilio_client.messages.create(
            from_=TWILIO_NUMBER,
            to=to,
            body=body
        )
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

    # Always return empty 200 response to Twilio immediately
    # Then send replies using Twilio API directly
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
            log.info(f"Not in DB, using AI for: {incoming_msg}")

        context = build_medicine_context(incoming_msg, db_info)

        # Send Telugu reply
        telugu_reply = ask_ai_in_language(context, TELUGU_PROMPT)
        if telugu_reply:
            send_whatsapp_message(sender, telugu_reply)
            log.info("Telugu message sent")

        # Send English reply
        english_reply = ask_ai_in_language(context, ENGLISH_PROMPT)
        if english_reply:
            send_whatsapp_message(sender, english_reply)
            log.info("English message sent")

        # Send Hindi reply
        hindi_reply = ask_ai_in_language(context, HINDI_PROMPT)
        if hindi_reply:
            send_whatsapp_message(sender, hindi_reply)
            log.info("Hindi message sent")

        if not telugu_reply and not english_reply and not hindi_reply:
            send_whatsapp_message(sender, ERROR_MESSAGE)

        return str(resp)

    # ── Empty message ─────────────────────
    send_whatsapp_message(sender, "మందు పేరు లేదా ఫోటో పంపండి | Type medicine name | दवा का नाम टाइप करें 💊")
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
        "version": "4.0",
        "medicines_loaded": db_status
    }, 200

# ─────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info(f"🚀 Starting MedScan v4.0 on port {port}")
    app.run(host="0.0.0.0", port=port)
