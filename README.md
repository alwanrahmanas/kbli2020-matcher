# KBLI 2025 Code Lookup v3.0 (Hybrid AI Edition)

## 🎯 Problem Statement
Mencari kode KBLI yang tepat seringkali sulit karena bahasa di dokumen resmi (baku) berbeda dengan bahasa sehari-hari (informal).

## ✅ Solution
**Hybrid Search Engine v3.0** menggabungkan:
1.  **AI Vector Search** (Paham makna kata, misal: "tukang"= "jasa", "warung" = "perdagangan eceran").
2.  **BM25 Keyword Search** (Pencarian kata kunci presisi).
3.  **LLM Re-ranking** (AI memeriksa ulang hasil pencarian dan memberikan alasan kenapa kode itu dipilih).

---

## � Cara Menjalankan Aplikasi (Guide)

Ada dua cara untuk menjalankan aplikasi ini. Gunakan **Cara 2 (Local)** jika internet/Docker sedang bermasalah.

### 🌟 Cara 1: Menggunakan Docker (Recommended)
Cara ini paling rapi karena semua kebutuhan (library, database) sudah dibungkus jadi satu.

1.  Klik ganda file **`docker_run.bat`**.
2.  Tunggu sampai muncul tulisan `Uvicorn running on http://0.0.0.0:8000`.
3.  Buka browser: [http://localhost:3001/app](http://localhost:3001/app).
4.  Untuk mematikan: Klik ganda **`docker_stop.bat`**.

---

### ⚡ Cara 2: Menjalankan Tanpa Docker (Local Mode)
Gunakan cara ini jika Docker gagal build atau internet lambat.

1.  **Matikan Docker** dulu (jika sedang nyala) dengan klik **`docker_stop.bat`**.
2.  Klik ganda file **`run_local.bat`**.
3.  Akan muncul jendela hitam (Terminal). Tunggu sampai muncul tulisan hijau:
    > `Uvicorn running on http://0.0.0.0:8000`
4.  **JANGAN TUTUP** jendela terminal tersebut. Biarkan terbuka selama Anda menggunakan aplikasi.
5.  Buka browser: [http://localhost:3001/app](http://localhost:3001/app).
    *(Jika link di atas tidak bisa, buka file `frontend/index.html` langsung di browser).*

---

## �️ Update Data KBLI
Jika ada kode KBLI yang kurang atau ingin update dari PDF terbaru:
1.  Pastikan file PDF ada di folder ini.
2.  Buka terminal (Powershell) di folder ini.
3.  Jalankan: `python update_missing_kbli.py`.
4.  Restart aplikasi (tutup dan buka lagi `run_local.bat`).

---

## ⚠️ Troubleshooting

**Q: Muncul error "Failed to fetch" di web?**
A: Itu artinya Backend belum siap.
- Cek apakah terminal `run_local.bat` masih terbuka?
- Cek apakah di terminal ada tulisan `Application startup complete`?
- Backend butuh waktu ~1 menit saat pertama kali jalan untuk membuat "otak" AI (embedding). Tunggu saja.

**Q: Docker error "lookup registry-1.docker.io"?**
A: Itu masalah DNS internet. Gunakan **Cara 2 (Local Mode)** saja.

---

## 🏗️ Architecture v3.0

```
[ FRONTEND ] 
      │
      ▼
[ BACKEND (FastAPI - Port 8000) ]
      │
      ├── 1. Dictionary Lookup (Cari kode instan)
      │
      └── Hibrid Search Engine:
             ├── A. BM25 Keyword Search (Cek kecocokan kata)
             ├── B. VECTOR Search (Cek makna via OpenAI Embedding)
             │
             ▼
        [ FUSION (RRF) ] -> Gabungkan hasil A & B
             │
             ▼
        [ GPT-4o-mini ] -> Analisa & Beri Alasan (Re-ranking)
             │
             ▼
        [ HASIL FINAL ] -> Dikirim ke User
```

---

## 📁 Project Structure (New)

```
kbli2020/
├── backend/             # FastAPI Backend Logic
├── frontend/            # HTML/JS Frontend UI
├── docs/                # Documentation & Guides
├── scripts/             # Python Utility Scripts
├── kbli_parsed_fast.json # KBLI Database
├── docker-compose.yml   # Docker Config
└── README.md            # This Guide
```
