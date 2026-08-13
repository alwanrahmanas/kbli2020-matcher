# KBLI 2025 Code Lookup v3.0 (Hybrid AI Edition)

## ðŸŽ¯ Problem Statement
Mencari kode KBLI yang tepat seringkali sulit karena bahasa di dokumen resmi (baku) berbeda dengan bahasa sehari-hari (informal).

## âœ… Solution
**Hybrid Search Engine v3.0** menggabungkan:
1.  **AI Vector Search** (Paham makna kata, misal: "tukang"= "jasa", "warung" = "perdagangan eceran").
2.  **BM25 Keyword Search** (Pencarian kata kunci presisi).
3.  **LLM Re-ranking** (AI memeriksa ulang hasil pencarian dan memberikan alasan kenapa kode itu dipilih).

---

## ï¿½ Cara Menjalankan Aplikasi (Guide)

Ada dua cara untuk menjalankan aplikasi ini. Gunakan **Cara 2 (Local)** jika internet/Docker sedang bermasalah.

### ðŸŒŸ Cara 1: Menggunakan Docker (Recommended)
Cara ini paling rapi karena semua kebutuhan (library, database) sudah dibungkus jadi satu.

1.  Klik ganda file **`docker_run.bat`**.
2.  Tunggu sampai muncul tulisan `Uvicorn running on http://0.0.0.0:8000`.
3.  Buka browser: [http://localhost:3001/app](http://localhost:3001/app).
4.  Untuk mematikan: Klik ganda **`docker_stop.bat`**.

---

### âš¡ Cara 2: Menjalankan Tanpa Docker (Local Mode)
Gunakan cara ini jika Docker gagal build atau internet lambat.

1.  **Matikan Docker** dulu (jika sedang nyala) dengan klik **`docker_stop.bat`**.
2.  Klik ganda file **`run_local.bat`**.
3.  Akan muncul jendela hitam (Terminal). Tunggu sampai muncul tulisan hijau:
    > `Uvicorn running on http://0.0.0.0:8000`
4.  **JANGAN TUTUP** jendela terminal tersebut. Biarkan terbuka selama Anda menggunakan aplikasi.
5.  Buka browser: [http://localhost:3001/app](http://localhost:3001/app).
    *(Jika link di atas tidak bisa, buka file `frontend/index.html` langsung di browser).*

---

## ï¿½ï¸ Update Data KBLI
Jika ada kode KBLI yang kurang atau ingin update dari PDF terbaru:
1.  Pastikan file PDF ada di folder ini.
2.  Buka terminal (Powershell) di folder ini.
3.  Jalankan: `python update_missing_kbli.py`.
4.  Restart aplikasi (tutup dan buka lagi `run_local.bat`).

---

## âš ï¸ Troubleshooting

**Q: Muncul error "Failed to fetch" di web?**
A: Itu artinya Backend belum siap.
- Cek apakah terminal `run_local.bat` masih terbuka?
- Cek apakah di terminal ada tulisan `Application startup complete`?
- Backend butuh waktu ~1 menit saat pertama kali jalan untuk membuat "otak" AI (embedding). Tunggu saja.

**Q: Docker error "lookup registry-1.docker.io"?**
A: Itu masalah DNS internet. Gunakan **Cara 2 (Local Mode)** saja.

---

## ðŸ—ï¸ Architecture v3.0

```
[ FRONTEND ] 
      â”‚
      â–¼
[ BACKEND (FastAPI - Port 8000) ]
      â”‚
      â”œâ”€â”€ 1. Dictionary Lookup (Cari kode instan)
      â”‚
      â””â”€â”€ Hibrid Search Engine:
             â”œâ”€â”€ A. BM25 Keyword Search (Cek kecocokan kata)
             â”œâ”€â”€ B. VECTOR Search (Cek makna via OpenAI Embedding)
             â”‚
             â–¼
        [ FUSION (RRF) ] -> Gabungkan hasil A & B
             â”‚
             â–¼
        [ GPT-4o-mini ] -> Analisa & Beri Alasan (Re-ranking)
             â”‚
             â–¼
        [ HASIL FINAL ] -> Dikirim ke User
```

---

## ðŸ“ Project Structure (New)

```
kbli2020/
â”œâ”€â”€ backend/             # FastAPI Backend Logic
â”œâ”€â”€ frontend/            # HTML/JS Frontend UI
â”œâ”€â”€ docs/                # Documentation & Guides
â”œâ”€â”€ scripts/             # Python Utility Scripts
â”œâ”€â”€ kbli_parsed_fast.json # KBLI Database
â”œâ”€â”€ docker-compose.yml   # Docker Config
â””â”€â”€ README.md            # This Guide
```

---

## Reliability & Performance

The production path includes the following safeguards and optimizations:

- BM25 uses an inverted index, so a query scores only documents containing its terms.
- Vector top-K retrieval uses [`numpy.argpartition`](https://numpy.org/doc/stable/reference/generated/numpy.argpartition.html) instead of sorting the complete corpus.
- Repeated semantic queries use bounded in-memory LRU caches and concurrent duplicate requests are coalesced.
- OpenAI calls use the asynchronous client with a configurable timeout so they do not block FastAPI's event loop. See [`asyncio.to_thread`](https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread) for the same principle applied to blocking workbook I/O.
- Query bounds use [FastAPI parameter validation](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/).
- Batch uploads accept `.xlsx` only, have a configurable size limit, sanitize output names, and remove generated files after download.
- CORS defaults to the production domain and local development origins, following [Starlette's explicit-origin guidance](https://www.starlette.io/middleware/#corsmiddleware).

Optional environment variables:

```env
OPENAI_TIMEOUT_SECONDS=30
MAX_UPLOAD_BYTES=10485760
CORS_ALLOW_ORIGINS=https://kbli2025.alwansegeramutasi.my.id,http://localhost:3001,http://127.0.0.1:3001
```

Run the local checks from the repository root:

```powershell
python -m unittest discover -s tests -v
python -m scripts.benchmark_search
python scripts\smoke_batch.py  # requires the backend on port 8000
```

