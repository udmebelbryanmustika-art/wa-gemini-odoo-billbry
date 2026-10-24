# UD BILLBRY MEBEL — WhatsApp / Gemini / Odoo

## Status perubahan

Perbaikan pada cabang `fix/whatsapp-api-diagnostics`. Diajukan sebagai draft pull request; belum digabung
ke main dan belum diterapkan pada produksi. Semua pengujian lokal menggunakan data tiruan; token, nomor,
Gemini, dan Odoo produksi belum divalidasi oleh pengujian ini.

## Konfigurasi Vercel (Production)

Pertahankan nilai rahasia hanya di Vercel. Jangan masukkan ke kode/repo/log/chat.

| Variable | Kegunaan |
| --- | --- |
| META_ACCESS_TOKEN | Token akses aplikasi WhatsApp yang berwenang |
| META_PHONE_ID | ID nomor produksi mebel; cocokkan dengan Meta Manager |
| META_API_VERSION | Opsional, default v25.0 |
| META_APP_SECRET | App Secret untuk validasi tanda tangan webhook Meta |
| VERIFY_TOKEN | Token verifikasi webhook; wajib eksplisit, tanpa default publik |
| GEMINI_API_KEY | Kunci Gemini |
| GEMINI_MODEL | Opsional, default gemini-flash-latest |
| DIAGNOSTIC_TOKEN | Rahasia terpisah untuk endpoint diagnosis read-only |
| ODOO_CRM_ENABLED | Default tidak aktif; set true hanya sesudah uji koneksi dan pemetaan |
| ODOO_URL | HTTPS database Odoo yang benar; jangan mengasumsikan domain usaha lain |
| ODOO_DB | Nama database |
| ODOO_API_KEY | API key pengguna teknis yang hanya berwenang atas perusahaan mebel |
| ODOO_COMPANY_ID | ID perusahaan dengan nama persis UD BILLBRY MEBEL |

`render.yaml` lama mengandung domain bor sumur. Nilai tersebut dihapus dari
konfigurasi contoh. Pengaturan environment Vercel yang sudah ada tidak diubah.

## Endpoint

- `GET /`: memastikan proses server hidup; bukan bukti API aktif.
- `GET /health`: hanya menampilkan nama konfigurasi yang belum diisi; tidak
  memanggil layanan berbayar dan tidak mengklaim kredensial valid.
- `GET /admin/meta-status`: memerlukan header `Authorization: Bearer <DIAGNOSTIC_TOKEN>`.
  Memanggil API Meta dengan token yang tersimpan di server. Hanya membaca metadata
  nomor; tidak mengirim pesan, mendaftarkan nomor, mengganti PIN, atau migrasi.
  Status verifikasi OTP bukan bukti seluruh registrasi Cloud API selesai.
- `GET /webhook`: mengembalikan challenge hanya bila token yang dikonfigurasi cocok.
  Membuka URL tanpa parameter memang menghasilkan HTTP 403.
- `POST /webhook`: memerlukan tanda tangan Meta, memfilter Phone ID, memproses semua
  pesan teks di payload, dan hanya menghitung pengiriman berhasil bila Meta
  mengembalikan ID pesan. Log hanya berisi kategori kegagalan dan kode numerik.

## CRM — harus ditinjau sebelum aktivasi

Konektor awal memakai Odoo JSON-2 (Odoo 19+); versi API instance produksi belum
terkonfirmasi. Mode awal membuat satu lead per pesan masuk. Nama perusahaan
diverifikasi sebelum penulisan dan context dibatasi ke ODOO_COMPANY_ID. Pencarian
message ID mengurangi duplikasi lead pada retry berurutan, tetapi tidak menjamin
keunikan pada request bersamaan. Jangan aktifkan sampai mode lead per pesan
serta hak akses pengguna teknis disetujui dan uji database mebel selesai.

Kode ini masih memproses webhook secara sinkron. Untuk traffic produksi,
implementasikan antrean persisten dan pencatatan message ID dengan constraint
unik. Retry Meta atas kegagalan/timeout atau batch yang berhasil sebagian bisa
mengulang balasan yang sudah terkirim; memori proses Vercel tidak boleh dipakai
sebagai satu-satunya mekanisme deduplikasi. Jangan terbitkan aplikasi Meta untuk
traffic pelanggan sampai jalur ini siap dan diuji.

## Verifikasi dan penerapan

1. Sambungkan akses tulis GitHub; push cabang perbaikan, bukan main, untuk review.
2. Lengkapi konfigurasi baru pada lingkungan uji. Jangan deploy main sebelum
   META_APP_SECRET dan VERIFY_TOKEN terisi; webhook baru fail closed bila kosong.
3. Jalankan `python -m pytest -q`. Tidak memakai kredensial produksi.
4. Uji preview: health, verifikasi webhook, payload bertanda tangan dan diagnosis
   Meta. Validasi hasil registrasi nomor secara terpisah dari status deployment.
5. Lengkapi antrean/deduplikasi persisten dan uji CRM mebel sebelum aktivasi live.
6. Tinjau persyaratan penerbitan aplikasi serta pembayaran Meta, lalu lakukan
   uji pesan end-to-end yang tujuan dan penerimanya telah ditentukan pengguna.

SDK Gemini diperbarui ke `google-genai`; error upstream tidak lagi ditutupi
sebagai status sukses. Jam/alamat dan aturan harga custom diperbaiki.
