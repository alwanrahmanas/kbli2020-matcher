import pandas as pd
import pdfplumber
import re
from pathlib import Path

# Paths
EXCEL_PATH = Path(r"c:\Users\US3R\OneDrive\Dokumen\Kerja\2026\Distribusi\SBR\kbli2020\muhamad.ridwan_1769660522728_direktori_usaha_checked.xlsx")
PDF_PATH = Path(r"c:\Users\US3R\OneDrive\Dokumen\Kerja\2026\Distribusi\SBR\kbli2020\KBLI_2020_1659511143.pdf")

def explore_excel():
    """Explore the Excel file structure efficiently"""
    print("\n" + "=" * 60)
    print("EKSPLORASI FILE EXCEL")
    print("=" * 60)
    
    if not EXCEL_PATH.exists():
        print(f"Error: File tidak ditemukan di {EXCEL_PATH}")
        return

    # Membuka file satu kali saja
    with pd.ExcelFile(EXCEL_PATH) as xlsx:
        print(f"Nama sheet ditemukan: {xlsx.sheet_names}")
        
        for sheet_name in xlsx.sheet_names:
            print(f"\n--- Memproses Sheet: {sheet_name} ---")
            # Menggunakan parse() lebih cepat daripada read_excel() berulang kali
            df = xlsx.parse(sheet_name)
            
            print(f"Jumlah baris: {len(df)}")
            print(f"Kolom: {list(df.columns)}")
            print(f"\nSample data (5 baris pertama):")
            print(df.head(5).to_string())
            
            # Identifikasi kolom KBLI secara otomatis
            kbli_cols = [col for col in df.columns if 'kbli' in str(col).lower()]
            if kbli_cols:
                print(f"\nKolom KBLI ditemukan: {kbli_cols}")
                for col in kbli_cols:
                    print(f"Top 10 nilai unik di '{col}':")
                    print(df[col].value_counts().head(10))
            
            # Regex Search: 5 digit angka (standar KBLI)
            kbli_pattern = re.compile(r'\b\d{5}\b')
            print("\nSearching KBLI patterns (5 digits) in object columns...")
            for col in df.columns:
                if df[col].dtype == 'object':
                    # Hindari apply(lambda) jika bisa, tapi untuk eksplorasi awal ini oke
                    matches = df[col].astype(str).apply(lambda x: kbli_pattern.findall(x))
                    count = matches.apply(len).sum()
                    if count > 0:
                        print(f"  - Kolom '{col}': {count} match ditemukan")

def explore_pdf():
    """Explore PDF text content without heavy table extraction"""
    print("\n" + "=" * 60)
    print("EKSPLORASI FILE PDF KBLI 2020")
    print("=" * 60)
    
    if not PDF_PATH.exists():
        print(f"Error: File tidak ditemukan di {PDF_PATH}")
        return

    with pdfplumber.open(PDF_PATH) as pdf:
        total_pages = len(pdf.pages)
        print(f"Total Halaman: {total_pages}")
        
        # Halaman sampel untuk melihat pola teks
        sample_pages = [0, 1, 2, 10, 50, 100]
        for pg_num in sample_pages:
            if pg_num < total_pages:
                print(f"\n--- Reading Halaman {pg_num + 1} ---")
                page = pdf.pages[pg_num]
                
                # Fokus ke text extraction karena jauh lebih ringan dari table extraction
                text = page.extract_text()
                if text:
                    print(text[:1000] + "..." if len(text) > 1000 else text)
                else:
                    print("[No text found on this page]")

                # TABLE EXTRACTION (DIMATIKAN UNTUK MENCEGAH HANG)
                # Jika ingin mencoba, lakukan hanya pada 1 halaman spesifik yang sudah pasti ada tabelnya.
                # tables = page.extract_tables() 
                # print(f"Tables detected: {len(tables)}")

if __name__ == "__main__":
    try:
        explore_excel()
    except Exception as e:
        print(f"\n[!] Gagal memproses Excel: {str(e)}")
        
    try:
        explore_pdf()
    except Exception as e:
        print(f"\n[!] Gagal memproses PDF: {str(e)}")

    print("\n" + "=" * 60)
    print("EKSPLORASI SELESAI")
    print("=" * 60)