"""The 2024 rules the validator checks against — functional facts loaded from the validator's data
dir (mined from the source rulebook by extract_2024.py). No game content is hard-coded here; it all
comes from the data files, keyed by catalog identifiers."""
import json
import os


class Rules:
    def __init__(self, class_progression=None, backgrounds=None):
        self.class_progression = class_progression or {}
        self.backgrounds = backgrounds or {}

    @classmethod
    def load(cls, data_dir):
        def rd(name, required=True):
            p = os.path.join(data_dir, name)
            if not os.path.exists(p):
                if required:
                    raise FileNotFoundError(p)
                return {}
            with open(p) as f:
                return json.load(f)
        return cls(class_progression=rd("class_progression.json"),
                   backgrounds=rd("backgrounds.json", required=False))

    def proficiency_bonus(self, level):
        """Proficiency bonus at a character level (read from any class's table — identical across classes)."""
        for levels in self.class_progression.values():
            entry = levels.get(str(level))
            if entry and entry.get("proficiency_bonus") is not None:
                return entry["proficiency_bonus"]
        return None

    def subclass_unlock(self, class_id):
        """The level a class gains its subclass — the first level whose features name a '… Subclass'."""
        levels = self.class_progression.get((class_id or "").lower())
        if not levels:
            return None
        for lv in sorted(levels, key=int):
            if any(str(f).lower().endswith("subclass") for f in levels[lv].get("features", [])):
                return int(lv)
        return None

    def background_abilities(self, name):
        """The three ability ids a background offers for its ability-score increases (or None)."""
        entry = self.backgrounds.get((name or "").lower())
        return entry["abilities"] if entry else None
