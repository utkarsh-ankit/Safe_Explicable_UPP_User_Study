from __future__ import annotations

import json
from pathlib import Path

from study.database import (
    connect,
    create_or_get_participant,
    discard_participant_study_data,
    get_or_create_sanity_challenge,
    has_failed_sanity,
    has_passed_sanity,
    init_db,
    save_trial,
    submit_sanity_check,
)


def _expected_answers(db_path: str, participant_id: int, challenge: dict) -> dict[str, str]:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT expected_json
            FROM sanity_checks
            WHERE participant_id = ? AND challenge_token = ?
            """,
            (participant_id, challenge["token"]),
        ).fetchone()
    return json.loads(row["expected_json"])


def test_sanity_check_passes_and_is_saved(tmp_path: Path) -> None:
    db_path = str(tmp_path / "study.sqlite3")
    init_db(db_path)
    participant = create_or_get_participant(db_path, "TEST_SANITY_1", "full")
    participant_id = int(participant["id"])

    challenge = get_or_create_sanity_challenge(db_path, participant_id)
    expected = _expected_answers(db_path, participant_id, challenge)

    assert not has_passed_sanity(db_path, participant_id)
    assert submit_sanity_check(
        db_path,
        participant_id,
        challenge["token"],
        expected,
        "",
        5000,
    )
    assert has_passed_sanity(db_path, participant_id)
    assert not has_failed_sanity(db_path, participant_id)


def test_failed_sanity_is_saved_and_trial_can_be_deleted(tmp_path: Path) -> None:
    db_path = str(tmp_path / "study.sqlite3")
    init_db(db_path)
    participant = create_or_get_participant(db_path, "TEST_SANITY_2", "partial")
    participant_id = int(participant["id"])

    save_trial(
        db_path,
        participant_id,
        0,
        "office",
        "partial",
        [[8, 4], [7, 4]],
        [],
        {"valid": True, "completed": True},
        2000,
        5,
        "test",
    )

    challenge = get_or_create_sanity_challenge(db_path, participant_id)
    expected = _expected_answers(db_path, participant_id, challenge)
    expected["math"] = "9999"

    assert not submit_sanity_check(
        db_path,
        participant_id,
        challenge["token"],
        expected,
        "",
        4000,
    )
    assert has_failed_sanity(db_path, participant_id)

    discard_participant_study_data(db_path, participant_id)
    with connect(db_path) as conn:
        trial_count = conn.execute(
            "SELECT COUNT(*) AS n FROM trials WHERE participant_id = ?",
            (participant_id,),
        ).fetchone()["n"]
        sanity_count = conn.execute(
            "SELECT COUNT(*) AS n FROM sanity_checks WHERE participant_id = ?",
            (participant_id,),
        ).fetchone()["n"]

    assert trial_count == 0
    assert sanity_count == 1


def test_honeypot_causes_failure(tmp_path: Path) -> None:
    db_path = str(tmp_path / "study.sqlite3")
    init_db(db_path)
    participant = create_or_get_participant(db_path, "TEST_SANITY_3", "partial")
    participant_id = int(participant["id"])
    challenge = get_or_create_sanity_challenge(db_path, participant_id)
    expected = _expected_answers(db_path, participant_id, challenge)

    assert not submit_sanity_check(
        db_path,
        participant_id,
        challenge["token"],
        expected,
        "filled by bot",
        100,
    )
    assert not has_passed_sanity(db_path, participant_id)
    assert has_failed_sanity(db_path, participant_id)
