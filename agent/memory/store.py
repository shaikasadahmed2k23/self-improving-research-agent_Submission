"""SQLite long-term memory: past runs, lessons and URL-level source trust.

Opens a short-lived connection per call, so one store can be shared by the CLI, tests and (later) Streamlit threads.
"""
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from agent import config

SCHEMA = Path(__file__).with_name("schema.sql")
_WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = set(
    "the a an of on and or to for in is are be what how does do would will with using use per its it this that these "
    "which from by at as vs than then there their about into can should could my our your me we you they them "
    "each any all more most much many find tell give show".split()
)
MIN_SHARED_TERMS = 2  # a past run counts as similar when its task shares at least this many content terms
DUPLICATE_OVERLAP = 0.5  # word-set Jaccard above which a new lesson counts as a repeat of an existing one
MAX_FACTS = 8


def terms(text: str) -> set[str]:
    """Content words for matching (lowercase, no stopwords, >2 chars)."""
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in STOPWORDS}


def _fts_query(words: set[str]) -> str:
    return " OR ".join(f'"{w}"' for w in sorted(words))


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


class MemoryStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or config.MEMORY_DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(SCHEMA.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        with closing(self._connect()) as con:
            return [dict(r) for r in con.execute(sql, params).fetchall()]

    # ---- recall -------------------------------------------------------------------------------------------

    def similar_runs(self, task: str, limit: int = 5) -> list[dict]:
        words = terms(task)
        if not words:
            return []
        rows = self._query(
            "SELECT r.*, bm25(runs_fts) AS rank FROM runs_fts JOIN runs r ON r.id = runs_fts.rowid "
            "WHERE runs_fts MATCH ? ORDER BY rank LIMIT 20",
            (_fts_query(words),),
        )
        similar = [r for r in rows if len(words & terms(r["task"])) >= MIN_SHARED_TERMS]
        return similar[:limit]

    def relevant_lessons(self, task: str, limit: int = 5) -> list[dict]:
        words = terms(task)
        if not words:
            return []
        return self._query(
            "SELECT l.*, bm25(lessons_fts) AS rank FROM lessons_fts JOIN lessons l ON l.id = lessons_fts.rowid "
            "WHERE lessons_fts MATCH ? ORDER BY rank - 0.5 * l.times_helpful - 0.2 * l.times_seen LIMIT ?",
            (_fts_query(words), limit),
        )

    def trusted_sources(self, run_ids: list[int], limit: int = 5) -> list[dict]:
        """Sources of the given (similar) runs that verified facts, or that reflection suggested and nothing has
        contradicted yet; verified ones first."""
        if not run_ids:
            return []
        marks = ",".join("?" * len(run_ids))
        rows = self._query(
            f"SELECT DISTINCT s.* FROM sources s JOIN run_sources rs ON rs.key = s.key WHERE rs.run_id IN ({marks}) "
            "AND (s.verified > s.failed OR (s.suggested = 1 AND s.failed = 0)) "
            "ORDER BY s.verified > 0 DESC, s.fetched DESC, s.verified - s.failed DESC, s.last_used DESC LIMIT ?",
            (*run_ids, limit),
        )
        for r in rows:
            r["facts"] = json.loads(r["facts"] or "[]")
        return rows

    def recall(self, task: str) -> dict:
        runs = self.similar_runs(task)
        return {
            "similar_runs": [{"id": r["id"], "task": r["task"], "score": r["score"], "revisions": r["revisions"]} for r in runs],
            "lessons": [{"id": l["id"], "text": l["text"], "category": l["category"]} for l in self.relevant_lessons(task)],
            "trusted_sources": [
                {"url": s["url"], "title": s["title"], "verified": s["verified"], "fetched": bool(s["fetched"]),
                 "suggested": bool(s["suggested"]), "facts": s["facts"]}
                for s in self.trusted_sources([r["id"] for r in runs])
            ],
        }

    # ---- write --------------------------------------------------------------------------------------------

    def save_run(self, task: str, score: int, verdict: str, revisions: int, report_path: str = "") -> int:
        with closing(self._connect()) as con, con:
            cur = con.execute(
                "INSERT INTO runs (task, score, verdict, revisions, report_path) VALUES (?, ?, ?, ?, ?)",
                (task, score, verdict, revisions, report_path),
            )
            return cur.lastrowid

    def set_run_tokens(self, run_id: int, tokens: int) -> None:
        with closing(self._connect()) as con, con:
            con.execute("UPDATE runs SET tokens = ? WHERE id = ?", (tokens, run_id))

    def add_lesson(self, run_id: int, text: str, category: str, keywords: list[str]) -> tuple[int, bool]:
        """Insert a lesson, or count a repeat of a near-identical one. Returns (lesson_id, is_new)."""
        new_terms = terms(text)
        for existing in self._query("SELECT id, text FROM lessons"):
            if _jaccard(new_terms, terms(existing["text"])) >= DUPLICATE_OVERLAP:
                with closing(self._connect()) as con, con:
                    con.execute("UPDATE lessons SET times_seen = times_seen + 1 WHERE id = ?", (existing["id"],))
                return existing["id"], False
        kw = " ".join(sorted({w for k in keywords for w in terms(k)}))
        with closing(self._connect()) as con, con:
            cur = con.execute(
                "INSERT INTO lessons (run_id, text, category, keywords) VALUES (?, ?, ?, ?)", (run_id, text, category, kw)
            )
            return cur.lastrowid, True

    def mark_lessons_used(self, run_id: int, lesson_ids: list[int], helpful: bool) -> None:
        with closing(self._connect()) as con, con:
            for lid in lesson_ids:
                con.execute("INSERT OR IGNORE INTO run_lessons (run_id, lesson_id) VALUES (?, ?)", (run_id, lid))
                con.execute(
                    "UPDATE lessons SET times_used = times_used + 1, times_helpful = times_helpful + ? WHERE id = ?",
                    (int(helpful), lid),
                )

    def record_sources(self, run_id: int, outcomes: list[dict]) -> None:
        """outcomes: [{key, url, domain, title, fetched, verified, failed, facts, suggested?}]: sources cited in this
        run, plus pages reflection suggested."""
        with closing(self._connect()) as con, con:
            for o in outcomes:
                row = con.execute("SELECT facts FROM sources WHERE key = ?", (o["key"],)).fetchone()
                old_facts = json.loads(row["facts"]) if row else []
                facts = list(dict.fromkeys(o["facts"] + old_facts))[:MAX_FACTS]
                con.execute(
                    "INSERT INTO sources (key, url, domain, title, verified, failed, fetched, suggested, facts) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET url = excluded.url, title = COALESCE(NULLIF(excluded.title, ''), title), "
                    "verified = verified + excluded.verified, failed = failed + excluded.failed, "
                    "fetched = MAX(fetched, excluded.fetched), suggested = MAX(suggested, excluded.suggested), "
                    "facts = excluded.facts, last_used = datetime('now')",
                    (o["key"], o["url"], o["domain"], o["title"], o["verified"], o["failed"], int(o["fetched"]),
                     int(o.get("suggested", False)), json.dumps(facts)),
                )
                con.execute(
                    "INSERT OR REPLACE INTO run_sources (run_id, key, verified, failed) VALUES (?, ?, ?, ?)",
                    (run_id, o["key"], o["verified"], o["failed"]),
                )

    # ---- inspection (CLI script, Memory tab) --------------------------------------------------------------

    def runs(self) -> list[dict]:
        return self._query("SELECT * FROM runs ORDER BY id")

    def lessons(self) -> list[dict]:
        return self._query("SELECT * FROM lessons ORDER BY times_helpful DESC, times_seen DESC, id")

    def sources(self) -> list[dict]:
        return self._query("SELECT * FROM sources ORDER BY verified - failed DESC, last_used DESC")
