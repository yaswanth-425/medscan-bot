import os
import requests
import base64
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
print(f"Groq client loaded. API key present: {bool(os.environ.get('GROQ_API_KEY'))}")

SYSTEM_PROMPT = """మీరు MedScan అనే తెలుగు వైద్య సహాయకుడు.
మీరు భారతీయ రోగులకు మందుల గురించి సహాయం చేస్తారు.

నియమాలు:
1. ALWAYS respond in Telugu script only
2. Keep response under 6 lines
3. Always say డాక్టర్‌ను సంప్రదించండి for serious symptoms

మందు పేరు వస్తే ఈ format లో చెప్పండి:
💊 మందు పేరు: [name]
🔍 దేనికి వాడతారు: [use in Telugu]
⏰ ఎప్పుడు తీసుకోవాలి: [timing in Telugu]
🍽️ తినడానికి ముందు/తర్వాత: [before/after food]
⚠️ జాగ్రత్త: [one warning in Telugu]
మరిన్ని సందేహాలు ఉంటే అడగండి 💊

రంగు/ఆకారం వస్తే:
1. మాత్రపై అక్షరాలు ఏమైనా ఉన్నాయా అని అడగండి
2. ఏ సమస్యకు ఇచ్చారు అని అడగండి

ఫోటో వస్తే మందు పేరు చదివి పై format లో చెప్పండి."""


def get_welcome_message():
    return """🙏 నమస్కారం! MedScan కి స్వాగతం!

మీ మందుల గురించి తెలుగులో సమాచారం పొందండి.

మీరు చేయగలిగేది:
📸 మందు ఫోటో పంపండి
💊 మందు పేరు టైప్ చేయండి
🔵 తెలుపు గుండ్రం మాత్ర అని వర్ణించండి

ఉదాహరణ: Paracetamol అని పంపండి"""


def ask_ai(prompt_text, image_b64=None, mime_type="image/jpeg"):
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text}
        ]

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"Groq error: {type(e).__name__}: {str(e)}")
        return None


@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    incoming_msg = request.form.get("Body", "").strip()
    media_url = request.form.get("MediaUrl0", None)
    media_type = request.form.get("MediaContentType0", "")

    resp = MessagingResponse()
    msg = resp.message()

    greetings = ["hi", "hello", "నమస్కారం", "హలో", "start", "help"]
    if incoming_msg.lower() in greetings:
        msg.body(get_welcome_message())
        return str(resp)

    try:
        if media_url and "image" in media_type:
            # For images, download and ask Gemini (Groq doesn't support images)
            # Fall back to asking user to type the medicine name
            msg.body("📸 ఫోటో అందింది! మందు పేరు కూడా టైప్ చేయండి — మరింత వేగంగా సమాచారం ఇస్తాం 💊")
            return str(resp)

        elif incoming_msg:
            prompt = f"మందు గురించి తెలుగులో చెప్పండి: {incoming_msg}"
            reply = ask_ai(prompt)
        else:
            msg.body("మందు పేరు లేదా ఫోటో పంపండి 💊")
            return str(resp)

        if reply:
            msg.body(reply)
        else:
            msg.body("సేవ తాత్కాలికంగా అందుబాటులో లేదు. కొద్దిసేపు తర్వాత మళ్ళీ ప్రయత్నించండి 🙏")

    except Exception as e:
        print(f"Error: {str(e)}")
        msg.body("సేవ తాత్కాలికంగా అందుబాటులో లేదు. కొద్దిసేపు తర్వాత మళ్ళీ ప్రయత్నించండి 🙏")

    return str(resp)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)