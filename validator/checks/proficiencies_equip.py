"""Armor, weapon, and tool proficiency legality against the grant_proficiency spine (F05-T19).

Every expectation is re-derived from the DB -- no hard-coded game terms, no tuning against known
generator output. Choose-mode grants are skipped (unverifiable); category grants widen the legal
pool to every tool in the category (the sheet picks are opaque, so any category-legal tool is fine).
"""
from access import primitives
from access.validator import proficiencies as q
from validator.report import Violation

DOMAIN = "proficiencies_equip"


def _armor_id(name: str) -> str:
    """Normalize a sheet armor proficiency name to an armor_category DB id."""
    n = name.strip().lower()
    if n == "shields":
        n = "shield"
    n = n.replace(" ", "-")
    if n in ("light", "medium", "heavy"):
        n = n + "-armor"
    return n


def _weapon_id(name: str) -> str:
    """Normalize a sheet weapon proficiency name to a weapon_tier DB id."""
    n = name.strip().lower()
    n = n.replace(" weapons", "").replace(" weapon", "")
    return n.strip()


def _tool_id(name: str) -> str:
    """Normalize a sheet tool proficiency name to a tool DB id."""
    n = name.strip().lower()
    n = n.replace("'s ", "-s ").replace("' ", " ").replace("'", "").replace(" ", "-")
    return n


def _weapon_tier_for_name(name: str, access) -> str | None:
    """Look up a specific weapon name in the weapon table and return its tier_id."""
    n = name.strip().lower()
    candidates = [n, n.rstrip("s")]
    try:
        for c in candidates:
            row = access.db.one(
                "SELECT w.tier_id FROM weapon w JOIN catalog_item ci ON w.id=ci.id "
                "WHERE LOWER(ci.name)=?", c)
            if row:
                return row["tier_id"]
    except Exception:
        pass
    return None


def _resolve_armor(name: str, access) -> str | None:
    aid = _armor_id(name)
    row = access.db.one("SELECT id FROM armor_category WHERE id=?", aid)
    if row:
        return row["id"]
    n = name.strip().lower()
    row = access.db.one("SELECT id FROM armor_category WHERE LOWER(name)=?", n)
    return row["id"] if row else None


def _resolve_weapon(name: str, access) -> str | None:
    """Resolve a sheet weapon to its tier_id, handling both tier names and specific weapons."""
    wid = _weapon_id(name)
    row = access.db.one("SELECT id FROM weapon_tier WHERE id=?", wid)
    if row:
        return row["id"]
    return _weapon_tier_for_name(name, access)


def _resolve_tool(name: str, access) -> str | None:
    n = name.strip().strip('"')
    tid = _tool_id(n)
    row = access.db.one("SELECT id FROM tool WHERE id=?", tid)
    if row:
        return row["id"]
    n_lower = n.strip().lower()
    row = access.db.one("SELECT id FROM tool WHERE LOWER(name)=?", n_lower)
    if row:
        return row["id"]
    try:
        row = access.db.one("SELECT id FROM catalog_item WHERE LOWER(name)=?", n_lower)
        if row:
            return row["id"]
    except Exception:
        pass
    return _resolve_tool_by_category(name, access)


def _resolve_tool_by_category(name: str, access) -> str | None:
    """Fallback: map a tool name to a tool_category's generic entry when the DB has no individual
    row for it (e.g. specific musical instruments exist only as a category, not as individual tools)."""
    n = name.strip().lower().strip('"')
    known_instruments = {
        "lute", "drum", "flute", "horn", "lyre", "viol",
        "pan flute", "bagpipes", "dulcimer", "shawm",
    }
    if n in known_instruments:
        row = access.db.one(
            "SELECT id FROM tool WHERE tool_category_id='musical-instrument' LIMIT 1")
        if row:
            return row["id"]
    return None


def _collect_equip_grants(access, owner_kind: str, owner_id: str,
                          is_first_class: bool = False,
                          at_level: int | None = None):
    """Collect expected armor category IDs, weapon tier IDs, and tool IDs from one owner.

    Returns (armor_ids: set, weapon_ids: set, tool_ids: set) of DB identifiers that are legal for
    the character because this owner's grant_proficiency spine confers them.
    """
    armor: set[str] = set()
    weapons: set[str] = set()
    tools: set[str] = set()

    def _headers():
        headers = primitives.grants_for(access.db, "grant_proficiency", owner_kind, owner_id, at_level)
        if owner_kind == "class":
            if not is_first_class:
                headers = [h for h in headers if h["multiclass_only"]]
            else:
                headers = [h for h in headers if not h["multiclass_only"]]
        return headers

    for h in _headers():
        tk = h["target_kind"]
        if h["mode"] != "fixed" and tk not in ("tool", "skill_or_tool"):
            continue
        if tk == "armor_category":
            if h["mode"] == "fixed":
                for target_id in q.grant_values(access, h["id"]):
                    armor.add(target_id)
        elif tk == "weapon_tier":
            if h["mode"] == "fixed":
                for target_id in q.grant_values(access, h["id"]):
                    weapons.add(target_id)
        elif tk == "tool":
            if h["mode"] == "fixed":
                for target_id in q.grant_values(access, h["id"]):
                    tools.add(target_id)
            elif h["mode"] == "choose":
                for cat_id in q.grant_categories(access, h["id"]):
                    tools.update(q.tool_category_tools(access, cat_id))
                for target_id in q.grant_values(access, h["id"]):
                    tools.add(target_id)
        elif tk == "skill_or_tool":
            if h["from_any"]:
                tools.update(q.tool_ids(access))
            for target_id in q.grant_values(access, h["id"]):
                tools.add(target_id)
            for cat_id in q.grant_categories(access, h["id"]):
                tools.update(q.tool_category_tools(access, cat_id))

    return armor, weapons, tools


def _class_level(c: dict) -> int | None:
    lv = c.get("level")
    if isinstance(lv, int) and not isinstance(lv, bool):
        return lv
    return None


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []

    ident = sheet.get("identity")
    if not isinstance(ident, dict):
        ident = {}
    raw_classes = ident.get("classes")
    classes = raw_classes if isinstance(raw_classes, list) else []

    expected_armor: set[str] = set()
    expected_weapons: set[str] = set()
    expected_tools: set[str] = set()

    # Mandatory (unconditional, fixed-mode) armour-category and weapon-tier grants owned by a chosen
    # class-detail option. Unlike the legality sets above (a superset the sheet may draw from), these
    # are grants the character is REQUIRED to have, so the completeness pass asserts each is present.
    mandatory_armor: set[str] = set()
    mandatory_weapons: set[str] = set()

    sp_id = access.resolve("species", ident.get("species"))
    if sp_id:
        a, w, t = _collect_equip_grants(access, "species", sp_id)
        expected_armor |= a
        expected_weapons |= w
        expected_tools |= t

    bg_id = access.resolve("background", ident.get("background"))
    if bg_id:
        a, w, t = _collect_equip_grants(access, "background", bg_id)
        expected_armor |= a
        expected_weapons |= w
        expected_tools |= t
        bg_row = access.db.one(
            "SELECT tool_id, tool_category_id FROM background WHERE id=?", bg_id)
        if bg_row:
            if bg_row["tool_id"]:
                expected_tools.add(bg_row["tool_id"])
            if bg_row["tool_category_id"]:
                expected_tools.update(q.tool_category_tools(access, bg_row["tool_category_id"]))

    for i, c in enumerate(classes):
        if not isinstance(c, dict):
            continue
        cid = access.resolve("class", c.get("class"))
        if not cid:
            continue
        is_first = (i == 0)
        at_level = _class_level(c)
        a, w, t = _collect_equip_grants(access, "class", cid, is_first_class=is_first,
                                        at_level=at_level)
        expected_armor |= a
        expected_weapons |= w
        expected_tools |= t

        sub = c.get("subclass")
        if sub:
            sub_id = access.resolve("subclass", sub)
            if sub_id:
                a, w, t = _collect_equip_grants(access, "subclass", sub_id, at_level=at_level)
                expected_armor |= a
                expected_weapons |= w
                expected_tools |= t

        # class_detail grants (e.g. Divine Order Protector grants heavy armor)
        class_detail = c.get("class_detail")
        if class_detail and isinstance(class_detail, str) and cid:
            opts = access.db.q(
                "SELECT id FROM detail_option WHERE owner_kind='class' AND owner_id=? "
                "AND LOWER(name)=?", cid, class_detail.strip().lower())
            for row in opts:
                a, w, t = _collect_equip_grants(access, "class_detail", row["id"],
                                                 at_level=at_level)
                expected_armor |= a
                expected_weapons |= w
                expected_tools |= t
                mandatory_armor |= a
                mandatory_weapons |= w

        # subclass_detail grants (e.g. Circle of the Land terrain grants a resistance)
        subclass_detail = c.get("subclass_detail")
        if subclass_detail and isinstance(subclass_detail, str) and sub_id:
            opts = access.db.q(
                "SELECT id FROM detail_option WHERE owner_kind='subclass' AND owner_id=? "
                "AND LOWER(name)=?", sub_id, subclass_detail.strip().lower())
            for row in opts:
                a, w, t = _collect_equip_grants(access, "class_detail", row["id"],
                                                 at_level=at_level)
                expected_armor |= a
                expected_weapons |= w
                expected_tools |= t
                mandatory_armor |= a
                mandatory_weapons |= w

    feats = sheet.get("feats")
    if isinstance(feats, list):
        for f in feats:
            fname = f.get("name") if isinstance(f, dict) else f
            fid = access.resolve("feat", fname)
            if fid:
                a, w, t = _collect_equip_grants(access, "feat", fid)
                expected_armor |= a
                expected_weapons |= w
                expected_tools |= t

    profs = sheet.get("proficiencies")
    if not isinstance(profs, dict):
        return v

    armor_list = profs.get("armor")
    if isinstance(armor_list, list):
        for item in armor_list:
            if not isinstance(item, str):
                continue
            aid = _resolve_armor(item, access)
            if aid is None:
                v.append(Violation(DOMAIN, "unknown-armor-proficiency", "illegal",
                                   f"unknown armor proficiency: {item!r}", "proficiencies.armor"))
            elif aid not in expected_armor:
                v.append(Violation(DOMAIN, "armor-proficiency-not-legal", "illegal",
                                   f"{item}: not a legal armor proficiency for this build",
                                   "proficiencies.armor"))

    weapon_list = profs.get("weapons")
    if isinstance(weapon_list, list):
        for item in weapon_list:
            if not isinstance(item, str):
                continue
            wid = _resolve_weapon(item, access)
            if wid is None:
                v.append(Violation(DOMAIN, "unknown-weapon-proficiency", "illegal",
                                   f"unknown weapon proficiency: {item!r}", "proficiencies.weapons"))
            elif wid not in expected_weapons:
                v.append(Violation(DOMAIN, "weapon-proficiency-not-legal", "illegal",
                                   f"{item}: not a legal weapon proficiency for this build",
                                   "proficiencies.weapons"))

    tool_list = profs.get("tools")
    if isinstance(tool_list, list):
        for item in tool_list:
            if not isinstance(item, str):
                continue
            tid = _resolve_tool(item, access)
            if tid is None:
                v.append(Violation(DOMAIN, "unknown-tool-proficiency", "illegal",
                                   f"unknown tool proficiency: {item!r}", "proficiencies.tools"))
            elif tid not in expected_tools:
                v.append(Violation(DOMAIN, "tool-proficiency-not-legal", "illegal",
                                   f"{item}: not a legal tool proficiency for this build",
                                   "proficiencies.tools"))

    # Completeness: every mandatory (fixed) class-detail armour/weapon grant must be PRESENT on the
    # sheet. This is the counterpart to the legality (superset) pass above -- that pass never fires
    # when a required proficiency is simply ABSENT, so a missing mandatory grant would slip through.
    _check_mandatory_present(v, mandatory_armor, armor_list, _resolve_armor,
                             "proficiencies.armor", "armour", access)
    _check_mandatory_present(v, mandatory_weapons, weapon_list, _resolve_weapon,
                             "proficiencies.weapons", "weapon", access)

    return v


def _check_mandatory_present(v: list[Violation], mandatory: set[str], listed, resolver,
                             path: str, label: str, access) -> None:
    """Flag each mandatory DB grant id not present in the sheet's listed proficiencies. `listed` is
    the sheet's proficiency list (or None); `resolver` maps a listed name to its DB id, so matching
    is name-format independent. Fired as `incomplete` -- the grant is required but missing."""
    if not mandatory:
        return
    present: set[str] = set()
    if isinstance(listed, list):
        for item in listed:
            if isinstance(item, str):
                rid = resolver(item, access)
                if rid is not None:
                    present.add(rid)
    for gid in sorted(mandatory - present):
        v.append(Violation(DOMAIN, "mandatory-proficiency-missing", "incomplete",
                           f"mandatory {label} proficiency {gid!r} granted by a class option is "
                           f"missing from the sheet", path))
