"""SQLite database — history, hotwords, correction rules, dictionary."""
from __future__ import annotations
import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Optional

from infrastructure.paths import database_path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 6

CREATE_TABLES = [
    """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY
    )""",
    """CREATE TABLE IF NOT EXISTS history (
        id TEXT PRIMARY KEY,
        raw_text TEXT NOT NULL DEFAULT '',
        refined_text TEXT NOT NULL DEFAULT '',
        normalized_text TEXT NOT NULL DEFAULT '',
        final_text TEXT NOT NULL DEFAULT '',
        app_name TEXT NOT NULL DEFAULT '',
        app_exe TEXT NOT NULL DEFAULT '',
        window_title TEXT NOT NULL DEFAULT '',
        window_class TEXT NOT NULL DEFAULT '',
        duration REAL NOT NULL DEFAULT 0.0,
        language TEXT NOT NULL DEFAULT 'zh-CN',
        language_label TEXT NOT NULL DEFAULT '中文',
        pasted INTEGER NOT NULL DEFAULT 0,
        error_msg TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        user_id TEXT,
        status TEXT,
        mode TEXT NOT NULL DEFAULT 'voice_transcript',
        mode_meta BLOB,
        client_metadata BLOB,
        audio_local_path TEXT,
        audio_metadata TEXT,
        mic_device_info BLOB,
        debug_info TEXT,
        audio_context TEXT,
        edited_text TEXT,
        edited_text_status TEXT NOT NULL DEFAULT 'NOT_EXTRACTED',
        edited_text_attempts INTEGER NOT NULL DEFAULT 0,
        hasRevertedAI INTEGER,
        ax_text TEXT,
        ax_html TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS dictionary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT NOT NULL UNIQUE,
        pinyin TEXT NOT NULL DEFAULT '',
        added_at TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS correction_rules (
        id TEXT PRIMARY KEY,
        pattern TEXT NOT NULL,
        replacement TEXT NOT NULL,
        source_type TEXT NOT NULL DEFAULT 'user_edit',
        source_history_id TEXT,
        confidence REAL NOT NULL DEFAULT 0.4,
        match_count INTEGER NOT NULL DEFAULT 1,
        apply_count INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        is_regex INTEGER NOT NULL DEFAULT 0,
        context_app TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )""",
]

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_history_app ON history(app_exe)",
    "CREATE INDEX IF NOT EXISTS idx_dict_word ON dictionary(word)",
    "CREATE INDEX IF NOT EXISTS idx_rules_pattern ON correction_rules(pattern)",
    "CREATE INDEX IF NOT EXISTS idx_rules_active ON correction_rules(is_active)",
]


class Database:
    """Thread-safe SQLite database singleton."""

    _instance: Optional["Database"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "Database":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._db_lock = threading.RLock()
        self._db_path = database_path()
        self._migrate()

    # ── Connection management ────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _migrate(self):
        with self._db_lock:
            conn = self._get_conn()
            try:
                for stmt in CREATE_TABLES:
                    conn.execute(stmt)
                # Check / set schema version
                cur = conn.execute("SELECT MAX(version) FROM schema_version")
                row = cur.fetchone()
                current = row[0] if row and row[0] else 0
                # Migration: add language column if missing (v1 → v2)
                if current < 2:
                    try:
                        conn.execute("ALTER TABLE history ADD COLUMN language TEXT NOT NULL DEFAULT 'zh-CN'")
                    except Exception:
                        pass  # column already exists
                    try:
                        conn.execute("ALTER TABLE history ADD COLUMN language_label TEXT NOT NULL DEFAULT '中文'")
                    except Exception:
                        pass
                # Migration v2→v3: Typeless history_v2 columns
                if current < 3:
                    for col in ['user_id','status','mode','mode_meta','client_metadata',
                                'audio_local_path','audio_metadata','mic_device_info','debug_info','audio_context',
                                'edited_text','edited_text_status','edited_text_attempts','hasRevertedAI','ax_text','ax_html']:
                        try: conn.execute(f'ALTER TABLE history ADD COLUMN {col} TEXT')
                        except: pass
                if current < 4:
                    self._backfill_empty_history_ids(conn)
                    try:
                        conn.execute("ALTER TABLE correction_rules ADD COLUMN context_app TEXT DEFAULT ''")
                    except Exception:
                        pass
                if current < 5:
                    self._migrate_history_id_to_text(conn)
                if current < 6:
                    # Phase 5: hotword promotion needs to track the set of
                    # distinct history_ids a rule has appeared in (one
                    # source_history_id per row is not enough) and a flag
                    # for already-promoted rules so re-scan is idempotent.
                    for col, decl in [
                        ("source_history_ids", "TEXT DEFAULT '[]'"),
                        ("promoted", "INTEGER NOT NULL DEFAULT 0"),
                    ]:
                        try:
                            conn.execute(
                                f"ALTER TABLE correction_rules ADD COLUMN {col} {decl}")
                        except Exception:
                            pass  # column already exists
                for stmt in CREATE_INDEXES:
                    conn.execute(stmt)
                if current < SCHEMA_VERSION:
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                        (SCHEMA_VERSION,))
                conn.commit()
                logger.info("Database migrated to version %d at %s", SCHEMA_VERSION, self._db_path)
            except Exception as e:
                conn.rollback()
                logger.error("Database migration failed: %s", e)
                raise
            finally:
                conn.close()

    # ── History ──────────────────────────────────────────────

    def add_history(self, raw_text: str, refined_text: str = "",
                    normalized_text: str = "", final_text: str = "",
                    app_name: str = "", app_exe: str = "",
                    window_title: str = "", window_class: str = "",
                    duration: float = 0.0, language: str = "zh-CN",
                    language_label: str = "中文",
                    pasted: bool = False, error_msg: str = "",
                    status: str = "completed", debug_info: str = "") -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._db_lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    ("""INSERT INTO history (id, raw_text, refined_text, normalized_text,
                        final_text, app_name, app_exe, window_title, window_class,
                        duration, language, language_label, pasted, error_msg, created_at,
                        status, debug_info)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
                     if self._history_id_is_text(conn)
                     else """INSERT INTO history (raw_text, refined_text, normalized_text,
                        final_text, app_name, app_exe, window_title, window_class,
                        duration, language, language_label, pasted, error_msg, created_at,
                        status, debug_info)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""),
                    ((uuid.uuid4().hex, raw_text, refined_text, normalized_text, final_text,
                      app_name, app_exe, window_title, window_class,
                      duration, language, language_label, int(pasted), error_msg, now,
                      status, debug_info)
                     if self._history_id_is_text(conn)
                     else (raw_text, refined_text, normalized_text, final_text,
                           app_name, app_exe, window_title, window_class,
                           duration, language, language_label, int(pasted), error_msg, now,
                           status, debug_info)))
                conn.commit()
                if self._history_id_is_text(conn):
                    return conn.execute("SELECT id FROM history WHERE rowid = ?", (cur.lastrowid,)).fetchone()[0]
                return cur.lastrowid
            finally:
                conn.close()

    def get_history(self, search: str = "", limit: int = 100,
                    offset: int = 0) -> list[dict]:
        with self._db_lock:
            conn = self._get_conn()
            try:
                if search:
                    kw = f"%{search}%"
                    cur = conn.execute(
                        """SELECT * FROM history
                           WHERE final_text LIKE ? OR raw_text LIKE ? OR app_name LIKE ?
                           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                        (kw, kw, kw, limit, offset))
                else:
                    cur = conn.execute(
                        "SELECT * FROM history ORDER BY created_at DESC LIMIT ? OFFSET ?",
                        (limit, offset))
                return [dict(row) for row in cur.fetchall()]
            finally:
                conn.close()

    def update_history_text(self, entry_id: int, final_text: str):
        with self._db_lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """UPDATE history
                       SET final_text = ?,
                           edited_text = ?,
                           edited_text_status = 'MANUAL_EDITED',
                           edited_text_attempts = COALESCE(edited_text_attempts, 0) + 1
                       WHERE id = ?""",
                    (final_text, final_text, entry_id))
                conn.commit()
            finally:
                conn.close()

    def get_history_entry(self, entry_id: int | str) -> Optional[dict]:
        with self._db_lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("SELECT * FROM history WHERE id = ?", (entry_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def _backfill_empty_history_ids(self, conn: sqlite3.Connection):
        try:
            rows = conn.execute(
                "SELECT rowid FROM history WHERE id IS NULL OR id = ''"
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE history SET id = ? WHERE rowid = ?",
                    (uuid.uuid4().hex, row["rowid"]))
            if rows:
                logger.info("Database backfilled %d empty history ids", len(rows))
        except Exception as e:
            logger.warning("Database history id backfill failed: %s", e)

    def _history_id_is_text(self, conn: sqlite3.Connection) -> bool:
        try:
            cols = conn.execute("PRAGMA table_info(history)").fetchall()
            for col in cols:
                if col["name"] == "id":
                    return "TEXT" in str(col["type"] or "").upper()
        except Exception:
            pass
        return False

    def _migrate_history_id_to_text(self, conn: sqlite3.Connection):
        """Rebuild legacy integer-id history table as TEXT ids."""
        if self._history_id_is_text(conn):
            return
        backup = f"history_int_id_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info("Database migrating history.id to TEXT via %s", backup)
        old_cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(history)").fetchall()}
        conn.execute(f'ALTER TABLE history RENAME TO "{backup}"')
        conn.execute(CREATE_TABLES[1])
        new_cols = conn.execute("PRAGMA table_info(history)").fetchall()
        insert_cols = ["id"]
        select_exprs = ['COALESCE(CAST("id" AS TEXT), hex(randomblob(16)))']
        for col in new_cols:
            name = col["name"]
            if name == "id" or name not in old_cols:
                continue
            insert_cols.append(name)
            if col["notnull"]:
                default = col["dflt_value"] if col["dflt_value"] is not None else "''"
                select_exprs.append(f'COALESCE("{name}", {default})')
            else:
                select_exprs.append(f'"{name}"')
        quoted_insert_cols = ", ".join(f'"{c}"' for c in insert_cols)
        conn.execute(
            f'INSERT INTO history ({quoted_insert_cols}) '
            f'SELECT {", ".join(select_exprs)} FROM "{backup}"'
        )
        conn.execute(f'DROP TABLE "{backup}"')

    def update_history_edit(self, entry_id: int | str, edited_text: str,
                            status: str, attempts_delta: int = 1):
        with self._db_lock:
            conn = self._get_conn()
            try:
                if edited_text is None:
                    conn.execute(
                        """UPDATE history
                           SET edited_text_status = ?,
                               edited_text_attempts = COALESCE(edited_text_attempts, 0) + ?
                           WHERE id = ?""",
                        (status, int(attempts_delta), entry_id))
                    conn.commit()
                    return
                conn.execute(
                    """UPDATE history
                       SET edited_text = ?,
                           edited_text_status = ?,
                           edited_text_attempts = COALESCE(edited_text_attempts, 0) + ?
                       WHERE id = ?""",
                    (edited_text or "", status, int(attempts_delta), entry_id))
                conn.commit()
            finally:
                conn.close()

    def delete_history(self, entry_id: int):
        with self._db_lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM history WHERE id = ?", (entry_id,))
                conn.commit()
            finally:
                conn.close()

    def cleanup_history(self, max_count: int = 1000, max_days: int = 90):
        with self._db_lock:
            conn = self._get_conn()
            try:
                # Delete by age
                conn.execute(
                    "DELETE FROM history WHERE created_at < datetime('now', ?)",
                    (f'-{max_days} days',))
                # Delete by count (keep newest max_count)
                conn.execute(
                    """DELETE FROM history WHERE id NOT IN
                       (SELECT id FROM history ORDER BY created_at DESC LIMIT ?)""",
                    (max_count,))
                conn.commit()
            finally:
                conn.close()

    def count_history(self, search: str = "") -> int:
        with self._db_lock:
            conn = self._get_conn()
            try:
                if search:
                    kw = f"%{search}%"
                    cur = conn.execute(
                        "SELECT COUNT(*) FROM history WHERE final_text LIKE ? OR raw_text LIKE ?",
                        (kw, kw))
                else:
                    cur = conn.execute("SELECT COUNT(*) FROM history")
                return cur.fetchone()[0]
            finally:
                conn.close()

    # ── Dictionary ───────────────────────────────────────────

    def get_dictionary(self) -> list[str]:
        with self._db_lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("SELECT word FROM dictionary ORDER BY added_at DESC")
                return [row[0] for row in cur.fetchall()]
            finally:
                conn.close()

    def add_dictionary_word(self, word: str, pinyin: str = "") -> bool:
        now = datetime.now().isoformat()
        with self._db_lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO dictionary (word, pinyin, added_at) VALUES (?,?,?)",
                    (word, pinyin, now))
                conn.commit()
                return conn.total_changes > 0
            finally:
                conn.close()

    def remove_dictionary_word(self, word: str):
        with self._db_lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM dictionary WHERE word = ?", (word,))
                conn.commit()
            finally:
                conn.close()

    def clear_dictionary(self):
        with self._db_lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM dictionary")
                conn.commit()
            finally:
                conn.close()

    # ── Correction Rules ─────────────────────────────────────

    def get_rules(self, active_only: bool = False) -> list[dict]:
        with self._db_lock:
            conn = self._get_conn()
            try:
                if active_only:
                    cur = conn.execute(
                        "SELECT * FROM correction_rules WHERE is_active = 1")
                else:
                    cur = conn.execute("SELECT * FROM correction_rules")
                rules: list[dict] = []
                for row in cur.fetchall():
                    d = dict(row)
                    # source_history_ids is stored as JSON text — decode for
                    # the caller. Backwards-compatible: missing/empty column
                    # falls back to source_history_id (singleton list).
                    raw = d.get("source_history_ids") or "[]"
                    try:
                        ids = json.loads(raw) if isinstance(raw, str) else list(raw)
                    except Exception:
                        ids = []
                    if not ids and d.get("source_history_id"):
                        ids = [d["source_history_id"]]
                    d["source_history_ids"] = [str(x) for x in ids if x]
                    d["promoted"] = bool(d.get("promoted", 0))
                    rules.append(d)
                return rules
            finally:
                conn.close()

    def merge_rules(self, new_rules: list[dict]) -> int:
        """Merge new rules, incrementing confidence for existing matches.

        For Phase 5 hotword promotion we additionally accumulate the SET of
        distinct ``source_history_id`` values that contributed evidence for
        each ``(pattern, replacement)``. Re-scanning the same history does
        not grow the set — that is the entire point of distinct-evidence
        gating.
        """
        count = 0
        with self._db_lock:
            conn = self._get_conn()
            try:
                for rule in new_rules:
                    cur = conn.execute(
                        "SELECT * FROM correction_rules WHERE pattern = ? AND replacement = ?",
                        (rule['pattern'], rule['replacement']))
                    existing = cur.fetchone()
                    new_hid = rule.get('source_history_id')
                    if existing:
                        # Pull existing set, add new history id if present.
                        existing_d = dict(existing)
                        raw = existing_d.get("source_history_ids") or "[]"
                        try:
                            ids = json.loads(raw) if isinstance(raw, str) else list(raw)
                        except Exception:
                            ids = []
                        # Backfill from legacy single-id column on the very
                        # first merge after the schema upgrade.
                        if not ids and existing_d.get("source_history_id"):
                            ids = [existing_d["source_history_id"]]
                        if new_hid and str(new_hid) not in {str(x) for x in ids}:
                            ids.append(str(new_hid))
                        new_conf = min(0.95, existing['confidence'] + 0.15)
                        new_count = existing['match_count'] + 1
                        conn.execute(
                            """UPDATE correction_rules
                               SET confidence=?, match_count=?, updated_at=?,
                                   source_history_ids=?
                               WHERE id=?""",
                            (new_conf, new_count, datetime.now().isoformat(),
                             json.dumps(ids), existing['id']))
                    else:
                        ids = [str(new_hid)] if new_hid else []
                        conn.execute(
                            """INSERT INTO correction_rules
                               (id, pattern, replacement, source_type, source_history_id,
                                confidence, match_count, apply_count, is_active, is_regex,
                                created_at, updated_at, source_history_ids, promoted)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (rule['id'], rule['pattern'], rule['replacement'],
                             rule.get('source_type', 'user_edit'),
                             rule.get('source_history_id'),
                             rule['confidence'], rule['match_count'], rule.get('apply_count', 0),
                             int(rule.get('is_active', True)),
                             int(rule.get('is_regex', False)),
                             rule.get('created_at', datetime.now().isoformat()),
                             rule.get('updated_at', datetime.now().isoformat()),
                             json.dumps(ids), 0))
                    count += 1
                conn.commit()
            finally:
                conn.close()
        return count

    def mark_rule_promoted(self, pattern: str, replacement: str) -> bool:
        """Flag a rule as already-promoted to the personal dictionary so
        re-scans skip it. Idempotent."""
        with self._db_lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    """UPDATE correction_rules SET promoted = 1, updated_at = ?
                       WHERE pattern = ? AND replacement = ?""",
                    (datetime.now().isoformat(), pattern, replacement))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def update_rule_stats(self, rule_id: str, applied: bool = True):
        with self._db_lock:
            conn = self._get_conn()
            try:
                if applied:
                    conn.execute(
                        "UPDATE correction_rules SET apply_count = apply_count + 1 WHERE id = ?",
                        (rule_id,))
                conn.commit()
            finally:
                conn.close()

    def update_rules_apply_counts(self, rule_ids: list[str]):
        if not rule_ids:
            return
        with self._db_lock:
            conn = self._get_conn()
            try:
                for rule_id in rule_ids:
                    conn.execute(
                        "UPDATE correction_rules SET apply_count = apply_count + 1 WHERE id = ?",
                        (rule_id,))
                conn.commit()
            finally:
                conn.close()

    # ── App Usage Stats ──────────────────────────────────────

    def get_app_stats(self, limit: int = 20) -> list[dict]:
        """Return top apps by usage count from history."""
        with self._db_lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    """SELECT app_exe, COUNT(*) as cnt
                       FROM history
                       WHERE app_exe != ''
                       GROUP BY app_exe
                       ORDER BY cnt DESC
                       LIMIT ?""", (limit,))
                return [{"app": row[0], "count": row[1]} for row in cur.fetchall()]
            finally:
                conn.close()
