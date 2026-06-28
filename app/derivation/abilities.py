"""Ability scores — base standard array + racial bonuses + ASIs — and the ability `modifier`
primitive the rest of the layer builds on."""
from app.generation import features
from app.generation import helpers as H


def modifier(score: int) -> int:
    return (score - 10) // 2


def class_levels(choices) -> list:
    """[(class_index, level)] from the choices' class entries (class names are display-cased)."""
    return [(H._ci(c["class"]), c["level"]) for c in choices.get("classes", [])]


def _asi_bumps(choices, asi_label) -> tuple:
    """(ability indices bumped by ASI picks, number of feat-slot picks made)."""
    picks = choices.get("feat")
    picks = [picks] if isinstance(picks, str) else list(picks or [])
    by_name = {v.lower(): k for k, v in asi_label.items()}
    bumps = []
    for p in picks:
        pl = str(p).lower()
        if pl.startswith("ability score improvement"):
            bumps.append(next((ab for name, ab in by_name.items() if name in pl), None))
    return [b for b in bumps if b], len(picks)


def ability_scores(cat, choices, classes) -> dict:
    """Base assignment + racial bonuses + ASIs (each pick +2, capped at 20). 2+ slots reserve one
    code ASI on the primary class's primary ability."""
    scores = {ab: v + H.race_bonus(cat, choices["race"], ab)
              for ab, v in choices["ability_assignment"].items()}
    total_slots = sum(features._asi_slots(cat, ci, lv) for ci, lv in classes)
    bumps, n_picks = _asi_bumps(choices, cat.get("asi_label", {}))
    reserved = max(0, total_slots - n_picks)
    primary = (cat.get("ability_priority", {}).get(classes[0][0]) or list(scores))[0]
    for ab in bumps + [primary] * reserved:
        scores[ab] = min(20, scores[ab] + 2)
    return scores
