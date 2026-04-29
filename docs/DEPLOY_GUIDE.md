# Panduan Deployment ke VPS/Server

Update v3.0 (Hybrid Search) membawa perubahan besar pada Backend dan Frontend. Ikuti langkah ini untuk deploy ke server produksi (`alwansegeramutasi.my.id`).

## 1. Persiapan File
Pastikan file-file berikut sudah siap di laptop Anda (hasil update kita tadi):
- `backend/hybrid_search.py` (File baru)
- `backend/main.py` (Update endpoint)
- `backend/requirements.txt` (Update library numpy)
- `frontend/index.html` (Update UI)
- `kbli_parsed_fast.json` (Data KBLI terupdate)
- `docker-compose.yml` (Konfigurasi port/service)

## 2. Cara Update di Server

### Opsi A: Menggunakan GIT (Recommended)
Jika Anda menggunakan GitHub/GitLab:

1.  **Di Laptop:**
    ```powershell
    git add .
    git commit -m "Upgrade to v3.0 Hybrid Search"
    git push origin main
    ```

2.  **Di Server (via SSH):**
    ```bash
    # Masuk ke folder project
    cd /path/to/kbli2020-matcher

    # Ambil update terbaru
    git pull origin main

    # Matikan container lama
    docker-compose down

    # Rebuild & Nyalakan (Penting: --build untuk install library baru)
    docker-compose up -d --build
    ```

---

### Opsi B: Upload Manual (SCP / FileZilla)
Jika tidak menggunakan Git:

1.  **Compress** semua file project di laptop menjadi `kbli-update.zip`.
2.  **Upload** file zip tersebut ke server.
3.  **Di Server:**
    ```bash
    unzip -o kbli-update.zip
    docker-compose down
    docker-compose up -d --build
    ```

## 3. Verifikasi Pasca-Deploy

1.  Cek log backend di server:
    ```bash
    docker logs -f kbli2020-backend
    ```
2.  Tunggu sampai muncul:
    > `✅ Hybrid Search Engine ready!`
    > `INFO: Uvicorn running...`
    *(Ingat: Proses embedding pertama kali di server butuh waktu ~1-2 menit)*.

3.  Cek website:
    Buka `https://kbli2020.alwansegeramutasi.my.id`.
    Pastikan icon kaca pembesar (search) sudah berubah interfacenya dan ada logo "Hybrid Search" saat mencari.

## ⚠️ Catatan Server
- Pastikan server memiliki RAM yang cukup (Min. 1GB, rekomendasi 2GB) karena proses Vector Embedding menggunakan memory.
- Pastikan `.env` di server memiliki `OPENAI_API_KEY` yang valid.
