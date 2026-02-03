# Project Plan: KBLI 2020 RAG Multi-Label Classifier

**Status:** Draft (v3.0 - Final)  
**Owner:** Data Scientist / Developer  
**Stack:** React, FastAPI, Supabase (pgvector), OpenAI

---

## 1. Tujuan & Scope

Membangun sistem klasifikasi otomatis yang menerima input file Excel berisi deskripsi teks "Kegiatan Usaha" (unstructured), dan menghasilkan output kode KBLI 2020 (5 digit) beserta skor kepercayaan (confidence score) **per kegiatan usaha**.

### Core Constraint & Requirement:

*   **Multi-label Handling:** Satu deskripsi usaha bisa mengandung multiple kegiatan (misal: "Jualan pulsa dan bengkel motor"). Sistem harus mampu memecah ini dan memberikan **confidence score granular** untuk masing-masing.
*   **Source Truth:** PDF KBLI 2020 (`KBLI_2020_1659511143.pdf`).
*   **Knowledge Base:** Supabase dengan pgvector + **HNSW Index**.
*   **Input Data:** Excel (`muhamad.ridwan_...xlsx`) kolom "Kegiatan Usaha".

---

## 2. Arsitektur Data & Ingestion (Critical Path)

Tantangan utama KBLI adalah struktur hierarkis. Embedding "01111" saja tanpa konteks "Pertanian" akan menghasilkan retrieval yang buruk.

### A. Strategi Parsing PDF (ETL)

> **Update v3.0:** Switch dari `pdfplumber` (visual table extraction) ke **`PyMuPDF` (fitz)** untuk stream-based text extraction. Jauh lebih cepat dan konsisten untuk 800+ halaman.

Jangan lakukan *blind chunking* (memotong per 500 karakter). Kita harus melakukan **Semantic/Structural Parsing**.

**Hierarchy Extraction:**
*   Parse PDF dengan `PyMuPDF` untuk membangun tree: Kategori -> Golongan Pokok -> Golongan -> Sub Golongan -> Kelompok (5 digit).
*   Setiap node anak mewarisi teks dari node induknya.

**Rich Chunking Strategy:**
*   Unit terkecil adalah **Kode 5 Digit**.
*   Setiap chunk harus "berdiri sendiri" (self-contained).

**Format Teks untuk Embedding:**

```
KODE: 47911
JUDUL: Perdagangan Eceran Melalui Media Untuk Komoditi Makanan, Minuman, Tembakau, Kimia, Farmasi, Kosmetik Dan Alat Laboratorium
HIERARKI: Perdagangan Besar Dan Eceran; Reparasi Dan Perawatan Mobil Dan Sepeda Motor > Perdagangan Eceran Bukan Di Mobil Dan Sepeda Motor > Perdagangan Eceran Bukan Melalui Toko, Kios, Kaki Lima Dan Los Pasar
CAKUPAN: Mencakup usaha perdagangan eceran berbagai jenis barang makanan, minuman, tembakau, kimia, farmasi, kosmetik dan alat laboratorium...
```

### B. Desain Schema Supabase (PostgreSQL)

Kita menggunakan tabel tunggal dengan kolom metadata JSONB yang kaya untuk filtering.

```sql
-- Enable extension
create extension if not exists vector;

create table kbli_documents (
  id bigserial primary key,
  kode_kbli varchar(10),       -- e.g., "47911"
  judul text,                  -- Judul resmi
  content text,                -- Teks lengkap (Hierarki + Judul + Cakupan) untuk RAG Context
  embedding vector(1536),      -- text-embedding-3-small/large
  metadata jsonb,              -- { "kategori": "G", "golongan_pokok": "47", "source_page": 105 }
  created_at timestamptz default now()
);

-- HNSW Index untuk performa (Updated v3.0)
-- HNSW lebih stabil untuk high-recall tanpa perlu sering re-index dibanding ivfflat
create index on kbli_documents using hnsw (embedding vector_cosine_ops)
with (m = 16, ef_construction = 64);
```

---

## 3. Pipeline RAG & Multi-Label Logic

**Masalah:** Query "Jualan nasi goreng dan bengkel" jika di-embed langsung, vektornya akan berada di "tengah-tengah" antara makanan dan otomotif, sehingga retrieval mungkin gagal mengambil keduanya.

### Strategi Retrieval (Hybrid + Intent Splitting)

> **Update v3.0:** Definisi eksplisit flow: **Split Intent -> Parallel Search**.

```
┌───────────────────────────────────────────────────────────────┐
│                    USER INPUT                                 │
│     "Jual pulsa dan nasi goreng"                              │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│             1. INTENT SPLITTER (LLM: gpt-4o-mini)             │
│                                                               │
│  Prompt: "Pecah deskripsi berikut menjadi kegiatan usaha      │
│           terpisah. Output: JSON array of strings."           │
│                                                               │
│  Output: ["Jual pulsa", "Jual nasi goreng"]                   │
└───────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│  2a. VECTOR SEARCH      │     │  2b. VECTOR SEARCH      │
│      "Jual pulsa"       │     │      "Jual nasi goreng" │
│      -> Top 5 results   │     │      -> Top 5 results   │
└─────────────────────────┘     └─────────────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
┌───────────────────────────────────────────────────────────────┐
│           3. DE-DUPLICATION & CONTEXT MERGE                   │
│              Gabung hasil, buang duplikat kode                │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│        4. CLASSIFIER (LLM: gpt-4o / gpt-4-turbo)              │
│           Input: Original query + Merged context              │
│           Output: JSON dengan confidence per-kegiatan         │
└───────────────────────────────────────────────────────────────┘
```

### Prompt Engineering (Generation)

Prompt harus memaksa output JSON terstruktur yang mendukung array dengan **confidence score granular per kegiatan**.

**System Prompt:**

```
You are an expert KBLI classifier for BPS Statistics Indonesia.
Your task is to classify the user's business activity description into one OR MORE KBLI 2020 codes based STRICTLY on the provided context.

Rules:
1. Analyze if the description contains multiple distinct business activities.
2. If multiple activities exist, output a list of classifications.
3. Assign a confidence score (0.0 - 1.0) for EACH code independently.
4. Explain your reasoning briefly referencing the "Cakupan".
5. If the context does not contain a suitable match, output "UNMAPPED".

Response Format (JSON):
{
  "classifications": [
    {
      "code": "47414",
      "title": "Perdagangan Eceran Telepon Seluler...",
      "confidence": 0.96,
      "reasoning": "User mentions selling 'pulsa' which is covered under telecom retail..."
    },
    {
      "code": "56303",
      "title": "Kedai Minuman",
      "confidence": 0.88,
      "reasoning": "Selling 'nasi goreng' at a kiosk aligns with food stall category..."
    }
  ]
}
```

---

## 4. Implementasi Backend (FastAPI)

*   **Async Processing:** Menggunakan `asyncio` untuk melakukan *Parallel Retrieval* (Langkah 2a & 2b) agar latency rendah.
*   **Batch Processing:** Endpoint `/classify/batch` menerima file Excel, tapi memproses dalam *micro-batches* (misal 10 baris per request ke OpenAI) untuk menghindari timeout dan rate limit.
*   **Progress Streaming:** Karena file Excel bisa besar, gunakan **Server-Sent Events (SSE)** atau WebSocket untuk kirim update progress ke Frontend ("Processed 50/1000 rows...").

---

## 5. Implementasi Frontend (React)

*   **Input:** Upload file `.xlsx`.
*   **Column Selector:** User memilih kolom mana yang berisi deskripsi usaha.
*   **Preview Table:**
    *   Kolom Kiri: Input Asli.
    *   Kolom Kanan: Render JSON hasil (bisa di-expand jika ada multiple KBLI).
    *   **Color Coding:**
        *   🟢 Hijau (Conf > 0.8)
        *   🟡 Kuning (0.5 - 0.8)
        *   🔴 Merah (< 0.5 / Unmapped)
*   **Action:** "Accept & Download" -> Generate Excel baru.

---

## 6. Rencana Eksekusi (Updated v3.0)

### Phase 1: Knowledge Base (ETL)

- [x] Run `fast_kbli_parser.py` (PyMuPDF version) -> `kbli_parsed_fast.json` ✅
- [ ] Setup Supabase (`kbli_documents` table + **HNSW** index) - *Pending: using in-memory for sampling*
- [x] Script `ingest.py`: Baca JSON -> OpenAI Embedding -> Insert ke Supabase ✅

### Phase 2: RAG Logic

- [x] Build `RAGService` class: ✅
    *   Method `split_intents(text) -> list[str]` ✅
    *   Method `retrieve(query) -> list[chunk]` ✅ (keyword-based for sampling)
    *   Method `classify(text, context) -> json` ✅
- [ ] **Test Case:** "Jualan nasi uduk dan tambal ban". *Ready to test with API key*

### Phase 3: Integration

- [x] FastAPI Endpoint `/classify`, `/upload`, `/classify/batch` dengan SSE progress ✅
- [x] Frontend HTML/JS (Upload, Column Select, Preview, SSE streaming) ✅

---

## 7. Format Output Excel (Final)

**Logic penulisan ke Excel untuk Multi-label:**

*   Jika 1 input menghasilkan 2 KBLI, baris tersebut **diduplikasi (explode)** ATAU kolom **diperlebar** (KBLI_1, KBLI_2).
*   ✅ **Keputusan:** Perlebar kolom agar jumlah baris input = output (lebih mudah buat user BPS validasi).

| Kegiatan Usaha       | KBLI_1_Code | KBLI_1_Title     | KBLI_1_Conf | KBLI_2_Code | KBLI_2_Title   | KBLI_2_Conf |
| -------------------- | ----------- | ---------------- | ----------- | ----------- | -------------- | ----------- |
| Jual pulsa & kopi    | 47414       | Eceran HP...     | 0.96        | 56303       | Kedai Minuman  | 0.92        |
| Bengkel motor saja   | 45403       | Reparasi Sepeda Motor | 0.98   |             |                |             |

---

*Last Updated: 2026-02-03 - v3.0 Final*
