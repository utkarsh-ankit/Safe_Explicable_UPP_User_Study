from __future__ import annotations

import json
import random
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: str) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str) -> None:
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_code TEXT UNIQUE NOT NULL,
                condition_name TEXT NOT NULL,
                domain_order_json TEXT NOT NULL,
                consented_at TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                completion_code TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id INTEGER NOT NULL,
                task_index INTEGER NOT NULL,
                domain_name TEXT NOT NULL,
                condition_name TEXT NOT NULL,
                trajectory_json TEXT NOT NULL,
                events_json TEXT NOT NULL,
                scores_json TEXT NOT NULL,
                response_time_ms INTEGER NOT NULL,
                confidence INTEGER,
                explanation TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(participant_id, task_index),
                FOREIGN KEY(participant_id) REFERENCES participants(id)
            );

            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id INTEGER UNIQUE NOT NULL,
                answers_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(participant_id) REFERENCES participants(id)
            );

            CREATE TABLE IF NOT EXISTS sanity_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id INTEGER NOT NULL,
                attempt_number INTEGER NOT NULL,
                challenge_token TEXT UNIQUE NOT NULL,
                questions_json TEXT NOT NULL,
                expected_json TEXT NOT NULL,
                answers_json TEXT,
                passed INTEGER,
                honeypot_triggered INTEGER NOT NULL DEFAULT 0,
                response_time_ms INTEGER,
                created_at TEXT NOT NULL,
                submitted_at TEXT,
                FOREIGN KEY(participant_id) REFERENCES participants(id)
            );
            """
        )


def _balanced_condition(conn: sqlite3.Connection) -> str:
    counts = {"full": 0, "partial": 0}
    for row in conn.execute(
        "SELECT condition_name, COUNT(*) AS n FROM participants GROUP BY condition_name"
    ):
        counts[row["condition_name"]] = int(row["n"])
    minimum = min(counts.values())
    candidates = [name for name, count in counts.items() if count == minimum]
    return random.choice(candidates)


def create_or_get_participant(path: str, participant_code: str, override: str | None = None) -> sqlite3.Row:
    participant_code = participant_code.strip()
    if not participant_code:
        participant_code = "P" + secrets.token_hex(4).upper()

    with connect(path) as conn:
        existing = conn.execute(
            "SELECT * FROM participants WHERE participant_code = ?", (participant_code,)
        ).fetchone()
        if existing:
            return existing

        condition = override if override in {"full", "partial"} else _balanced_condition(conn)
        domains = ["office", "search_recon"]
        random.shuffle(domains)
        completion_code = "SEP" + secrets.token_hex(3).upper()
        conn.execute(
            """
            INSERT INTO participants (
                participant_code, condition_name, domain_order_json,
                started_at, completion_code
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (participant_code, condition, json.dumps(domains), utc_now(), completion_code),
        )
        return conn.execute(
            "SELECT * FROM participants WHERE participant_code = ?", (participant_code,)
        ).fetchone()


def get_participant(path: str, participant_id: int) -> sqlite3.Row | None:
    with connect(path) as conn:
        return conn.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()


def mark_consent(path: str, participant_id: int) -> None:
    with connect(path) as conn:
        conn.execute(
            "UPDATE participants SET consented_at = COALESCE(consented_at, ?) WHERE id = ?",
            (utc_now(), participant_id),
        )


def has_passed_sanity(path: str, participant_id: int) -> bool:
    with connect(path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM sanity_checks
            WHERE participant_id = ? AND passed = 1
            LIMIT 1
            """,
            (participant_id,),
        ).fetchone()
        return row is not None


def has_failed_sanity(path: str, participant_id: int) -> bool:
    with connect(path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM sanity_checks
            WHERE participant_id = ?
              AND passed = 0
              AND submitted_at IS NOT NULL
            LIMIT 1
            """,
            (participant_id,),
        ).fetchone()
        return row is not None


def _new_sanity_questions(first_domain: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    groups = random.randint(3, 7)
    items_per_group = random.randint(2, 6)
    extra = random.randint(2, 9)

    if first_domain == "office":
        domain_question = {
            "id": "domain_question",
            "kind": "select",
            "prompt": "In the first task, what did the robot need to collect before going to office O?",
            "options": [
                {"value": "", "label": "Select an answer"},
                {"value": "coffee", "label": "Coffee"},
                {"value": "books", "label": "Books"},
                {"value": "tools", "label": "Tools"},
            ],
        }
        domain_answer = "coffee"
    else:
        domain_question = {
            "id": "domain_question",
            "kind": "select",
            "prompt": "In the first task, what did the robot need to do at locations A, B, C, and D?",
            "options": [
                {"value": "", "label": "Select an answer"},
                {"value": "photos", "label": "Take photographs"},
                {"value": "deliver", "label": "Deliver coffee"},
                {"value": "repair", "label": "Repair the walls"},
            ],
        }
        domain_answer = "photos"

    questions = [
        {
            "id": "math",
            "kind": "number",
            "prompt": f"What is ({groups} × {items_per_group}) + {extra}?",
        },
        {
            "id": "study_task",
            "kind": "select",
            "prompt": "What did you create in the first task?",
            "options": [
                {"value": "", "label": "Select an answer"},
                {"value": "route", "label": "A route for a robot"},
                {"value": "shopping", "label": "A shopping list"},
                {"value": "story", "label": "A short story"},
            ],
        },
        domain_question,
        {
            "id": "attention",
            "kind": "select",
            "prompt": "To show that you are reading carefully, select Triangle.",
            "options": [
                {"value": "", "label": "Select an answer"},
                {"value": "circle", "label": "Circle"},
                {"value": "triangle", "label": "Triangle"},
                {"value": "square", "label": "Square"},
            ],
        },
    ]
    expected = {
        "math": str((groups * items_per_group) + extra),
        "study_task": "route",
        "domain_question": domain_answer,
        "attention": "triangle",
    }
    return questions, expected


def get_or_create_sanity_challenge(path: str, participant_id: int) -> dict[str, Any]:
    with connect(path) as conn:
        existing = conn.execute(
            """
            SELECT *
            FROM sanity_checks
            WHERE participant_id = ? AND submitted_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (participant_id,),
        ).fetchone()
        if existing:
            return {
                "token": existing["challenge_token"],
                "questions": json.loads(existing["questions_json"]),
                "attempt_number": int(existing["attempt_number"]),
            }

        failed = conn.execute(
            """
            SELECT 1
            FROM sanity_checks
            WHERE participant_id = ?
              AND passed = 0
              AND submitted_at IS NOT NULL
            LIMIT 1
            """,
            (participant_id,),
        ).fetchone()
        if failed:
            raise ValueError("The attention check has already been completed and failed.")

        participant = conn.execute(
            "SELECT domain_order_json FROM participants WHERE id = ?",
            (participant_id,),
        ).fetchone()
        if participant is None:
            raise ValueError("Participant not found.")
        order = json.loads(participant["domain_order_json"])
        first_domain = order[0] if order else "office"

        row = conn.execute(
            "SELECT COUNT(*) AS n FROM sanity_checks WHERE participant_id = ?",
            (participant_id,),
        ).fetchone()
        attempt_number = int(row["n"]) + 1
        questions, expected = _new_sanity_questions(first_domain)
        token = secrets.token_urlsafe(24)
        conn.execute(
            """
            INSERT INTO sanity_checks (
                participant_id, attempt_number, challenge_token,
                questions_json, expected_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                participant_id,
                attempt_number,
                token,
                json.dumps(questions),
                json.dumps(expected),
                utc_now(),
            ),
        )
        return {
            "token": token,
            "questions": questions,
            "attempt_number": attempt_number,
        }


def submit_sanity_check(
    path: str,
    participant_id: int,
    token: str,
    answers: dict[str, Any],
    honeypot_value: str,
    response_time_ms: int,
) -> bool:
    normalized_answers = {
        key: str(value).strip().lower() for key, value in answers.items()
    }
    honeypot_triggered = bool(str(honeypot_value).strip())
    safe_response_time = max(0, min(int(response_time_ms), 3_600_000))

    with connect(path) as conn:
        challenge = conn.execute(
            """
            SELECT *
            FROM sanity_checks
            WHERE participant_id = ?
              AND challenge_token = ?
              AND submitted_at IS NULL
            """,
            (participant_id, token),
        ).fetchone()
        if challenge is None:
            return False

        expected = {
            key: str(value).strip().lower()
            for key, value in json.loads(challenge["expected_json"]).items()
        }
        passed = not honeypot_triggered and all(
            normalized_answers.get(key, "") == expected_value
            for key, expected_value in expected.items()
        )

        conn.execute(
            """
            UPDATE sanity_checks
            SET answers_json = ?,
                passed = ?,
                honeypot_triggered = ?,
                response_time_ms = ?,
                submitted_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(normalized_answers),
                int(passed),
                int(honeypot_triggered),
                safe_response_time,
                utc_now(),
                int(challenge["id"]),
            ),
        )
        return passed


def discard_participant_study_data(path: str, participant_id: int) -> None:
    """Remove research responses after a failed mid study attention check.

    The participant row and sanity check row are retained for assignment and audit.
    Trial trajectories and survey responses are removed.
    """
    with connect(path) as conn:
        conn.execute("DELETE FROM trials WHERE participant_id = ?", (participant_id,))
        conn.execute("DELETE FROM surveys WHERE participant_id = ?", (participant_id,))

def invalidate_completion_code(path: str, participant_id: int) -> None:
    """Invalidate the completion code after a failed sanity check."""

    with connect(path) as conn:
        conn.execute(
            """
            UPDATE participants
            SET completion_code = ?,
                completed_at = NULL
            WHERE id = ?
            """,
            ("SANITY_FAILED", participant_id),
        )


def mark_participant_completed(path: str, participant_id: int) -> None:
    with connect(path) as conn:
        conn.execute(
            "UPDATE participants SET completed_at = COALESCE(completed_at, ?) WHERE id = ?",
            (utc_now(), participant_id),
        )


def save_trial(
    path: str,
    participant_id: int,
    task_index: int,
    domain: str,
    condition: str,
    trajectory: list,
    events: list,
    scores: dict,
    response_time_ms: int,
    confidence: int | None,
    explanation: str,
) -> None:
    with connect(path) as conn:
        conn.execute(
            """
            INSERT INTO trials (
                participant_id, task_index, domain_name, condition_name,
                trajectory_json, events_json, scores_json, response_time_ms,
                confidence, explanation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(participant_id, task_index) DO UPDATE SET
                trajectory_json = excluded.trajectory_json,
                events_json = excluded.events_json,
                scores_json = excluded.scores_json,
                response_time_ms = excluded.response_time_ms,
                confidence = excluded.confidence,
                explanation = excluded.explanation,
                created_at = excluded.created_at
            """,
            (
                participant_id,
                task_index,
                domain,
                condition,
                json.dumps(trajectory),
                json.dumps(events),
                json.dumps(scores),
                int(response_time_ms),
                confidence,
                explanation,
                utc_now(),
            ),
        )


def count_trials(path: str, participant_id: int) -> int:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM trials WHERE participant_id = ?", (participant_id,)
        ).fetchone()
        return int(row["n"])


def save_survey(path: str, participant_id: int, answers: dict[str, Any]) -> None:
    with connect(path) as conn:
        conn.execute(
            """
            INSERT INTO surveys (participant_id, answers_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(participant_id) DO UPDATE SET
                answers_json = excluded.answers_json,
                created_at = excluded.created_at
            """,
            (participant_id, json.dumps(answers), utc_now()),
        )
        conn.execute(
            "UPDATE participants SET completed_at = ? WHERE id = ?",
            (utc_now(), participant_id),
        )


def export_rows(path: str) -> list[dict[str, Any]]:
    with connect(path) as conn:
        rows = conn.execute(
            """
            SELECT
                p.participant_code,
                p.condition_name AS assigned_condition,
                p.domain_order_json,
                p.started_at,
                p.completed_at,
                COALESCE((
                    SELECT MAX(sc.passed)
                    FROM sanity_checks sc
                    WHERE sc.participant_id = p.id
                ), 0) AS sanity_passed,
                (
                    SELECT COUNT(*)
                    FROM sanity_checks sc
                    WHERE sc.participant_id = p.id
                      AND sc.submitted_at IS NOT NULL
                ) AS sanity_attempts,
                COALESCE((
                    SELECT MAX(sc.honeypot_triggered)
                    FROM sanity_checks sc
                    WHERE sc.participant_id = p.id
                ), 0) AS sanity_honeypot_triggered,
                (
                    SELECT sc.answers_json
                    FROM sanity_checks sc
                    WHERE sc.participant_id = p.id
                      AND sc.submitted_at IS NOT NULL
                    ORDER BY sc.id DESC
                    LIMIT 1
                ) AS sanity_last_answers_json,
                (
                    SELECT sc.response_time_ms
                    FROM sanity_checks sc
                    WHERE sc.participant_id = p.id
                      AND sc.submitted_at IS NOT NULL
                    ORDER BY sc.id DESC
                    LIMIT 1
                ) AS sanity_last_response_time_ms,
                (
                    SELECT MIN(sc.response_time_ms)
                    FROM sanity_checks sc
                    WHERE sc.participant_id = p.id
                      AND sc.submitted_at IS NOT NULL
                ) AS sanity_min_response_time_ms,
                CASE
                    WHEN (
                        SELECT MIN(sc.response_time_ms)
                        FROM sanity_checks sc
                        WHERE sc.participant_id = p.id
                          AND sc.submitted_at IS NOT NULL
                    ) < 1500 THEN 1
                    ELSE 0
                END AS sanity_any_very_fast,
                t.task_index,
                t.domain_name,
                t.trajectory_json,
                t.events_json,
                t.scores_json,
                t.response_time_ms,
                t.confidence,
                t.explanation,
                s.answers_json
            FROM participants p
            LEFT JOIN trials t ON t.participant_id = p.id
            LEFT JOIN surveys s ON s.participant_id = p.id
            ORDER BY p.id, t.task_index
            """
        ).fetchall()
        return [dict(row) for row in rows]
