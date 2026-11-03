from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from .contract import normalize_state


class StateStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS bindings (
                session_id TEXT PRIMARY KEY,
                package_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS states (
                session_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                package_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, member_id, package_id)
            );
            CREATE TABLE IF NOT EXISTS nsfw (
                session_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (session_id, member_id)
            );
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                package_id TEXT NOT NULL,
                action TEXT NOT NULL,
                event_id TEXT,
                success INTEGER NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS state_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                package_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS state_versions (
                session_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                package_id TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (session_id, member_id, package_id)
            );
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def bind(self, session_id: str, package_id: str | None) -> None:
        if package_id is None:
            self.db.execute("DELETE FROM bindings WHERE session_id = ?", (session_id,))
        else:
            self.db.execute("INSERT INTO bindings(session_id, package_id) VALUES (?, ?) ON CONFLICT(session_id) DO UPDATE SET package_id=excluded.package_id", (session_id, package_id))
        self.db.commit()

    def binding(self, session_id: str) -> str | None:
        row = self.db.execute("SELECT package_id FROM bindings WHERE session_id = ?", (session_id,)).fetchone()
        return str(row[0]) if row else None

    def state(self, session_id: str, member_id: str, package_id: str, initial: dict[str, Any]) -> dict[str, Any]:
        row = self.db.execute("SELECT state_json FROM states WHERE session_id = ? AND member_id = ? AND package_id = ?", (session_id, member_id, package_id)).fetchone()
        return normalize_state(json.loads(row[0]), initial) if row else deepcopy(initial)

    def save_state(self, session_id: str, member_id: str, package_id: str, state: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO states(session_id, member_id, package_id, state_json) VALUES (?, ?, ?, ?) ON CONFLICT(session_id, member_id, package_id) DO UPDATE SET state_json=excluded.state_json, updated_at=CURRENT_TIMESTAMP",
            (session_id, member_id, package_id, json.dumps(state, ensure_ascii=False)),
        )
        self._advance_revision(session_id, member_id, package_id)
        self.db.commit()

    def revision(self, session_id: str, member_id: str, package_id: str) -> int:
        row = self.db.execute("SELECT revision FROM state_versions WHERE session_id = ? AND member_id = ? AND package_id = ?", (session_id, member_id, package_id)).fetchone()
        return int(row[0]) if row else 0

    def _advance_revision(self, session_id: str, member_id: str, package_id: str) -> None:
        self.db.execute(
            "INSERT INTO state_versions(session_id, member_id, package_id, revision) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(session_id, member_id, package_id) DO UPDATE SET revision=revision+1",
            (session_id, member_id, package_id),
        )

    def save_turn(
        self, session_id: str, member_id: str, package_id: str,
        previous: dict[str, Any], state: dict[str, Any], initial: dict[str, Any],
        expected_revision: int | None = None,
    ) -> bool:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if expected_revision is not None and self.revision(session_id, member_id, package_id) != expected_revision:
                return False
            if self.state(session_id, member_id, package_id, initial) != previous:
                return False
            payload = json.dumps(state, ensure_ascii=False)
            self.db.execute(
                "INSERT INTO states(session_id, member_id, package_id, state_json) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id, member_id, package_id) DO UPDATE SET state_json=excluded.state_json, updated_at=CURRENT_TIMESTAMP",
                (session_id, member_id, package_id, payload),
            )
            self.db.execute(
                "INSERT INTO state_history(session_id, member_id, package_id, state_json) VALUES (?, ?, ?, ?)",
                (session_id, member_id, package_id, payload),
            )
            self._advance_revision(session_id, member_id, package_id)
        return True

    def reset_state(self, session_id: str, member_id: str, package_id: str) -> None:
        self.db.execute("DELETE FROM states WHERE session_id = ? AND member_id = ? AND package_id = ?", (session_id, member_id, package_id))
        self._advance_revision(session_id, member_id, package_id)
        self.db.commit()

    def nsfw_enabled(self, session_id: str, member_id: str) -> bool:
        row = self.db.execute("SELECT enabled FROM nsfw WHERE session_id = ? AND member_id = ?", (session_id, member_id)).fetchone()
        return bool(row[0]) if row else False

    def set_nsfw(self, session_id: str, member_id: str, enabled: bool) -> None:
        self.db.execute("INSERT INTO nsfw(session_id, member_id, enabled) VALUES (?, ?, ?) ON CONFLICT(session_id, member_id) DO UPDATE SET enabled=excluded.enabled", (session_id, member_id, int(enabled)))
        self.db.commit()

    def audit(self, session_id: str, member_id: str, package_id: str, action: str, event_id: str | None, success: bool, error: str | None = None) -> None:
        self.db.execute("INSERT INTO audits(session_id, member_id, package_id, action, event_id, success, error) VALUES (?, ?, ?, ?, ?, ?, ?)", (session_id, member_id, package_id, action, event_id, int(success), error))
        self.db.commit()

    def recent_audits(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT session_id, member_id, package_id, action, event_id, success, error, created_at FROM audits ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def state_rows(
        self,
        session_id: str | None = None,
        member_id: str | None = None,
        package_id: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = []
        values: list[str] = []
        for column, value in (
            ("session_id", session_id),
            ("member_id", member_id),
            ("package_id", package_id),
        ):
            if value:
                filters.append(f"{column} = ?")
                values.append(value)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        rows = self.db.execute(
            "SELECT session_id, member_id, package_id, state_json, updated_at "
            f"FROM states{where} ORDER BY updated_at DESC",
            values,
        ).fetchall()
        return [
            {
                **dict(row),
                "state": json.loads(row["state_json"]),
                "nsfw_enabled": self.nsfw_enabled(row["session_id"], row["member_id"]),
            }
            for row in rows
        ]

    def binding_rows(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id:
            rows = self.db.execute(
                "SELECT session_id, package_id FROM bindings WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT session_id, package_id FROM bindings ORDER BY session_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def has_binding(self, package_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM bindings WHERE package_id = ? LIMIT 1",
            (package_id,),
        ).fetchone()
        return row is not None

