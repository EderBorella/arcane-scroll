"""Ability scores — base standard array + racial bonuses + ASIs — and the ability `modifier`
primitive the rest of the layer builds on."""
from app.generation import features
from app.generation import helpers as H


def modifier(score: int) -> int:
    return (score - 10) // 2


def class_levels(choices) -> list:
    """[(class_index, level)] from the choices' class entries (class names are display-cased)."""
    return [(H._ci(c["class"]), c["level"]) for c in choices.get("classes", [])]


def _asi_points(choices, total_slots) -> int:
    """ASI points available (2 per ASI slot). A slot the model spent on a real feat yields none; an
    'Ability Score Improvement' pick or an unspent slot yields a +2. (Which ability the model named on
    an ASI pick is ignored — the points are placed optimally by _allocate_asi.)"""
    picks = choices.get("feat")
    picks = [picks] if isinstance(picks, str) else list(picks or [])
    real_feats = sum(1 for p in picks if not str(p).lower().startswith("ability score improvement"))
    return 2 * max(0, total_slots - real_feats)


def _allocate_asi(scores, points, order) -> None:
    """Place ASI points to maximise modifiers (a point only buys a modifier when it takes an odd score
    to even). The primary (highest-priority) ability is raised toward 20 first — through odd steps —
    but never left stranded on a no-modifier odd number (that point goes elsewhere). Remaining points
    go to the highest-priority odd ability (odd→even = +1 modifier), else the highest-priority < 20."""
    primary = order[0]
    target = min(20, scores[primary] + points)
    if target % 2 == 1:                       # e.g. 17 with 1 ASI → 18 (+ a spare point elsewhere), not 19
        target -= 1
    points -= target - scores[primary]
    scores[primary] = target
    rest = [ab for ab in order if ab != primary]
    while points > 0:
        odd = [ab for ab in rest if scores[ab] < 20 and scores[ab] % 2 == 1]
        pool = odd or [ab for ab in rest if scores[ab] < 20]
        if not pool:
            break
        scores[pool[0]] += 1
        points -= 1


def ability_scores(cat, choices, classes) -> dict:
    """Base assignment + racial bonuses, then ASI points allocated to maximise modifiers (see
    _allocate_asi): the primary ability up to 20, the rest spent evening out odd scores."""
    scores = {ab: v + H.race_bonus(cat, choices["race"], ab)
              for ab, v in choices["ability_assignment"].items()}
    points = _asi_points(choices, sum(features._asi_slots(cat, ci, lv) for ci, lv in classes))
    if points:
        order = cat.get("ability_priority", {}).get(classes[0][0]) or list(scores)
        _allocate_asi(scores, points, order)
    return scores
