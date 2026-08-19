# KBLI 2025 Code Lookup v3.0 (Hybrid AI Edition)

## 🎯 Problem Statement
Mencari kode KBLI yang tepat seringkali sulit karena bahasa di dokumen resmi (baku) berbeda dengan bahasa sehari-hari (informal).

## ✅ Solution
**Hybrid Search Engine v3.0** menggabungkan:
1.  **AI Vector Search** (Paham makna kata, misal: "tukang"= "jasa", "warung" = "perdagangan eceran").
2.  **BM25 Keyword Search** (Pencarian kata kunci presisi).
3.  **LLM Re-ranking** (AI memeriksa ulang hasil pencarian dan memberikan alasan kenapa kode itu dipilih).
4.  **Feedback Learning** (pilihan eksplisit user membantu mengurutkan pencarian berikutnya tanpa langsung mengubah klasifikasi resmi).

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

## Update Data KBJI

KBJI harus diekstrak dengan mode layout agar kode, judul, dan deskripsi tidak bergeser antarhalaman:

```powershell
python scripts\etl_kbji_parser.py
python -m unittest discover -s tests -v
```

Restart backend setelah regenerasi. Cache embedding KBJI memiliki fingerprint data dan akan dibangun ulang otomatis ketika `kbji_parsed.json` berubah.

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

---

## Reliability & Performance

The production path includes the following safeguards and optimizations:

- BM25 uses an inverted index, so a query scores only documents containing its terms.
- Vector top-K retrieval uses [`numpy.argpartition`](https://numpy.org/doc/stable/reference/generated/numpy.argpartition.html) instead of sorting the complete corpus.
- Repeated semantic queries use bounded in-memory LRU caches and concurrent duplicate requests are coalesced.
- OpenAI calls use the asynchronous client with a configurable timeout so they do not block FastAPI's event loop. See [`asyncio.to_thread`](https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread) for the same principle applied to blocking workbook I/O.
- Detailed KBLI/KBJI inputs are normalized into core concepts, context, and excluded interpretations before sparse+dense retrieval; repeated queries reuse a bounded cache.
- Explicit KBLI/KBJI selections are stored as anonymous relevance judgments in SQLite. A browser's previous choice personalizes an identical query immediately, while a global boost requires support from at least two distinct browser IDs on similar queries.
- Feedback only reorders candidates already returned by the classifier. It does not create codes, rewrite official KBLI/KBJI definitions, or treat a single vote as global truth.
- BM25 weights official titles and hierarchy above long descriptions, while vector indexes include the same classification context.
- Query bounds use [FastAPI parameter validation](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/).
- Batch uploads accept `.xlsx` only, have a configurable size limit, sanitize output names, and remove generated files after download.
- CORS defaults to the production domain and local development origins, following [Starlette's explicit-origin guidance](https://www.starlette.io/middleware/#corsmiddleware).

Optional environment variables:

```env
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MODEL=gpt-5.6-terra
# Optional overrides:
# QUERY_UNDERSTANDING_MODEL=gpt-5.6-terra
# KBLI_RERANK_MODEL=gpt-5.6-terra
# KBJI_RERANK_MODEL=gpt-5.6-terra
MAX_UPLOAD_BYTES=10485760
FEEDBACK_DB_PATH=/app/data/feedback.sqlite3
CORS_ALLOW_ORIGINS=https://kbli2025.alwansegeramutasi.my.id,http://localhost:3001,http://127.0.0.1:3001
```

For Docker production, keep the `./data:/app/data` volume so feedback survives container rebuilds. Do not commit `data/feedback.sqlite3`; it can contain user-entered search text.

Run the local checks from the repository root:

```powershell
python -m unittest discover -s tests -v
python -m scripts.benchmark_search
python scripts\smoke_batch.py  # requires the backend on port 8000
```
