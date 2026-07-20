"""F07-T12 — validator under-fill `incomplete` emissions (G5).

An empty / under-filled REQUIRED choice field (skills / expertise / tools / languages) now yields an
`incomplete` finding, re-derived independently from the reference rules via the validator's OWN access
layer. Over-fill stays `illegal` (unchanged). Synthetic ids only.

The build fixtures reuse the shared synthetic rules DB: class-a grants a skill pool (choose 2) plus an
expertise pick (1 at L1, a 2nd at L6); class-tl grants a language choice (2), a tool choice (1) and an
expertise choice (1). Background A grants one fixed skill and one fixed tool.
"""
import validator.checks.proficiencies as prof
from validator.checks.proficiencies import check


def _sk(proficient=True, expertise=False):
    return {"ability": "Ability 1", "proficient": proficient, "expertise": expertise}


def _codes_by_kind(sheet, access):
    return {(v.code, v.kind) for v in check(sheet, access)}


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


# --------------------------------------------------------------------------- skills under-fill

def test_underfilled_skills_are_incomplete(access):
    # class-a (choose 2) + Background A (1 fixed skill) => budget 3; only one proficient skill chosen.
    sheet = {"identity": {"classes": [{"class": "Class A", "level": 3}], "background": "Background A"},
             "skills": {"sk1": _sk()}, "feats": []}
    assert ("too-few-skill-proficiencies", "incomplete") in _codes_by_kind(sheet, access)


def test_absent_skills_with_a_budget_are_incomplete(access):
    # A partial sheet with NO skills key at all, but a build that must choose some, is incomplete
    # (previously the check returned clean for absent skills — proficiencies.py:171-172).
    sheet = {"identity": {"classes": [{"class": "Class A", "level": 3}], "background": "Background A"},
             "feats": []}
    assert "too-few-skill-proficiencies" in _codes(sheet, access)


def test_fully_chosen_skills_are_not_flagged(access):
    # sk1,sk2 (class pool) + sk4 (background) + sk5 (species fixed) fills the budget exactly.
    sheet = {"identity": {"classes": [{"class": "Class A", "level": 3}],
                          "background": "Background A", "species": "Species A"},
             "skills": {"sk1": _sk(expertise=True), "sk2": _sk(), "sk4": _sk(), "sk5": _sk()},
             "feats": []}
    assert "too-few-skill-proficiencies" not in _codes(sheet, access)


# --------------------------------------------------------------------------- expertise under-fill

def test_unfilled_expertise_is_incomplete(access):
    # class-a grants one expertise pick at L1; a sheet that makes none is incomplete.
    sheet = {"identity": {"classes": [{"class": "Class A", "level": 3}],
                          "background": "Background A", "species": "Species A"},
             "skills": {"sk1": _sk(), "sk2": _sk(), "sk4": _sk(), "sk5": _sk()}, "feats": []}
    assert ("too-few-expertise", "incomplete") in _codes_by_kind(sheet, access)


def test_filled_expertise_is_not_flagged(access):
    sheet = {"identity": {"classes": [{"class": "Class A", "level": 3}],
                          "background": "Background A", "species": "Species A"},
             "skills": {"sk1": _sk(expertise=True), "sk2": _sk(), "sk4": _sk(), "sk5": _sk()},
             "feats": []}
    assert "too-few-expertise" not in _codes(sheet, access)


# --------------------------------------------------------------------------- language under-fill

def test_unfilled_languages_are_incomplete(access):
    # class-tl (first class, L2) must choose 2 languages; a sheet with none is incomplete.
    sheet = {"identity": {"classes": [{"class": "Class TL", "level": 2}]}}
    codes = _codes_by_kind(sheet, access)
    assert ("too-few-languages", "incomplete") in codes


def test_partially_filled_languages_are_incomplete(access):
    sheet = {"identity": {"classes": [{"class": "Class TL", "level": 2}]},
             "languages": ["lang-a"]}
    assert "too-few-languages" in _codes(sheet, access)


def test_fully_chosen_languages_are_not_flagged(access):
    sheet = {"identity": {"classes": [{"class": "Class TL", "level": 2}]},
             "languages": ["lang-a", "lang-b"]}
    assert "too-few-languages" not in _codes(sheet, access)


def test_build_without_a_language_choice_is_never_flagged(access):
    # class-a makes no language choice -> no language finding regardless of the sheet's languages.
    sheet = {"identity": {"classes": [{"class": "Class A", "level": 3}], "background": "Background A"},
             "skills": {"sk1": _sk(expertise=True), "sk2": _sk(), "sk4": _sk()},
             "languages": [], "feats": []}
    assert "too-few-languages" not in _codes(sheet, access)


# --------------------------------------------------------------------------- tool under-fill

def test_unfilled_tools_are_incomplete(access):
    # class-tl (first class) must choose 1 tool; Background A confers 1 fixed tool -> a complete
    # sheet lists 2. A sheet with none is incomplete.
    sheet = {"identity": {"classes": [{"class": "Class TL", "level": 2}], "background": "Background A"},
             "proficiencies": {"armor": [], "weapons": [], "tools": []}}
    assert "too-few-tool-proficiencies" in _codes(sheet, access)


def test_fully_chosen_tools_are_not_flagged(access):
    # fixed background tool + the chosen tool = 2 present == required.
    sheet = {"identity": {"classes": [{"class": "Class TL", "level": 2}], "background": "Background A"},
             "proficiencies": {"armor": [], "weapons": [], "tools": ["Herb Kit", "Tool X"]}}
    assert "too-few-tool-proficiencies" not in _codes(sheet, access)


def test_build_without_a_tool_choice_is_never_flagged(access):
    # class-a makes no tool CHOICE; a fixed-only tool shortfall stays out of scope (F05-T19).
    sheet = {"identity": {"classes": [{"class": "Class A", "level": 3}], "background": "Background A"},
             "skills": {"sk1": _sk(expertise=True), "sk2": _sk(), "sk4": _sk()},
             "proficiencies": {"armor": [], "weapons": [], "tools": []}, "feats": []}
    assert "too-few-tool-proficiencies" not in _codes(sheet, access)


# --------------------------------------------------------------------------- over-fill unchanged

def test_over_fill_still_illegal(access):
    # A 4th proficient skill over a budget of 3 is still an ERROR (illegal), not a WARNING.
    sheet = {"identity": {"classes": [{"class": "Class A", "level": 3}], "background": "Background A"},
             "skills": {"sk1": _sk(expertise=True), "sk2": _sk(), "sk3": _sk(), "sk4": _sk()},
             "feats": []}
    codes = _codes_by_kind(sheet, access)
    assert ("too-many-skill-proficiencies", "illegal") in codes
    # a build that is over-filled is not simultaneously under-filled
    assert "too-few-skill-proficiencies" not in {c for c, _ in codes}


def test_malformed_skills_still_illegal_and_does_not_crash(access):
    sheet = {"identity": {"classes": [{"class": "Class A", "level": 3}]}, "skills": "oops"}
    assert ("malformed-skills", "illegal") in _codes_by_kind(sheet, access)


# --------------------------------------------------------------------------- two-layer independence

def test_validator_does_not_import_generation_or_manifest():
    # The under-fill re-derivation must be independent: the validator never imports the generator,
    # the deriver, or the T11 manifest builder (that would collapse the two independent layers).
    src = open(prof.__file__, encoding="utf-8").read()
    for forbidden in ("app.generation", "app.derivation", "manifest"):
        assert forbidden not in src, f"validator must not reference {forbidden!r}"
