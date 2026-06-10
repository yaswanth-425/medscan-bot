import os
import requests
import base64
import logging
from flask import Flask, request
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

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")

if not GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY is not set. Add it to Railway Variables.")

client = Groq(api_key=GROQ_API_KEY)
log.info("✅ MedScan bot started successfully.")

# ─────────────────────────────────────────
#  Prompts & Messages
# ─────────────────────────────────────────
SYSTEM_PROMPT = """You are MedScan, an expert Indian medicine assistant.
You help Indian patients understand their medicines clearly and safely.

STRICT RULE — ALWAYS reply in ALL 3 languages together in this exact order:
1. Telugu first
2. English second
3. Hindi third

When a medicine name is received, reply in this EXACT detailed format:

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
- [how to take detail 1 in Telugu]
- [how to take detail 2 in Telugu]

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
- [timing detail 1 in English]
- [timing detail 2 in English]

🍽️ *How to take:*
- [how to take detail 1 in English]
- [how to take detail 2 in English]

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
- [timing detail 1 in Hindi]
- [timing detail 2 in Hindi]

🍽️ *कैसे लें:*
- [how to take detail 1 in Hindi]
- [how to take detail 2 in Hindi]

⚠️ *चेतावनी:*
- [warning 1 in Hindi]
- [warning 2 in Hindi]
- [warning 3 in Hindi]

━━━━━━━━━━━━━━━━━━━━━━
_సందేహాలు ఉంటే అడగండి | Ask doubts | सवाल पूछें_ 💊

For color/shape description — ask follow-up questions in all 3 languages:
→ మాత్రపై అక్షరాలు ఉన్నాయా? | Any letters on tablet? | गोली पर कोई अक्षर है?
→ ఏ సమస్యకు ఇచ్చారు? | Given for what problem? | किस बीमारी के लिए दी?

For serious symptoms always add:
డాక్టర్‌ను సంప్రదించండి | Consult a doctor | डॉक्टर से मिलें"""


ERROR_MESSAGE = "⚠️ సేవ తాత్కాలికంగా అందుబాటులో లేదు. కొద్దిసేపు తర్వాత మళ్ళీ ప్రయత్నించండి. 🙏"

EMPTY_MESSAGE = "మందు పేరు లేదా ఫోటో పంపండి 💊"

GREETINGS = {"hi", "hello", "hey", "నమస్కారం", "హలో", "నమస్తే", "start", "help", "హాయ్"}

# ─────────────────────────────────────────
#  AI Helper
# ─────────────────────────────────────────
def ask_ai(user_message: str) -> str | None:
    """Send message to Groq and return Telugu response."""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Give complete information about this medicine in Telugu, English and Hindi all together: {user_message}"}
            ],
            max_tokens=2000,
            temperature=0.3
        )
        reply = response.choices[0].message.content.strip()
        log.info(f"AI replied successfully for: {user_message[:30]}")
        return reply

    except Exception as e:
        log.error(f"Groq API error: {type(e).__name__}: {e}")
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
        msg.body(PHOTO_RECEIVED_MESSAGE)
        return str(resp)

    # ── Medicine query ────────────────────
    if incoming_msg:
        reply = ask_ai(incoming_msg)
        msg.body(reply if reply else ERROR_MESSAGE)
        return str(resp)

    # ── Empty message ─────────────────────
    msg.body(EMPTY_MESSAGE)
    return str(resp)

# ─────────────────────────────────────────
#  Health Check
# ─────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health_check():
    return {"status": "ok", "bot": "MedScan", "version": "2.0"}, 200

# ─────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info(f"🚀 Starting MedScan on port {port}")
    app.run(host="0.0.0.0", port=port)