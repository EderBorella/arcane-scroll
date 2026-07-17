"""CORE deriver — materialises a ``core-sheet:1`` document from a generated character's choices,
grounded entirely in the data-access layer. It is edition-agnostic: every rule is read from the
loaded reference dataset, never hard-coded, so the deriver follows whatever ruleset is loaded.

This is the keystone of generator adoption: CORE holds the permanent, always-active facts (identity,
abilities, proficiencies, permanent senses/speed/defences, hit points, features, feats). The other
DAL derivers (GRIMOIRE / INVENTORY / MODIFIER / COMPANION) layer the rest on top of it.

The rules points this deriver enforces (each verified against the reference dataset, never any
earlier generator stack):

* **Ability increases come from the BACKGROUND, not the species.** Under the loaded ruleset a species
  grants NO ability bonus. The background confers +2/+1 (to two of its three abilities) or +1/+1/+1
  (to all three). ``final = base + background_bonus + any origin/feat increase``.
* **The origin feat comes from the background.** It is always present in the feats array; class/level
  feats a build takes are added alongside it.
* **Proficiency bonus** = ``2 + (total_level - 1) // 4``.
* **Hit points** = max hit-die at the first class's first level, then the fixed average (round up,
  ``faces // 2 + 1``) for every level after, plus the Constitution modifier per level, plus any
  species HP rider.
* **Saving throws** — the FIRST class grants save proficiencies; species/feat/subclass/class-feature
  grants add to that set.
* **Skills** — the first class's chosen pool picks + the background's fixed skills + species/feat
  fixed grants.
* **Proficiencies** — armour/weapon/tool from the fixed grant spine. Weapon proficiencies are emitted
  in the canonical LOWERCASE corpus form ("simple weapons"), never title-case.

Permanent senses, speed, and defences are resolved **independently** in this module. Only the pure,
grant-GATHERING walkers are shared with the validator checks (collecting the raw grant rows for every
owner); the rule math on top — the sense max-not-sum rule and the speed sets-total / additive /
equals-walk rule — is re-implemented here, deriver-owned. That is deliberate: the validator's own
resolvers must provide genuine, independent cross-checking of the deriver, not rubber-stamp an output
that was produced with the same code. Names are resolved from the DB via ``access/`` — no game
literals live in this code.
"""
from typing import Any

from access import primitives
from access.generator import backgrounds as bg_q
from access.generator import catalog
from access.generator import species as species_q
from access.validator import abilities as abilities_q
from access.validator import defenses as defenses_q
from access.validator import features as features_q
from access.validator import movement as movement_q
from access.validator import proficiencies as prof_q
from access.validator import resources as resources_q
from access.validator import saving_throws as saves_q
from access.validator import senses as senses_q
from access.validator import vitals as vitals_q

# A choice-space structure — the generator's selections, all as catalog ids (except free-text player
# input like languages). Documented here rather than in a JSON contract; the ids are content-neutral
# and resolve against the loaded ruleset.
#
# choices = {
#   "character_id":       str,                 # shared id across the 5 sheets
#   "character_name":     str,
#   "species":            species_id,
#   "size":               size_id | None,      # chosen size when the species offers several
#   "lineage":            lineage_id | None,   # optional (sub-species)
#   "species_variant":    str | None,          # optional (full support is a later card)
#   "alignment":          str | None,
#   "classes": [ {"class": class_id, "level": int, "subclass": subclass_id | None}, ... ],
#   "background":         background_id,
#   "ability_scores":     { ability_key: base_int, ... },   # standard-array / point-buy result
#   "background_increase":{ ability_key: amount_int, ... },  # the +2/+1 or +1/+1/+1 distribution
#   "skills":             [ skill_id, ... ],   # first-class pool picks + any choose-grant picks
#   "expertise":          [ skill_id, ... ],   # optional
#   "feats": [ {"feat": feat_id, "ability_increase": {"ability": key, "amount": int}
#                                     | [ {"ability": key, "amount": int}, ... ] | None}, ... ],
#   "tools":              [ tool_id, ... ],    # optional chosen tools (category-choice picks)
#   "weapon_masteries":   [ str, ... ],        # required when a Weapon Mastery feature is present
#   "languages":          [ str, ... ],        # player choice; unvalidated in CORE
# }
Choices = dict[str, Any]


# --------------------------------------------------------------------------- helpers

def _classes(choices: Choices) -> list[dict]:
    return [c for c in choices.get("classes", []) if isinstance(c, dict)]


def _ability_maps(access):
    """(rows, id->abbrev-lowercase key) for every ability in the rulebook."""
    rows = catalog.list_abilities(access)
    key_of = {r["id"]: r["abbrev"].lower() for r in rows}
    return rows, key_of


def _resolve_ability(access, key: str) -> str | None:
    return abilities_q.ability_id(access, key)


def _display(access, dim: str, id_value: str | None) -> str | None:
    """A sheet-safe display value for a catalog id. Choice values are canonical DB ids; the sheet must
    carry a string the validator's name-resolver accepts. A proper slug id (its normalised form equals
    the row's normalised name) round-trips, so it is emitted verbatim — matching the corpus, which
    keys these fields by id. An id that does NOT round-trip (a non-slug synthetic id) falls back to the
    display name, which always resolves."""
    if id_value is None:
        return None
    if access.resolve(dim, id_value) is not None:
        return id_value
    return catalog.name_of(access, dim, id_value)


def _con_modifier(access, abilities_out: dict, key_of: dict) -> int:
    """Constitution modifier from the derived abilities, or 0 when the ruleset has no CON ability
    (the synthetic test ruleset does not)."""
    con_id = abilities_q.ability_id(access, "con")
    if con_id is None:
        return 0
    entry = abilities_out.get(key_of.get(con_id))
    if not isinstance(entry, dict):
        return 0
    final = entry.get("final")
    return (final - 10) // 2 if isinstance(final, int) else 0


# --------------------------------------------------------------------------- sections

def _identity(access, choices: Choices) -> dict:
    classes_out = []
    total_level = 0
    for c in _classes(choices):
        cid = c.get("class")
        level = int(c.get("level", 0))
        total_level += level
        sub_id = c.get("subclass")
        entry = {
            "class": _display(access, "class", cid),
            "level": level,
            # the corpus keys subclass by display name (unlike the id-keyed sibling fields)
            "subclass": catalog.name_of(access, "subclass", sub_id) if sub_id else None,
        }
        # Per-class/per-subclass detail choices (a class-level detail choice, a subclass sub-option). These are
        # player selections, not derivable from the DB alone, and are consumed downstream by the
        # GRIMOIRE deriver for spell-list widening; emit them as display strings when the choice
        # supplies one, so a widening-relevant build round-trips through CORE. Omitted when absent.
        detail_id = c.get("class_detail")
        if detail_id is not None:
            entry["class_detail"] = _display(access, "detail_option", detail_id)
        sub_detail_id = c.get("subclass_detail")
        if sub_detail_id is not None:
            entry["subclass_detail"] = _display(access, "detail_option", sub_detail_id)
        classes_out.append(entry)

    species_id = choices.get("species")
    size_id = choices.get("size")
    if size_id is None:
        # default to the species' first declared size when the choice omits one
        sizes = species_q.species_sizes(access, species_id) if species_id else []
        size_id = sizes[0] if sizes else None
    creature_type_id = species_q.species_creature_type(access, species_id) if species_id else None

    species_display = _display(access, "species", species_id)
    size_display = _display(access, "size", size_id)
    creature_type_display = _display(access, "creature_type", creature_type_id)
    # core-sheet:1 requires non-null strings for these — fail fast with a clear message rather than
    # emit a null the validator would reject downstream.
    if species_display is None:
        raise ValueError(f"unknown species id {species_id!r}")
    if size_display is None:
        raise ValueError(f"species {species_id!r} has no size and choices supplied none")
    if creature_type_display is None:
        raise ValueError(f"species {species_id!r} has no creature_type")

    identity = {
        "name": choices.get("character_name"),
        "species": species_display,
        "size": size_display,
        "creature_type": creature_type_display,
        "classes": classes_out,
        "total_level": total_level,
        "background": _display(access, "background", choices.get("background")),
    }
    # Optional identity fields — emitted only when the choice supplies them, so an absent value is
    # simply omitted rather than serialised as an explicit null.
    #
    # ``lineage`` is a resolver dim: choices carry its canonical id, so it is rendered to its display
    # name here (the grant walkers resolve identity.lineage back to the id to gather lineage grants).
    # ``species_variant`` is a name-keyed field (matched by (species, axis, option_name); no resolver
    # dim), so the chosen option name is carried verbatim.
    lineage_id = choices.get("lineage")
    if lineage_id is not None:
        identity["lineage"] = _display(access, "lineage", lineage_id)
    for key, value in (("species_variant", choices.get("species_variant")),
                       ("alignment", choices.get("alignment"))):
        if value is not None:
            identity[key] = value
    return identity


def _abilities(access, choices: Choices, key_of: dict) -> dict:
    base_by_aid: dict[str, int] = {}
    for key, score in (choices.get("ability_scores") or {}).items():
        aid = _resolve_ability(access, key)
        if aid is not None:
            base_by_aid[aid] = int(score)

    bonus_by_aid: dict[str, int] = {}
    for key, amount in (choices.get("background_increase") or {}).items():
        aid = _resolve_ability(access, key)
        if aid is not None:
            bonus_by_aid[aid] = bonus_by_aid.get(aid, 0) + int(amount)

    # Origin / class-feat ability increases fold into `final` (the per-ability breakdown only tracks
    # the background bonus, per the contract's abilityEntry).
    feat_inc_by_aid: dict[str, int] = {}
    for f in choices.get("feats") or []:
        inc = f.get("ability_increase") if isinstance(f, dict) else None
        # A feat's ability increase is either a single {ability, amount} (a +2 to one ability) or a
        # list of them (a +1/+1 split across two abilities); normalise to a list before folding.
        for one in _increase_list(inc):
            if isinstance(one, dict) and one.get("ability") is not None:
                aid = _resolve_ability(access, one["ability"])
                if aid is not None:
                    feat_inc_by_aid[aid] = feat_inc_by_aid.get(aid, 0) + int(one.get("amount", 0))

    # The final score is clamped to the ruleset's standard cap (read from the DB, 20 by default): base
    # + background bonus + any feat/ASI increase, never above the cap.
    cap = abilities_q.standard_ability_cap(access)
    out: dict[str, dict] = {}
    for aid, base in base_by_aid.items():
        bonus = bonus_by_aid.get(aid, 0)
        final = base + bonus + feat_inc_by_aid.get(aid, 0)
        if cap is not None:
            final = min(final, cap)
        out[key_of[aid]] = {"base": base, "background_bonus": bonus, "final": final}
    return out


def _proficiency_bonus(total_level: int) -> int:
    return 2 + (max(1, total_level) - 1) // 4


def _saving_throws(access, choices: Choices, key_of: dict) -> dict:
    classes = _classes(choices)
    expected: set[str] = set()
    if classes:
        first_cid = classes[0].get("class")
        if first_cid:
            expected |= set(saves_q.class_save_abilities(access, first_cid))

    species_id = choices.get("species")
    if species_id:
        expected |= set(saves_q.granted_save_abilities(access, "species", species_id))

    for f in choices.get("feats") or []:
        fid = f.get("feat") if isinstance(f, dict) else f
        if fid:
            expected |= set(saves_q.granted_save_abilities(access, "feat", fid))

    bg_id = choices.get("background")
    origin = bg_q.background_origin_feat(access, bg_id) if bg_id else None
    if origin:
        expected |= set(saves_q.granted_save_abilities(access, "feat", origin[0]))

    for c in classes:
        level = int(c.get("level", 0))
        cid = c.get("class")
        if cid:
            expected |= set(saves_q.granted_save_abilities(access, "class", cid, at_level=level))
        sub_id = c.get("subclass")
        if sub_id:
            expected |= set(saves_q.granted_save_abilities(access, "subclass", sub_id, at_level=level))

    return {key_of[aid]: {"proficient": aid in expected}
            for aid in key_of if aid in {r["id"] for r in catalog.list_abilities(access)}}


def _skill_sources(access, choices: Choices) -> dict[str, str]:
    """skill_id -> source, for every proficient skill this build confers."""
    classes = _classes(choices)
    source: dict[str, str] = {}

    class_pool: set[str] = set()
    class_any = False
    if classes:
        first_cid = classes[0].get("class")
        if first_cid:
            _n, from_any, pool = prof_q.class_skill_pool(access, first_cid)
            class_pool = set(pool)
            # A class with a choose-any pool has no explicit rows — any chosen skill is a class pick.
            class_any = bool(from_any)

    # Fixed grants from species / origin-feat / class feats resolve first so a chosen pick doesn't
    # shadow an automatically-conferred grant's source.
    def _add_grant_fixed(owner_kind: str, owner_id: str, src: str):
        _any, fixed, _cp, _cn = prof_q.grant_skill_sets(access, owner_kind, owner_id)
        for sid in fixed:
            source.setdefault(sid, src)

    species_id = choices.get("species")
    if species_id:
        _add_grant_fixed("species", species_id, "species")

    for f in choices.get("feats") or []:
        fid = f.get("feat") if isinstance(f, dict) else f
        if fid:
            _add_grant_fixed("feat", fid, "feat")

    bg_id = choices.get("background")
    if bg_id:
        for sid in prof_q.background_skills(access, bg_id):
            source.setdefault(sid, "background")

    # Player pool picks: attributed to the class when drawn from its pool (explicit OR choose-any),
    # else to a choose-grant feature.
    for sid in choices.get("skills") or []:
        source.setdefault(sid, "class" if (sid in class_pool or class_any) else "feature")

    return source


def _skills(access, choices: Choices, key_of: dict) -> dict:
    sources = _skill_sources(access, choices)
    expertise = set(choices.get("expertise") or [])
    out: dict[str, dict] = {}
    for row in catalog.list_skills(access):
        sid = row["id"]
        proficient = sid in sources
        out[row["name"]] = {
            "ability": key_of.get(row["ability_id"], row["ability_id"]),
            "proficient": proficient,
            "expertise": sid in expertise,
            "source": sources.get(sid) if proficient else None,
        }
    return out


def _armor_display(access, category_id: str) -> str:
    if category_id == "shield":
        return "shields"
    name = catalog.name_of(access, "armor_category", category_id)
    return (name or category_id).lower()


def _weapon_display(access, tier_id: str) -> str:
    name = catalog.name_of(access, "weapon_tier", tier_id)
    return f"{(name or tier_id).lower()} weapons"


def _fixed_equip_grants(access, owner_kind: str, owner_id: str,
                        at_level: int | None = None, is_first_class: bool = False):
    """(armor_ids, weapon_ids, tool_ids) from an owner's FIXED grant_proficiency rows. Choose-mode and
    category grants are skipped — those widen the legal pool but are not automatically-held
    proficiencies the sheet lists."""
    armor: set[str] = set()
    weapons: set[str] = set()
    tools: set[str] = set()
    for h in primitives.grants_for(access.db, "grant_proficiency", owner_kind, owner_id, at_level):
        if h["mode"] != "fixed":
            continue
        if owner_kind == "class":
            if is_first_class and h["multiclass_only"]:
                continue
            if not is_first_class and not h["multiclass_only"]:
                continue
        tk = h["target_kind"]
        vals = prof_q.grant_values(access, h["id"])
        if tk == "armor_category":
            armor.update(vals)
        elif tk == "weapon_tier":
            weapons.update(vals)
        elif tk == "tool":
            tools.update(vals)
    return armor, weapons, tools


def _proficiencies(access, choices: Choices) -> dict:
    armor: set[str] = set()
    weapons: set[str] = set()
    tools: set[str] = set()

    def merge(a, w, t):
        armor.update(a)
        weapons.update(w)
        tools.update(t)

    species_id = choices.get("species")
    if species_id:
        merge(*_fixed_equip_grants(access, "species", species_id))

    bg_id = choices.get("background")
    if bg_id:
        merge(*_fixed_equip_grants(access, "background", bg_id))
        bg_tool = bg_q.background_tool(access, bg_id)
        if bg_tool:
            tools.add(bg_tool)

    for i, c in enumerate(_classes(choices)):
        level = int(c.get("level", 0))
        cid = c.get("class")
        if cid:
            merge(*_fixed_equip_grants(access, "class", cid, at_level=level, is_first_class=(i == 0)))
        sub_id = c.get("subclass")
        if sub_id:
            merge(*_fixed_equip_grants(access, "subclass", sub_id, at_level=level))
        # A class-detail / subclass-detail choice (an order-style sub-choice) can confer heavier
        # armour and a broader weapon tier — materialise those exactly like any other fixed grant.
        # Both a class-owned and a subclass-owned detail option carry their grants under owner_kind
        # ``class_detail`` on the grant spine; the choice supplies the detail option's id.
        detail_id = c.get("class_detail")
        if detail_id:
            merge(*_fixed_equip_grants(access, "class_detail", detail_id, at_level=level))
        sub_detail_id = c.get("subclass_detail")
        if sub_detail_id:
            merge(*_fixed_equip_grants(access, "class_detail", sub_detail_id, at_level=level))

    for f in choices.get("feats") or []:
        fid = f.get("feat") if isinstance(f, dict) else f
        if fid:
            merge(*_fixed_equip_grants(access, "feat", fid))

    # Player-chosen tools (category-choice picks) are added explicitly by the generator.
    for tid in choices.get("tools") or []:
        tools.add(tid)

    return {
        "armor": sorted(_armor_display(access, a) for a in armor),
        "weapons": sorted(_weapon_display(access, w) for w in weapons),
        "tools": sorted(catalog.name_of(access, "tool", t) or t for t in tools),
    }


def _vitals(access, choices: Choices, con_mod: int):
    resolved: list[tuple[int, int]] = []  # (level, faces) in class order
    for c in _classes(choices):
        cid = c.get("class")
        faces = vitals_q.class_hit_die(access, cid) if cid else None
        if faces is None:
            continue
        resolved.append((int(c.get("level", 0)), faces))

    hit_dice: dict[str, dict] = {}
    total_level = 0
    for level, faces in resolved:
        total_level += level
        key = f"d{faces}"
        hit_dice[key] = {"max": hit_dice.get(key, {}).get("max", 0) + level}

    hp = 0
    if resolved:
        first_faces = resolved[0][1]
        hp = first_faces  # max at the first class's first level
        for i, (level, faces) in enumerate(resolved):
            avg_levels = level - 1 if i == 0 else level
            hp += avg_levels * (faces // 2 + 1)
        hp += total_level * con_mod
        species_id = choices.get("species")
        if species_id:
            for row in vitals_q.hp_grants(access, "species", species_id):
                hp += (row["flat"] or 0) + (row["per_level"] or 0) * total_level

    hit_points = {"max": max(1, hp)}
    return hit_points, hit_dice


def _features(access, choices: Choices) -> list[dict]:
    out: list[dict] = []
    for c in _classes(choices):
        level = int(c.get("level", 0))
        cid = c.get("class")
        if cid:
            cname = catalog.name_of(access, "class", cid) or cid
            for row in features_q.class_features(access, cid, level):
                out.append({"name": row["name"], "source": f"{cname} {row['level']}"})
        sub_id = c.get("subclass")
        if sub_id:
            sname = catalog.name_of(access, "subclass", sub_id) or sub_id
            for row in features_q.subclass_features(access, sub_id, level):
                out.append({"name": row["name"], "source": f"{sname} {row['class_level']}"})
    return out


def _feats(access, choices: Choices) -> list[dict]:
    out: list[dict] = []
    bg_id = choices.get("background")
    if bg_id:
        origin = bg_q.background_origin_feat(access, bg_id)
        if origin:
            out.append({"name": origin[0], "source": "background"})

    for f in choices.get("feats") or []:
        if not isinstance(f, dict):
            continue
        entry = {"name": f.get("feat"), "source": f.get("source", "class")}
        inc = f.get("ability_increase")
        if isinstance(inc, list):
            # A split increase (+1/+1) — carry each well-formed target as its own {ability, amount}.
            built = [{"ability": one["ability"], "amount": int(one.get("amount", 0))}
                     for one in inc
                     if isinstance(one, dict) and _resolve_ability(access, one.get("ability")) is not None]
            if built:
                entry["ability_increase"] = built
        elif isinstance(inc, dict):
            aid = _resolve_ability(access, inc.get("ability"))
            if aid is not None:
                entry["ability_increase"] = {"ability": inc["ability"],
                                             "amount": int(inc.get("amount", 0))}
        out.append(entry)
    return out


def _increase_list(inc) -> list:
    """Normalise a feat's ``ability_increase`` to a list of ``{ability, amount}`` entries: a single
    object becomes a one-item list, a list is returned as-is, anything else becomes empty."""
    if isinstance(inc, list):
        return inc
    if isinstance(inc, dict):
        return [inc]
    return []


def _derive_senses(grant_rows: list) -> dict:
    """Deriver-owned sense resolution (independent of the validator's resolver).

    Special-sense ranges follow a max-not-sum rule: several non-extending grants of the same sense are
    ALTERNATIVES, so the largest wins; an extending grant (``extends_existing``) adds its range on top
    of that base."""
    base: dict[str, int] = {}
    extension: dict[str, int] = {}
    for row in grant_rows:
        sid = row["sense_id"]
        rng = row["range_ft"] or 0
        if row["extends_existing"]:
            extension[sid] = extension.get(sid, 0) + rng
        else:
            base[sid] = max(base.get(sid, 0), rng)
    return {sid: rng + extension.get(sid, 0) for sid, rng in base.items()}


def _derive_speeds(grant_rows: list, base_walk: int, class_bonuses: list[int]) -> dict:
    """Deriver-owned speed resolution (independent of the validator's resolver).

    Walk starts from the species/lineage base. A ``sets_total`` grant OVERRIDES a mode (largest wins
    across several); an ``additive`` grant SUMS onto the mode; a class-resource speed bonus adds to
    walk; an ``equals_walk`` mode mirrors the resolved walk speed. Zero-valued modes are dropped, so a
    baseless build never emits a spurious ``walk 0``."""
    speeds: dict[str, int] = {}
    if base_walk:
        speeds["walk"] = base_walk

    set_total: dict[str, int] = {}
    additive: dict[str, int] = {}
    equals_walk: set[str] = set()
    for row in grant_rows:
        mode = row["movement_mode_id"]
        if row["sets_total"]:
            feet = row["feet"]
            if feet is not None:
                set_total[mode] = max(set_total.get(mode, 0), feet)
        elif row["additive"]:
            additive[mode] = additive.get(mode, 0) + (row["feet"] or 0)
        elif row["equals_walk"]:
            equals_walk.add(mode)

    for mode, feet in set_total.items():
        speeds[mode] = feet
    for mode, feet in additive.items():
        speeds[mode] = speeds.get(mode, 0) + feet
    if class_bonuses:
        speeds["walk"] = speeds.get("walk", 0) + max(class_bonuses)
    # sorted() only for a deterministic key order — an equals_walk mode mirrors the resolved walk.
    for mode in sorted(equals_walk):
        if mode != "walk":
            speeds[mode] = speeds.get("walk", 0)

    return {mode: feet for mode, feet in speeds.items() if feet > 0}


def _permanent_senses(access, partial: dict) -> dict:
    return _derive_senses(senses_q.gather_owner_grants(access, partial))


def _base_walk(access, choices: Choices) -> int:
    """Species base walk speed, falling back to the lineage's PARENT species when the lineage's own
    row carries none — mirroring the movement check so a lineage build resolves the same base walk."""
    species_id = choices.get("species")
    base_walk = (movement_q.species_base_walk(access, species_id) if species_id else 0) or 0
    lineage_id = choices.get("lineage")
    if lineage_id and not base_walk:
        parent_id = movement_q.lineage_parent_species(access, lineage_id)
        if parent_id:
            base_walk = movement_q.species_base_walk(access, parent_id) or 0
    return base_walk


def _permanent_speed(access, choices: Choices, partial: dict) -> dict:
    grants = movement_q.gather_owner_grants(access, partial)
    bonuses = movement_q.gather_class_bonuses(access, partial)
    return _derive_speeds(grants, _base_walk(access, choices), bonuses)


def _resource_budgets(access, choices: Choices) -> dict:
    """Per-resource maximums from the class-resource ladder.

    For each class (and its subclass) the build takes, every resource with a COUNT ladder — a
    whole-number use pool (a per-rest use count), as opposed to a die or a flat bonus — contributes
    its maximum at that class's level, keyed by the resource's display name.
    On a name collision across a multiclass the larger maximum wins. Dice/bonus resources and
    formula-based feature uses are not on this ladder and are intentionally not emitted here."""
    out: dict[str, dict] = {}

    def add(owner_kind: str, owner_id: str, level: int) -> None:
        for res in resources_q.count_class_resources(access, owner_kind, owner_id):
            count = resources_q.resource_count_at(access, res["id"], level)
            if count is None:
                continue
            name = res["name"]
            prev = out.get(name, {}).get("max")
            out[name] = {"max": count if prev is None else max(prev, count)}

    for c in _classes(choices):
        level = int(c.get("level", 0))
        cid = c.get("class")
        if cid:
            add("class", cid, level)
        sub_id = c.get("subclass")
        if sub_id:
            add("subclass", sub_id, level)
    return out


def _permanent_defenses(access, partial: dict) -> dict:
    res_rows = defenses_q.gather_owner_grants(access, partial, defenses_q.resistance_grants)
    resistance_set = {r["damage_type_id"] for r in res_rows
                      if r["mode"] == "fixed" and r["damage_type_id"]}
    # A variant-axis resistance names its axis but not its damage type — the concrete type is decided
    # by the chosen species_variant option. Resolve it here (deriver-owned, re-derived from the DB, so
    # the deriver stays independent of the validator's own variant resolution).
    ident = partial.get("identity", {}) or {}
    variant_name = ident.get("species_variant")
    if isinstance(variant_name, str) and variant_name:
        spid = access.resolve("species", ident.get("species"))
        if spid:
            for row in res_rows:
                if row["variant_axis"]:
                    dmg = defenses_q.variant_damage_type(
                        access, spid, row["variant_axis"], variant_name)
                    if dmg:
                        resistance_set.add(dmg)
    resistances = sorted(resistance_set)

    cond_rows = defenses_q.gather_owner_grants(access, partial, defenses_q.condition_grants)
    condition_immunities = sorted({r["condition_id"] for r in cond_rows if r["effect"] == "immunity"})
    condition_advantages = []
    for r in cond_rows:
        if r["effect"] in ("advantage_to_avoid_or_end", "advantage_to_end"):
            effect = "avoid_or_end" if r["effect"] == "advantage_to_avoid_or_end" else "end"
            condition_advantages.append({"condition": r["condition_id"], "effect": effect})

    sa_rows = defenses_q.gather_owner_grants(access, partial, defenses_q.save_advantage_grants)
    save_advantages = sorted({s for s in (defenses_q.save_scope_for(access, r) for r in sa_rows) if s})

    return {
        "resistances": resistances,
        "immunities": [],
        "vulnerabilities": [],
        "condition_immunities": condition_immunities,
        "save_advantages": save_advantages,
        "condition_advantages": condition_advantages,
    }


# --------------------------------------------------------------------------- orchestrator

def derive_core(choices: Choices, access) -> dict:
    """Materialise a ``core-sheet:1`` document from a generated character's choices.

    ``access`` is any data-access handle exposing ``.db`` / ``.resolve`` / ``.resolver`` (a
    ``GeneratorAccess`` or ``ValidatorAccess``). The output passes ``/validate-core`` for a legal set
    of choices.
    """
    _ab_rows, key_of = _ability_maps(access)

    identity = _identity(access, choices)
    total_level = identity["total_level"]
    abilities = _abilities(access, choices, key_of)
    con_mod = _con_modifier(access, abilities, key_of)

    feats = _feats(access, choices)
    # Partial sheet the shared grant walkers read (identity + feats are all they need for CORE).
    partial = {"identity": identity, "feats": feats}

    hit_points, hit_dice = _vitals(access, choices, con_mod)

    sheet = {
        "schema_version": 1,
        "character_id": choices.get("character_id"),
        "character_name": choices.get("character_name"),
        "identity": identity,
        "abilities": abilities,
        "proficiency_bonus": _proficiency_bonus(total_level),
        "saving_throws": _saving_throws(access, choices, key_of),
        "skills": _skills(access, choices, key_of),
        "proficiencies": _proficiencies(access, choices),
        "permanent_senses": _permanent_senses(access, partial),
        "permanent_speed": _permanent_speed(access, choices, partial),
        "permanent_defenses": _permanent_defenses(access, partial),
        "hit_points": hit_points,
        "hit_dice": hit_dice,
        "languages": list(choices.get("languages") or []),
        "weapon_masteries": list(choices.get("weapon_masteries") or []),
        "features": _features(access, choices),
        "feats": feats,
    }
    # Per-resource maximums from the class-resource ladder — emitted only when the build has at least
    # one count-ladder resource, matching the corpus (an optional, absent-when-empty block).
    resource_budgets = _resource_budgets(access, choices)
    if resource_budgets:
        sheet["resource_budgets"] = resource_budgets
    return sheet
