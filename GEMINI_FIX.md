# Pemulihan Gemini

Dasar perubahan: log produksi 24 Oktober 2026 menunjukkan daftar model HTTP 200, tetapi generateContent HTTP 503 pada primary dan model pengganti. Akar gangguan di sisi penyedia belum dapat dipastikan; perubahan ini tidak menjamin layanan penyedia selalu tersedia.

- Maksimal tiga permintaan: primary, satu retry primary, lalu GEMINI_FALLBACK_MODEL (default gemini-2.5-flash-lite).
- Hanya gangguan sementara/transport yang dicoba ulang. HTTP 400/401/403/404, output diblokir, dan respons kosong langsung gagal.
- Timeout connect 3 detik/read 10 detik per percobaan, jeda total 1,5 detik. Batas ini bukan tenggat total ketat. Pastikan batas durasi deployment memadai; pemrosesan webhook sinkron masih memerlukan antrean untuk trafik publik yang andal.
- Log berisi status/kode aman, tanpa API key, isi pelanggan atau respons mentah penyedia.
- POST /admin/gemini-test memerlukan Authorization: Bearer DIAGNOSTIC_TOKEN. Input selalu sintetis dan tetap; tidak mengirim WhatsApp dan tidak menulis Odoo. GET tidak menjalankan model.
- GEMINI_FALLBACK_MODEL kosong menonaktifkan perpindahan model (percobaan terakhir memakai primary).

Validasi lokal: 11 tes lulus, termasuk pemulihan 503, kegagalan permanen, model cadangan, output diblokir dan otorisasi probe.

Belum di-deploy dan belum diuji memakai key produksi. Jangan menyatakan Gemini pulih sebelum probe live sukses. Perubahan ini tidak mengubah status integrasi Odoo atau menyediakan kotak masuk admin.
