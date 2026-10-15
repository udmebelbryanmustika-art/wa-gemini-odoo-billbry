import os
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify

app = Flask(__name__)

# Konfigurasi Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Konfigurasi WhatsApp API Meta
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_PHONE_ID = os.getenv("META_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "ud_billbry_mebel_123")

# Konfigurasi Odoo (Siap digunakan untuk integrasi selanjutnya)
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")

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

# Endpoint POST untuk Menerima & Membalas Pesan WhatsApp
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    # 1. Menangkap pesan masuk dari pelanggan
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
        return jsonify({"status": "ignored", "reason": "Format bukan pesan teks"}), 200

    if not user_message:
        return jsonify({"status": "error", "message": "Pesan kosong"}), 400

    # 2. Memberikan instruksi ke AI (Prompt disesuaikan dengan data website)
    info_website = """
    INFORMASI TOKO UNTUK MENJAWAB PELANGGAN:
    1. Website Resmi: Katalog lengkap dan portofolio kami ada di https://mebel.billbry.id
    2. Produk & Layanan: Kami menyediakan berbagai kebutuhan mebel berkualitas dan menerima pesanan mebel kustom (custom) sesuai permintaan.
    3. Lokasi: Kami beroperasi di Ponorogo, Jawa Timur.
    4. Jam Operasional: Senin - Sabtu (08:00 - 16:00 WIB).
    """

    prompt = f"""
    Anda adalah asisten AI customer service resmi untuk toko meubel "UD Billbry Mebel".
    Tugas Anda adalah melayani pelanggan WhatsApp dengan ramah, sopan, dan profesional layaknya seorang pramuniaga yang andal.

    Berikut adalah informasi acuan yang HARUS Anda gunakan sebagai dasar untuk menjawab:
    {info_website}

    Aturan menjawab:
    - Selalu berikan balasan yang ringkas, jelas, dan sangat membantu.
    - Jika pelanggan menanyakan produk, selalu arahkan atau rekomendasikan mereka dengan sopan untuk melihat katalog lengkap di https://mebel.billbry.id
    - Jika Anda tidak tahu jawabannya berdasarkan informasi di atas, sampaikan dengan sopan bahwa Anda akan meneruskan pesan ini ke tim admin kami.

    Pesan pelanggan: "{user_message}"
    """

    try:
        response = model.generate_content(prompt)
        ai_reply = response.text
    except Exception as e:
        ai_reply = "Mohon maaf, saat ini sistem AI kami sedang mengalami penyesuaian. Silakan tinggalkan pesan Anda."

    # 3. Mengirimkan balasan AI kembali ke HP Pelanggan via Meta API
    if META_ACCESS_TOKEN and META_PHONE_ID:
        whatsapp_url = f"https://graph.facebook.com/v18.0/{META_PHONE_ID}/messages"
        headers = {
            "Authorization": f"Bearer {META_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": sender_number,
            "type": "text",
            "text": {"body": ai_reply}
        }
        # Tembak API Meta
        requests.post(whatsapp_url, headers=headers, json=payload)

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
