from __future__ import annotations

import json
import shutil
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ResearchDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'historical place',
                    pixel_x REAL NOT NULL,
                    pixel_y REAL NOT NULL,
                    x1 REAL,
                    y1 REAL,
                    x2 REAL,
                    y2 REAL,
                    crop_path TEXT NOT NULL DEFAULT '',
                    crop_blob BLOB,
                    raw_ocr TEXT NOT NULL DEFAULT '',
                    transcription TEXT NOT NULL DEFAULT '',
                    transliteration TEXT NOT NULL DEFAULT '',
                    translation TEXT NOT NULL DEFAULT '',
                    translation_provenance TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    status TEXT NOT NULL DEFAULT 'unreviewed',
                    notes TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    longitude REAL,
                    latitude REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS control_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'historical place',
                    pixel_x REAL NOT NULL,
                    pixel_y REAL NOT NULL,
                    longitude REAL NOT NULL,
                    latitude REAL NOT NULL,
                    source_reasoning TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    notes TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transformations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    method TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    diagnostics_json TEXT NOT NULL,
                    control_point_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_records_project ON records(project_id);
                CREATE INDEX IF NOT EXISTS idx_control_points_project ON control_points(project_id);
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            record_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(records)").fetchall()
            }
            if "crop_blob" not in record_columns:
                connection.execute("ALTER TABLE records ADD COLUMN crop_blob BLOB")
            count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            if count == 0:
                now = utc_now()
                connection.execute(
                    "INSERT INTO projects(name, description, created_at, updated_at) VALUES(?,?,?,?)",
                    (
                        "Fra Mauro study",
                        "Private research project. Geographic matches are hypotheses until reviewed.",
                        now,
                        now,
                    ),
                )

    def projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def add_project(self, name: str, description: str = "") -> int:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO projects(name, description, created_at, updated_at) VALUES(?,?,?,?)",
                (name.strip(), description.strip(), now, now),
            )
            return int(cursor.lastrowid)

    def records(self, project_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM records WHERE project_id=? ORDER BY updated_at DESC", (project_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_record(self, record_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        return dict(row) if row else None

    def save_record(self, project_id: int, values: dict[str, Any], record_id: int | None = None) -> int:
        now = utc_now()
        fields = (
            "title", "category", "pixel_x", "pixel_y", "x1", "y1", "x2", "y2",
            "crop_path", "crop_blob", "raw_ocr", "transcription", "transliteration", "translation",
            "translation_provenance", "confidence", "status", "notes", "tags",
            "longitude", "latitude",
        )
        data = [values.get(field) for field in fields]
        with self.connect() as connection:
            if record_id is None:
                placeholders = ",".join("?" for _ in fields)
                cursor = connection.execute(
                    f"INSERT INTO records(project_id,{','.join(fields)},created_at,updated_at) "
                    f"VALUES(?,{placeholders},?,?)",
                    [project_id, *data, now, now],
                )
                return int(cursor.lastrowid)
            assignments = ",".join(f"{field}=?" for field in fields)
            connection.execute(
                f"UPDATE records SET {assignments}, updated_at=? WHERE id=? AND project_id=?",
                [*data, now, record_id, project_id],
            )
            return record_id

    def delete_record(self, project_id: int, record_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM records WHERE id=? AND project_id=?", (record_id, project_id)
            )

    def search_records(
        self,
        project_id: int,
        query: str,
        status: str = "All",
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM records WHERE project_id=? AND confidence>=?"
        parameters: list[Any] = [project_id, min_confidence]
        if status != "All":
            sql += " AND status=?"
            parameters.append(status)
        with self.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        records = [dict(row) for row in rows]

        def normalize(value: str) -> str:
            decomposed = unicodedata.normalize("NFKD", value.casefold())
            return "".join(character for character in decomposed if not unicodedata.combining(character))

        needle = normalize(query.strip())
        if not needle:
            return sorted(records, key=lambda row: (row["confidence"], row["updated_at"]), reverse=True)
        fields = ("title", "raw_ocr", "transcription", "transliteration", "translation", "tags")
        matches = []
        for record in records:
            values = [normalize(str(record.get(field) or "")) for field in fields]
            if any(needle == value for value in values):
                record["_match_type"] = "exact"
                record["_match_score"] = 1.0
            elif any(needle in value for value in values):
                record["_match_type"] = "partial"
                record["_match_score"] = 0.9
            else:
                score = max(
                    (SequenceMatcher(None, needle, token).ratio() for value in values for token in value.split()),
                    default=0.0,
                )
                if score < 0.68:
                    continue
                record["_match_type"] = "fuzzy"
                record["_match_score"] = score
            matches.append(record)
        return sorted(
            matches,
            key=lambda row: (row["_match_score"], row["confidence"], row["updated_at"]),
            reverse=True,
        )

    def control_points(self, project_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM control_points WHERE project_id=? ORDER BY id", (project_id,)
            ).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["enabled"] = bool(row["enabled"])
        return result

    def save_control_point(
        self, project_id: int, values: dict[str, Any], point_id: int | None = None
    ) -> int:
        now = utc_now()
        fields = (
            "name", "category", "pixel_x", "pixel_y", "longitude", "latitude",
            "source_reasoning", "confidence", "notes", "enabled",
        )
        data = [values.get(field) for field in fields]
        data[-1] = int(bool(data[-1]))
        with self.connect() as connection:
            if point_id is None:
                placeholders = ",".join("?" for _ in fields)
                cursor = connection.execute(
                    f"INSERT INTO control_points(project_id,{','.join(fields)},created_at,updated_at) "
                    f"VALUES(?,{placeholders},?,?)",
                    [project_id, *data, now, now],
                )
                return int(cursor.lastrowid)
            assignments = ",".join(f"{field}=?" for field in fields)
            connection.execute(
                f"UPDATE control_points SET {assignments}, updated_at=? WHERE id=? AND project_id=?",
                [*data, now, point_id, project_id],
            )
            return point_id

    def delete_control_point(self, project_id: int, point_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM control_points WHERE id=? AND project_id=?", (point_id, project_id)
            )

    def save_transformation(
        self, project_id: int, parameters: dict, diagnostics: dict, point_ids: list[int]
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO transformations(
                    project_id, method, parameters_json, diagnostics_json,
                    control_point_ids_json, created_at
                ) VALUES(?,?,?,?,?,?)""",
                (
                    project_id,
                    "affine",
                    json.dumps(parameters),
                    json.dumps(diagnostics),
                    json.dumps(point_ids),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def transformations(self, project_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM transformations WHERE project_id=? ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def backup_bytes(self) -> bytes:
        return self.path.read_bytes()

    def restore_bytes(self, payload: bytes) -> None:
        temporary = self.path.with_suffix(".restore")
        temporary.write_bytes(payload)
        try:
            with sqlite3.connect(temporary) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise ValueError(f"SQLite integrity check failed: {result}")
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                required = {"projects", "records", "control_points", "transformations"}
                if not required.issubset(tables):
                    raise ValueError("This is not a Fra Mauro project database.")
            shutil.move(temporary, self.path)
            self.initialize()
        finally:
            temporary.unlink(missing_ok=True)
