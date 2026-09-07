from __future__ import annotations

from typing import Any

Coord = tuple[int, int]


def _edge(a: Coord, b: Coord) -> tuple[Coord, Coord]:
    return tuple(sorted((a, b)))  # type: ignore[return-value]


def office_blocked_edges() -> set[tuple[Coord, Coord]]:
    walls: set[tuple[Coord, Coord]] = set()
    for r in [1, 2, 3, 5, 6, 7]:
        walls.add(_edge((r, 2), (r, 3)))
        walls.add(_edge((r, 5), (r, 6)))
    for c in [1, 2, 3, 5, 6, 7]:
        walls.add(_edge((2, c), (3, c)))
        walls.add(_edge((5, c), (6, c)))
    return walls


ROOM_A = {(r, c) for r in range(3, 6) for c in range(6, 9)}
ROOM_L = {(r, c) for r in range(3, 6) for c in range(3, 6)}
OFFICE_BUSY_TRUE = ROOM_A | ROOM_L


def search_wall_cells() -> set[Coord]:
    return {
        # Upper wall section
        (1, 1), (1, 2), (1, 3), (1, 4),
        (1, 6), (1, 7), (1, 8), (1, 9),

        # Upper rooms
        (2, 4), (2, 6),

        (3, 1), (3, 4), (3, 6), (3, 9),

        (4, 1), (4, 3), (4, 4),
        (4, 6), (4, 7), (4, 9),

        # Lower rooms
        (6, 1), (6, 3), (6, 4),
        (6, 6), (6, 7), (6, 9),

        (7, 1), (7, 4), (7, 6), (7, 9),

        (8, 4), (8, 6),

        # Lower wall section
        (9, 1), (9, 2), (9, 3), (9, 4),
        (9, 6), (9, 7), (9, 8), (9, 9),
    }


SEARCH_WALLS = search_wall_cells()


SEARCH_TARGETS = {
    "A": (2, 2),
    "B": (2, 8),
    "C": (8, 2),
    "D": (8, 8),
}


# Complete true environment.
SEARCH_TRUE_DEBRIS: dict[Coord, str] = {
    (0, 10): "low",
    (5, 6): "low",
    (8, 1): "low",
    (10, 3): "high",
}


# Debris visible to the participant in partial observability.
# The high debris at (10, 3) is hidden.
SEARCH_DETECTED = {
    (0, 10),
    (5, 6),
    (8, 1),
}


def _coord_list(values: set[Coord] | list[Coord]) -> list[list[int]]:
    return [[r, c] for r, c in sorted(values)]


def _edge_list(values: set[tuple[Coord, Coord]]) -> list[list[int]]:
    output: list[list[int]] = []
    for (r1, c1), (r2, c2) in sorted(values):
        output.append([r1, c1, r2, c2])
    return output


def office_config(condition: str) -> dict[str, Any]:
    visible_busy = OFFICE_BUSY_TRUE if condition == "full" else ROOM_L
    condition_text = "All busy areas are visible." if condition == "full" else "Only busy areas visible to the observer are shown."
    return {
        "domain": "office",
        "condition": condition,
        "condition_label": "Full view" if condition == "full" else "Limited view",
        "condition_text": condition_text,
        "title": "Office delivery",
        "task_text": (
    "Your goal is to pick up coffee from either cafeteria A or "
    "cafeteria B and deliver it to office O. Areas shown in orange "
    "are busy. If the robot enters a busy area, it may take longer "
    "to move through that area. Create the route you expect the "
    "robot to take to complete the task."
),
        "interaction_text": (
    "Click one neighboring cell at a time. "
    "The robot cannot cross black walls."
),
        "grid_size": 9,
        "start": [8, 4],
        "blocked_cells": [],
        "blocked_edges": _edge_list(office_blocked_edges()),
        "visible_busy": _coord_list(visible_busy),
        "coffee": [[1, 4], [4, 7]],
        "coffee_labels": {"1,4": "B", "4,7": "A"},
        "office": [7, 4],
        "labels": {
            "4,4": "L",
            "4,7": "A",
            "1,4": "B",
            "7,4": "O",
        },
        "completion": "office",
        "legend": [
            {"class": "busy", "label": "Busy area"},
            {"class": "coffee", "label": "Coffee source"},
            {"class": "goal", "label": "Delivery office"},
            {"class": "start", "label": "Robot start"},
            {"class": "wall_line", "label": "Wall"},
        ],
    }


def _room_cells() -> dict[str, list[list[int]]]:
    rooms = {
        "A": [
            (2, 1), (2, 2), (2, 3),
            (3, 2), (3, 3),
            (4, 2),
        ],

        "B": [
            (2, 7), (2, 8), (2, 9),
            (3, 7), (3, 8),
            (4, 8),
        ],

        "C": [
            (6, 2),
            (7, 2), (7, 3),
            (8, 1), (8, 2), (8, 3),
        ],

        "D": [
            (6, 8),
            (7, 7), (7, 8),
            (8, 7), (8, 8), (8, 9),
        ],
    }

    return {
        name: _coord_list(cells)
        for name, cells in rooms.items()
    }


def search_config(condition: str) -> dict[str, Any]:
    if condition == "full":
        visible = SEARCH_TRUE_DEBRIS

        debris_legend = [
            {"class": "debris low", "label": "Low debris"},
            {"class": "debris high", "label": "High debris"},
        ]
    else:
        visible = {
            loc: "low"
            for loc in SEARCH_DETECTED
        }

        debris_legend = [
            {"class": "debris low", "label": "Debris"},
        ]
    condition_text = ""
    if condition == "partial":
        task_text = (
            "In this task, the goal is to photograph locations A, B, C, "
            "and D (visit all 4) and then return to the starting position S. "
            "Some cells contain debris, which can cause the robot to be stuck if entered. "
            "The gray cells are walls and cannot be entered. "
            "Create the route you expect the robot to take to complete the task."
        )
    else:
        task_text = (
            "In this task, the goal is to photograph locations A, B, C, "
            "and D (visit all 4) and then return to the starting position S. "
            "Some cells contain a low amount of debris, which the robot "
            "can climb over without any issues. Some cells contain a high "
            "amount of debris, which can cause the robot to be stuck if entered. "
            "The gray cells are walls and cannot be entered. "
            "Create the route you expect the robot to take to complete the task."
        )
    return {
        "domain": "search_recon",
        "condition": condition,
        "condition_label": "Full view" if condition == "full" else "Limited view",
        "condition_text": condition_text,
        "title": "Search and reconnaissance",
        "task_text": task_text,
        "interaction_text": (
    "Click one neighboring cell at a time."
),
        "grid_size": 11,
        "start": [0, 0],
        "blocked_cells": _coord_list(SEARCH_WALLS),
        "blocked_edges": [],
        "visible_busy": [],
        "visible_debris": {
            f"{r},{c}": level for (r, c), level in visible.items()
        },
        "photo_targets": {
            name: [loc[0], loc[1]] for name, loc in SEARCH_TARGETS.items()
        },
        "room_cells": _room_cells(),
        "labels": {"0,0": "S"},
        "completion": "search_recon",
        "legend": [
            {"class": "room", "label": "Room floor"},
            {"class": "corridor", "label": "Corridor"},
            {"class": "photo", "label": "Photo target"},
            *debris_legend,
            {"class": "wall", "label": "Wall"},
            {"class": "start", "label": "Robot start"},
        ]
    }


def get_domain_config(domain: str, condition: str) -> dict[str, Any]:
    if condition not in {"full", "partial"}:
        raise ValueError("Unknown condition")
    if domain == "office":
        return office_config(condition)
    if domain == "search_recon":
        return search_config(condition)
    raise ValueError("Unknown domain")
