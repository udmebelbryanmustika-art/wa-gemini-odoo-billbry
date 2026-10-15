import os
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify

app = Flask(__name__)

# Konfigurasi Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Konfigurasi Odoo
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")

@app.route("/", methods=["GET"])
def home():
    return "Server Bot WA UD Billbry Mebel Aktif!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
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
