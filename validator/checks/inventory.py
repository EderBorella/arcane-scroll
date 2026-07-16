"""Inventory domain (inventory:1 shape): validates equipped items and backpack entries against
the DB. 7 violations across 5 subtasks: item identity (duplicate-id, unknown-item), slot legality
(invalid-slot, two-handed-plus-shield), template resolution (invalid-template), single-use
casting item integrity (invalid-casting-consumable), and consumable attribution
(consumable-missing-inventory).

Violation paths point directly into the inventory:1 shape: ``equipped.<slot>``, ``backpack[<i>]``."""
from access.validator import inventory as q
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
        if off_cat.lower() == "shield":
            v.append(Violation(DOMAIN, "two-handed-plus-shield", "illegal",
                               f"two-handed weapon {main_name!r} + shield in off_hand",
                               "equipped.main_hand"))


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
    _check_templates(items, access, v)
    _check_casting_consumables(items, access, v)
    _check_consumable_attribution(sheet, items, access, v)

    return v
