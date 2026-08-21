"""Parse the KBJI 2014 PDF into clean, searchable JSON.

The PDF stores text in visual blocks, so plain extraction order frequently puts
continuation paragraphs before their occupation titles. pdfplumber's layout mode
preserves the printed ``code title`` rows and makes the hierarchy deterministic.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "Klasifikasi_Baku_Jabatan_Indonesia_2014_1659512277.pdf"
OUTPUT_PATH = ROOT / "kbji_parsed.json"

CODE_TITLE_RE = re.compile(r"^(?P<code>\d{4}(?:\.\d{2})?)\s+(?P<title>.+?)$")
DOUBLED_CODE_TITLE_RE = re.compile(
    r"^(?P<code>\d{8}\.\.\d{4})\s+(?P<title>.+?)$"
)
SECTION_LABELS = {
    "golongan",
    "jabatan",
    "subgolongan",
    "subgolongan pokok",
}
PAGE_DECORATION_RE = re.compile(
    r"^(?:golongan pokok\s+\d+|halaman\s+\d+|"
    r"klasifikasi baku jabatan indonesia tahun 2014)",
    re.IGNORECASE,
)
# Earlier pages contain examples and comparison tables whose numeric years and
# codes otherwise look like classification rows.
FIRST_CLASSIFICATION_PAGE = 44
EXPECTED_SUBGROUPS = 446
EXPECTED_DETAILED_JOBS = 2137


def clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line or "").strip()


def is_noise(line: str) -> bool:
    normalized = line.lower()
    return (
        not line
        or normalized in SECTION_LABELS
        or bool(PAGE_DECORATION_RE.match(line))
        or "klasifikasi baku jabatan indonesia tahun 2014" in normalized
    )


def match_code_title(line: str) -> tuple[str, str] | None:
    match = CODE_TITLE_RE.match(line)
    if match:
        return match.group("code"), clean_line(match.group("title"))

    # Two rows in the source PDF duplicate every glyph in the code, e.g.
    # 55331111..0033 means 5311.03. Normalize only when every pair agrees.
    match = DOUBLED_CODE_TITLE_RE.match(line)
    if not match:
        return None
    raw_code = match.group("code")
    left, right = raw_code.split("..", 1)
    pairs = [left[index:index + 2] for index in range(0, len(left), 2)]
    pairs += [right[index:index + 2] for index in range(0, len(right), 2)]
    if not all(len(pair) == 2 and pair[0] == pair[1] for pair in pairs):
        return None
    code = left[::2] + "." + right[::2]
    return code, clean_line(match.group("title"))


def iter_layout_lines(pdf_path: Path):
    """Yield page-aware lines in visual reading order."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            if page_number < FIRST_CLASSIFICATION_PAGE:
                continue
            text = page.extract_text(layout=True, x_tolerance=2, y_tolerance=3) or ""
            for raw_line in text.splitlines():
                line = clean_line(raw_line)
                if not is_noise(line):
                    yield page_number, line


def candidate_quality(entry: dict) -> tuple[int, int, int]:
    """Prefer the detailed declaration over list and table references."""
    description = entry.get("deskripsi", "")
    title = entry.get("judul", "")
    title_words = re.findall(r"[A-Za-z]+", title)
    title_case_words = sum(word[:1].isupper() for word in title_words)
    return (len(description), title_case_words, len(title))


def parse_entries(lines) -> list[dict]:
    candidates = []
    current = None

    def finish_current() -> None:
        nonlocal current
        if not current:
            return
        description = clean_line(" ".join(current.pop("description_lines")))
        current["deskripsi"] = description
        current["content"] = (
            f"KODE: {current['kode_kbji']}\n"
            f"JUDUL: {current['judul']}\n"
            f"DESKRIPSI: {description}"
        )
        candidates.append(current)
        current = None

    for page_number, line in lines:
        matched = match_code_title(line)
        if matched:
            finish_current()
            code, title = matched
            current = {
                "kode_kbji": code,
                "judul": title,
                "source_page": page_number,
                "level": "rinci" if "." in code else "subgolongan",
                "description_lines": [],
            }
        elif current:
            current["description_lines"].append(line)

    finish_current()

    by_code = defaultdict(list)
    for entry in candidates:
        if len(entry["judul"]) >= 4:
            by_code[entry["kode_kbji"]].append(entry)

    entries = [max(group, key=candidate_quality) for group in by_code.values()]
    entries.sort(key=lambda entry: entry["kode_kbji"])
    return entries


def validate_entries(entries: list[dict]) -> None:
    codes = [entry["kode_kbji"] for entry in entries]
    if len(codes) != len(set(codes)):
        raise ValueError("KBJI parser produced duplicate codes")

    bad_titles = [entry for entry in entries if len(entry["judul"]) < 4]
    if bad_titles:
        raise ValueError(f"KBJI parser produced {len(bad_titles)} invalid titles")

    subgroup_count = sum("." not in code for code in codes)
    detailed_count = sum("." in code for code in codes)
    if subgroup_count != EXPECTED_SUBGROUPS:
        raise ValueError(
            f"Expected {EXPECTED_SUBGROUPS} KBJI subgroups, parsed {subgroup_count}"
        )
    if detailed_count != EXPECTED_DETAILED_JOBS:
        raise ValueError(
            f"Expected {EXPECTED_DETAILED_JOBS} detailed KBJI jobs, parsed {detailed_count}"
        )


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"KBJI PDF not found: {PDF_PATH}")

    entries = parse_entries(iter_layout_lines(PDF_PATH))
    validate_entries(entries)
    OUTPUT_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    detailed_count = sum(entry["level"] == "rinci" for entry in entries)
    print(
        f"Parsed {len(entries)} unique KBJI entries "
        f"({detailed_count} detailed jobs) -> {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
