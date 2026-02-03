# KBLI 2020 Code Lookup v2.1

## 🎯 Problem Statement
Punya kode KBLI tapi tidak tahu apa klasifikasinya. Program ini untuk mencari deskripsi/klasifikasi dari kode KBLI tanpa perlu repot membuka PDF/dokumen manual.

## ✅ Solution
**Pattern Matching Lookup + Smart Search** - bukan AI/RAG classifier. Lebih cepat, lebih akurat, lebih scalable.

---

## ✨ Features

### 🔎 **Search & Autocomplete**
- **Keyword Search**: Cari KBLI berdasarkan judul, hierarki, atau deskripsi
- **Smart Autocomplete**: Saran real-time saat mengetik (kode atau judul)
- **Fuzzy Matching**: Toleransi typo dan pencarian multi-kata
- **Relevance Scoring**: Hasil diurutkan berdasarkan relevansi

### 🔢 **Code Lookup**
- **Single Lookup**: Cari klasifikasi untuk satu kode KBLI
- **O(1) Lookup Time**: Instant results dengan dictionary-based lookup
- **Code Autocomplete**: Saran kode saat mengetik

### 📊 **Batch Processing**
- **Full File Processing**: Proses **semua baris** tanpa sampling
- **Excel Upload**: Drag & drop atau click to upload
- **Column Selection**: Pilih kolom yang berisi kode KBLI
- **Real-time Progress**: Progress bar dengan statistik live
- **Excel Download**: Download hasil dengan kolom tambahan:
  - `KBLI_Judul`: Judul klasifikasi
  - `KBLI_Hierarki`: Hierarki lengkap
  - `Lookup_Status`: Status (Found/Not Found)

### ⚡ **Performance**
- **Pattern Matching**: Tidak pakai AI, 100% akurat
- **Fast Processing**: ~1000 rows/second
- **In-Memory Lookup**: Data loaded ke RAM untuk kecepatan maksimal
- **No External Dependencies**: Tidak perlu API key atau internet

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  ┌──────────────────┐  ┌────────────────────────────────┐  │
│  │ Keyword Search   │  │ Code Lookup                    │  │
│  │ - Autocomplete   │  │ - Code autocomplete            │  │
│  │ - Fuzzy match    │  │ - Instant result               │  │
│  └────────┬─────────┘  └─────────────┬──────────────────┘  │
│           │                          │                      │
│  ┌────────┴──────────────────────────┴──────────────────┐  │
│  │           Batch Excel Processing                     │  │
│  │  - Upload Excel  - Select column  - Download result  │  │
│  └──────────────────────────┬───────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              kbli_lookup Dictionary                   │  │
│  │     { "46591" -> info, "28221" -> info, ... }        │  │
│  │               O(1) Lookup Time                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Endpoints:                                                  │
│  - GET  /lookup/{code}          → Single lookup             │
│  - GET  /search?q=...           → Keyword search            │
│  - GET  /autocomplete?q=...     → Autocomplete suggestions  │
│  - POST /upload-preview         → Preview Excel headers     │
│  - POST /lookup/batch           → Process & return Excel    │
│  - POST /lookup/batch-stream    → SSE streaming + download  │
└─────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────┐
│                   kbli_parsed_fast.json                      │
│          ~2500+ KBLI entries from PDF parsing               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
cd backend
pip install fastapi uvicorn openpyxl python-multipart
```

### 2. Run Backend
```bash
cd backend
python main.py
# API will be available at http://localhost:8000
```

Or double-click `run_backend.bat`

### 3. Open Frontend
Open `frontend/index_v2.html` in browser

---

## 📁 Project Structure

```
kbli2020/
├── backend/
│   ├── main.py              # FastAPI app with lookup + search endpoints
│   └── requirements.txt     # Dependencies (fastapi, openpyxl)
├── frontend/
│   ├── index.html           # Original UI
│   └── index_v2.html        # New UI with search & autocomplete
├── kbli_parsed_fast.json    # Parsed KBLI database (~2500 entries)
├── etl_kbli_parser.py       # PDF → JSON parser
├── run_backend.bat          # Windows launcher
└── README.md                # This file
```

---

## 🔧 API Reference

### GET /lookup/{code}
Lookup single KBLI code

**Response:**
```json
{
  "code": "46591",
  "found": true,
  "judul": "Perdagangan Besar Mesin Kantor dan Industri...",
  "hierarki": "G PERDAGANGAN... > 46 PERDAGANGAN BESAR...",
  "cakupan": "Kelompok ini mencakup..."
}
```

### GET /search?q={query}&limit={limit}
Search KBLI by keyword

**Parameters:**
- `q`: Search query (min 2 characters)
- `limit`: Max results (default: 10)

**Response:**
```json
{
  "query": "perdagangan",
  "total": 150,
  "results": [
    {
      "code": "46591",
      "judul": "Perdagangan Besar...",
      "hierarki": "G PERDAGANGAN...",
      "score": 175
    }
  ]
}
```

### GET /autocomplete?q={query}&limit={limit}
Get autocomplete suggestions

**Parameters:**
- `q`: Query string (min 1 character)
- `limit`: Max suggestions (default: 5)

**Response:**
```json
{
  "suggestions": [
    {
      "type": "code",
      "code": "46591",
      "judul": "Perdagangan Besar...",
      "match": "46591 - Perdagangan Besar..."
    }
  ]
}
```

### POST /lookup/batch
Process entire Excel file

**Input:**
- `file`: Excel file (.xlsx)
- `column_name`: Column containing KBLI codes

**Output:** Excel file with added columns

### POST /lookup/batch-stream
Process with progress streaming

**Input:** Same as `/lookup/batch`

**Output:** Server-Sent Events with progress + base64 Excel

---

## 💡 Usage Examples

### Single Lookup
1. Masukkan kode KBLI (misal: `46591`)
2. Langsung dapat hasil: judul, hierarki, cakupan

### Keyword Search
1. Ketik kata kunci (misal: "perdagangan", "restoran", "konstruksi")
2. Lihat autocomplete suggestions
3. Klik search untuk hasil lengkap

### Batch Processing
1. Upload file Excel (.xlsx)
2. Pilih kolom yang berisi kode KBLI
3. Proses semua row (tanpa limit)
4. Download Excel hasil dengan kolom tambahan

---

## ⚡ Performance

- **Lookup Time**: O(1) - instant lookup via dictionary
- **Search Time**: O(n) with relevance scoring (~50ms for 2500 entries)
- **Batch Processing**: ~1000 rows/second
- **Memory**: ~50MB untuk 2500+ entries
- **No AI calls**: Zero latency, zero cost

---

## 📝 Changelog

### v2.1.0 (2026-02-03)
- ✨ **NEW**: Keyword search dengan fuzzy matching
- ✨ **NEW**: Smart autocomplete untuk kode dan judul
- ✨ **NEW**: Relevance scoring untuk hasil search
- 🎨 Improved UI/UX dengan search tab
- 📚 Updated API documentation

### v2.0.0 (2026-02-03)
- 🔄 Complete refactor: RAG → Pattern Matching
- ✅ No AI dependency - pure pattern matching
- ✅ Full batch processing (no sampling limit)
- ✅ Excel download with results
- ✅ SSE progress streaming
- ✅ Scalable architecture

### v1.0.0 (2026-02-03)
- Initial RAG-based classifier (deprecated)

---

## 🛠️ Development

### Running Tests
```bash
# Test lookup data quality
python test_lookup.py
```

### Parsing New KBLI Data
```bash
# Parse PDF to JSON
python etl_kbli_parser.py
```

---

## 📄 License

Data source: Klasifikasi Baku Lapangan Usaha Indonesia 2020 (BPS)

---

## 🤝 Contributing

Contributions welcome! Please open an issue or PR.
