"""
memory.py
Persistent session memory using SQLite. Backs three features:
  1. Conversation history (so follow-up questions have context)
  2. Coverage tracking (which doc/page combos have been discussed)
  3. Source material for "quiz me on what we covered" generation
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/memory.db")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qa_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            question TEXT,
            answer TEXT,
            citations TEXT,     -- JSON list of {doc_name, page_number}
            refused INTEGER
        )
    """)
    conn.commit()
    conn.close()


def log_turn(question: str, answer: str, citations: list, refused: bool):
    conn = get_connection()
    conn.execute(
        "INSERT INTO qa_log (timestamp, question, answer, citations, refused) VALUES (?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), question, answer, json.dumps(citations), int(refused)),
    )
    conn.commit()
    conn.close()


def get_recent_history(n: int = 5):
    conn = get_connection()
    rows = conn.execute(
        "SELECT question, answer FROM qa_log ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [{"question": r["question"], "answer": r["answer"]} for r in reversed(rows)]


def get_full_log():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM qa_log ORDER BY id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_covered_pages():
    """Returns the set of (doc_name, page_number) pairs that have been
    cited in answers so far this session -- used for the coverage sidebar."""
    conn = get_connection()
    rows = conn.execute("SELECT citations FROM qa_log WHERE refused = 0").fetchall()
    conn.close()

    covered = set()
    for r in rows:
        for c in json.loads(r["citations"]):
            covered.add((c["doc_name"], c["page_number"]))
    return covered


def get_recently_cited_chunks(n_turns: int = 3):
    """Used to source material for grounded quiz generation -- pulls the
    citations from the last few non-refused answers."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT citations FROM qa_log WHERE refused = 0 ORDER BY id DESC LIMIT ?",
        (n_turns,),
    ).fetchall()
    conn.close()

    all_citations = []
    for r in rows:
        all_citations.extend(json.loads(r["citations"]))
    return all_citations


def clear_session():
    conn = get_connection()
    conn.execute("DELETE FROM qa_log")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Initialized memory DB at {DB_PATH}")
