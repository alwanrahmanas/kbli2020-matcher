"""Persistent, conservative relevance feedback for KBLI and KBJI search."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4


TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
STOPWORDS = {
    "adalah", "agar", "atau", "dalam", "dan", "dari", "dengan", "di", "ini",
    "itu", "ke", "pada", "sebagai", "serta", "untuk", "yang",
}


def normalize_query(value: str) -> str:
    """Normalize user text without discarding short identifiers such as PP."""
    text = unicodedata.normalize("NFKD", str(value or "")).lower()
    tokens = TOKEN_RE.findall(text)
    return " ".join(tokens)


def query_tokens(value: str, extra_terms: list[str] | None = None) -> set[str]:
    tokens = set(TOKEN_RE.findall(normalize_query(value))) - STOPWORDS
    for term in extra_terms or []:
        tokens.update(TOKEN_RE.findall(normalize_query(term)))
    return tokens


def query_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class FeedbackStore:
    """Store search impressions and use explicit selections as ranking signals."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS search_impressions (
                    session_id TEXT PRIMARY KEY,
                    taxonomy TEXT NOT NULL CHECK (taxonomy IN ('kbli', 'kbji')),
                    query TEXT NOT NULL,
                    normalized_query TEXT NOT NULL,
                    query_terms TEXT NOT NULL,
                    candidate_codes TEXT NOT NULL,
                    method TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relevance_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    taxonomy TEXT NOT NULL CHECK (taxonomy IN ('kbli', 'kbji')),
                    normalized_query TEXT NOT NULL,
                    query_terms TEXT NOT NULL,
                    selected_code TEXT,
                    no_match INTEGER NOT NULL DEFAULT 0,
                    client_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES search_impressions(session_id),
                    UNIQUE (client_id, taxonomy, normalized_query)
                );

                CREATE INDEX IF NOT EXISTS idx_feedback_taxonomy
                ON relevance_feedback(taxonomy, created_at);
                """
            )

    def create_impression(
        self,
        taxonomy: str,
        query: str,
        candidate_codes: list[str],
        method: str,
        terms: list[str] | None = None,
    ) -> str:
        taxonomy = str(taxonomy).lower()
        if taxonomy not in {"kbli", "kbji"}:
            raise ValueError("Unsupported taxonomy")

        session_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        normalized = normalize_query(query)
        tokens = sorted(query_tokens(query, terms))
        codes = list(dict.fromkeys(str(code).strip() for code in candidate_codes if code))

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO search_impressions (
                    session_id, taxonomy, query, normalized_query, query_terms,
                    candidate_codes, method, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    taxonomy,
                    str(query)[:200],
                    normalized,
                    json.dumps(tokens),
                    json.dumps(codes),
                    str(method)[:80],
                    now,
                ),
            )
        return session_id

    def save_feedback(
        self,
        session_id: str,
        client_id: str,
        selected_code: str | None = None,
        no_match: bool = False,
    ) -> dict:
        if not CLIENT_ID_RE.fullmatch(str(client_id or "")):
            raise ValueError("Invalid anonymous client identifier")
        if bool(selected_code) == bool(no_match):
            raise ValueError("Choose exactly one result or mark no match")

        with self._lock, self._connect() as connection:
            impression = connection.execute(
                "SELECT * FROM search_impressions WHERE session_id = ?",
                (str(session_id),),
            ).fetchone()
            if impression is None:
                raise LookupError("Search session not found")

            candidates = json.loads(impression["candidate_codes"])
            code = str(selected_code).strip() if selected_code else None
            if code is not None and code not in candidates:
                raise ValueError("Selected code was not part of this search result")

            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                INSERT INTO relevance_feedback (
                    session_id, taxonomy, normalized_query, query_terms,
                    selected_code, no_match, client_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_id, taxonomy, normalized_query) DO UPDATE SET
                    session_id = excluded.session_id,
                    query_terms = excluded.query_terms,
                    selected_code = excluded.selected_code,
                    no_match = excluded.no_match,
                    created_at = excluded.created_at
                """,
                (
                    impression["session_id"],
                    impression["taxonomy"],
                    impression["normalized_query"],
                    impression["query_terms"],
                    code,
                    int(no_match),
                    client_id,
                    now,
                ),
            )

        return {
            "status": "saved",
            "taxonomy": impression["taxonomy"],
            "selected_code": code,
            "no_match": bool(no_match),
        }

    def apply_feedback(
        self,
        taxonomy: str,
        query: str,
        results: list[dict],
        client_id: str | None = None,
        terms: list[str] | None = None,
    ) -> tuple[list[dict], dict]:
        """Rerank existing candidates; feedback never invents a classification."""
        if not results:
            return [], {"applied": False, "signals": 0}

        normalized = normalize_query(query)
        current_tokens = query_tokens(query, terms)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT normalized_query, query_terms, selected_code, no_match, client_id
                FROM relevance_feedback
                WHERE taxonomy = ?
                ORDER BY id DESC
                LIMIT 1000
                """,
                (taxonomy,),
            ).fetchall()

        personal_code = None
        votes: dict[str, dict[str, float]] = {}
        for row in rows:
            if row["no_match"] or not row["selected_code"]:
                continue
            if client_id and row["client_id"] == client_id and row["normalized_query"] == normalized:
                personal_code = row["selected_code"]

            stored_tokens = set(json.loads(row["query_terms"]))
            similarity = 1.0 if row["normalized_query"] == normalized else query_similarity(
                current_tokens,
                stored_tokens,
            )
            if similarity < 0.6:
                continue
            code_votes = votes.setdefault(row["selected_code"], {})
            code_votes[row["client_id"]] = max(similarity, code_votes.get(row["client_id"], 0.0))

        ranked = []
        signals = 0
        for original_rank, raw_result in enumerate(results):
            result = dict(raw_result)
            code = str(result.get("code") or result.get("kode_kbli") or result.get("kode_kbji") or "")
            supporters = votes.get(code, {})
            support_count = len(supporters)
            community_weight = sum(supporters.values()) if support_count >= 2 else 0.0
            is_personal = bool(personal_code and code == personal_code)
            priority = float(original_rank)
            feedback_note = ""

            if is_personal:
                priority -= 100.0
                feedback_note = "Urutan diperkuat oleh pilihan Anda sebelumnya untuk pencarian ini."
                signals += 1
            elif community_weight:
                priority -= min(3.0, community_weight)
                feedback_note = (
                    f"Urutan diperkuat oleh {support_count} pilihan pengguna "
                    "pada pencarian serupa."
                )
                signals += 1

            if feedback_note:
                result["feedback_note"] = feedback_note
                result["feedback_support"] = support_count
            ranked.append((priority, original_rank, result))

        ranked.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked], {
            "applied": signals > 0,
            "signals": signals,
            "personalized": personal_code is not None,
        }

    def stats(self) -> dict:
        with self._lock, self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM relevance_feedback").fetchone()[0]
            selections = connection.execute(
                "SELECT COUNT(*) FROM relevance_feedback WHERE no_match = 0"
            ).fetchone()[0]
        return {"total": total, "selections": selections, "no_match": total - selections}
