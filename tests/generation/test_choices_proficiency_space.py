"""Choice-space coverage for the tool / language / expertise proficiency choices and the equipment
choice-items (F07 D3 — T07/T08/T09).

Proves the three deliverables at the generator (rule) layer, on synthetic ids only:

* **Presence + counts** — the build's required tool / language / expertise choice counts are derived
  independently from the grant spine, level-gated and multiclass-gated;
* **Validate-a-pick** — a pick is accepted only when a grant admits it (from-any / category /
  named-pool), an illegal pick is dropped, and the list is capped at the required count;
* **No option pool** — the grammar offers these as free string arrays (no enum), and the readers
  expose only membership predicates — the copyrighted candidate menus are never emitted;
* **Choice-items** — a bundle's tool-category / focus / proficiency-choice entries are represented as
  flaggable gaps rather than silently dropped.

Feat-granted choices are out of the pass-1 owner scope by design (a feat is itself a pass-1 pick),
mirroring how the skill-choice pool is the first class's alone.
"""
from app.generation.choices import assemble, grammar, options, parse_request


def _spec(gen_access, classes, **kw):
    payload = {"species": "species-a", "background": "bg-a", "classes": classes}
    payload.update(kw)
    return parse_request(gen_access, payload)


# --------------------------------------------------------------------------- presence + counts

def test_language_choice_presence_and_count(gen_access):
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    n, grants = options.language_choice(gen_access, [("class-tl", 2, None)], spec)
    assert n == 2 and [g[2]["id"] for g in grants] == ["gpr-tl-lang"]
    # level-gated: no language choice before the granting level
    spec1 = _spec(gen_access, [{"class": "class-tl", "level": 1}])
    assert options.language_choice(gen_access, [("class-tl", 1, None)], spec1) == (0, [])
    # a plain class makes no language choice
    spec_a = _spec(gen_access, [{"class": "class-a", "level": 3}])
    assert options.language_choice(gen_access, [("class-a", 3, None)], spec_a)[0] == 0


def test_tool_choice_count(gen_access):
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    assert options.tool_choice(gen_access, [("class-tl", 2, None)], spec)[0] == 1
    spec_a = _spec(gen_access, [{"class": "class-a", "level": 3}])
    assert options.tool_choice(gen_access, [("class-a", 3, None)], spec_a)[0] == 0


def test_expertise_choice_count(gen_access):
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    assert options.expertise_choice(gen_access, [("class-tl", 2, None)], spec)[0] == 1
    # class-a grants one expertise choice at level 1 (a second unlocks at level 6)
    spec_a = _spec(gen_access, [{"class": "class-a", "level": 3}])
    assert options.expertise_choice(gen_access, [("class-a", 3, None)], spec_a)[0] == 1
    assert options.expertise_choice(gen_access, [("class-a", 8, None)], spec_a)[0] == 2


# --------------------------------------------------------------------------- multiclass gating

def test_choice_gating_across_multiclass(gen_access):
    # class-tl as a SECONDARY class: its first-class-only language grant (multiclass_only=0) no
    # longer applies, but its secondary-only tool grant (multiclass_only=1) does — the reduced
    # multiclass proficiency set.
    spec = _spec(gen_access, [{"class": "class-a", "level": 3}, {"class": "class-tl", "level": 2}])
    resolved = [("class-a", 3, None), ("class-tl", 2, None)]
    assert options.language_choice(gen_access, resolved, spec)[0] == 0
    assert options.tool_choice(gen_access, resolved, spec)[0] == 1
    # as the FIRST (single) class the first-class grants apply instead
    spec_first = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    assert options.language_choice(gen_access, [("class-tl", 2, None)], spec_first)[0] == 2


# --------------------------------------------------------------------------- validate-a-pick

def test_language_pick_validation(gen_access):
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    resolved = [("class-tl", 2, None)]
    assert options.language_pick_is_valid(gen_access, resolved, spec, "lang-a") is True
    assert options.language_pick_is_valid(gen_access, resolved, spec, "not-a-language") is False
    assert options.language_pick_is_valid(gen_access, resolved, spec, "tool-x") is False


def test_tool_pick_validation_by_category(gen_access):
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    resolved = [("class-tl", 2, None)]
    assert options.tool_pick_is_valid(gen_access, resolved, spec, "tool-x") is True   # in tc-music
    assert options.tool_pick_is_valid(gen_access, resolved, spec, "tool-z") is False  # no category
    assert options.tool_pick_is_valid(gen_access, resolved, spec, "lang-a") is False


def test_expertise_pick_validation_named_pool_vs_any(gen_access):
    # class-tl names a pool {sk1, sk2}
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    resolved = [("class-tl", 2, None)]
    assert options.expertise_pick_is_valid(gen_access, resolved, spec, "sk1") is True
    assert options.expertise_pick_is_valid(gen_access, resolved, spec, "sk3") is False
    # class-a names no pool -> any skill is a legal pick (proficiency prereq is a downstream concern)
    spec_a = _spec(gen_access, [{"class": "class-a", "level": 3}])
    assert options.expertise_pick_is_valid(gen_access, [("class-a", 3, None)], spec_a, "sk3") is True


# --------------------------------------------------------------------------- grammar shape

def test_grammar_offers_choice_fields_without_option_enum(gen_access):
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    schema = grammar.build_pass1_grammar(gen_access, spec, [("class-tl", 2, None)])
    props = schema["properties"]
    for field, n in (("languages", 2), ("tools", 1), ("expertise", 1)):
        assert field in props and field in schema["required"]
        assert props[field]["minItems"] == n and props[field]["maxItems"] == n
        # free string array — the candidate pool is NEVER enumerated (liability)
        assert props[field]["items"] == {"type": "string"}
        assert "enum" not in props[field]["items"]


def test_grammar_omits_absent_choice_fields(gen_access):
    # class-a makes no language/tool choice, but DOES grant an expertise choice
    spec = _spec(gen_access, [{"class": "class-a", "level": 3}])
    props = grammar.build_pass1_grammar(gen_access, spec, [("class-a", 3, None)])["properties"]
    assert "languages" not in props and "tools" not in props
    assert "expertise" in props


# --------------------------------------------------------------------------- assemble population

def test_assemble_populates_and_validates_and_caps(gen_access):
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    resolved = [("class-tl", 2, None)]
    choices = assemble.assemble_choices(gen_access, spec, resolved, {
        "name": "T",
        "languages": ["lang-a", "lang-b", "lang-c"],  # 3 valid, capped at 2
        "tools": ["tool-z", "tool-x"],                # tool-z invalid (no category) -> dropped
        "expertise": ["sk3", "sk1"],                  # sk3 not in named pool -> dropped
    })
    assert choices["languages"] == ["lang-a", "lang-b"]
    assert choices["tools"] == ["tool-x"]
    assert choices["expertise"] == ["sk1"]


def test_assemble_empty_when_no_grant(gen_access):
    # class-a: no language/tool choice -> stray picks are dropped, replacing the former hardcoded []
    spec = _spec(gen_access, [{"class": "class-a", "level": 3}])
    choices = assemble.assemble_choices(gen_access, spec, [("class-a", 3, None)], {
        "name": "A", "languages": ["lang-a"], "tools": ["tool-x"]})
    assert choices["languages"] == [] and choices["tools"] == []


# --------------------------------------------------------------------------- T09 equipment choice-items

def test_apply_equipment_represents_choice_items(gen_access):
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    resolved = [("class-tl", 2, None)]
    choices = assemble.assemble_choices(gen_access, spec, resolved, {"name": "T"})
    choices = assemble.apply_equipment(
        gen_access, spec, resolved, {"equipment_class": "sa-tl"}, choices)
    # the concrete item still resolves (gear -> backpack); the choice-items are represented, not lost
    assert [i["id"] for i in choices["equipment"]["backpack"]] == ["gear-tl"]
    assert choices["equipment_choices"] == [
        {"kind": "tool_category", "tool_category": "tc-music"},
        {"kind": "focus", "focus_type": "ft-a"},
        {"kind": "proficiency_choice"},
    ]


def test_apply_equipment_no_choice_key_when_none(gen_access):
    # a bundle of only concrete items + gp carries no choice-item gap
    spec = _spec(gen_access, [{"class": "class-a", "level": 3}])
    resolved = [("class-a", 3, None)]
    choices = assemble.assemble_choices(gen_access, spec, resolved, {"name": "A"})
    choices = assemble.apply_equipment(
        gen_access, spec, resolved, {"equipment_class": "sa-a"}, choices)
    assert "equipment_choices" not in choices
