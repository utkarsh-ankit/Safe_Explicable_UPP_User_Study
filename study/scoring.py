from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

from .domains import (
    OFFICE_BUSY_TRUE,
    ROOM_L,
    SEARCH_DETECTED,
    SEARCH_TARGETS,
    SEARCH_TRUE_DEBRIS,
    SEARCH_WALLS,
)

Coord = tuple[int, int]


@dataclass
class TrialScores:
    valid: bool
    completed: bool
    steps: int
    task_reward: float
    full_user_reward: float
    partial_user_reward: float
    true_safety_cost: float
    perceived_safety_cost: float
    hidden_hazard_entered: bool
    details: dict

    def to_dict(self) -> dict:
        return asdict(self)


def parse_trajectory(raw: Iterable[Iterable[int]]) -> list[Coord]:
    trajectory: list[Coord] = []
    for item in raw:
        pair = list(item)
        if len(pair) != 2:
            raise ValueError("Every trajectory point must contain row and column")
        trajectory.append((int(pair[0]), int(pair[1])))
    return trajectory


def _is_adjacent(a: Coord, b: Coord) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def score_office(trajectory: list[Coord], gamma: float = 0.99) -> TrialScores:
    if not trajectory or trajectory[0] != (8, 4):
        return TrialScores(False, False, 0, 0, 0, 0, 0, 0, False, {"error": "wrong start"})

    coffee_locations = {(1, 4), (4, 7)}
    office = (7, 4)
    coffee_picked = False
    picked_from: Coord | None = None
    task = 0.0
    full = 0.0
    partial = 0.0
    true_cost = 0.0
    perceived_cost = 0.0
    discount = 1.0

    for index, (current, nxt) in enumerate(zip(trajectory, trajectory[1:])):
        if not _is_adjacent(current, nxt):
            return TrialScores(False, False, index, task, full, partial, true_cost, perceived_cost, False, {"error": "non adjacent move"})

        task_step = -0.1
        full_step = 0.0
        partial_step = 0.0

        if nxt in OFFICE_BUSY_TRUE:
            true_cost += discount * 0.5
            full_step -= 0.5
        if nxt in ROOM_L:
            perceived_cost += discount * 0.5
            partial_step -= 0.5

        if not coffee_picked and nxt in coffee_locations:
            coffee_picked = True
            picked_from = nxt
            task_step += 5.0
            if nxt == (4, 7):
                full_step += 5.0
                partial_step += 5.0

        if coffee_picked and nxt == office:
            task_step += 10.0
            full_step += 10.0
            partial_step += 10.0

        task += discount * task_step
        full += discount * full_step
        partial += discount * partial_step
        discount *= gamma

    completed = coffee_picked and trajectory[-1] == office
    return TrialScores(
        valid=True,
        completed=completed,
        steps=max(0, len(trajectory) - 1),
        task_reward=task,
        full_user_reward=full,
        partial_user_reward=partial,
        true_safety_cost=true_cost,
        perceived_safety_cost=perceived_cost,
        hidden_hazard_entered=False,
        details={
            "coffee_picked": coffee_picked,
            "picked_from": list(picked_from) if picked_from else None,
            "entered_true_busy": any(loc in OFFICE_BUSY_TRUE for loc in trajectory[1:]),
            "entered_visible_busy": any(loc in ROOM_L for loc in trajectory[1:]),
        },
    )


def _is_search_hallway(loc: Coord) -> bool:
    r, c = loc
    return r in {0, 5, 10} or c in {0, 5, 10}


def score_search_recon(trajectory: list[Coord], gamma: float = 0.97) -> TrialScores:
    start = (0,0)
    if not trajectory or trajectory[0] != start:
        return TrialScores(False, False, 0, 0, 0, 0, 0, 0, False, {"error": "wrong start"})

    target_by_loc = {loc: name for name, loc in SEARCH_TARGETS.items()}
    photos: set[str] = set()
    task = 0.0
    full = 0.0
    partial = 0.0
    true_cost = 0.0
    perceived_cost = 0.0
    hidden_entered = False
    visible_high_entered = False
    stuck = False
    first_high_step: int | None = None
    discount = 1.0
    effective_steps = 0

    for index, (current, nxt) in enumerate(zip(trajectory, trajectory[1:]), start=1):
        if not _is_adjacent(current, nxt):
            return TrialScores(False, False, index - 1, task, full, partial, true_cost, perceived_cost, hidden_entered, {"error": "non adjacent move"})
        if nxt in SEARCH_WALLS:
            return TrialScores(False, False, index - 1, task, full, partial, true_cost, perceived_cost, hidden_entered, {"error": "route enters a wall"})

        effective_steps += 1
        task_step = -0.1
        explic_step = -0.1
        if not _is_search_hallway(nxt):
            explic_step -= 0.5

        if nxt in target_by_loc and target_by_loc[nxt] not in photos:
            photos.add(target_by_loc[nxt])
            task_step += 5.0
            explic_step += 5.0

        level = SEARCH_TRUE_DEBRIS.get(nxt)
        full_safety = -0.1
        partial_safety = -0.1
        if level == "low":
            task_step -= 0.2
            full_safety -= 0.3
            true_cost += discount * 0.3
            if nxt in SEARCH_DETECTED:
                partial_safety -= 0.3
                perceived_cost += discount * 0.3
        elif level == "high":
            full_safety -= 3.0
            true_cost += discount * 1.0
            if first_high_step is None:
                first_high_step = index
            if nxt in SEARCH_DETECTED:
                visible_high_entered = True
                partial_safety -= 3.0
                perceived_cost += discount * 1.0
            else:
                hidden_entered = True
            stuck = True

        if len(photos) == len(SEARCH_TARGETS) and nxt == start:
            task_step += 10.0
            explic_step += 10.0

        task += discount * task_step
        full += discount * (explic_step + full_safety + 0.1)
        partial += discount * (explic_step + partial_safety + 0.1)
        discount *= gamma

    # A participant submission is complete when the DRAWN route visits every
    # photo target and returns to S. Entering HIGH debris is recorded as a
    # failed true-world execution, but it must not prevent submission. Rejecting
    # such routes would remove exactly the unsafe choices the study is meant to
    # measure under partial observability.
    route_completed = len(photos) == len(SEARCH_TARGETS) and trajectory[-1] == start
    execution_success = route_completed and not stuck

    return TrialScores(
        valid=True,
        completed=route_completed,
        steps=effective_steps,
        task_reward=task,
        full_user_reward=full,
        partial_user_reward=partial,
        true_safety_cost=true_cost,
        perceived_safety_cost=perceived_cost,
        hidden_hazard_entered=hidden_entered,
        details={
            "photos": sorted(photos),
            "photo_count": len(photos),
            "stuck": stuck,
            "execution_success": execution_success,
            "route_completed": route_completed,
            "returned_home": trajectory[-1] == start,
            "first_high_step": first_high_step,
            "visible_high_hazard_entered": visible_high_entered,
        },
    )


def score_trajectory(domain: str, raw_trajectory, gamma: float | None = None) -> dict:
    trajectory = parse_trajectory(raw_trajectory)
    if domain == "office":
        return score_office(trajectory, gamma or 0.99).to_dict()
    if domain == "search_recon":
        return score_search_recon(trajectory, gamma or 0.97).to_dict()
    raise ValueError("Unknown domain")
