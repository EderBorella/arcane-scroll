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


# --------------------------------- class use pool gained above level 1 (F05-T113 shape)

def _esc_sheet(level, budgets):
    return _sheet(budgets, classes=[{"class": "Class A", "level": level, "subclass": None}])


def test_pool_gained_above_level_1_absent_below_it(access):
    # 'Pool Esc' is gained at level 4; a level-3 build does not own it, so a budget entry for it is
    # outside the check's remit — the pool is correctly gated below its first ladder level.
    assert check(_esc_sheet(3, {"Pool Esc": {"max": 1}}), access) == []


def test_pool_gained_above_level_1_first_step_max(access):
    assert check(_esc_sheet(4, {"Pool Esc": {"max": 1}}), access) == []


def test_pool_gained_above_level_1_wrong_first_step_flagged(access):
    assert "resource-max-wrong" in _codes(_esc_sheet(4, {"Pool Esc": {"max": 2}}), access)


def test_pool_gained_above_level_1_second_step_max(access):
    assert check(_esc_sheet(8, {"Pool Esc": {"max": 2}}), access) == []


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


# ------------------------------------------------ feat/subclass grant_resource (T114)

def _feat_sheet(budgets):
    """A build carrying feat-res (an always-on feat use-pool: 'Feat Res Boon', int max 1)."""
    return {
        "identity": {"classes": [{"class": "Class A", "level": 3, "subclass": None}]},
        "feats": [{"name": "feat-res"}],
        "resource_budgets": budgets,
    }


def test_feat_grant_resource_re_derived(access):
    assert check(_feat_sheet({"Feat Res Boon": {"max": 1}}), access) == []


def test_feat_grant_resource_wrong_max_flagged(access):
    assert "resource-max-wrong" in _codes(_feat_sheet({"Feat Res Boon": {"max": 2}}), access)


def test_subclass_grant_resource_re_derived(access):
    # sub-res grants 'Sub Res Power' (int max 1) at class level 3; a level-3 build owns it.
    sheet = _sheet({"Sub Res Power": {"max": 1}},
                   classes=[{"class": "Class A", "level": 3, "subclass": "Sub Res"}])
    assert check(sheet, access) == []


def test_subclass_grant_wrong_max_flagged(access):
    sheet = _sheet({"Sub Res Power": {"max": 3}},
                   classes=[{"class": "Class A", "level": 3, "subclass": "Sub Res"}])
    assert "resource-max-wrong" in _codes(sheet, access)


def test_subclass_grant_gated_on_class_level_no_multiclass_leak(access):
    # sub-res class is only level 2 (< 3), so 'Sub Res Power' is NOT owned even though the total
    # level (2 + 5) is past 3 — the check must treat a wrong-max entry as outside its remit, not flag
    # it against a leaked total-level derivation.
    sheet = _sheet({"Sub Res Power": {"max": 3}},
                   classes=[{"class": "Class A", "level": 2, "subclass": "Sub Res"},
                            {"class": "Class B", "level": 5, "subclass": None}])
    assert "resource-max-wrong" not in _codes(sheet, access)


# ----------------------------------------- subclass-owned count ladder (epic R1)

def _sub_ladder_sheet(level, budgets):
    return _sheet(budgets, classes=[{"class": "Class A", "level": level, "subclass": "Sub Ladder"}])


def test_subclass_count_ladder_re_derived(access):
    # sub-ladder's 'Sub Ladder Pool' count ladder is 2 at subclass level 3, 3 from level 6.
    assert check(_sub_ladder_sheet(3, {"Sub Ladder Pool": {"max": 2}}), access) == []
    assert check(_sub_ladder_sheet(6, {"Sub Ladder Pool": {"max": 3}}), access) == []


def test_subclass_count_ladder_wrong_max_flagged(access):
    assert "resource-max-wrong" in _codes(_sub_ladder_sheet(3, {"Sub Ladder Pool": {"max": 3}}), access)


def test_subclass_count_ladder_absent_below_first_level(access):
    # gained at subclass level 3; a level-2 build does not own it, so the entry is outside the remit.
    assert check(_sub_ladder_sheet(2, {"Sub Ladder Pool": {"max": 2}}), access) == []


def test_subclass_count_ladder_gated_on_class_level_no_multiclass_leak(access):
    # the sub-ladder class is only level 2 (< 3), so the pool is NOT owned even though the total level
    # (2 + 5) is past 3 — a wrong-max entry is outside the remit, not flagged on a leaked derivation.
    sheet = _sheet({"Sub Ladder Pool": {"max": 3}},
                   classes=[{"class": "Class A", "level": 2, "subclass": "Sub Ladder"},
                            {"class": "Class B", "level": 5, "subclass": None}])
    assert "resource-max-wrong" not in _codes(sheet, access)
