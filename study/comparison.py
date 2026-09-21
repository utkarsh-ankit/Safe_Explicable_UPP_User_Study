from __future__ import annotations

import random
from typing import Any

# Policy identity is kept on the server only. The participant sees neutral
# labels ("Route 1", "Route 2", "Route 3") and neutral image file names, so
# nothing in the rendered page or the page source reveals which planner
# produced which route.
#
# All participants see the SAME three partially observable images, regardless
# of the full/partial condition assigned for the two route drawing tasks.
COMPARISON_POLICIES: list[str] = ["baseline", "optimal", "sepupp"]

POLICY_IMAGES: dict[str, str] = {
    "baseline": "images/compare/route_a.png",
    "optimal": "images/compare/route_b.png",
    "sepupp": "images/compare/route_c.png",
}

RATING_MIN = 1
RATING_MAX = 5

# Shown under every image. Keep the wording identical for all three so the
# rating scale means the same thing for each route.
RATING_PROMPT = (
    "How well does this route match what you would expect a sensible, "
    "careful robot to do?"
)

RATING_SCALE_LABELS = {
    1: "Not at all what I would expect",
    5: "Exactly what I would expect",
}

CHOICE_PROMPT = (
    "Rate all three routes with stars, but choose only one: the route you "
    "would want the robot to actually carry out. All four answers are required."
)


def build_order(participant_id: int) -> list[str]:
    """Return the three policies in a stable, per participant random order.

    The order is seeded from the participant id, so a page refresh does not
    reshuffle the images. The order that is actually shown is written to the
    database as well, so analysis never depends on this function staying the
    same.
    """
    policies = list(COMPARISON_POLICIES)
    random.Random(f"sep_upp_compare_{participant_id}").shuffle(policies)
    return policies


def build_slots(order: list[str]) -> list[dict[str, Any]]:
    """Turn a policy order into the neutral display slots used by the template."""
    return [
        {
            "slot": index + 1,
            "label": f"Route {index + 1}",
            "image": POLICY_IMAGES[policy],
        }
        for index, policy in enumerate(order)
    ]


def parse_submission(order: list[str], form: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    """Validate a posted comparison form.

    Returns (payload, error). The payload keys are policy names, never slot
    numbers, so the stored data is already decoded.
    """
    ratings_by_policy: dict[str, int] = {}
    for index, policy in enumerate(order):
        slot = index + 1
        raw = (form.get(f"rating_{slot}") or "").strip()
        if not raw:
            return None, "Please give a star rating to all three routes."
        try:
            value = int(raw)
        except ValueError:
            return None, "Ratings must be whole numbers of stars."
        if value < RATING_MIN or value > RATING_MAX:
            return None, "Ratings must be between 1 and 5 stars."
        ratings_by_policy[policy] = value

    raw_choice = (form.get("choice") or "").strip()
    if not raw_choice:
        return None, "Please choose the route you would want the robot to carry out."
    try:
        choice_slot = int(raw_choice)
    except ValueError:
        return None, "Please choose one of the three routes."
    if choice_slot < 1 or choice_slot > len(order):
        return None, "Please choose one of the three routes."

    return (
        {
            "choice_slot": choice_slot,
            "choice_policy": order[choice_slot - 1],
            "ratings": ratings_by_policy,
        },
        None,
    )
