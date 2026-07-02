"""The rules the validator checks against — loaded from the validator's data dir (built by
build_rules.py). No game content is hard-coded here; it comes from the data files, keyed by identifier."""
import json
import os


class Rules:
    def __init__(self, class_progression=None, backgrounds=None, spell_lists=None, hit_dice=None,
                 class_proficiencies=None, spell_slots=None, caster_types=None, subclass_spells=None):
        self.class_progression = class_progression or {}
        self.backgrounds = backgrounds or {}
        self.spell_lists = spell_lists or {}
        self.hit_dice = hit_dice or {}
        self.class_proficiencies = class_proficiencies or {}
        self.spell_slots = spell_slots or {}
        self.caster_types = caster_types or {}
        self.subclass_spells = subclass_spells or {}
        self._spell_level = None      # lazy name → level index
        self._sub_by_norm = None      # lazy alnum-normalised subclass → grants

    @staticmethod
    def _alnum(s):
        return "".join(ch for ch in str(s or "").lower() if ch.isalnum())

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
                   class_proficiencies=rd("class_proficiencies.json", required=False),
                   spell_slots=rd("spell_slots.json", required=False),
                   caster_types=rd("caster_types.json", required=False),
                   subclass_spells=rd("subclass_spells.json", required=False))

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

    def class_multiclass(self, class_id):
        """The REDUCED proficiencies gained when this class is taken as a secondary class
        ({skills, armor, weapons, tools}), or None if not loaded."""
        return (self.class_proficiencies.get((class_id or "").lower()) or {}).get("multiclass")

    def class_armor(self, class_id):
        """The class's armour-category tokens (light/medium/heavy/shields), or None if not loaded."""
        return (self.class_proficiencies.get((class_id or "").lower()) or {}).get("armor")

    def class_weapons(self, class_id):
        """The class's weapon-category tokens (simple/martial), or None if not loaded."""
        return (self.class_proficiencies.get((class_id or "").lower()) or {}).get("weapons")

    def class_tools(self, class_id):
        """The class's tool grant {fixed: [names]} or {choose: N}, or None."""
        return (self.class_proficiencies.get((class_id or "").lower()) or {}).get("tools")

    def expertise_granted(self, class_id, level):
        """How many expertise picks a class has granted by `level`. Each 'Expertise' feature grant is
        two skills; returns None if the class isn't in the progression data (check then skips)."""
        levels = self.class_progression.get((class_id or "").lower())
        if not levels:
            return None
        grants = sum(1 for lv in levels if int(lv) <= level
                     and any(str(f).strip().lower() == "expertise" for f in levels[lv].get("features", [])))
        return grants * 2

    # --- spellcasting -------------------------------------------------------
    def caster_type(self, class_id):
        """'full' | 'half' | 'pact' for a casting class, else None (non-caster)."""
        return self.caster_types.get((class_id or "").lower())

    def spell_level(self, name):
        """The spell's level (0 = cantrip) from any class list, or None if unknown."""
        if self._spell_level is None:
            self._spell_level = {n: lv for by in self.spell_lists.values() for n, lv in by.items()}
        return self._spell_level.get(name)

    def cantrips_known(self, class_id, level):
        """Cantrips a class knows at a level (or None if not tracked)."""
        e = (self.class_progression.get((class_id or "").lower()) or {}).get(str(level))
        return e.get("cantrips_known") if e else None

    def prepared_count(self, class_id, level):
        """Leveled spells a class prepares at a level (or None if not tracked)."""
        e = (self.class_progression.get((class_id or "").lower()) or {}).get(str(level))
        return e.get("prepared_spells") if e else None

    def subclass_grants(self, subclass, level):
        """Always-prepared spell names a subclass grants by `level` (empty set if none/unknown)."""
        if not self.subclass_spells:
            return set()
        if self._sub_by_norm is None:
            self._sub_by_norm = {self._alnum(k): v for k, v in self.subclass_spells.items()}
        by = self._sub_by_norm.get(self._alnum(subclass))
        if not by:
            return set()
        return {n for lv, names in by.items() if int(lv) <= level for n in names}

    def expected_slots(self, classes):
        """Expected leveled spell slots {spell_level: n} for the character's caster classes (pact
        excluded — see expected_pact). Single caster → its own table; multiple → the multiclass table
        at the combined caster level. Per the multiclass rule: full casters add their full level, half
        casters (paladin/ranger) add half their level ROUNDED UP, and a third-caster subclass adds a
        third of its class level rounded down. Returns {} when no leveled caster, or None if the needed
        row isn't in the data."""
        ss = self.spell_slots
        if not ss:
            return None
        own, combined = [], 0
        for c in classes:
            cid = (c.get("class") or "").lower()
            lvl = c.get("level") or 0
            t = self.caster_type(cid)
            sub = self._alnum(c.get("subclass"))
            if t == "full":
                combined += lvl
                own.append(("class", cid, lvl))
            elif t == "half":
                combined += (lvl + 1) // 2      # round UP per the multiclass rule, not floor
                own.append(("class", cid, lvl))
            elif sub and sub in {self._alnum(k): 1 for k in ss.get("third", {})}:
                combined += lvl // 3            # third-caster rounds down
                own.append(("third", sub, lvl))
        if not own:
            return {}
        if len(own) == 1:
            kind, key, lvl = own[0]
            table = ss.get("classes", {}) if kind == "class" else ss.get("third", {})
            if kind == "third":
                table = {self._alnum(k): v for k, v in ss.get("third", {}).items()}
            return (table.get(key) or {}).get(str(lvl))
        return ss.get("multiclass", {}).get(str(combined))

    def expected_pact(self, classes):
        """Expected pact-magic slots {spell_level: n} from a pact caster's level, or None if the
        character has no pact class."""
        pact = self.spell_slots.get("pact", {}) if self.spell_slots else {}
        for c in classes:
            if self.caster_type((c.get("class") or "").lower()) == "pact":
                row = pact.get(str(c.get("level") or 0))
                return {str(row["level"]): row["slots"]} if row else {}
        return None
