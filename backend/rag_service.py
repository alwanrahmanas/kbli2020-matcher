"""
RAG Service for KBLI Classification
Implements: Intent Splitting -> Parallel Search -> Classification
"""
import asyncio
import json
import re
from typing import Optional
from openai import AsyncOpenAI

# For now, we'll use a mock vector store (in-memory) for sampling
# Real implementation would use Supabase

class RAGService:
    def __init__(self, openai_client: AsyncOpenAI, kbli_data: list[dict]):
        self.client = openai_client
        self.kbli_data = kbli_data  # In-memory for sampling
        self._embeddings_cache = {}
    
    async def split_intents(self, text: str) -> list[str]:
        """
        Step 1: Split multi-activity descriptions into separate intents.
        Example: "Jual pulsa dan nasi goreng" -> ["Jual pulsa", "Jual nasi goreng"]
        """
        prompt = f"""Pecah deskripsi kegiatan usaha berikut menjadi kegiatan usaha terpisah.
Jika hanya ada 1 kegiatan, kembalikan hanya 1 item.
Output HANYA JSON array of strings, tanpa penjelasan.

Deskripsi: "{text}"

Contoh output: ["Jual pulsa", "Jual nasi goreng"]"""

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=200
        )
        
        try:
            content = response.choices[0].message.content.strip()
            # Extract JSON array from response
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                return json.loads(match.group())
            return [text]  # Fallback to original
        except:
            return [text]
    
    async def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Step 2: Vector search (simplified keyword match for sampling).
        Real implementation uses Supabase pgvector.
        """
        # Simplified: keyword matching for sampling mode
        query_lower = query.lower()
        keywords = query_lower.split()
        
        scored = []
        for entry in self.kbli_data:
            content = entry.get("content", "").lower()
            judul = entry.get("judul", "").lower()
            
            # Skip invalid entries (like intro pages)
            if not entry.get("kode_kbli", "").isdigit():
                continue
            if len(entry.get("kode_kbli", "")) != 5:
                continue
            
            score = 0
            for kw in keywords:
                if len(kw) > 2:  # Skip short words
                    if kw in judul:
                        score += 3
                    elif kw in content:
                        score += 1
            
            if score > 0:
                scored.append((score, entry))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]
    
    async def classify(self, original_text: str, context_chunks: list[dict]) -> dict:
        """
        Step 3: Use LLM to classify based on retrieved context.
        Returns structured JSON with confidence scores.
        """
        if not context_chunks:
            return {
                "classifications": [{
                    "code": "UNMAPPED",
                    "title": "Tidak ditemukan kecocokan",
                    "confidence": 0.0,
                    "reasoning": "Tidak ada konteks yang relevan ditemukan dalam database KBLI."
                }]
            }
        
        # Build context string
        context_str = "\n---\n".join([
            f"KODE: {c['kode_kbli']}\nJUDUL: {c['judul']}\nCAKUPAN: {c.get('cakupan', '')[:500]}"
            for c in context_chunks
        ])
        
        system_prompt = """You are an expert KBLI classifier for BPS Statistics Indonesia.
Your task is to classify the user's business activity description into one OR MORE KBLI 2020 codes based STRICTLY on the provided context.

Rules:
1. Analyze if the description contains multiple distinct business activities.
2. If multiple activities exist, output a list of classifications.
3. Assign a confidence score (0.0 - 1.0) for EACH code independently.
4. Explain your reasoning briefly referencing the "Cakupan".
5. If the context does not contain a suitable match, output "UNMAPPED".

Response Format (JSON ONLY, no markdown):
{
  "classifications": [
    {
      "code": "47414",
      "title": "Perdagangan Eceran...",
      "confidence": 0.96,
      "reasoning": "..."
    }
  ]
}"""

        user_prompt = f"""Deskripsi Usaha: "{original_text}"

Konteks KBLI yang tersedia:
{context_str}

Klasifikasikan deskripsi di atas. Output JSON saja."""

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            max_tokens=800
        )
        
        try:
            content = response.choices[0].message.content.strip()
            # Extract JSON from response (handle markdown code blocks)
            if "```" in content:
                match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
                if match:
                    content = match.group(1).strip()
            return json.loads(content)
        except Exception as e:
            return {
                "classifications": [{
                    "code": "ERROR",
                    "title": "Parsing error",
                    "confidence": 0.0,
                    "reasoning": f"Failed to parse LLM response: {str(e)}"
                }]
            }
    
    async def process(self, text: str) -> dict:
        """
        Full pipeline: Split -> Parallel Retrieve -> Classify
        """
        # Step 1: Split intents
        intents = await self.split_intents(text)
        
        # Step 2: Parallel retrieval for each intent
        retrieve_tasks = [self.retrieve(intent) for intent in intents]
        all_results = await asyncio.gather(*retrieve_tasks)
        
        # Merge and deduplicate by kode_kbli
        seen_codes = set()
        merged_context = []
        for results in all_results:
            for entry in results:
                code = entry.get("kode_kbli")
                if code and code not in seen_codes:
                    seen_codes.add(code)
                    merged_context.append(entry)
        
        # Step 3: Classify
        result = await self.classify(text, merged_context[:10])  # Limit context
        result["intents_detected"] = intents
        return result


# Test function for sampling
async def test_rag_service():
    """Quick test with sample data"""
    import os
    from pathlib import Path
    
    # Load sample KBLI data
    json_path = Path(__file__).parent.parent / "kbli_parsed_fast.json"
    with open(json_path, 'r', encoding='utf-8') as f:
        kbli_data = json.load(f)
    
    # Filter valid entries (5-digit codes only)
    valid_data = [
        e for e in kbli_data 
        if e.get("kode_kbli", "").isdigit() and len(e.get("kode_kbli", "")) == 5
    ][:100]  # Sample first 100
    
    print(f"Loaded {len(valid_data)} valid KBLI entries for testing")
    
    # Initialize
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    rag = RAGService(client, valid_data)
    
    # Test cases
    test_inputs = [
        "Jualan nasi uduk dan tambal ban",
        "Bengkel motor",
        "Warung kopi dan jual pulsa"
    ]
    
    for text in test_inputs:
        print(f"\n{'='*50}")
        print(f"INPUT: {text}")
        result = await rag.process(text)
        print(f"INTENTS: {result.get('intents_detected')}")
        for cls in result.get("classifications", []):
            print(f"  -> {cls['code']}: {cls['title'][:50]}... (conf: {cls['confidence']})")


if __name__ == "__main__":
    asyncio.run(test_rag_service())
