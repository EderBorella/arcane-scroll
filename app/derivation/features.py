"""Features & traits — the auto-granted entries on a sheet: class features (from the per-level
tables, up to each class's level), race (and subrace) traits, and the background feature.

Each is `{name, source}`. Deeper subclass-specific feature text is data-limited (the level tables
carry the class progression + the subclass-grant markers, not every subclass sub-feature)."""
import re

from app.derivation.proficiency import _background
from app.generation import helpers as H


def _race_traits(cat, race) -> list:
    """Trait names for a race — a subrace plus its parent race."""
    idx = re.sub(r"\s+", "-", str(race).strip().lower())
    recs = []
    sub = cat.record("subraces", idx)
    if sub:
        recs.append(sub)
        parent = cat.record("races", sub.get("race", {}).get("index"))
        if parent:
            recs.append(parent)
    elif cat.record("races", idx):
        recs.append(cat.record("races", idx))
    return [t["name"] for r in recs for t in r.get("traits", [])]


def features_and_traits(cat, choices) -> list:
    """[{name, source}] — class features by level, race/subrace traits, and the background feature."""
    out = []
    for c in choices.get("classes", []):
        ci, lv = H._ci(c["class"]), c["level"]
        for rec in cat.records("levels").values():
            if rec.get("class", {}).get("index") == ci and rec.get("level", 0) <= lv:
                for f in rec.get("features", []):
                    out.append({"name": f["name"], "source": f"{c['class']} {rec['level']}"})
    out += [{"name": t, "source": "Race"} for t in _race_traits(cat, choices.get("race"))]
    bg = _background(cat, choices.get("background"))
    if bg and bg.get("feature"):
        out.append({"name": bg["feature"]["name"], "source": "Background"})
    return out
