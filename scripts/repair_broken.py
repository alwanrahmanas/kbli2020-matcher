"""Quick LLM repair for broken KBLI entries"""
import asyncio, json, os
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(Path("backend") / ".env")
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")  # fallback
key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=key)
LLM_MODEL = "gpt-5.6-terra"

with open(Path(__file__).parent.parent / "kbli_parsed_fast.json", encoding="utf-8") as f:
    data = json.load(f)

THRESHOLD = 40
broken = [e for e in data if len(e.get("cakupan", "")) < THRESHOLD]
print(f"Broken entries: {[e['kode_kbli'] for e in broken]}")

SYS = "Anda adalah ahli KBLI 2025. Tulis deskripsi cakupan kegiatan usaha singkat dan formal dalam Bahasa Indonesia. Output: 2-4 kalimat SAJA, tanpa label."

async def fix_all():
    sem = asyncio.Semaphore(5)
    async def fix(entry):
        async with sem:
            msg = (
                f"KODE: {entry['kode_kbli']}\n"
                f"JUDUL: {entry['judul']}\n"
                f"HIERARKI: {entry['hierarki']}\n"
                f"Tulis cakupan."
            )
            r = await client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "system", "content": SYS}, {"role": "user", "content": msg}],
                temperature=0.2,
                max_completion_tokens=300,
            )
            return r.choices[0].message.content.strip()
    results = await asyncio.gather(*[fix(e) for e in broken])
    return results

results = asyncio.run(fix_all())
repair_map = {e["kode_kbli"]: r for e, r in zip(broken, results)}

for entry in data:
    k = entry["kode_kbli"]
    if k in repair_map:
        entry["cakupan"] = repair_map[k]
        entry["content"] = (
            f"KODE: {k}\nJUDUL: {entry['judul']}\n"
            f"HIERARKI: {entry['hierarki']}\nCAKUPAN: {repair_map[k]}"
        )
        print(f"Fixed {k}: {repair_map[k][:80]}...")

output = Path(__file__).parent.parent / "kbli_parsed_fast.json"
with open(output, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

total5 = [e for e in data if e["kode_kbli"].isdigit() and len(e["kode_kbli"]) == 5]
still_broken = [e for e in total5 if len(e.get("cakupan", "")) < THRESHOLD]
print(f"\nDone. Total: {len(data)}, still broken: {len(still_broken)}")
