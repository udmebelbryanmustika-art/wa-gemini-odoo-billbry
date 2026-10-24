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


# Public policies for the WhatsApp service.
@app.route("/privacy", methods=["GET"])
def privacy_policy():
    return "<!doctype html>\n<html lang=\"id\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>Kebijakan Privasi — UD BILLBRY MEBEL</title>\n<style>body{font:17px/1.7 system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 24px;color:#222}h1,h2{line-height:1.3}a{color:#754124}footer{border-top:1px solid #ddd;margin-top:32px;padding-top:16px}</style>\n<main><h1>Kebijakan Privasi</h1><p>UD BILLBRY MEBEL · Berlaku mulai 24 Oktober 2026</p>\n<h2>Data dan tujuan penggunaan</h2>\n<p>Dalam layanan konsultasi melalui WhatsApp, kami menggunakan nomor telepon, nama profil yang tersedia, serta isi pesan yang Anda kirim untuk memahami kebutuhan furnitur, menjawab pertanyaan, dan menindaklanjuti permintaan Anda. Informasi tambahan, seperti alamat pengiriman atau spesifikasi pesanan, digunakan bila diperlukan untuk permintaan tersebut.</p>\n<h2>Layanan yang memproses data</h2>\n<p>Komunikasi WhatsApp diproses melalui layanan WhatsApp/Meta. Server layanan menggunakan Vercel. Ketika balasan AI diaktifkan, isi pesan dapat dikirim ke Google Gemini untuk menyusun jawaban. Ketika integrasi CRM diaktifkan, nomor dan pesan dapat dicatat dalam Odoo untuk tindak lanjut admin. Masing-masing penyedia juga memiliki kebijakan privasinya sendiri.</p>\n<p>Hindari mengirim kata sandi, PIN, OTP, atau informasi pribadi sensitif yang tidak diperlukan untuk konsultasi. Jawaban AI dapat keliru; harga custom, ketersediaan, ongkir, dan jadwal pengerjaan perlu dikonfirmasi kepada admin.</p>\n<h2>Penyimpanan dan akses</h2>\n<p>Data diproses untuk pelayanan pelanggan dan operasional pesanan. Penyimpanan dapat mencakup percakapan, catatan CRM ketika diaktifkan, dan catatan teknis layanan. Akses internal dibatasi kepada pihak yang memerlukannya untuk melayani permintaan. Permintaan penghapusan ditinjau dengan mempertimbangkan data yang masih diperlukan untuk pesanan, pencatatan transaksi, atau kewajiban yang berlaku.</p>\n<h2>Permintaan terkait data</h2>\n<p>Anda dapat meminta penjelasan, koreksi, atau penghapusan data melalui email <a href=\"mailto:udmebelbryanmustika@gmail.com\">udmebelbryanmustika@gmail.com</a>. Cantumkan nomor WhatsApp terkait dan jenis permintaan. Kami mungkin meminta verifikasi seperlunya agar data tidak diberikan kepada pihak lain. Jangan mengirim kata sandi atau OTP.</p>\n<p>Lihat <a href=\"/data-deletion\">petunjuk penghapusan data</a>. Kebijakan ini dapat diperbarui ketika cara kerja layanan berubah.</p>\n<footer><strong>UD BILLBRY MEBEL</strong><br>Jl. Irian, Ngasinan, Jetis, Ponorogo<br><a href=\"https://mebel.billbry.id/\">mebel.billbry.id</a></footer></main></html>\n", 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/data-deletion", methods=["GET"])
def data_deletion_policy():
    return "<!doctype html>\n<html lang=\"id\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>Penghapusan Data — UD BILLBRY MEBEL</title>\n<style>body{font:17px/1.7 system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 24px;color:#222}h1,h2{line-height:1.3}a{color:#754124}footer{border-top:1px solid #ddd;margin-top:32px;padding-top:16px}</style>\n<main><h1>Petunjuk Penghapusan Data</h1><p>UD BILLBRY MEBEL · Berlaku mulai 24 Oktober 2026</p>\n<p>Untuk meminta penghapusan data dari layanan konsultasi WhatsApp UD BILLBRY MEBEL:</p>\n<ol><li>Kirim email ke <a href=\"mailto:udmebelbryanmustika@gmail.com\">udmebelbryanmustika@gmail.com</a> dengan subjek <strong>Permintaan Penghapusan Data WhatsApp</strong>.</li>\n<li>Cantumkan nomor WhatsApp yang digunakan untuk menghubungi kami dan keterangan singkat data yang ingin dihapus.</li>\n<li>Admin akan meninjau permintaan dan, bila diperlukan, memverifikasi bahwa nomor tersebut milik Anda. Jangan mengirim kata sandi, PIN, atau OTP.</li></ol>\n<p>Penghapusan ditangani secara manual. Admin akan menjelaskan hasil peninjauan, termasuk bila sebagian data masih diperlukan untuk pesanan, transaksi, atau kewajiban yang berlaku. Halaman ini tidak menghapus data secara otomatis.</p>\n<p>Permintaan ini berlaku untuk data yang dikelola UD BILLBRY MEBEL. Salinan pada perangkat Anda atau data yang dikelola secara mandiri oleh penyedia layanan mengikuti pengaturan dan kebijakan penyedia tersebut.</p>\n<p><a href=\"/privacy\">Kebijakan privasi</a></p><footer>UD BILLBRY MEBEL<br>Jl. Irian, Ngasinan, Jetis, Ponorogo</footer></main></html>\n", 200, {"Content-Type": "text/html; charset=utf-8"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
