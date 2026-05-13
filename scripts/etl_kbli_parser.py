"""
KBLI 2025 Parser - v3 (Accurate + LLM-Assisted Repair)
=======================================================
Dari analisis PDF, struktur konten KBLI 2025:
- Kode 5-digit ditulis dalam HURUF KAPITAL: "01111  PERTANIAN JAGUNG"
- Hierarki (kategori/golongan) juga kapital: "A  PERTANIAN, KEHUTANAN, DAN PERIKANAN"
- Cakupan ditulis dalam kalimat normal (mixed case)
- URL noise: "https://www.bps.go.id" sering terselip di baris
- Footer pages: "232  Klasifikasi Baku Lapangan Usaha Indonesia (KBLI) 2025"
- Konten dimulai sekitar halaman 248

Perbaikan dari v2:
- Kembali ke simple text extraction (sort=True), bukan block-based (yang merusak urutan)
- Filter halaman perubahan (tabel kode lama->baru) di awal PDF
- Lebih agresif strip URL dan footer noise
- Deduplikasi by quality score
- LLM repair untuk entri ber-cakupan kosong/pendek
"""

import fitz
import re
import json
import asyncio
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from collections import defaultdict
import time
from typing import Optional

# ── Config ─────────────────────────────────────────────────────────────────────
PDF_PATH    = Path(r"c:\Users\Acer\Downloads\kbbi-writer\kbli2020-matcher\klasifikasi-baku-lapangan-usaha-indonesia--kbli--2025-.pdf")
OUTPUT_PATH = Path(r"c:\Users\Acer\Downloads\kbbi-writer\kbli2020-matcher\kbli_parsed_fast.json")

USE_LLM_REPAIR = True
LLM_MODEL      = "gpt-5.4-mini-2026-03-17"

# Page offset: the real KBLI entries start around page 248 (0-indexed: 247)
# Pages before this are introduction, TOC, and change-log tables
DATA_START_PAGE = 240  # Be conservative, start a bit before 248

# ── Patterns ───────────────────────────────────────────────────────────────────
# Category headers (single uppercase letter + all-caps title)
RE_KATEGORI      = re.compile(r"^([A-U])\s{2,}([A-ZÉÀÂÊÈ,\s\/\-\.]+)$")
RE_GOL_POKOK     = re.compile(r"^(\d{2})\s{2,}([A-ZÉÀÂÊÈ,\s\/\-\.]+)$")
RE_GOLONGAN      = re.compile(r"^(\d{3})\s{2,}([A-ZÉÀÂÊÈ,\s\/\-\.]+)$")
RE_SUB_GOLONGAN  = re.compile(r"^(\d{4})\s{2,}([A-ZÉÀÂÊÈ,\s\/\-\.]+)$")
RE_KELOMPOK      = re.compile(r"^(\d{5})\s{2,}(.+)$")

# Noise lines to drop
RE_URL           = re.compile(r"https?://\S*")
RE_PAGE_FOOTER   = re.compile(r"^\d{1,4}\s+Klasifikasi Baku", re.IGNORECASE)
RE_PAGE_HEADER   = re.compile(r"^[A-Z]\s{2,}[A-Z ]+\s+\d{1,4}$")  # "A  PERTANIAN...  233"
RE_BARE_NUMBER   = re.compile(r"^\d{1,4}$")
RE_CHANGE_TABLE  = re.compile(
    r"(Pecah Kode|Gabung Kode|Recoding|Pindah|Hapus Kode|Lebur Cakupan|Kode/Cakupan)",
    re.IGNORECASE
)


def clean_line(line: str) -> str:
    """Remove inline URLs and trailing noise from a line."""
    line = RE_URL.sub("", line)
    return line.strip()


def is_noise(line: str) -> bool:
    """True if this line should be completely discarded."""
    if not line:
        return True
    if RE_BARE_NUMBER.match(line):
        return True
    if RE_PAGE_FOOTER.match(line):
        return True
    if RE_PAGE_HEADER.match(line):
        return True
    if RE_CHANGE_TABLE.search(line):
        return True
    return False


@dataclass
class KBLIEntry:
    kode_kbli:     str
    judul:         str
    hierarki:      str
    cakupan:       str
    source_page:   int
    category_code: str = ""
    category_name: str = ""
    golongan_pokok:str = ""
    golongan:      str = ""
    sub_golongan:  str = ""

    def to_content_text(self) -> str:
        c = " ".join(self.cakupan.split())
        j = " ".join(self.judul.split())
        return (
            f"KODE: {self.kode_kbli}\n"
            f"JUDUL: {j}\n"
            f"HIERARKI: {self.hierarki}\n"
            f"CAKUPAN: {c}"
        )

    def quality_score(self) -> int:
        score = len(self.cakupan) + len(self.judul) * 3
        if self.cakupan:
            score += 200
        if re.search(r"https?://", self.judul):
            score -= 500
        # Penalize if judul contains another 5-digit code (bleed from adjacent line)
        if re.search(r"\d{5}", self.judul):
            score -= 300
        return score


class KBLIParser2025:
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.entries: list[KBLIEntry] = []

        self.cat_code   = ""
        self.cat_name   = ""
        self.gol_pok    = ""
        self.gol        = ""
        self.sub_gol    = ""

    def _line_stream(self, doc):
        """Yield (cleaned_line, page_num_1indexed) for all pages from DATA_START_PAGE."""
        for page_num in range(DATA_START_PAGE, len(doc)):
            page = doc[page_num]
            text = page.get_text("text", sort=True)
            for raw in text.split("\n"):
                cleaned = clean_line(raw.strip())
                if cleaned:
                    yield cleaned, page_num + 1

    def parse(self):
        print(f"Opening: {self.pdf_path}")
        t0 = time.time()
        doc = fitz.open(self.pdf_path)
        print(f"Pages: {len(doc)}  |  Scanning from page {DATA_START_PAGE+1}")

        current  = None
        buf      = []

        for line, pgno in self._line_stream(doc):
            if is_noise(line):
                continue

            # ── Hierarchy ──────────────────────────────────────────────────────
            if m := RE_KATEGORI.match(line):
                # Only accept if it's truly a category (single letter A-U)
                self._finalize(current, buf); current, buf = None, []
                self.cat_code = m.group(1)
                self.cat_name = m.group(2).strip()
                self.gol_pok = self.gol = self.sub_gol = ""
                continue

            if m := RE_GOL_POKOK.match(line):
                self._finalize(current, buf); current, buf = None, []
                self.gol_pok = f"{m.group(1)} {m.group(2).strip()}"
                self.gol = self.sub_gol = ""
                continue

            if m := RE_GOLONGAN.match(line):
                self._finalize(current, buf); current, buf = None, []
                self.gol = f"{m.group(1)} {m.group(2).strip()}"
                self.sub_gol = ""
                continue

            if m := RE_SUB_GOLONGAN.match(line):
                self._finalize(current, buf); current, buf = None, []
                self.sub_gol = f"{m.group(1)} {m.group(2).strip()}"
                continue

            # ── 5-Digit Code ────────────────────────────────────────────────────
            if m := RE_KELOMPOK.match(line):
                self._finalize(current, buf); buf = []
                h = f"{self.cat_code} {self.cat_name} > {self.gol_pok} > {self.gol} > {self.sub_gol}"
                current = KBLIEntry(
                    kode_kbli      = m.group(1),
                    judul          = m.group(2).strip().upper(),
                    hierarki       = h,
                    cakupan        = "",
                    source_page    = pgno,
                    category_code  = self.cat_code,
                    category_name  = self.cat_name,
                    golongan_pokok = self.gol_pok.split()[0] if self.gol_pok else "",
                    golongan       = self.gol.split()[0]     if self.gol     else "",
                    sub_golongan   = self.sub_gol.split()[0] if self.sub_gol else "",
                )
                continue

            # ── Cakupan text ────────────────────────────────────────────────────
            if current:
                buf.append(line)

        self._finalize(current, buf)
        print(f"\n[OK] Raw: {len(self.entries)} entries in {time.time()-t0:.1f}s")

        self._deduplicate()
        print(f"[OK] After dedup: {len(self.entries)}")
        return self.entries

    def _finalize(self, entry: Optional[KBLIEntry], buf: list):
        if not entry:
            return
        raw = " ".join(buf)
        # Clean leading standard prefixes
        raw = re.sub(
            r"^(Kelompok|Subgolongan|Golongan)\s+ini\s+mencakup\s*",
            "", raw, flags=re.IGNORECASE
        )
        entry.cakupan = raw.strip()
        self.entries.append(entry)

    def _deduplicate(self):
        groups: dict[str, list[KBLIEntry]] = defaultdict(list)
        for e in self.entries:
            groups[e.kode_kbli].append(e)

        deduped = []
        for code, lst in groups.items():
            if len(lst) == 1:
                deduped.append(lst[0])
                continue
            best = max(lst, key=lambda e: e.quality_score())
            # Merge longer cakupan from siblings
            for sib in lst:
                if sib is not best and len(sib.cakupan) > len(best.cakupan):
                    if not re.search(r"https?://", sib.cakupan):
                        best.cakupan = sib.cakupan
            deduped.append(best)

        self.entries = sorted(deduped, key=lambda e: e.kode_kbli)

    def to_json(self, path: Path):
        data = []
        for e in self.entries:
            d = asdict(e)
            d["metadata"] = {
                "category_code":   e.category_code,
                "category_name":   e.category_name,
                "golongan_pokok":  e.golongan_pokok,
                "golongan":        e.golongan,
                "sub_golongan":    e.sub_golongan,
                "source_page":     e.source_page,
            }
            for k in ["category_code","category_name","golongan_pokok",
                      "golongan","sub_golongan","source_page"]:
                d.pop(k, None)
            d["content"] = e.to_content_text()
            data.append(d)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] Saved {len(data)} entries → {path}")


# ── LLM Repair ─────────────────────────────────────────────────────────────────

async def llm_repair(entries: list[dict]) -> list[dict]:
    """Use LLM to generate cakupan for entries that are missing or too short."""
    try:
        from openai import AsyncOpenAI
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / "backend" / ".env")
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            print("[WARN] No API key - skip LLM repair")
            return entries
        client = AsyncOpenAI(api_key=key)
    except ImportError:
        print("[WARN] openai not installed - skip LLM repair")
        return entries

    THRESHOLD = 40  # chars
    broken = [e for e in entries if len(e.get("cakupan", "")) < THRESHOLD]
    print(f"\n[LLM] Repairing {len(broken)} entries (cakupan < {THRESHOLD} chars)...")

    SYS = """Anda adalah ahli KBLI (Klasifikasi Baku Lapangan Usaha Indonesia) 2025.
Tulis deskripsi cakupan kegiatan usaha yang singkat, akurat, dan formal dalam Bahasa Indonesia.
Output: 2-4 kalimat cakupan SAJA, tanpa label, tanpa preamble."""

    sem = asyncio.Semaphore(8)

    async def fix(entry: dict) -> str:
        async with sem:
            msg = (
                f"KODE: {entry['kode_kbli']}\n"
                f"JUDUL: {entry['judul']}\n"
                f"HIERARKI: {entry['hierarki']}\n"
                f"Tulis cakupan (deskripsi kegiatan usaha) untuk kode ini."
            )
            try:
                r = await client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[{"role":"system","content":SYS},{"role":"user","content":msg}],
                    temperature=0.2,
                    max_completion_tokens=300,
                )
                return r.choices[0].message.content.strip()
            except Exception as ex:
                print(f"  [WARN] {entry['kode_kbli']}: {ex}")
                return entry.get("cakupan","")

    results = await asyncio.gather(*[fix(e) for e in broken])
    repair_map = {e["kode_kbli"]: r for e,r in zip(broken, results)}

    repaired = 0
    for entry in entries:
        k = entry["kode_kbli"]
        if k in repair_map and len(repair_map[k]) > len(entry.get("cakupan","")):
            entry["cakupan"] = repair_map[k]
            entry["content"] = (
                f"KODE: {k}\nJUDUL: {entry['judul']}\n"
                f"HIERARKI: {entry['hierarki']}\nCAKUPAN: {repair_map[k]}"
            )
            repaired += 1

    print(f"[LLM] Repaired {repaired} entries")
    return entries


# ── Main ────────────────────────────────────────────────────────────────────────

async def main():
    if not PDF_PATH.exists():
        print(f"ERROR: {PDF_PATH} not found")
        return

    parser = KBLIParser2025(PDF_PATH)
    parser.parse()
    parser.to_json(OUTPUT_PATH)

    if USE_LLM_REPAIR:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        data = await llm_repair(data)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # Summary
    with open(OUTPUT_PATH, encoding="utf-8") as f:
        final = json.load(f)
    five = [e for e in final if e["kode_kbli"].isdigit() and len(e["kode_kbli"])==5]
    empty = [e for e in five if len(e.get("cakupan","")) < 40]
    print(f"\n=== FINAL SUMMARY ===")
    print(f"  Total entries    : {len(final)}")
    print(f"  5-digit entries  : {len(five)}")
    print(f"  Short cakupan    : {len(empty)}")
    if empty:
        print(f"  Still broken     : {[e['kode_kbli'] for e in empty[:15]]}")
    print(f"  Sample (19209)   : {next((e['judul'] for e in final if e['kode_kbli']=='19209'), 'NOT FOUND')}")


if __name__ == "__main__":
    asyncio.run(main())