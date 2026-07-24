"""Local SQLite persistence (stdlib sqlite3) for analyses (by analysis_id) and logged meals."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH


def _init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                analysis_id TEXT PRIMARY KEY,
                patient_id TEXT,
                meal_type TEXT,
                kind TEXT NOT NULL,
                foods_json TEXT NOT NULL,
                needs_confirmation_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meals (
                meal_id TEXT PRIMARY KEY,
                patient_id TEXT,
                timestamp TEXT,
                meal_type TEXT,
                foods_json TEXT NOT NULL,
                nutrition_json TEXT NOT NULL,
                logged_at TEXT NOT NULL
            )
            """
        )


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


_init_db()


def save_analysis(
    analysis_id: str,
    patient_id: str | None,
    meal_type: str | None,
    kind: str,
    foods: list[dict],
    needs_confirmation: dict,
    created_at: str,
) -> None:
    """kind is 'meal' (Tool 1) or 'completion' (Tool 2) — resolve_meal_clarification doesn't care which."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO analyses
                (analysis_id, patient_id, meal_type, kind, foods_json, needs_confirmation_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (analysis_id, patient_id, meal_type, kind, json.dumps(foods), json.dumps(needs_confirmation), created_at),
        )


def get_analysis(analysis_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT patient_id, meal_type, kind, foods_json, needs_confirmation_json, created_at "
            "FROM analyses WHERE analysis_id = ?",
            (analysis_id,),
        ).fetchone()
    if row is None:
        return None
    patient_id, meal_type, kind, foods_json, needs_confirmation_json, created_at = row
    return {
        "analysis_id": analysis_id,
        "patient_id": patient_id,
        "meal_type": meal_type,
        "kind": kind,
        "foods": json.loads(foods_json),
        "needs_confirmation": json.loads(needs_confirmation_json),
        "created_at": created_at,
    }


def save_meal(
    meal_id: str,
    patient_id: str | None,
    timestamp: str | None,
    meal_type: str | None,
    foods: list[dict],
    nutrition: dict,
    logged_at: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO meals
                (meal_id, patient_id, timestamp, meal_type, foods_json, nutrition_json, logged_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (meal_id, patient_id, timestamp, meal_type, json.dumps(foods), json.dumps(nutrition), logged_at),
        )


def log_meal_impl(patient_id: str, timestamp: str, meal_type: str, foods: list[dict], nutrition: dict) -> dict:
    """Tool 5 (log_meal): persists the meal and returns {meal_id, status}."""
    meal_id = uuid.uuid4().hex
    save_meal(
        meal_id=meal_id,
        patient_id=patient_id,
        timestamp=timestamp,
        meal_type=meal_type,
        foods=foods,
        nutrition=nutrition,
        logged_at=datetime.now(timezone.utc).isoformat(),
    )
    return {"meal_id": meal_id, "status": "logged"}
