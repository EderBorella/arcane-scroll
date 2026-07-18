"""F05-T141 — recharge cadence + uses.

resource_state[key].recharge is read from the resource_recharge spine (a bounded pool shows its
collapsed cadence; a pool with no recharge row stays None). The resources check independently
re-derives the cadence and flags a mismatch. A feat that owns a bounded pool NOT already single-homed
in resource_budgets surfaces max + recharge on its own uses; a pool that IS a budget entry is left
single-homed in resource_state (not duplicated).

Synthetic fixtures: 'Pool A' (class-a) recovers on short OR long rest (collapses to short-rest),
'Pool Esc' (class-a) on long rest, 'Sub Ladder Pool' (subclass 'Sub Ladder') has no recharge row.
'Feat Res Boon' (feat 'Feat Res') recovers on a long rest."""
from app.derivation.modifier import ActiveEffects, derive_resource_state, derive_feats
from validator.checks.resources import check_recharge


def _core(budgets, classes=None, feats=None):
    return {
        "identity": {"species": "Species A",
                     "classes": classes if classes is not None
                     else [{"class": "Class A", "level": 6, "subclass": "Sub Ladder"}]},
        "feats": feats or [],
        "abilities": {"a1": {"final": 14}},
        "proficiency_bonus": 3,
        "resource_budgets": budgets,
    }


# ---- deriver: resource_state recharge ----

def test_bounded_pool_shows_collapsed_cadence(access):
    core = _core({"Pool A": {"max": 4}, "Pool Esc": {"max": 2}})
    rs = derive_resource_state(core, ActiveEffects(), access)
    # Pool A recovers on short OR long rest -> collapses to the more-frequent short-rest.
    assert rs["Pool A"]["recharge"] == "short-rest"
    assert rs["Pool Esc"]["recharge"] == "long-rest"


def test_unlimited_pool_stays_none(access):
    # 'Sub Ladder Pool' is owned (subclass Sub Ladder at level 6) but has no recharge row -> None.
    core = _core({"Sub Ladder Pool": {"max": 3}})
    rs = derive_resource_state(core, ActiveEffects(), access)
    assert rs["Sub Ladder Pool"]["recharge"] is None
    assert rs["Sub Ladder Pool"]["recharge_amount"] is None


# ---- validator: recharge re-derivation ----

def test_recharge_correct_passes(access):
    core = _core({"Pool A": {"max": 4}})
    resource_state = {"Pool A": {"max": 4, "remaining": 4,
                                 "recharge": "short-rest", "recharge_amount": None}}
    assert check_recharge(core, resource_state, access) == []


def test_recharge_wrong_cadence_flagged(access):
    core = _core({"Pool A": {"max": 4}})
    resource_state = {"Pool A": {"max": 4, "remaining": 4,
                                 "recharge": "long-rest", "recharge_amount": None}}
    codes = {v.code for v in check_recharge(core, resource_state, access)}
    assert "recharge-wrong" in codes


def test_recharge_unlimited_with_cadence_flagged(access):
    core = _core({"Sub Ladder Pool": {"max": 3}})
    resource_state = {"Sub Ladder Pool": {"max": 3, "remaining": 3,
                                          "recharge": "short-rest", "recharge_amount": None}}
    codes = {v.code for v in check_recharge(core, resource_state, access)}
    assert "recharge-wrong" in codes


# ---- deriver: feat uses single-homing ----

def test_feat_pool_single_homed_when_a_budget(access):
    # 'Feat Res Boon' is already a resource_budgets entry -> single-homed in resource_state, so the
    # feat's own uses is NOT duplicated (stays None).
    core = _core({"Feat Res Boon": {"max": 1}}, feats=[{"name": "Feat Res", "source": "asi"}])
    feats = derive_feats(core, access)
    entry = next(f for f in feats if f["name"] == "Feat Res")
    assert entry["uses"]["max"] is None
    assert "recharge" not in entry["uses"]


def test_feat_pool_surfaced_when_not_a_budget(access):
    # When the pool is NOT a budget entry, the feat surfaces its own max + recharge.
    core = _core({}, feats=[{"name": "Feat Res", "source": "asi"}])
    feats = derive_feats(core, access)
    entry = next(f for f in feats if f["name"] == "Feat Res")
    assert entry["uses"]["max"] == 1
    assert entry["uses"]["recharge"] == "long-rest"
