"""Test KBLI lookup data"""
import json
from pathlib import Path

json_path = Path("kbli_parsed_fast.json")
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Count 5-digit codes
codes_5digit = [e['kode_kbli'] for e in data if e.get('kode_kbli', '').isdigit() and len(e.get('kode_kbli', '')) == 5]
print(f"Total entries: {len(data)}")
print(f"5-digit codes: {len(codes_5digit)}")
print(f"Unique 5-digit codes: {len(set(codes_5digit))}")
print(f"\nSample codes: {codes_5digit[:20]}")
print(f"\nSample from end: {codes_5digit[-20:]}")

# Build lookup dict  
lookup = {}
for entry in data:
    code = entry.get("kode_kbli", "").strip()
    if code and code.isdigit() and len(code) == 5:
        lookup[code] = {
            "judul": entry.get("judul", ""),
            "hierarki": entry.get("hierarki", "")
        }

print(f"\nLookup dictionary size: {len(lookup)}")

# Test some lookups
test_codes = ["95120", "96111", "46591", "01111"]
print("\nTest lookups:")
for code in test_codes:
    if code in lookup:
        print(f"  {code}: Found - {lookup[code]['judul'][:50]}...")
    else:
        print(f"  {code}: NOT FOUND")
