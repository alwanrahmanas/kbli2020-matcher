"""Small reproducible benchmark for the local BM25 implementation."""

from collections import Counter
from statistics import median
from time import perf_counter

from backend.hybrid_search import BM25


def reference_search(index: BM25, query: str, top_k: int):
    """Pre-optimization full-corpus scoring path."""
    query_tokens = index._tokenize(query)
    scores = []
    for document_index, document_tokens in enumerate(index.documents):
        score = 0.0
        term_frequencies = Counter(document_tokens)
        for term in query_tokens:
            if term not in index.idf:
                continue
            term_frequency = term_frequencies.get(term, 0)
            if term_frequency == 0:
                continue
            numerator = term_frequency * (index.k1 + 1)
            denominator = term_frequency + index.k1 * (
                1 - index.b + index.b * (index.doc_len[document_index] / index.avgdl)
            )
            score += index.idf[term] * (numerator / denominator)
        if score > 0:
            scores.append((document_index, score))
    scores.sort(key=lambda item: item[1], reverse=True)
    return scores[:top_k]


def measure(callable_, repetitions=7):
    samples = []
    result = None
    for _ in range(repetitions):
        started = perf_counter()
        result = callable_()
        samples.append((perf_counter() - started) * 1000)
    return median(samples), result


def main():
    documents = []
    for index in range(20_000):
        activity = "warung makan restoran" if index % 400 == 0 else "perdagangan umum barang"
        documents.append({
            "judul": f"{activity} {index}",
            "hierarki": "penyediaan makanan" if index % 400 == 0 else "perdagangan",
            "cakupan": "layanan pelanggan bangunan tetap" if index % 400 == 0 else "eceran",
        })

    bm25 = BM25()
    bm25.fit(documents)
    query = "warung makan"
    optimized_ms, optimized = measure(lambda: bm25.search(query, 20))
    reference_ms, reference = measure(lambda: reference_search(bm25, query, 20))
    assert optimized == reference
    print(f"documents={len(documents)}")
    print(f"reference_median_ms={reference_ms:.3f}")
    print(f"optimized_median_ms={optimized_ms:.3f}")
    print(f"speedup={reference_ms / optimized_ms:.1f}x")


if __name__ == "__main__":
    main()

