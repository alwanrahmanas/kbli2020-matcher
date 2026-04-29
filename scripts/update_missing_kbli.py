
import json
import re
import pdfplumber
from pathlib import Path
from tqdm import tqdm

def extract_from_pdf(pdf_path):
    print(f"📄 Reading PDF: {pdf_path}")
    extracted_data = {}
    
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        # Read all pages
        for page in tqdm(pdf.pages, desc="Extracting text"):
            text = page.extract_text()
            if text:
                full_text += "\n" + text
    
    # Regex pattern to capture KBLI 2020 structure
    # Patterns: 5 digit code followed by Title
    # Example: 01111 PERTANIAN JAGUNG
    pattern = re.compile(r'\n(\d{5})\s+([A-Z\s\/\.,\-\(\)]+?)(?=\n\d{5}|\n[A-Z]|\nUraian|\Z)', re.DOTALL)
    
    matches = pattern.finditer(full_text)
    
    for match in matches:
        code = match.group(1).strip()
        title = match.group(2).strip().replace('\n', ' ')
        
        # Simple heuristic to extract description/cakupan if available nearby
        # (This is basic, might need refinement for detailed cakupan extraction)
        
        extracted_data[code] = {
            "kode_kbli": code,
            "judul": title,
            "hierarki": "", # Placeholder
            "cakupan": "", # Placeholder, will be filled if detailed parsing added
            "metadata": {"source": "pdf_update"}
        }
        
    print(f"✅ Extracted {len(extracted_data)} potential KBLI codes from PDF.")
    return extracted_data

def update_json_file(json_path, new_data):
    print(f"📂 Loading existing JSON: {json_path}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            existing_list = json.load(f)
    except FileNotFoundError:
        existing_list = []
        
    # Create lookup map of existing codes
    existing_map = {item['kode_kbli']: item for item in existing_list}
    
    added_count = 0
    updated_list = existing_list.copy()
    
    # Compare and Add
    for code, data in new_data.items():
        if code not in existing_map:
            print(f"➕ Found missing code: {code} - {data['judul'][:50]}...")
            
            # Format to match existing schema
            new_entry = {
                "kode_kbli": code,
                "judul": data['judul'],
                "hierarki": f"Golongan Pokok {code[:2]} -> Golongan {code[:3]} -> Subgolongan {code[:4]}",
                "cakupan": data['judul'], # Fallback cakupan to title if empty
                "metadata": {"added_via": "update_script"}
            }
            updated_list.append(new_entry)
            added_count += 1
            
    if added_count > 0:
        print(f"\n💾 Saving {added_count} new entries to {json_path}...")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(updated_list, f, indent=2, ensure_ascii=False)
        print("✅ Update complete!")
    else:
        print("\n✨ No missing codes found. JSON is up to date.")

if __name__ == "__main__":
    current_dir = Path(__file__).parent
    pdf_file = current_dir / "KBLI_2020_1659511143.pdf"
    json_file = current_dir / "kbli_parsed_fast.json"
    
    if not pdf_file.exists():
        print(f"❌ PDF not found: {pdf_file}")
    elif not json_file.exists():
        print(f"❌ JSON not found: {json_file}")
    else:
        try:
            # 1. Extract from PDF
            pdf_data = extract_from_pdf(pdf_file)
            
            # 2. Update JSON
            update_json_file(json_file, pdf_data)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
