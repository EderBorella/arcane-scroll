"""Resources domain: a CORE ``resource_budgets`` entry that maps to a resource this build owns must
declare the maximum that resource confers.

The check re-derives every expected maximum independently from the DB — it never reads the deriver.
It covers two owned-resource sources:

* the **class-resource COUNT ladder** — the maximum a class/subclass count ladder confers at the
  build's level.
* the **``grant_resource`` use-pool spine** — a species-, lineage-, feat-, class-, or subclass-owned
  use pool whose maximum is a fixed count (``int``), the proficiency bonus (re-derived from total
  level), or an ability modifier (re-derived from the sheet's abilities, minimum one).
  Species/lineage/feat pools are always-on; a class or subclass pool gates on that class's level (not
  total level).

A budget entry whose name matches a resource this build owns but whose maximum is not a queryable
number (a die-/bonus-only pool, or a pool not yet reached at the build's level) is left alone by the
maximum check — the check is not weakened to wave through a wrong maximum.

A budget entry whose name matches NO resource this build owns — across count ladders, die-only pools,
and ``grant_resource`` use-pools for every owner kind — is an orphan (epic R5 / T122): it cannot be
verified against anything real, so it is flagged rather than silently accepted. The owned-name set is
re-derived independently from the DB via the access layer, never from the deriver or gold."""
import re

from access.validator import resources as q
from validator.report import Violation

DOMAIN = "resources"

# The owner kinds the owned-name derivation knows how to resolve from a sheet's identity/feats. A
# grant_resource owner kind outside this set cannot be resolved, so a budget legitimately owned via
# that kind would otherwise be mis-classified as an orphan — the check guards that case instead.
KNOWN_OWNER_KINDS = frozenset({"class", "subclass", "species", "lineage", "feat"})

# Recharge-cadence collapse: a resource may recover on more than one cadence (a short OR a long rest).
# The single sheet label is the MOST FREQUENT trigger present — a short-rest pool also recovers on a
# long rest, so short-rest wins. Order = descending frequency. Re-derived independently of the deriver;
# 'dawn' is unattested in the reference dataset today.
_RECHARGE_PRIORITY = ("short-rest", "dawn", "long-rest")


def _collapse_recharge(cadences) -> str | None:
    """Collapse a resource's recharge cadence id(s) to a single sheet label by descending frequency,
    or None when no recharge cadence is recorded (a genuinely unlimited pool)."""
    present = set(cadences)
    for cad in _RECHARGE_PRIORITY:
        if cad in present:
            return cad
    return None


def _proficiency_bonus(total_level: int) -> int:
    """Proficiency bonus re-derived from total level (independent of the deriver)."""
    return 2 + (max(1, total_level) - 1) // 4


def _norm(name: str) -> str:
    """A loose key for matching a sheet's display label to a resource name: lower-cased, with any
    parenthetical qualifier and non-alphanumerics dropped and a trailing plural 's' removed (so a
    singular label matches its plural DB name, and casing/spacing differences collapse)."""
    s = re.sub(r"\(.*?\)", "", name.lower())
    s = re.sub(r"[^a-z0-9]", "", s)
    return s[:-1] if s.endswith("s") else s


def _grant_resource_max(res: dict, proficiency_bonus: int, ability_mods: dict) -> int | None:
    """The maximum a ``grant_resource`` use-pool confers, re-derived from its ``uses_kind`` (kept
    independent of the deriver): ``int`` -> the fixed ``uses_num``; ``proficiency_bonus`` -> the
    proficiency bonus; ``ability_modifier`` -> the named ability modifier, minimum one."""
    kind = res.get("uses_kind")
    if kind == "int":
        n = res.get("uses_num")
        return n if isinstance(n, int) and not isinstance(n, bool) else None
    if kind == "proficiency_bonus":
        return proficiency_bonus
    if kind == "ability_modifier":
        return max(1, ability_mods.get(res.get("uses_ability_id"), 0))
    return None


def _ability_mods(sheet: dict, access) -> dict[str, int]:
    """{ability_id: modifier} re-derived from the sheet's abilities (keyed there by abbreviation)."""
    mods: dict[str, int] = {}
    abilities = sheet.get("abilities")
    if not isinstance(abilities, dict):
        return mods
    for aid_row in access.db.q("SELECT id, abbrev FROM ability"):
        entry = abilities.get((aid_row["abbrev"] or "").lower())
        if isinstance(entry, dict) and isinstance(entry.get("final"), int):
            mods[aid_row["id"]] = (entry["final"] - 10) // 2
    return mods


def _owned_maxima(sheet: dict, access) -> dict[str, int]:
    """{normalised-resource-name: expected max} for every resource this build owns — count-ladder
    class/subclass resources at their levels, plus species/lineage/feat/class/subclass
    ``grant_resource`` use-pools (a class or subclass pool gated on that class's level). On a name
    collision the larger maximum wins."""
    owned: dict[str, int] = {}
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        return owned

    def put(name: str, value: int) -> None:
        nk = _norm(name)
        if nk not in owned or value > owned[nk]:
            owned[nk] = value

    total_level = 0
    class_levels: list[tuple[str, int]] = []
    subclass_levels: list[tuple[str, int]] = []
    for c in ident.get("classes", []) or []:
        if not isinstance(c, dict):
            continue
        level = c.get("level")
        if not (isinstance(level, int) and not isinstance(level, bool)):
            continue
        total_level += level
        cid = access.resolve("class", c.get("class"))
        sub_id = access.resolve("subclass", c.get("subclass"))
        for owner_kind, owner_id in (("class", cid), ("subclass", sub_id)):
            if not owner_id:
                continue
            for res in q.count_class_resources(access, owner_kind, owner_id):
                cnt = q.resource_count_at(access, res["id"], level)
                if cnt is not None:
                    put(res["name"], cnt)
        if cid:
            class_levels.append((cid, level))
        if sub_id:
            subclass_levels.append((sub_id, level))

    # grant_resource use-pools, re-derived from DB facts (independent of the deriver).
    pb = _proficiency_bonus(total_level)
    ability_mods = _ability_mods(sheet, access)

    def add_grants(owner_kind: str, owner_id: str, at_level: int) -> None:
        for res in q.grant_resources(access, owner_kind, owner_id, at_level=at_level):
            value = _grant_resource_max(res, pb, ability_mods)
            if value is not None:
                put(res["name"], value)

    # Species / lineage pools are always-on, gated on total level.
    for owner_kind, key in (("species", "species"), ("lineage", "lineage")):
        owner_id = access.resolve(owner_kind, ident.get(key))
        if owner_id:
            add_grants(owner_kind, owner_id, total_level)

    # A class pool gates on THAT class's level, not the character's total level, so a high-level class
    # grant does not leak into a low-class-level multiclass build.
    for cid, level in class_levels:
        add_grants("class", cid, level)

    # A subclass pool gates on THAT class's level, not the character's total level, so a high-level
    # subclass grant does not leak into a low-subclass-level multiclass build.
    for sub_id, level in subclass_levels:
        add_grants("subclass", sub_id, level)

    # Feat pools are always-on (a NULL gained_at_level always applies), resolved from the sheet's
    # feats list (which includes the background origin feat the CORE deriver records there).
    for entry in sheet.get("feats", []) or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        fid = access.resolve("feat", name)
        if fid:
            add_grants("feat", fid, total_level)
    return owned


def _owned_names(sheet: dict, access) -> set[str]:
    """{normalised-resource-name} for EVERY resource this build owns, regardless of level gate or
    whether its maximum is queryable — count-ladder AND die-/bonus-only class/subclass pools, plus
    species/lineage/feat/class/subclass ``grant_resource`` use-pools. This is the orphan check's
    name-existence set: a die-only pool (a ``class_resource`` with no count max) and a pool not yet
    reached at the build's level are both OWNED here, so neither is flagged as an orphan. Re-derived
    independently from the DB via the access layer, never from the deriver or gold."""
    names: set[str] = set()
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        return names

    def add(owner_kind: str, owner_id: str | None) -> None:
        if not owner_id:
            return
        for n in q.owned_resource_names(access, owner_kind, owner_id):
            names.add(_norm(n))

    for c in ident.get("classes", []) or []:
        if not isinstance(c, dict):
            continue
        add("class", access.resolve("class", c.get("class")))
        add("subclass", access.resolve("subclass", c.get("subclass")))
    add("species", access.resolve("species", ident.get("species")))
    add("lineage", access.resolve("lineage", ident.get("lineage")))
    for entry in sheet.get("feats", []) or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        add("feat", access.resolve("feat", name))
    return names


def _owned_recharge(sheet: dict, access) -> dict[str, str]:
    """{normalised-resource-name: collapsed recharge cadence} for every resource this build owns that
    records a recharge cadence — class/subclass count-ladder resources and species/lineage/feat/class/
    subclass ``grant_resource`` use-pools. Re-derived independently from the ``resource_recharge`` spine
    via the access layer (never from the deriver). On a name collision the higher-frequency cadence
    wins."""
    cadences: dict[str, set[str]] = {}
    ident = sheet.get("identity", {}) or {}
    if not isinstance(ident, dict):
        return {}

    def add(kind: str, resource_id: str, name: str) -> None:
        cads = q.recharge_cadences(access, kind, resource_id)
        if cads:
            cadences.setdefault(_norm(name), set()).update(cads)

    for c in ident.get("classes", []) or []:
        if not isinstance(c, dict):
            continue
        for owner_kind, owner_id in (("class", access.resolve("class", c.get("class"))),
                                     ("subclass", access.resolve("subclass", c.get("subclass")))):
            if not owner_id:
                continue
            for res in q.count_class_resources(access, owner_kind, owner_id):
                add("class_resource", res["id"], res["name"])
            for res in q.grant_resources(access, owner_kind, owner_id):
                add("grant_resource", res["id"], res["name"])

    for owner_kind, key in (("species", "species"), ("lineage", "lineage")):
        owner_id = access.resolve(owner_kind, ident.get(key))
        if owner_id:
            for res in q.grant_resources(access, owner_kind, owner_id):
                add("grant_resource", res["id"], res["name"])

    for entry in sheet.get("feats", []) or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        fid = access.resolve("feat", name)
        if fid:
            for res in q.grant_resources(access, "feat", fid):
                add("grant_resource", res["id"], res["name"])

    return {nk: _collapse_recharge(cads) for nk, cads in cadences.items()
            if _collapse_recharge(cads) is not None}


def check_recharge(core_sheet: dict, resource_state: dict, access) -> list[Violation]:
    """Independently re-derive the recharge cadence for each MODIFIER ``resource_state`` budget key from
    the ``resource_recharge`` spine and flag a mismatch (mirrors ``resource-max-wrong``).

    ``core_sheet`` supplies the owner set (identity + feats); ``resource_state`` is the MODIFIER block
    whose per-key ``recharge`` label is validated. A key that maps to a resource with a recharge row
    must carry the collapsed cadence; a key that maps to none must carry ``None``. Keys that map to no
    owned resource are left to the CORE ``resource_budgets`` orphan check — recharge is not re-flagged
    here."""
    v: list[Violation] = []
    if not isinstance(resource_state, dict) or not resource_state:
        return v
    expected = _owned_recharge(core_sheet, access)
    for key, entry in resource_state.items():
        if not isinstance(entry, dict):
            continue
        nk = _norm(key)
        exp = expected.get(nk)  # None = no recharge cadence recorded (unlimited pool)
        actual = entry.get("recharge")
        if actual != exp:
            v.append(Violation(DOMAIN, "recharge-wrong", "illegal",
                               f"{key}: recharge cadence {actual!r} does not match the {exp!r} this "
                               "resource recharges on for the build",
                               f"resource_state.{key}.recharge"))
    return v


def _feat_pool_uses(access, fid: str, budget_names: set[str], pb: int,
                    ability_mods: dict) -> dict | None:
    """The ``uses`` a feat-owned bounded ``grant_resource`` pool confers — ``{max, recharge}`` (recharge
    only when a cadence is recorded) — or None when the feat confers no such non-budget pool. Re-derived
    from the DB, independent of the deriver; single-homing skips a pool already in ``resource_budgets``
    (matched on the same normalised key the deriver uses)."""
    for res in q.grant_resources(access, "feat", fid):
        if _norm(res["name"]) in budget_names:
            continue  # single-homed in resource_state — the deriver does not duplicate it onto the feat
        mx = _grant_resource_max(res, pb, ability_mods)
        if mx is None:
            continue
        uses: dict = {"max": mx}
        cadence = _collapse_recharge(q.recharge_cadences(access, "grant_resource", res["id"]))
        if cadence:
            uses["recharge"] = cadence
        return uses
    return None


def check_feat_uses(core_sheet: dict, mod_feats, access) -> list[Violation]:
    """Independently re-derive each MODIFIER feat's ``uses.max``/``uses.recharge`` from a feat-owned
    bounded ``grant_resource`` pool that is NOT a ``resource_budgets`` entry, and flag a mismatch.

    ``check_recharge`` covers only ``resource_state`` budget keys and the MODIFIER feat-presence check
    validates presence only, so a feat that surfaces its own bounded pool (a pool single-homed on the
    feat, not in ``resource_state``) had no independent coverage. This closes that gap. A feat whose
    only pool is a budget entry (single-homed in ``resource_state``) expects ``max: None`` and no
    recharge — re-derived from the DB, never from the deriver."""
    v: list[Violation] = []
    if not isinstance(mod_feats, list) or not mod_feats:
        return v
    if not isinstance(core_sheet, dict):
        core_sheet = {}
    budget_names = {_norm(k) for k in (core_sheet.get("resource_budgets") or {})}
    ident = core_sheet.get("identity", {}) or {}
    total_level = 0
    for c in (ident.get("classes", []) if isinstance(ident, dict) else []):
        if isinstance(c, dict) and isinstance(c.get("level"), int) and not isinstance(c.get("level"), bool):
            total_level += c["level"]
    pb = _proficiency_bonus(total_level)
    ability_mods = _ability_mods(core_sheet, access)

    for f in mod_feats:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        fid = access.resolve("feat", name)
        if fid is None:
            continue
        expected = _feat_pool_uses(access, fid, budget_names, pb, ability_mods)
        uses = f.get("uses")
        if not isinstance(uses, dict):
            uses = {}
        exp_max = expected.get("max") if expected else None
        exp_recharge = expected.get("recharge") if expected else None
        if uses.get("max") != exp_max:
            v.append(Violation(DOMAIN, "feat-uses-max-wrong", "illegal",
                               f"{name}: feat uses max {uses.get('max')!r} does not match the {exp_max!r} "
                               "the feat's bounded pool confers for the build",
                               f"feats.{name}.uses.max"))
        if uses.get("recharge") != exp_recharge:
            v.append(Violation(DOMAIN, "feat-uses-recharge-wrong", "illegal",
                               f"{name}: feat uses recharge {uses.get('recharge')!r} does not match the "
                               f"{exp_recharge!r} the feat's bounded pool recharges on for the build",
                               f"feats.{name}.uses.recharge"))
    return v


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    budgets = sheet.get("resource_budgets")
    if budgets is None:
        return v
    if not isinstance(budgets, dict):
        v.append(Violation(DOMAIN, "malformed-resource-budgets", "illegal",
                           "resource_budgets must be an object", "resource_budgets"))
        return v

    owned = _owned_maxima(sheet, access)
    owned_names = _owned_names(sheet, access)

    # Guard the orphan check against a grant_resource owner kind the owned-name derivation cannot
    # resolve from a sheet. If the spine carries such a kind, a budget legitimately owned via it would
    # be mis-flagged as an orphan — so surface it as an internal finding and suspend orphan
    # classification for this run rather than emit a false orphan. Derived from the DB, not hardcoded.
    unaccounted = q.grant_resource_owner_kinds(access) - KNOWN_OWNER_KINDS
    if unaccounted:
        v.append(Violation(DOMAIN, "orphan-owner-kind-unaccounted", "internal",
                           "grant_resource carries owner kind(s) the orphan check cannot resolve "
                           f"({', '.join(sorted(unaccounted))}); orphan classification suspended",
                           "resource_budgets"))

    for key, budget in budgets.items():
        if not isinstance(budget, dict):
            continue
        nk = _norm(key)
        if nk not in owned_names:
            if unaccounted:
                # An owner kind the check cannot resolve is present, so this key may be owned via it —
                # do not risk a false orphan; the internal finding above already flags the gap.
                continue
            # An orphan: the budget declares a pool no resource this build owns confers — not a count
            # ladder, not a die-only pool, not a grant_resource across any owner. It cannot be
            # verified against anything real, so it is flagged rather than silently accepted.
            v.append(Violation(DOMAIN, "resource-budget-orphan", "illegal",
                               f"{key}: budget entry maps to no resource this build owns",
                               f"resource_budgets.{key}"))
            continue
        if nk not in owned:
            # Owned, but with no queryable maximum (a die-only pool) or not yet reached at this level
            # — outside the max-check's remit, and not an orphan.
            continue
        declared = budget.get("max")
        if not (isinstance(declared, int) and not isinstance(declared, bool)):
            continue
        expected = owned[nk]
        if declared != expected:
            v.append(Violation(DOMAIN, "resource-max-wrong", "illegal",
                               f"{key}: budget max {declared} does not match the {expected} this "
                               "resource confers for the build",
                               f"resource_budgets.{key}"))
    return v
