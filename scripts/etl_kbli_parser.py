"""
Optimized ETL Script: KBLI 2020 Parser (PyMuPDF Version)
========================================================
Menggunakan PyMuPDF untuk kecepatan tinggi dan iterator pattern
untuk menangani deskripsi yang terpotong antar halaman.
"""

import fitz  # PyMuPDF
import re
import json
from pathlib import Path
from dataclasses import dataclass, asdict
import time

# Configuration
PDF_PATH = Path(r"c:\Users\US3R\OneDrive\Dokumen\Kerja\2026\Distribusi\SBR\kbli2020\KBLI_2020_1659511143.pdf")
OUTPUT_PATH = Path(r"c:\Users\US3R\OneDrive\Dokumen\Kerja\2026\Distribusi\SBR\kbli2020\kbli_parsed_fast.json")

# Regex patterns (Sama, tapi di-compile sekali di luar)
PATTERNS = {
    "kategori": re.compile(r"^([A-U])\s+([A-ZÉÈÊ\s,]+)$"),
    "golongan_pokok": re.compile(r"^(\d{2})\s+([A-ZÉÈÊ\s,]+)$"),
    "golongan": re.compile(r"^(\d{3})\s+([A-ZÉÈÊ\s,]+)$"),
    "sub_golongan": re.compile(r"^(\d{4})\s+([A-ZÉÈÊ\s,]+)$"),
    "kelompok": re.compile(r"^(\d{5})\s+(.+)$"),
    # Regex untuk mendeteksi baris yang MERUPAKAN header kode baru (untuk stop condition)
    "any_code_start": re.compile(r"^([A-U]|\d{2}|\d{3}|\d{4}|\d{5})\s+")
}

@dataclass
class KBLIEntry:
    kode_kbli: str
    judul: str
    hierarki: str
    cakupan: str
    source_page: int
    # Structured Metadata Fields
    category_code: str = ""
    category_name: str = ""
    golongan_pokok: str = ""
    golongan: str = ""
    sub_golongan: str = ""

    def to_content_text(self) -> str:
        # Bersihkan spasi berlebih/newline pada cakupan
        clean_cakupan = " ".join(self.cakupan.split())
        return f"KODE: {self.kode_kbli}\nJUDUL: {self.judul}\nHIERARKI: {self.hierarki}\nCAKUPAN: {clean_cakupan}"

class FastKBLIParser:
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.entries = []
        
        # State Hierarchy (Raw strings)
        self.cat_code = ""
        self.cat_name = ""
        self.gol_pok = ""
        self.gol = ""
        self.sub_gol = ""

    def _get_line_stream(self, doc):
        """Generator yang menggabungkan seluruh halaman jadi satu aliran teks panjang.
        Ini solusi untuk masalah Cross-Page."""
        for page_num, page in enumerate(doc):
            # Flags: sort=True penting agar urutan teks sesuai layout visual
            text = page.get_text("text", sort=True) 
            lines = text.split('\n')
            for line in lines:
                cleaned = line.strip()
                if cleaned: # Skip empty lines
                    yield cleaned, page_num + 1

    def parse(self):
        print(f"Opening PDF: {self.pdf_path}")
        start_time = time.time()
        
        doc = fitz.open(self.pdf_path)
        print(f"Total pages: {len(doc)}")

        line_stream = self._get_line_stream(doc)
        
        current_entry = None
        buffer_cakupan = []
        
        for line, page_num in line_stream:
            # 1. Cek Pattern Hirarki (Reset state sesuai level)
            if match := PATTERNS["kategori"].match(line):
                self.cat_code = match.group(1)
                self.cat_name = match.group(2)
                self.gol_pok = self.gol = self.sub_gol = "" # Reset lower
                self._finalize_entry(current_entry, buffer_cakupan) # Save prev entry if exists
                current_entry = None; buffer_cakupan = []
                continue

            if match := PATTERNS["golongan_pokok"].match(line):
                self.gol_pok = f"{match.group(1)} {match.group(2)}"
                self.gol = self.sub_gol = ""
                self._finalize_entry(current_entry, buffer_cakupan)
                current_entry = None; buffer_cakupan = []
                continue

            if match := PATTERNS["golongan"].match(line):
                self.gol = f"{match.group(1)} {match.group(2)}"
                self.sub_gol = ""
                self._finalize_entry(current_entry, buffer_cakupan)
                current_entry = None; buffer_cakupan = []
                continue

            if match := PATTERNS["sub_golongan"].match(line):
                self.sub_gol = f"{match.group(1)} {match.group(2)}"
                self._finalize_entry(current_entry, buffer_cakupan)
                current_entry = None; buffer_cakupan = []
                continue

            # 2. Target Utama: Kelompok (5 Digit)
            if match := PATTERNS["kelompok"].match(line):
                # Simpan entry sebelumnya dulu sebelum mulai yang baru
                self._finalize_entry(current_entry, buffer_cakupan)
                buffer_cakupan = [] 

                # Buat object entry baru
                full_cat = f"{self.cat_code} {self.cat_name}"
                full_hierarchy = f"{full_cat} > {self.gol_pok} > {self.gol} > {self.sub_gol}"
                current_entry = KBLIEntry(
                    kode_kbli=match.group(1),
                    judul=match.group(2).strip(),
                    hierarki=full_hierarchy,
                    cakupan="", # Akan diisi buffer
                    source_page=page_num,
                    category_code=self.cat_code,
                    category_name=self.cat_name,
                    golongan_pokok=self.gol_pok.split()[0] if self.gol_pok else "",
                    golongan=self.gol.split()[0] if self.gol else "",
                    sub_golongan=self.sub_gol.split()[0] if self.sub_gol else ""
                )
                continue

            # 3. Logika Cakupan (Description Collection)
            # Jika kita sedang berada di dalam "mode entry" (sudah ketemu 5 digit)
            # DAN baris ini BUKAN awal dari kode lain
            if current_entry:
                # Cek apakah baris ini adalah header/footer (noise)
                # Contoh noise: angka halaman tunggal, atau header berulang
                if line.isdigit() and len(line) < 4: continue 
                
                # Jika baris ini ternyata match pattern kode lain (misal langsung masuk kode berikutnya tanpa cakupan)
                if PATTERNS["any_code_start"].match(line):
                    # Ini shouldn't happen here karena sudah dicek di blok "if match" di atas,
                    # tapi ini fail-safe kalau patternnya kompleks.
                    # Dalam logic stream ini, blok "if match" di atas akan menangkap duluan.
                    # Jadi bagian ini aman: apapun yang lolos ke sini adalah teks biasa.
                    pass
                
                buffer_cakupan.append(line)

        # Finalize entry terakhir
        self._finalize_entry(current_entry, buffer_cakupan)
        
        end_time = time.time()
        print(f"\n[OK] Extracted {len(self.entries)} entries in {end_time - start_time:.2f} seconds")
        return self.entries

    def _finalize_entry(self, entry, buffer):
        if entry:
            # Join buffer text
            full_text = " ".join(buffer)
            # Bersihkan prefix umum
            full_text = re.sub(r"^(Kelompok|Subgolongan|Golongan) ini mencakup\s*", "", full_text, flags=re.IGNORECASE)
            entry.cakupan = full_text.strip()
            self.entries.append(entry)

    def to_json(self, output_path: Path):
        data = []
        for entry in self.entries:
            d = asdict(entry)
            # Create structured metadata object for Supabase/pgvector
            d["metadata"] = {
                "category_code": entry.category_code,
                "category_name": entry.category_name,
                "golongan_pokok": entry.golongan_pokok,
                "golongan": entry.golongan,
                "sub_golongan": entry.sub_golongan,
                "source_page": entry.source_page
            }
            # Remove redundant flat fields to keep metadata clean
            for key in ["category_code", "category_name", "golongan_pokok", "golongan", "sub_golongan", "source_page"]:
                d.pop(key, None)
                
            d["content"] = entry.to_content_text()
            data.append(d)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] Saved to {output_path}")

if __name__ == "__main__":
    if not PDF_PATH.exists():
        print("File not found")
    else:
        parser = FastKBLIParser(PDF_PATH)
        parser.parse()
        parser.to_json(OUTPUT_PATH)