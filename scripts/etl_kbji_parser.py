"""
Parse KBJI 2014 PDF into a searchable JSON file.

The PDF text extraction is not perfect, but most occupation entries follow:
    5414.01
    Pengawal Pribadi
    description...

This script extracts both 4-digit subgolongan entries and detailed x.x entries.
"""

import json
import re
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "Klasifikasi_Baku_Jabatan_Indonesia_2014_1659512277.pdf"
OUTPUT_PATH = ROOT / "kbji_parsed.json"

CODE_RE = re.compile(r"^(?P<code>\d{4}(?:\.\d{2})?)$")
NOISE_RE = re.compile(
    r"^(Halaman\s+\d+|Golongan Pokok \d+|Klasifikasi Baku Jabatan Indonesia Tahun 2014|"
    r"H|alaman\s+\d+|Kl|asifikasi Baku Jabatan Indonesia Tahun 2014|"
    r"Jabatan|Subgolongan|Tugas meliputi:|Contoh pekerjaan diklasifikasikan di sini:)$",
    re.IGNORECASE,
)


def clean_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line or "").strip()
    line = line.replace("Kl asifikasi", "Klasifikasi")
    line = line.replace("G olongan", "Golongan")
    return line


def is_noise(line: str) -> bool:
    if not line:
        return True
    if NOISE_RE.match(line):
        return True
    if line.lower().startswith("klasifikasi baku jabatan indonesia"):
        return True
    if line.startswith("- ") and len(line) < 80:
        return False
    return False


def page_lines(reader: PdfReader) -> list[tuple[int, str]]:
    lines = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            line = clean_line(raw_line)
            if not is_noise(line):
                lines.append((page_index, line))
    return lines


def parse_entries(lines: list[tuple[int, str]]) -> list[dict]:
    entries = []
    code_positions = []

    for idx, (page, line) in enumerate(lines):
        match = CODE_RE.match(line)
        if match:
            code_positions.append((idx, page, match.group("code")))

    for pos_idx, (line_idx, page, code) in enumerate(code_positions):
        next_line_idx = code_positions[pos_idx + 1][0] if pos_idx + 1 < len(code_positions) else len(lines)
        block = [line for _, line in lines[line_idx + 1:next_line_idx]]

        title = ""
        description_lines = []
        for line in block:
            if CODE_RE.match(line):
                continue
            if not title and not line.startswith("- "):
                title = line
                continue
            description_lines.append(line)

        if not title:
            continue

        description = " ".join(description_lines).strip()
        if code == "5414":
            title = "Penjaga Keamanan"
            if "Penjaga keamanan adalah seseorang" in description:
                description = description[description.index("Penjaga keamanan adalah seseorang"):]
        elif code == "5413.00":
            title = "Penjaga Lembaga Pemasyarakatan"
            if "Penjaga lembaga pemasyarakatan bertugas" in description:
                description = description[description.index("Penjaga lembaga pemasyarakatan bertugas"):]

        entries.append({
            "kode_kbji": code,
            "judul": title,
            "deskripsi": description,
            "source_page": page,
            "level": "rinci" if "." in code else "subgolongan",
            "content": f"KODE: {code}\nJUDUL: {title}\nDESKRIPSI: {description}",
        })

    deduped = []
    seen = set()
    for entry in entries:
        key = (entry["kode_kbji"], entry["judul"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    return deduped


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"KBJI PDF not found: {PDF_PATH}")

    reader = PdfReader(str(PDF_PATH))
    entries = parse_entries(page_lines(reader))

    OUTPUT_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Parsed {len(entries)} KBJI entries -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
