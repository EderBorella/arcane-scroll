"""Inventory domain (inventory:1 shape): validates equipped items and backpack entries against
the DB. Item identity (duplicate-id, unknown-item), slot legality (invalid-slot,
two-handed-plus-shield), equipped-slot grounding (slot-assignment-mismatch — a weapon / worn armour
/ held shield sitting in a slot its DB facts forbid), catalog-enrichment re-derivation
(enrichment-mismatch — a stated weapon / armour fact that contradicts the DB), template resolution
(invalid-template), single-use casting item integrity (invalid-casting-consumable), and consumable
attribution (consumable-missing-inventory).

Violation paths point directly into the inventory:1 shape: ``equipped.<slot>``, ``backpack[<i>]``."""
from access.validator import inventory as q
from validator.checks._vocab import armor_category_id
from validator.report import Violation

DOMAIN = "inventory"


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _collect_items(sheet: dict) -> list[tuple[str | None, dict, str]]:
    """Return [(slot_or_None, item_dict, path_prefix), ...] for all items in the sheet."""
    items: list[tuple[str | None, dict, str]] = []
    equipped = sheet.get("equipped")
    if isinstance(equipped, dict):
        for slot, item in equipped.items():
            if isinstance(item, dict):
                items.append((slot, item, f"equipped.{slot}"))
    backpack = sheet.get("backpack")
    if isinstance(backpack, list):
        for i, item in enumerate(backpack):
            if isinstance(item, dict):
                items.append((None, item, f"backpack[{i}]"))
    return items


# ── C-I1a: item identity ─────────────────────────────────────────────────────


def _check_duplicate_ids(items: list[tuple[str | None, dict, str]],
                         v: list[Violation]) -> None:
    seen: dict[str, str] = {}
    for slot, item, path in items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        if item_id in seen:
            v.append(Violation(DOMAIN, "duplicate-item-id", "illegal",
                               f"duplicate item id {item_id!r} (first seen at {seen[item_id]})",
                               f"{path}.id"))
        else:
            seen[item_id] = path


def _check_item_names(items: list[tuple[str | None, dict, str]],
                      access, v: list[Violation]) -> None:
    for slot, item, path in items:
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        if not q.item_exists(access, name):
            v.append(Violation(DOMAIN, "unknown-catalog-item", "illegal",
                               f"unknown item: {name!r}", f"{path}.name"))


# ── C-I1b: slot legality ─────────────────────────────────────────────────────


def _check_slot_legality(sheet: dict, items: list[tuple[str | None, dict, str]],
                         access, v: list[Violation]) -> None:
    equipped = sheet.get("equipped")
    if not isinstance(equipped, dict):
        return

    valid_slots = q.get_slot_ids(access)
    slot_items: dict[str, list[str]] = {}

    for slot, item in equipped.items():
        if not isinstance(item, dict):
            continue
        if slot not in valid_slots:
            v.append(Violation(DOMAIN, "invalid-slot", "illegal",
                               f"unknown slot: {slot!r}", "equipped"))
            continue

        item_id = item.get("id", "")
        slot_items.setdefault(slot, []).append(item_id)

        if len(slot_items[slot]) > 1:
            v.append(Violation(DOMAIN, "invalid-slot", "illegal",
                               f"slot {slot!r} has multiple items", f"equipped.{slot}"))

    _check_two_handed_shield_combo(sheet, access, v)


def _check_two_handed_shield_combo(sheet: dict, access,
                                   v: list[Violation]) -> None:
    equipped = sheet.get("equipped")
    if not isinstance(equipped, dict):
        return

    main_hand = equipped.get("main_hand")
    if not isinstance(main_hand, dict):
        return

    off_hand = equipped.get("off_hand")
    if not isinstance(off_hand, dict):
        return

    main_name = main_hand.get("name")
    if not isinstance(main_name, str):
        return

    main_id = access.resolve("catalog_item", main_name)
    if main_id is None:
        main_id = access.resolve("magic_item", main_name)

    if main_id is not None and q.item_is_two_handed(access, main_id):
        off_name = off_hand.get("name", "")
        off_cat = off_hand.get("category") or off_hand.get("armor_category") or ""
        if armor_category_id(off_cat) == "shield":
            v.append(Violation(DOMAIN, "two-handed-plus-shield", "illegal",
                               f"two-handed weapon {main_name!r} + shield in off_hand",
                               "equipped.main_hand"))


# ── C-I1b2: equipped-slot grounding ──────────────────────────────────────────


def _grounded_slots(access, name: str) -> set[str] | None:
    """The body slots a mundane catalogue item may occupy, re-derived from DB facts, or None when
    the item's slot is not DB-groundable (a magic item, an unresolved name, or a kind with no
    rules-bound slot — tools / gear / adventuring gear go to the backpack, and wondrous magic items
    occupy slots the DB does not bind to a base category).

    Grounded in the reference rules' equipment model: armour is WORN (it occupies the armour slot), a
    shield is HELD (the shield slot), and a weapon is WIELDED in a hand (main or off hand). Only the
    armour and shield slots are rules-bound to an item category, so those are the facts re-derived
    here (F05-T102)."""
    if q.item_is_magic(access, name):
        return None
    cid = access.resolve("catalog_item", name)
    if cid is None:
        return None
    kind = q.catalog_kind(access, cid)
    if kind == "weapon":
        return {"main_hand", "off_hand"}
    if kind == "armor":
        facts = q.armor_facts(access, cid)
        category = facts["category_id"] if facts else None
        if category is None:
            return None
        return {"shield"} if armor_category_id(category) == "shield" else {"armor"}
    return None


def _check_slot_grounding(sheet: dict, access, v: list[Violation]) -> None:
    """Assert each equipped item sits in a slot its DB facts permit. Independent of the generator's
    slot-assignment heuristic: the permissible slots are re-derived from the item's catalogue kind
    and armour category (see :func:`_grounded_slots`), so a weapon parked in the armour slot, or
    worn armour placed in a hand, is flagged. Items whose slot is not DB-groundable are skipped."""
    equipped = sheet.get("equipped")
    if not isinstance(equipped, dict):
        return
    for slot, item in equipped.items():
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        grounded = _grounded_slots(access, name)
        if grounded is None or slot in grounded:
            continue
        v.append(Violation(DOMAIN, "slot-assignment-mismatch", "illegal",
                           f"{name!r} in slot {slot!r}: its facts permit only "
                           f"{sorted(grounded)}", f"equipped.{slot}"))


# ── C-I1b3: catalog-enrichment re-derivation ─────────────────────────────────


def _check_enrichment(items: list[tuple[str | None, dict, str]],
                      access, v: list[Violation]) -> None:
    """Independently re-derive an item's catalogue facts from the DB and flag any the sheet ASSERTS
    that contradict them. Grounded in the reference rules DB, never the deriver's output: a weapon's
    base damage dice / type and an armour's numeric defence facts (base AC, shield AC bonus, Dex cap,
    Strength requirement) are re-read from the ``weapon`` / ``armor`` rows and compared to the values
    the sheet carries.

    Only genuine CONTRADICTIONS are flagged — a value the sheet states that differs from the DB fact.
    An omitted fact is not an error (the sheet need not restate every catalogue fact), and a magic
    item is skipped (its facts derive from the magic item, not a mundane base row). The armour-category
    label is compared through the shared vocabulary normaliser (F05-T120), so a short corpus display
    form (``heavy``) and the DB id (``heavy-armor``) compare equal while a genuinely wrong category
    still flags."""
    for _slot, item, path in items:
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        if q.item_is_magic(access, name):
            continue
        cid = access.resolve("catalog_item", name)
        if cid is None:
            continue

        weapon = q.weapon_damage_facts(access, cid)
        if weapon is not None:
            _enrich_weapon(item, weapon, access, path, v)

        armor = q.armor_facts(access, cid)
        if armor is not None:
            _enrich_armor(item, armor, path, v)


def _enrich_weapon(item: dict, weapon: dict, access, path: str, v: list[Violation]) -> None:
    dice = item.get("damage_dice")
    if isinstance(dice, str) and weapon["damage_dice"] and dice != weapon["damage_dice"]:
        v.append(Violation(DOMAIN, "enrichment-mismatch", "illegal",
                           f"{path}: damage_dice {dice!r} != DB {weapon['damage_dice']!r}",
                           f"{path}.damage_dice"))
    dtype = item.get("damage_type")
    if isinstance(dtype, str) and weapon["damage_type_id"]:
        resolved = access.resolve("damage_type", dtype) or dtype
        if resolved != weapon["damage_type_id"]:
            v.append(Violation(DOMAIN, "enrichment-mismatch", "illegal",
                               f"{path}: damage_type {dtype!r} != DB "
                               f"{weapon['damage_type_id']!r}", f"{path}.damage_type"))
    props = item.get("properties")
    if isinstance(props, list):
        resolved = {access.resolve("weapon_property_vocab", p) or p
                    for p in props if isinstance(p, str)}
        extra = resolved - weapon["properties"]
        for p in sorted(extra):
            v.append(Violation(DOMAIN, "enrichment-mismatch", "illegal",
                               f"{path}: property {p!r} not on the DB weapon", f"{path}.properties"))


def _enrich_armor(item: dict, armor: dict, path: str, v: list[Violation]) -> None:
    for field in ("base_ac", "ac_bonus", "dex_cap", "strength_req"):
        stated = item.get(field)
        expected = armor[field]
        if _int(stated) and _int(expected) and stated != expected:
            v.append(Violation(DOMAIN, "enrichment-mismatch", "illegal",
                               f"{path}: {field} {stated} != DB {expected}", f"{path}.{field}"))

    stated_cat = item.get("armor_category")
    db_cat = armor.get("category_id")
    if isinstance(stated_cat, str) and stated_cat and db_cat:
        if armor_category_id(stated_cat) != armor_category_id(db_cat):
            v.append(Violation(DOMAIN, "enrichment-mismatch", "illegal",
                               f"{path}: armor_category {stated_cat!r} != DB {db_cat!r}",
                               f"{path}.armor_category"))


# ── C-I1c: template resolution ───────────────────────────────────────────────


def _check_templates(items: list[tuple[str | None, dict, str]],
                     access, v: list[Violation]) -> None:
    for slot, item, path in items:
        template = item.get("template_item")
        if template is None:
            continue
        if not isinstance(template, str):
            continue

        base_item = item.get("base_item")
        err = q.template_valid(access, template, base_item if isinstance(base_item, str) else None)
        if err is not None:
            v.append(Violation(DOMAIN, "invalid-template", "illegal",
                               err, f"{path}.template_item"))


# ── C-I1d: single-use casting item integrity ─────────────────────────────────


def _check_casting_consumables(items: list[tuple[str | None, dict, str]],
                               access, v: list[Violation]) -> None:
    for slot, item, path in items:
        spell_id = item.get("spell_id")
        if spell_id is None:
            continue
        if not isinstance(spell_id, str):
            continue
        if access.resolve("spell", spell_id) is None:
            v.append(Violation(DOMAIN, "invalid-casting-consumable", "illegal",
                               f"unknown spell_id: {spell_id!r}", f"{path}.spell_id"))


# ── C-I1e: consumable attribution ────────────────────────────────────────────


def _check_consumable_attribution(sheet: dict, items: list[tuple[str | None, dict, str]],
                                  access, v: list[Violation]) -> None:
    modifier = sheet.get("modifier")
    if modifier is None:
        return

    item_states = modifier.get("item_states", [])
    if not isinstance(item_states, list):
        return

    inventory_ids = set()
    for slot, item, path in items:
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            inventory_ids.add(item_id)

    for istate in item_states:
        if not isinstance(istate, dict):
            continue
        if not istate.get("consumable"):
            continue
        inv_ref = istate.get("inventory_ref")
        if not isinstance(inv_ref, str):
            continue
        if inv_ref not in inventory_ids:
            v.append(Violation(DOMAIN, "consumable-missing-inventory", "illegal",
                               f"consumable {inv_ref!r} in MODIFIER has no INVENTORY entry",
                               inv_ref))


# ── dispatcher ───────────────────────────────────────────────────────────────


def check(sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []

    if sheet.get("equipped") is None and not isinstance(sheet.get("backpack"), list):
        return v

    items = _collect_items(sheet)

    _check_duplicate_ids(items, v)
    _check_item_names(items, access, v)
    _check_slot_legality(sheet, items, access, v)
    _check_slot_grounding(sheet, access, v)
    _check_enrichment(items, access, v)
    _check_templates(items, access, v)
    _check_casting_consumables(items, access, v)
    _check_consumable_attribution(sheet, items, access, v)

    return v
