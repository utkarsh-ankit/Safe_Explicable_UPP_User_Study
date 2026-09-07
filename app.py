from __future__ import annotations

import csv
import io
import json
import os

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

from study.database import (
    count_trials,
    create_or_get_participant,
    discard_participant_study_data,
    export_rows,
    get_or_create_sanity_challenge,
    get_participant,
    has_failed_sanity,
    has_passed_sanity,
    init_db,
    mark_consent,
    invalidate_completion_code,
    save_survey,
    save_trial,
    submit_sanity_check,
)
from study.domains import get_domain_config, office_config, search_config
from study.scoring import score_trajectory


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "development_only_change_me"),
        DATABASE_PATH=os.environ.get("DATABASE_PATH", "data/study.sqlite3"),
        ADMIN_TOKEN=os.environ.get("ADMIN_TOKEN", "change_me"),
        ALLOW_CONDITION_OVERRIDE=os.environ.get("ALLOW_CONDITION_OVERRIDE", "0") == "1",
    )
    if test_config:
        app.config.update(test_config)

    init_db(app.config["DATABASE_PATH"])

    def current_participant():
        participant_id = session.get("participant_id")
        if participant_id is None:
            return None
        return get_participant(app.config["DATABASE_PATH"], int(participant_id))

    def participant_passed_sanity(participant_id: int) -> bool:
        return has_passed_sanity(app.config["DATABASE_PATH"], participant_id)

    def participant_failed_sanity(participant_id: int) -> bool:
        return has_failed_sanity(app.config["DATABASE_PATH"], participant_id)

    @app.get("/")
    def index():
        participant = current_participant()
        if participant:
            participant_id = int(participant["id"])
            if participant_failed_sanity(participant_id):
                return redirect(url_for("sanity_failed"))
            return redirect(url_for("consent"))
        return render_template("login.html")

    @app.post("/login")
    def login():
        participant_code = request.form.get("participant_code", "").strip()
        override = request.args.get("condition") if app.config["ALLOW_CONDITION_OVERRIDE"] else None
        participant = create_or_get_participant(
            app.config["DATABASE_PATH"], participant_code, override
        )
        session.clear()
        session["participant_id"] = int(participant["id"])
        if participant_failed_sanity(int(participant["id"])):
            return redirect(url_for("sanity_failed"))
        return redirect(url_for("consent"))

    @app.route("/consent", methods=["GET", "POST"])
    def consent():
        participant = current_participant()
        if not participant:
            return redirect(url_for("index"))
        participant_id = int(participant["id"])
        if participant_failed_sanity(participant_id):
            return redirect(url_for("sanity_failed"))
        if request.method == "POST":
            if request.form.get("consent") != "yes":
                return render_template("consent.html", error="Consent is required to continue.")
            mark_consent(app.config["DATABASE_PATH"], participant_id)
            return redirect(url_for("instructions"))
        return render_template("consent.html")

    @app.get("/instructions")
    def instructions():
        participant = current_participant()
        if not participant:
            return redirect(url_for("index"))
        participant_id = int(participant["id"])
        if participant_failed_sanity(participant_id):
            return redirect(url_for("sanity_failed"))
        condition = participant["condition_name"]
        return render_template(
            "instructions.html",
            condition=condition,
            office_legend=office_config(condition)["legend"],
            search_legend=search_config(condition)["legend"],
        )

    @app.route("/sanity", methods=["GET", "POST"])
    def sanity():
        participant = current_participant()
        if not participant:
            return redirect(url_for("index"))

        participant_id = int(participant["id"])
        if participant_failed_sanity(participant_id):
            return redirect(url_for("sanity_failed"))
        if count_trials(app.config["DATABASE_PATH"], participant_id) < 1:
            return redirect(url_for("task", task_index=0))
        if participant_passed_sanity(participant_id):
            return redirect(url_for("task", task_index=1))

        challenge = get_or_create_sanity_challenge(
            app.config["DATABASE_PATH"], participant_id
        )
        error = None
        if request.method == "POST":
            answers = {
                question["id"]: request.form.get(f"answer_{question['id']}", "")
                for question in challenge["questions"]
            }
            try:
                response_time_ms = int(request.form.get("response_time_ms", "0"))
            except ValueError:
                response_time_ms = 0

            passed = submit_sanity_check(
                app.config["DATABASE_PATH"],
                participant_id,
                request.form.get("challenge_token", ""),
                answers,
                request.form.get("website", ""),
                response_time_ms,
            )
            if passed:
                return redirect(url_for("task", task_index=1))

            discard_participant_study_data(
                app.config["DATABASE_PATH"],
                participant_id,
            )

            invalidate_completion_code(
                app.config["DATABASE_PATH"],
                participant_id,
            )

            return redirect(url_for("sanity_failed"))

        return render_template("sanity.html", challenge=challenge, error=error)

    @app.get("/sanity_failed")
    def sanity_failed():
        participant = current_participant()
        if not participant:
            return redirect(url_for("index"))
        participant_id = int(participant["id"])
        if not participant_failed_sanity(participant_id):
            return redirect(url_for("instructions"))
        return render_template("sanity_failed.html")


    @app.get("/task/<int:task_index>")
    def task(task_index: int):
        participant = current_participant()
        if not participant:
            return redirect(url_for("index"))

        participant_id = int(participant["id"])
        if participant_failed_sanity(participant_id):
            return redirect(url_for("sanity_failed"))

        order = json.loads(participant["domain_order_json"])
        if task_index < 0 or task_index >= len(order):
            return redirect(url_for("survey"))

        if task_index >= 1:
            if count_trials(app.config["DATABASE_PATH"], participant_id) < 1:
                return redirect(url_for("task", task_index=0))
            if not participant_passed_sanity(participant_id):
                return redirect(url_for("sanity"))

        domain = order[task_index]
        config = get_domain_config(domain, participant["condition_name"])
        return render_template(
            "task.html",
            task_index=task_index,
            total_tasks=len(order),
            domain=domain,
            config=config,
        )

    @app.post("/api/trial")
    def submit_trial():
        participant = current_participant()
        if not participant:
            return jsonify({"ok": False, "error": "No participant session"}), 401

        participant_id = int(participant["id"])
        if participant_failed_sanity(participant_id):
            return jsonify({"ok": False, "error": "This study session is closed"}), 403

        payload = request.get_json(force=True)
        task_index = int(payload.get("task_index", 0))
        order = json.loads(participant["domain_order_json"])
        if task_index < 0 or task_index >= len(order):
            return jsonify({"ok": False, "error": "Invalid task index"}), 400
        if task_index >= 1 and not participant_passed_sanity(participant_id):
            return jsonify({"ok": False, "error": "Attention check is required"}), 403

        domain = order[task_index]
        trajectory = payload.get("trajectory", [])
        try:
            scores = score_trajectory(domain, trajectory)
        except (TypeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not scores["valid"]:
            return jsonify({"ok": False, "error": scores.get("details", {}).get("error", "Invalid trajectory")}), 400
        if not scores["completed"]:
            return jsonify({"ok": False, "error": "The trajectory does not complete the task."}), 400

        confidence_raw = payload.get("confidence")
        confidence = int(confidence_raw) if confidence_raw not in {None, ""} else None
        save_trial(
            app.config["DATABASE_PATH"],
            participant_id,
            task_index,
            domain,
            participant["condition_name"],
            trajectory,
            payload.get("events", []),
            scores,
            int(payload.get("response_time_ms", 0)),
            confidence,
            str(payload.get("explanation", ""))[:4000],
        )

        next_url = url_for("sanity") if task_index == 0 else url_for("task", task_index=task_index + 1)
        return jsonify({"ok": True, "next_url": next_url})

    @app.route("/survey", methods=["GET", "POST"])
    def survey():
        participant = current_participant()
        if not participant:
            return redirect(url_for("index"))

        participant_id = int(participant["id"])
        if participant_failed_sanity(participant_id):
            return redirect(url_for("sanity_failed"))
        if not participant_passed_sanity(participant_id):
            return redirect(url_for("sanity"))
        if count_trials(app.config["DATABASE_PATH"], participant_id) < 2:
            return redirect(url_for("task", task_index=1))

        if request.method == "POST":
            answers = {
                "information_complete": request.form.get("information_complete"),
                "strategy": request.form.get("strategy", "")[:4000],
                "comments": request.form.get("comments", "")[:4000],
            }
            save_survey(app.config["DATABASE_PATH"], participant_id, answers)
            return redirect(url_for("complete"))
        return render_template("survey.html")

    @app.get("/complete")
    def complete():
        participant = current_participant()
        if not participant:
            return redirect(url_for("index"))
        if participant_failed_sanity(int(participant["id"])):
            return redirect(url_for("sanity_failed"))
        return render_template("complete.html", completion_code=participant["completion_code"])

    @app.get("/admin/export.csv")
    def export_csv():
        if request.args.get("token") != app.config["ADMIN_TOKEN"]:
            return Response("Forbidden", status=403)
        rows = export_rows(app.config["DATABASE_PATH"])
        output = io.StringIO()
        fieldnames = list(rows[0].keys()) if rows else ["participant_code"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=sep_upp_user_study.csv"},
        )

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
