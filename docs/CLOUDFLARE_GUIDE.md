# Panduan Konfigurasi Cloudflare Tunnel
(Untuk KBLI 2020 Matcher v3.0)

Berdasarkan setup Cloudflare Tunnel yang Anda gunakan, berikut adalah konfigurasi yang **sudah benar** dan rekomendasi optimasi.

## 1. Konfigurasi Tunnel (Sudah Benar) ✅

Pastikan setting di dashboard Cloudflare Zero Trust seperti ini:

- **Public Hostname:** `kbli2020.alwansegeramutasi.my.id`
- **Service Type:** `HTTP`
- **URL:** `localhost:3001` (atau `kbli2020-frontend:80` jika pakai Docker network nama)

> **Penjelasan:** Kita hanya perlu mengekspos port Frontend (3001). Request ke API backend (8000) akan ditangani secara internal oleh Nginx yang ada di dalam container frontend, jadi **TIDAK PERLU** membuat tunnel terpisah untuk port 8000.

---

## 2. Optimasi (Caching & Speed) ⚡

Agar website lebih cepat diakses user, aktifkan fitur caching untuk file statis (CSS, JS, Images), tapi **JANGAN** cache API request.

Masuk ke menu **Caching > Cache Rules** di dashboard Cloudflare:

### Rule 1: Bypass Cache for API (Wajib)
Buat rule baru agar pencarian selalu fresh (tidak nyangkut data lama):
- **Rule Name:** `Bypass API`
- **If Incoming Request Matches:**
  - URI Path contains `/search`
  - OR URI Path contains `/lookup`
  - OR URI Path contains `/autocomplete`
- **Cache Eligibility:** `Bypass cache`
- **Deploy**

### Rule 2: Cache Static Files
Cloudflare otomatis melakukan ini, tapi pastikan **Rocket Loader** aktif di menu **Speed > Optimization** untuk mempercepat loading JS.

---

## 3. Keamanan (WAF) 🛡️

Untuk melindungi backend dari serangan bot/DDOS:

Masuk ke **Security > WAF (Web Application Firewall)**:
1. **Create Rule**.
2. **Rule Name:** `Block Bad Bots`.
3. **Expression:**
   - Field: `User Agent`
   - Operator: `contains`
   - Value: `sqlmap` (atau tool hacking lainnya)
4. **Action:** `Block`.

---

## 4. Troubleshooting Cloudflare Tunnel

Jika website muncul **"Bad Gateway (502)"**:
- Artinya Docker container `kbli2020-frontend` mati atau port 3001 tertutup di server.
- Cek di server: `docker ps` (Pastikan frontend status `Up`).
- Cek log tunnel: `docker logs cloudflared` (jika cloudflared jalan di docker) atau `systemctl status cloudflared`.

Jika website bisa dibuka tapi **Search Error**:
- Artinya tunnel jalan, frontend jalan, tapi **Backend Mati**.
- Cek backend: `docker logs kbli2020-backend`.
- Pastikan backend sudah selesai startup ("Hybrid Search Engine ready").
