"""The rules the validator checks against — loaded from the validator's data dir (built by
build_rules.py). No game content is hard-coded here; it comes from the data files, keyed by identifier."""
import json
import os


class Rules:
    def __init__(self, class_progression=None, backgrounds=None, spell_lists=None, hit_dice=None,
                 class_proficiencies=None, spell_slots=None, caster_types=None, subclass_spells=None,
                 caster_meta=None, feats=None, feature_choice_counts=None):
        self.class_progression = class_progression or {}
        self.backgrounds = backgrounds or {}
        self.spell_lists = spell_lists or {}
        self.hit_dice = hit_dice or {}
        self.class_proficiencies = class_proficiencies or {}
        self.spell_slots = spell_slots or {}
        self.caster_types = caster_types or {}
        self.subclass_spells = subclass_spells or {}
        self.caster_meta = caster_meta or {}
        self.feats = feats or {}
        self.feature_choice_counts = feature_choice_counts or {}
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
                   subclass_spells=rd("subclass_spells.json", required=False),
                   caster_meta=rd("caster_meta.json", required=False),
                   feats=rd("feats.json", required=False),
                   feature_choice_counts=rd("feature_choice_counts.json", required=False))

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

    def class_primary(self, class_id):
        """The class's primary ability ids (>1 ⇒ any-of, e.g. Strength OR Dexterity), or None."""
        return (self.class_proficiencies.get((class_id or "").lower()) or {}).get("primary")

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

    def has_spellbook(self, classes):
        """True if any of the character's classes prepares from a Spellbook (a known pool) — leveled
        spells may then legally be unprepared."""
        book = set(self.caster_meta.get("spellbook") or [])
        return any((c.get("class") or "").lower() in book for c in classes)

    def arcanum_max_level(self, classes):
        """Highest spell level a pact caster can cast via Mystic Arcanum (0 if none) — these are cast
        without a normal/pact slot, so they legitimately exceed the pact slot level."""
        arc = self.caster_meta.get("arcanum") or {}
        best = 0
        for c in classes:
            if self.caster_type((c.get("class") or "").lower()) == "pact":
                lvl = c.get("level") or 0
                best = max([best] + [sl for at, sl in arc.items() if int(at) <= lvl])
        return best

    def always_prepared(self, classes):
        """Set of class-feature always-prepared spell names for the character's classes — these are
        additive and don't count against the prepared budget."""
        ap = self.caster_meta.get("always_prepared") or {}
        out = set()
        for c in classes:
            out |= set(ap.get((c.get("class") or "").lower()) or [])
        return out

    # --- features ------------------------------------------------------------
    def class_features(self, class_id, level):
        """Expected class-feature names granted at or below `level`, EXCLUDING the markers handled by
        other layers: subclass unlocks (class_level), and Ability Score Improvement / Epic Boon (feats).
        Subclass-specific and species features aren't in the progression data, so aren't covered here."""
        levels = self.class_progression.get((class_id or "").lower()) or {}
        out = set()
        for lv, entry in levels.items():
            if int(lv) <= level:
                for f in entry.get("features", []):
                    fl = str(f).strip().lower()
                    if (not fl or fl == "—" or fl.endswith("subclass")
                            or "ability score improvement" in fl or fl == "epic boon"):
                        continue
                    out.add(f)
        return out

    def feature_choice_expected(self, class_id, feature_name, level):
        """Expected number of choices for a choice-count feature (invocations, weapon mastery) at a
        class level, or None if that class/feature/level isn't tracked."""
        by_feat = self.feature_choice_counts.get((class_id or "").lower()) or {}
        want = self._alnum(feature_name)
        for header, by_level in by_feat.items():
            if self._alnum(header) == want:
                return by_level.get(str(level))
        return None

    # --- feats ---------------------------------------------------------------
    def feat(self, name):
        """A feat's {category, repeatable, prereq?} or None if unknown."""
        return self.feats.get((name or "").lower())

    def feat_slots(self, classes, has_background):
        """How many feat opportunities the character has: one Origin feat if it has a background, plus
        every Ability-Score-Improvement / Epic-Boon feature its classes have reached (read from the
        class progression). Feats taken must not exceed this (an ASI slot may instead be a raw ASI)."""
        n = 1 if has_background else 0
        for c in classes:
            lvl = c.get("level") or 0
            levels = self.class_progression.get((c.get("class") or "").lower()) or {}
            for lv, entry in levels.items():
                if int(lv) <= lvl:
                    n += sum(1 for f in entry.get("features", [])
                             if "ability score improvement" in str(f).lower()
                             or str(f).strip().lower() == "epic boon")
        return n
