"""Resource-budget check (F05-T74): a class-resource-ladder budget entry must declare the maximum
the ladder confers at the build's level. Entries the ladder does not model are outside its remit."""
from validator.checks.resources import check


def _sheet(budgets, classes=None):
    return {
        "identity": {"classes": classes if classes is not None
                     else [{"class": "Class A", "level": 3, "subclass": None}]},
        "resource_budgets": budgets,
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_correct_ladder_max_passes(access):
    # class-a's 'Pool A' count ladder is 3 at level 3.
    assert check(_sheet({"Pool A": {"max": 3}}), access) == []


def test_wrong_ladder_max_flagged(access):
    assert "resource-max-wrong" in _codes(_sheet({"Pool A": {"max": 5}}), access)


def test_loose_plural_still_matches_ladder(access):
    # a loose plural label still maps to the ladder resource (normalised match).
    assert check(_sheet({"Pool As": {"max": 3}}), access) == []


def test_unmodelled_resource_is_ignored(access):
    # a pool the class-resource ladder does not model is outside this check's remit — no finding.
    assert check(_sheet({"Some Feature Use": {"max": 1}}), access) == []


def test_absent_budgets_no_findings(access):
    assert check({"identity": {}}, access) == []


def test_malformed_budgets_flagged(access):
    assert "malformed-resource-budgets" in _codes({"resource_budgets": "nope"}, access)


def test_ladder_max_gated_by_level(access):
    # at level 1 the ladder confers 2, so a level-1 build declaring 3 is wrong.
    sheet = _sheet({"Pool A": {"max": 3}}, classes=[{"class": "Class A", "level": 1}])
    assert "resource-max-wrong" in _codes(sheet, access)


# ------------------------------------------------------- species/lineage grant_resource (T101/T98)

def _grant_sheet(budgets):
    """A level-3 species-l + lin-l1 build (PB 2; a1 final 17 -> modifier 3), so the grant_resource
    maxima are: int -> 1, ability_modifier(a1) -> 3, proficiency_bonus -> 2."""
    return {
        "identity": {"species": "Species L", "lineage": "Lineage One",
                     "classes": [{"class": "Class A", "level": 3, "subclass": None}]},
        "abilities": {"x1": {"final": 17}},
        "resource_budgets": budgets,
    }


def test_grant_resource_int_max(access):
    assert check(_grant_sheet({"Species L Boon": {"max": 1}}), access) == []


def test_grant_resource_proficiency_bonus_max(access):
    assert check(_grant_sheet({"Lineage L Power": {"max": 2}}), access) == []


def test_grant_resource_ability_modifier_max(access):
    assert check(_grant_sheet({"Species L Focus": {"max": 3}}), access) == []


def test_grant_resource_wrong_max_flagged(access):
    assert "resource-max-wrong" in _codes(_grant_sheet({"Lineage L Power": {"max": 4}}), access)
