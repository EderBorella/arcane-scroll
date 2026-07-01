"""The rules the validator checks against — loaded from the validator's data dir (built by
build_rules.py). No game content is hard-coded here; it comes from the data files, keyed by identifier."""
import json
import os


class Rules:
    def __init__(self, class_progression=None, backgrounds=None, spell_lists=None, hit_dice=None,
                 class_proficiencies=None):
        self.class_progression = class_progression or {}
        self.backgrounds = backgrounds or {}
        self.spell_lists = spell_lists or {}
        self.hit_dice = hit_dice or {}
        self.class_proficiencies = class_proficiencies or {}

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
                   backgrounds=rd("backgrounds.json", required=False),
                   spell_lists=rd("spell_lists.json", required=False),
                   hit_dice=rd("hit_dice.json", required=False),
                   class_proficiencies=rd("class_proficiencies.json", required=False))

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

    def background_skills(self, name):
        """The skill proficiencies a background grants (or None)."""
        return (self.backgrounds.get((name or "").lower()) or {}).get("skills")

    def all_spells(self):
        """Every spell name across all class lists (empty if no spell-list data is loaded)."""
        return {name for by_name in self.spell_lists.values() for name in by_name}

    def hit_die(self, class_id):
        """The hit die size (int) for a class, or None if unknown."""
        return self.hit_dice.get((class_id or "").lower())

    def class_saves(self, class_id):
        """The class's two saving-throw proficiency ability ids, or None."""
        return (self.class_proficiencies.get((class_id or "").lower()) or {}).get("saving_throws")

    def class_skills(self, class_id):
        """The class's skill grant {choose: N, from: [names] | None}, or None."""
        return (self.class_proficiencies.get((class_id or "").lower()) or {}).get("skills")
