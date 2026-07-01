"""Layer: vitals & derived numbers (2024). Max HP within the legal range for the hit dice + Con; the
hit-dice pool matches (each class contributes its level in its own hit die); plus the cheap
self-consistent derivations — initiative = Dex modifier, passive Perception = 10 + Perception.
Collects all findings; never raises."""
from validator.report import Violation

LAYER = "vitals"


def check(sheet, rules):
    out = []
    ident = sheet.get("identity") or {}
    combat = sheet.get("combat") or {}
    abilities = sheet.get("abilities") or {}
    classes = ident.get("classes") or []
    total = ident.get("total_level")
    con = (abilities.get("con") or {}).get("modifier")

    dies = [(c, rules.hit_die(c.get("class"))) for c in classes]
    if classes and all(d is not None for _, d in dies):
        expected = {}
        for c, die in dies:
            expected[f"d{die}"] = expected.get(f"d{die}", 0) + (c.get("level") or 0)
        actual = combat.get("hit_dice") or {}
        if actual != expected:
            out.append(Violation(LAYER, "hit_dice_pool",
                                 f"hit-dice pool {actual} != expected {expected}", expected, actual))

        hp = (combat.get("hit_points") or {}).get("max")
        if hp is not None and con is not None and total:
            die0 = dies[0][1]
            max_hp = sum(die * (c.get("level") or 0) for c, die in dies) + con * total
            min_hp = die0 + (total - 1) + con * total     # L1 die maxed; other levels roll ≥ 1
            if not (min_hp <= hp <= max_hp):
                out.append(Violation(LAYER, "hp_out_of_range",
                                     f"max HP {hp} outside the legal range [{min_hp}, {max_hp}] for the hit dice + Con",
                                     [min_hp, max_hp], hp))

    init = combat.get("initiative")
    dexmod = (abilities.get("dex") or {}).get("modifier")
    if init is not None and dexmod is not None and init != dexmod:
        out.append(Violation(LAYER, "initiative", f"initiative {init} != Dex modifier {dexmod}", dexmod, init))

    pp = sheet.get("passive_perception")
    perc = next((v.get("modifier") for k, v in (sheet.get("skills") or {}).items()
                 if k.strip().lower() == "perception"), None)
    if pp is not None and perc is not None and pp != 10 + perc:
        out.append(Violation(LAYER, "passive_perception",
                             f"passive Perception {pp} != 10 + Perception modifier {perc}", 10 + perc, pp))
    return out
