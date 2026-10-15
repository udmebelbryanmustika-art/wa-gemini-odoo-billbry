import os
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify

app = Flask(__name__)

# Konfigurasi Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Konfigurasi Odoo & Webhook Token
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "ud_billbry_mebel_123")

@app.route("/", methods=["GET"])
def home():
    return "Server Bot WA UD Billbry Mebel Aktif!", 200

# Endpoint GET untuk Verifikasi Webhook Meta
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

# Endpoint POST untuk Menerima Pesan WhatsApp
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    # Menangani payload dari WhatsApp Cloud API Meta
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        
        if not messages:
            return jsonify({"status": "ignored", "reason": "No messages found"}), 200

        message_obj = messages[0]
        user_message = message_obj.get("text", {}).get("body", "")
        sender_number = message_obj.get("from", "")
    except Exception:
        user_message = data.get("message", "")
        sender_number = data.get("sender", "")

    if not user_message:
        return jsonify({"status": "error", "message": "Pesan kosong"}), 400

    prompt = f"""
    Anda adalah asisten AI customer service untuk toko meubel "UD Billbry Mebel".
    Tugas Anda adalah melayani pelanggan WhatsApp dengan ramah, sopan, dan informatif.

    Pesan pelanggan: {user_message}

    Berikan balasan yang singkat, jelas, dan membantu.
    """

    try:
        response = model.generate_content(prompt)
        ai_reply = response.text
    except Exception as e:
        ai_reply = "Mohon maaf, saat ini sistem AI kami sedang mengalami gangguan. Silakan coba beberapa saat lagi."

    return jsonify({
        "status": "success",
        "reply": ai_reply,
        "sender": sender_number
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
