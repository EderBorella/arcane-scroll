from validator.checks.proficiencies_equip import check


def _sheet(armor=None, weapons=None, tools=None, classes=None, background="Background A",
           species="Species A", feats=None):
    profs = {}
    if armor is not None:
        profs["armor"] = armor
    if weapons is not None:
        profs["weapons"] = weapons
    if tools is not None:
        profs["tools"] = tools
    return {
        "identity": {
            "classes": classes if classes is not None else [{"class": "Class A", "level": 3}],
            "background": background,
            "species": species,
        },
        "feats": feats if feats is not None else [],
        "proficiencies": profs,
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_clean_sheet_with_expected_proficiencies_has_no_findings(access):
    sheet = _sheet(
        armor=["light armor", "medium armor"],
        weapons=["simple weapons"],
    )
    assert check(sheet, access) == []


def test_no_proficiencies_dict_has_no_findings(access):
    sheet = _sheet()
    sheet.pop("proficiencies")
    assert check(sheet, access) == []


def test_armor_not_granted_is_illegal(access):
    sheet = _sheet(armor=["heavy armor"])
    assert "armor-proficiency-not-legal" in _codes(sheet, access)


def test_weapon_not_granted_is_illegal(access):
    sheet = _sheet(weapons=["martial weapons"])
    assert "weapon-proficiency-not-legal" in _codes(sheet, access)


def test_tool_not_granted_is_illegal(access):
    sheet = _sheet(tools=["Smith's Tools"])
    assert "tool-proficiency-not-legal" in _codes(sheet, access)


def test_unknown_armor_is_flagged(access):
    sheet = _sheet(armor=["mythril armor"])
    assert "unknown-armor-proficiency" in _codes(sheet, access)


def test_unknown_weapon_is_flagged(access):
    sheet = _sheet(weapons=["laser weapons"])
    assert "unknown-weapon-proficiency" in _codes(sheet, access)


def test_unknown_tool_is_flagged(access):
    sheet = _sheet(tools=["Arcane Widget"])
    assert "unknown-tool-proficiency" in _codes(sheet, access)


def test_multiclass_secondary_class_weapon_grants_martial(access):
    sheet = _sheet(
        weapons=["simple weapons", "martial weapons"],
        classes=[{"class": "Class A", "level": 3}, {"class": "Class B", "level": 1}],
        background=None, species=None,
    )
    codes = _codes(sheet, access)
    assert "weapon-proficiency-not-legal" not in codes


def test_multiclass_weapon_requires_secondary_class_present(access):
    sheet = _sheet(
        weapons=["simple weapons", "martial weapons"],
        classes=[{"class": "Class A", "level": 3}],
        background=None, species=None,
    )
    assert "weapon-proficiency-not-legal" in _codes(sheet, access)


def test_subclass_shield_at_level_3_is_legal(access):
    sheet = _sheet(
        armor=["light armor", "medium armor", "shields"],
        classes=[{"class": "Class A", "subclass": "Sub A", "level": 3}],
        background=None, species=None,
    )
    codes = _codes(sheet, access)
    assert "armor-proficiency-not-legal" not in codes


def test_subclass_shield_before_level_3_is_illegal(access):
    sheet = _sheet(
        armor=["light armor", "medium armor", "shields"],
        classes=[{"class": "Class A", "subclass": "Sub A", "level": 2}],
        background=None, species=None,
    )
    assert "armor-proficiency-not-legal" in _codes(sheet, access)


def test_background_tool_is_legal(access):
    sheet = _sheet(
        tools=["Herbalism Kit"],
        background="Background A",
    )
    codes = _codes(sheet, access)
    assert "tool-proficiency-not-legal" not in codes


def test_case_insensitive_name_matching(access):
    sheet = _sheet(
        armor=["Light Armor", "Medium Armor"],
        weapons=["Simple Weapons"],
    )
    assert check(sheet, access) == []


def test_shield_vs_shields_are_equivalent(access):
    sheet = _sheet(
        armor=["light armor", "medium armor", "shield"],
        classes=[{"class": "Class A", "subclass": "Sub A", "level": 3}],
        background=None, species=None,
    )
    codes = _codes(sheet, access)
    assert "armor-proficiency-not-legal" not in codes
    assert "unknown-armor-proficiency" not in codes


def test_malformed_identity_not_a_dict_does_not_raise(access):
    sheet = _sheet(armor=["light armor", "medium armor"])
    sheet["identity"] = "oops"
    codes = _codes(sheet, access)
    assert "armor-proficiency-not-legal" in codes   # no grants resolved
