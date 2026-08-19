"""Cost-aware query understanding for KBLI and KBJI retrieval."""

import asyncio
import copy
import json
import re
import time
from collections import OrderedDict

from openai import AsyncOpenAI


INDONESIAN_STOPWORDS = {
    "ada", "adalah", "agar", "akan", "atau", "bagi", "bahwa", "dalam",
    "dan", "dari", "dengan", "di", "dimana", "ini", "itu", "jadi", "juga", "lalu",
    "karena", "ke", "kepada", "lebih", "melalui", "oleh", "pada", "sebagai",
    "seperti", "serta", "terhadap", "untuk", "yang",
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"\b[a-z0-9]{3,}\b", str(text).lower())


def _unique_terms(values, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    terms = []
    seen = set()
    for value in values:
        term = " ".join(str(value).lower().split()).strip(" ,.;:")
        if not term or len(term) > 80 or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def local_query_understanding(query: str, taxonomy: str) -> dict:
    normalized = " ".join(str(query).lower().split())
    terms = []
    for token in _tokens(normalized):
        if token not in INDONESIAN_STOPWORDS and token not in terms:
            terms.append(token)

    return {
        "taxonomy": taxonomy,
        "method": "local",
        "normalized_query": normalized,
        "core_terms": terms[:12],
        "context_terms": [],
        "excluded_intents": [],
        "summary": normalized,
    }


def build_retrieval_queries(query: str, understanding: dict) -> tuple[str, str, str]:
    """Build sparse, dense, and reranker inputs while preserving the original query."""
    normalized = understanding.get("normalized_query", "")
    core_terms = understanding.get("core_terms", [])
    context_terms = understanding.get("context_terms", [])
    summary = understanding.get("summary", "")
    exclusions = understanding.get("excluded_intents", [])

    # Core terms are repeated once to provide transparent BM25 weighting. The
    # original query remains present to limit expansion drift.
    sparse_parts = [query, normalized, " ".join(core_terms), " ".join(core_terms), " ".join(context_terms)]
    sparse_query = " ".join(part for part in sparse_parts if part).strip()
    semantic_query = "\n".join(part for part in [query, normalized, summary] if part).strip()
    rerank_context = (
        f"Ringkasan maksud: {summary}. "
        f"Konsep inti: {', '.join(core_terms) or '-'}. "
        f"Konteks: {', '.join(context_terms) or '-'}. "
        f"Bukan maksud: {', '.join(exclusions) or '-'}"
    )
    return sparse_query, semantic_query, rerank_context


class QueryUnderstandingService:
    """Analyze detailed queries once and cache the structured interpretation."""

    def __init__(
        self,
        client: AsyncOpenAI | None,
        model: str,
        cache_ttl: float = 600.0,
        cache_size: int = 256,
    ):
        self.client = client
        self.model = model
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        self._cache: OrderedDict[tuple[str, str], tuple[float, dict]] = OrderedDict()
        self._inflight: dict[tuple[str, str], asyncio.Task] = {}

    @staticmethod
    def is_detailed(query: str) -> bool:
        return len(_tokens(query)) >= 7 or len(str(query).strip()) >= 70

    async def analyze(self, query: str, taxonomy: str) -> dict:
        fallback = local_query_understanding(query, taxonomy)
        if not self.client or not self.is_detailed(query):
            return fallback

        key = (taxonomy, " ".join(str(query).lower().split()))
        now = time.monotonic()
        cached = self._cache.pop(key, None)
        if cached and now - cached[0] <= self.cache_ttl:
            self._cache[key] = cached
            return copy.deepcopy(cached[1])

        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._analyze_with_llm(query, taxonomy, fallback))
            self._inflight[key] = task

        try:
            result = await asyncio.shield(task)
        finally:
            if task.done() and self._inflight.get(key) is task:
                self._inflight.pop(key, None)

        self._cache[key] = (time.monotonic(), copy.deepcopy(result))
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return result

    async def _analyze_with_llm(self, query: str, taxonomy: str, fallback: dict) -> dict:
        if taxonomy == "kbli":
            focus = (
                "Pisahkan aktivitas utama, objek/produk/jasa, cara menghasilkan atau menjual, "
                "target pelanggan, dan konteks lokasi. Bedakan produksi, perdagangan, dan jasa."
            )
        else:
            focus = (
                "Pisahkan tugas utama, hasil kerja, alat/sistem, tingkat tanggung jawab, dan "
                "konteks tempat kerja. Tempat kerja tidak boleh dianggap sebagai nama pekerjaan."
            )

        system_prompt = f"""Anda menganalisis query untuk pencarian klasifikasi {taxonomy.upper()} Indonesia.
{focus}
Jangan menambah fakta yang tidak diberikan pengguna. Normalisasikan istilah informal ke bahasa klasifikasi.
Keluarkan JSON dengan tepat lima field:
{{
  "normalized_query": "deskripsi ringkas dalam bahasa klasifikasi",
  "core_terms": ["maksimal 8 konsep tugas/aktivitas paling menentukan"],
  "context_terms": ["maksimal 6 konteks pendukung"],
  "excluded_intents": ["maksimal 4 interpretasi yang jelas bukan maksud pengguna"],
  "summary": "satu kalimat tentang maksud klasifikasi"
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": str(query)},
                ],
                temperature=0,
                max_completion_tokens=700,
                response_format={"type": "json_object"},
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                raise ValueError("query understanding returned an empty response")
            parsed = json.loads(content)
            normalized = " ".join(str(parsed.get("normalized_query", "")).split())[:500]
            summary = " ".join(str(parsed.get("summary", "")).split())[:500]
            result = {
                "taxonomy": taxonomy,
                "method": "llm",
                "normalized_query": normalized or fallback["normalized_query"],
                "core_terms": _unique_terms(parsed.get("core_terms"), 8) or fallback["core_terms"][:8],
                "context_terms": _unique_terms(parsed.get("context_terms"), 6),
                "excluded_intents": _unique_terms(parsed.get("excluded_intents"), 4),
                "summary": summary or normalized or fallback["summary"],
            }
            return result
        except Exception as exc:
            print(f"Query understanding error ({taxonomy}): {exc}")
            return {**fallback, "method": "fallback"}
