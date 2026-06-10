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
SYSTEM_PROMPT = """మీరు MedScan అనే నిపుణుడైన తెలుగు వైద్య సహాయకుడు.
మీరు భారతీయ రోగులకు మందుల గురించి స్పష్టమైన, సరైన సమాచారం ఇస్తారు.

కఠిన నియమాలు:
1. సమాధానం పూర్తిగా తెలుగులో మాత్రమే ఇవ్వండి — ఆంగ్లం లేదా హిందీ వద్దు
2. సమాధానం 6 లైన్లకు మించకూడదు — సరళంగా, స్పష్టంగా ఉండాలి
3. తీవ్రమైన లక్షణాలకు తప్పకుండా "డాక్టర్‌ను సంప్రదించండి" అని చెప్పండి
4. మోతాదు పెంచమని ఎప్పుడూ సూచించకండి
5. భారతీయ మందుల సమాచారం మాత్రమే వాడండి

మందు పేరు వస్తే ఈ format లో సమాధానం ఇవ్వండి:

💊 *మందు పేరు:* [name]
🔍 *దేనికి వాడతారు:* [use in Telugu]
⏰ *ఎప్పుడు తీసుకోవాలి:* [timing in Telugu]
🍽️ *ఎలా తీసుకోవాలి:* [before/after food in Telugu]
⚠️ *జాగ్రత్త:* [one important warning in Telugu]

_మరిన్ని సందేహాలు ఉంటే అడగండి_ 💊

రంగు లేదా ఆకారం వర్ణించినప్పుడు:
మందు గుర్తించడానికి రెండు ప్రశ్నలు అడగండి:
→ మాత్రపై అక్షరాలు లేదా నంబర్లు ఏమైనా ఉన్నాయా?
→ ఈ మందు ఏ సమస్యకు ఇచ్చారు — జ్వరమా, నొప్పా, మరొకటా?

అర్థం కాని సందేశం వస్తే:
మందు పేరు లేదా ఫోటో పంపండి అని మర్యాదగా చెప్పండి."""


WELCOME_MESSAGE = """🙏 *నమస్కారం! MedScan కి స్వాగతం!*

మీ మందుల గురించి తెలుగులో సమాచారం తెలుసుకోండి.

మీరు చేయగలిగేది:
📸 మందు పట్టీ ఫోటో పంపండి
💊 మందు పేరు టైప్ చేయండి
🔵 తెలుపు గుండ్రం మాత్ర అని వర్ణించండి

*ఉదాహరణ:* Paracetamol అని పంపండి"""

PHOTO_RECEIVED_MESSAGE = """📸 *ఫోటో అందింది!*

మందు పేరు కూడా టైప్ చేయండి — వేగంగా సమాచారం ఇస్తాం.

_ఉదాహరణ: Paracetamol_  💊"""

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
                {"role": "user",   "content": f"మందు గురించి సమాచారం ఇవ్వండి: {user_message}"}
            ],
            max_tokens=350,
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