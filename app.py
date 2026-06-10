import os
import requests
import base64
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
print(f"Gemini client loaded. API key present: {bool(os.environ.get('GEMINI_API_KEY'))}")

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


def ask_gemini(prompt_text, image_data=None, mime_type="image/jpeg"):
    try:
        if image_data:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=[
                    types.Part.from_bytes(data=image_data, mime_type=mime_type),
                    types.Part.from_text(text=prompt_text)
                ]
            )
        else:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt_text
            )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini error: {type(e).__name__}: {str(e)}")
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
            image_data = requests.get(
                media_url,
                auth=(
                    os.environ.get("TWILIO_ACCOUNT_SID"),
                    os.environ.get("TWILIO_AUTH_TOKEN")
                )
            ).content
            prompt = SYSTEM_PROMPT + "\nఈ మందు ఫోటో చూసి తెలుగులో వివరించండి:"
            reply = ask_gemini(prompt, image_data=image_data, mime_type=media_type)

        elif incoming_msg:
            prompt = SYSTEM_PROMPT + f"\n\nUser message: {incoming_msg}\n\nతెలుగులో జవాబు ఇవ్వండి:"
            reply = ask_gemini(prompt)

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