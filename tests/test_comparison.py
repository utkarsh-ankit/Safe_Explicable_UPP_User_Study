from __future__ import annotations

import json
from pathlib import Path

from study.comparison import COMPARISON_POLICIES, build_order, build_slots, parse_submission
from study.database import (
    connect,
    create_or_get_participant,
    discard_participant_study_data,
    get_or_create_comparison_order,
    has_comparison,
    init_db,
    save_comparison,
    save_trial,
)


def _seed(db_path: str, code: str, condition: str) -> int:
    participant = create_or_get_participant(db_path, code, condition)
    participant_id = int(participant["id"])
    for task_index, domain in enumerate(["office", "search_recon"]):
        save_trial(
            db_path,
            participant_id,
            task_index,
            domain,
            condition,
            [[0, 0], [0, 1]],
            [],
            {"valid": True, "completed": True},
            1000,
            5,
            "test",
        )
    return participant_id


def test_order_is_a_stable_permutation() -> None:
    first = build_order(42)
    second = build_order(42)
    assert first == second
    assert sorted(first) == sorted(COMPARISON_POLICIES)


def test_slots_are_neutral_and_hide_policy_names() -> None:
    slots = build_slots(build_order(7))
    assert [slot["label"] for slot in slots] == ["Route 1", "Route 2", "Route 3"]
    for slot in slots:
        assert "sepupp" not in slot["image"]
        assert "optimal" not in slot["image"]
        assert "baseline" not in slot["image"]


def test_stored_order_does_not_change_on_second_view(tmp_path: Path) -> None:
    db_path = str(tmp_path / "study.sqlite3")
    init_db(db_path)
    participant_id = _seed(db_path, "TEST_CMP_ORDER", "partial")

    first = get_or_create_comparison_order(db_path, participant_id)
    second = get_or_create_comparison_order(db_path, participant_id)
    assert first == second
    assert not has_comparison(db_path, participant_id)


def test_parse_submission_decodes_slots_to_policies() -> None:
    order = ["optimal", "sepupp", "baseline"]
    payload, error = parse_submission(
        order,
        {"rating_1": "4", "rating_2": "5", "rating_3": "2", "choice": "2"},
    )
    assert error is None
    assert payload["choice_policy"] == "sepupp"
    assert payload["ratings"] == {"optimal": 4, "sepupp": 5, "baseline": 2}


def test_parse_submission_rejects_incomplete_forms() -> None:
    order = ["optimal", "sepupp", "baseline"]
    _, error = parse_submission(order, {"rating_1": "4", "rating_2": "5", "choice": "1"})
    assert error is not None
    _, error = parse_submission(
        order, {"rating_1": "4", "rating_2": "5", "rating_3": "3", "choice": ""}
    )
    assert error is not None
    _, error = parse_submission(
        order, {"rating_1": "9", "rating_2": "5", "rating_3": "3", "choice": "1"}
    )
    assert error is not None


def test_save_comparison_and_discard(tmp_path: Path) -> None:
    db_path = str(tmp_path / "study.sqlite3")
    init_db(db_path)
    participant_id = _seed(db_path, "TEST_CMP_SAVE", "full")

    order = get_or_create_comparison_order(db_path, participant_id)
    save_comparison(
        db_path,
        participant_id,
        order,
        1,
        order[0],
        {policy: 3 for policy in order},
        8000,
        "because it looked safe",
    )
    assert has_comparison(db_path, participant_id)

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM comparisons WHERE participant_id = ?", (participant_id,)
        ).fetchone()
    assert row["choice_policy"] == order[0]
    assert json.loads(row["ratings_json"])[order[0]] == 3

    discard_participant_study_data(db_path, participant_id)
    assert not has_comparison(db_path, participant_id)


def test_flow_sends_participant_through_sanity_then_compare(tmp_path: Path) -> None:
    import app as app_module
    from study.database import get_or_create_sanity_challenge, submit_sanity_check

    db_path = str(tmp_path / "study.sqlite3")
    flask_app = app_module.create_app(
        {"DATABASE_PATH": db_path, "TESTING": True, "SECRET_KEY": "test"}
    )
    client = flask_app.test_client()
    client.post("/login", data={"participant_code": "TEST_FLOW"})
    client.post("/consent", data={"consent": "yes"})

    # Before any route is drawn, part 2 sends the participant back to task 0.
    assert "/task/0" in client.get("/compare").headers["Location"]

    with connect(db_path) as conn:
        participant_id = int(
            conn.execute("SELECT id FROM participants LIMIT 1").fetchone()["id"]
        )

    # One route done: part 2 and the attention check both send them to task 1.
    save_trial(
        db_path, participant_id, 0, "office", "full",
        [[0, 0], [0, 1]], [], {"valid": True, "completed": True}, 1000, 5, "",
    )
    assert "/task/1" in client.get("/compare").headers["Location"]
    assert "/task/1" in client.get("/sanity").headers["Location"]

    # Both routes done: the attention check is now the gate to part 2.
    save_trial(
        db_path, participant_id, 1, "search_recon", "full",
        [[0, 0], [0, 1]], [], {"valid": True, "completed": True}, 1000, 5, "",
    )
    assert "/sanity" in client.get("/compare").headers["Location"]
    assert "/sanity" in client.get("/survey").headers["Location"]
    assert client.get("/sanity").status_code == 200

    # Passing the check opens part 2, which is then the gate to the survey.
    challenge = get_or_create_sanity_challenge(db_path, participant_id)
    with connect(db_path) as conn:
        expected = json.loads(
            conn.execute(
                "SELECT expected_json FROM sanity_checks WHERE challenge_token = ?",
                (challenge["token"],),
            ).fetchone()["expected_json"]
        )
    assert submit_sanity_check(db_path, participant_id, challenge["token"], expected, "", 6000)

    assert client.get("/compare").status_code == 200
    assert "/compare" in client.get("/survey").headers["Location"]

    order = get_or_create_comparison_order(db_path, participant_id)
    response = client.post(
        "/compare",
        data={
            "rating_1": "4", "rating_2": "2", "rating_3": "5",
            "choice": "3", "explanation": "safest", "response_time_ms": "12000",
        },
    )
    assert "/survey" in response.headers["Location"]
    assert has_comparison(db_path, participant_id)

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM comparisons WHERE participant_id = ?", (participant_id,)
        ).fetchone()
    assert row["choice_policy"] == order[2]
    assert json.loads(row["ratings_json"]) == {order[0]: 4, order[1]: 2, order[2]: 5}
