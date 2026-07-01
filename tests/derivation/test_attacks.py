"""Attacks — weapon rows: ability selection (STR / DEX / finesse), proficiency bonus, damage strings."""
from app.derivation import derive
from app.derivation.attacks import attack_rows


def _mods(**kw):
    m = {"str": 3, "dex": 1, "con": 2, "int": 0, "wis": 1, "cha": 0}
    m.update(kw)
    return m


def _inv(*names):
    return [{"item": n, "quantity": 1} for n in names]


def test_martial_category_proficient(catalog):
    row = attack_rows(catalog, _mods(), 3, [("fighter", 5)], _inv("Blade"))[0]
    assert row == {"name": "Blade", "attack_bonus": 6, "damage": "1d8+3 Slashing"}   # str3 + pb3


def test_finesse_picks_better_ability(catalog):
    row = attack_rows(catalog, _mods(dex=5), 3, [("fighter", 5)], _inv("Foil"))[0]
    assert row["attack_bonus"] == 8 and row["damage"] == "1d8+5 Piercing"            # dex5 > str3


def test_ranged_uses_dex(catalog):
    row = attack_rows(catalog, _mods(dex=4), 3, [("fighter", 5)], _inv("Bow"))[0]
    assert row["attack_bonus"] == 7 and row["damage"] == "1d8+4 Piercing"


def test_two_handed_melee_uses_str(catalog):
    row = attack_rows(catalog, _mods(str=4, dex=9), 2, [("fighter", 1)], _inv("Maul"))[0]
    assert row["damage"] == "2d6+4 Bludgeoning"                                       # str, no finesse


def test_versatile_notes_two_handed_dice(catalog):
    row = attack_rows(catalog, _mods(str=2), 2, [("fighter", 1)], _inv("Pike"))[0]
    assert row["damage"] == "1d6+2 Piercing (versatile 1d8+2)"


def test_proficiency_bonus_only_when_proficient(catalog):
    # mage is proficient with Foils (a specific-weapon prof) but not with a martial Blade
    rows = {r["name"]: r for r in attack_rows(catalog, _mods(str=3, dex=3), 3, [("mage", 3)],
                                              _inv("Foil", "Blade"))}
    assert rows["Foil"]["attack_bonus"] == 6      # 3 + pb3 (proficient)
    assert rows["Blade"]["attack_bonus"] == 3     # 3 + 0 (not proficient)


def test_nonweapons_skipped(catalog):
    rows = attack_rows(catalog, _mods(), 3, [("fighter", 5)], _inv("Shield", "Club"))
    assert [r["name"] for r in rows] == ["Club"]


def test_attacks_through_derive(catalog):
    choices = {"race": "Human", "classes": [{"class": "Warrior", "level": 3}],
               "ability_assignment": {"str": 16, "dex": 10, "con": 14, "int": 8, "wis": 12, "cha": 10},
               "equipment_0": "Club"}
    row = next(r for r in derive(catalog, choices)["attacks"] if r["name"] == "Club")
    assert row["attack_bonus"] == 3 and row["damage"] == "1d4+3 Bludgeoning"          # str16 mod, no prof
