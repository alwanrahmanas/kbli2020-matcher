"""
Ingestion Script: Load KBLI JSON and insert to Supabase with embeddings.
SAMPLING MODE: Only processes first N entries for quick testing.
"""
import json
import asyncio
from pathlib import Path
from openai import AsyncOpenAI
from config import OPENAI_API_KEY, EMBEDDING_MODEL, SAMPLE_MODE, SAMPLE_LIMIT

# For now, just validate and prepare data (no Supabase yet)


async def generate_embedding(client: AsyncOpenAI, text: str) -> list[float]:
    """Generate embedding for text using OpenAI"""
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


async def ingest_sample():
    """
    Sample ingestion - validates data and tests embedding generation.
    For production, extend this to insert into Supabase.
    """
    # Load JSON
    json_path = Path(__file__).parent.parent / "kbli_parsed_fast.json"
    with open(json_path, 'r', encoding='utf-8') as f:
        kbli_data = json.load(f)
    
    print(f"Total entries in JSON: {len(kbli_data)}")
    
    # Filter valid 5-digit codes
    valid_entries = []
    for entry in kbli_data:
        kode = entry.get("kode_kbli", "")
        if kode.isdigit() and len(kode) == 5:
            valid_entries.append(entry)
    
    print(f"Valid 5-digit entries: {len(valid_entries)}")
    
    # Sample for quick test
    sample = valid_entries[:SAMPLE_LIMIT] if SAMPLE_MODE else valid_entries
    print(f"Processing {len(sample)} entries (sample_mode={SAMPLE_MODE})")
    
    # Test embedding generation for first 3
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    print("\n--- Sample Embeddings Test ---")
    for i, entry in enumerate(sample[:3]):
        content = entry.get("content", "")[:500]  # Truncate for test
        print(f"\n[{i+1}] {entry['kode_kbli']}: {entry['judul'][:50]}...")
        
        embedding = await generate_embedding(client, content)
        print(f"    Embedding dim: {len(embedding)}, first 5 values: {embedding[:5]}")
    
    print("\n--- Ingest Preview Complete ---")
    print("To insert into Supabase, uncomment the supabase insert logic.")
    
    # TODO: Supabase insert
    # from supabase import create_client
    # supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    # for entry in sample:
    #     embedding = await generate_embedding(client, entry["content"])
    #     supabase.table("kbli_documents").insert({
    #         "kode_kbli": entry["kode_kbli"],
    #         "judul": entry["judul"],
    #         "content": entry["content"],
    #         "embedding": embedding,
    #         "metadata": {"source_page": entry.get("source_page")}
    #     }).execute()


if __name__ == "__main__":
    asyncio.run(ingest_sample())
