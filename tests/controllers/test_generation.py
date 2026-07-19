"""Controller (HTTP): /v1/characters end-to-end with the model client mocked. Exercises the wiring
(request validation, the DAL choice grammar + derivation pipeline), not the model. /v1/characters
now returns the five-schema document; each part is asserted to conform to its live sub-schema AND to
pass its rule validator."""
import json
import pathlib

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

_CONTRACTS = pathlib.Path(__file__).parents[2] / "contracts"


def _schema_errors(schema_file, doc) -> list:
    schema = json.loads((_CONTRACTS / schema_file).read_text())
    return sorted(f"{list(e.path)}: {e.message}" for e in Draft202012Validator(schema).iter_errors(doc))


def _fake_flavour():
    return {"age": 40, "height_inches": 70, "weight_lbs": 150, "gender": "Male",
            "eyes": "Brown", "hair": "Black", "skin": "Pale",
            "personality_traits": ["calm", "wry"], "ideal": "truth", "bond": "home",
            "flaw": "proud", "backstory": "A short tale."}


def _fake_model(prompt, schema, **kw):
    """One mock for both endpoints. For the backstory schema it returns a flavour bundle; for the
    generation passes it returns picks shaped to whatever the offered grammar exposes (so the same
    stub drives a caster, a non-caster, and the equipment pass without over-picking fields the build
    was never offered)."""
    props = schema.get("properties", {})
    if "backstory" in props:
        return _fake_flavour()
    if "equipment_class" in props or "equipment_background" in props:
        return {}                      # take no starting-equipment bundle (a legal empty inventory)
    out = {"name": "Tester"}
    if "background_increase" in props:
        out["background_increase"] = {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"}
    if "skills" in props:
        n = props["skills"].get("minItems", 0)
        out["skills"] = props["skills"]["items"]["enum"][:n]
    if "spells" in props:
        sp = props["spells"]["properties"]
        out["spells"] = {"cantrips": sp["cantrips"]["items"]["enum"][:1],
                         "spells": sp["spells"]["items"]["enum"][:1]}
    if "feats" in props:
        n = props["feats"].get("minItems", 0)
        out["feats"] = props["feats"]["items"]["enum"][:n]
    return out


@pytest.fixture
def client(rules_db, monkeypatch):
    # rules_db builds the DAL rules DB that the /characters + /backstory pipeline reads via
    # $ARCANE_RULES_DB. The model client is mocked, so no real backend is contacted; OLLAMA_URL/MODEL
    # are set only to satisfy the client module's env reads.
    monkeypatch.setenv("ARCANE_RULES_DB", rules_db)
    monkeypatch.setenv("OLLAMA_URL", "http://test")
    monkeypatch.setenv("MODEL", "test-model")
    import app.generation.client as model_client
    monkeypatch.setattr(model_client, "generate", _fake_model)
    from app.main import app
    with TestClient(app) as c:
        yield c


def _validator_access(rules_db):
    from access.validator import ValidatorAccess
    return ValidatorAccess(path=rules_db)


def _assert_document_conforms(doc, rules_db):
    """Every present part of the five-schema document conforms to its live sub-schema and passes its
    rule validator."""
    from validator.validate_core import validate_core
    from validator.validate_grimoire import validate_grimoire
    from validator.validate_inventory import validate_inventory
    from validator.validate_modifier import validate_modifier

    access = _validator_access(rules_db)

    assert _schema_errors("core-sheet.schema.json", doc["core"]) == []
    assert _schema_errors("inventory.schema.json", doc["inventory"]) == []
    assert _schema_errors("modifier-sheet.schema.json", doc["modifier"]) == []

    assert validate_core(doc["core"], access)["legal"] is True
    inv = validate_inventory(doc["core"], doc["inventory"], doc.get("modifier"), access)
    assert inv["legal"] is True, inv["violations"]
    mod = validate_modifier(doc["core"], doc["inventory"], doc.get("grimoire"), doc["modifier"], access)
    assert mod["legal"] is True, mod["violations"]

    if "grimoire" in doc:
        assert _schema_errors("grimoire.schema.json", doc["grimoire"]) == []
        assert validate_grimoire(doc["core"], doc["grimoire"], access)["legal"] is True
        # the deriver emits `school` as a string when the DB has one (never null); the class-a
        # choosable spells carry school-a in the fixture
        assert all(isinstance(s.get("school", "x"), str) for s in doc["grimoire"]["spells"])
        assert any(s.get("school") == "school-a" for s in doc["grimoire"]["spells"])


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready").json()
    assert ready["ready"] is True and ready["abilities"] > 0


def test_post_characters_noncaster_document(client, rules_db):
    # class-m below its subclass-unlock level, with a species that grants no innate spell
    # (species-l), is a genuine non-caster -> no GRIMOIRE.
    r = client.post("/v1/characters", json={
        "species": "species-l", "classes": [{"class": "class-m", "level": 2}],
        "background": "bg-a"})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert set(doc) >= {"core", "inventory", "modifier"}
    assert "grimoire" not in doc
    assert doc["core"]["character_id"]                  # server-assigned identity
    _assert_document_conforms(doc, rules_db)


def test_post_characters_caster_document(client, rules_db):
    # class-a is a full spellcasting class -> a GRIMOIRE sheet; also exercises the class skill pool.
    r = client.post("/v1/characters", json={
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a"})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert "grimoire" in doc
    assert doc["core"]["character_name"] == "Tester"     # the model-picked name
    _assert_document_conforms(doc, rules_db)


def test_post_characters_bad_species_400(client):
    r = client.post("/v1/characters", json={"species": "nope", "classes": [{"class": "class-a", "level": 1}]})
    assert r.status_code == 400
    assert "species" in r.json()["detail"].lower()


def test_post_characters_unknown_class_400(client):
    r = client.post("/v1/characters", json={"species": "species-a", "classes": [{"class": "nope", "level": 1}]})
    assert r.status_code == 400
    assert "class" in r.json()["detail"].lower()


def test_post_characters_400_closes_db_handle(client, monkeypatch):
    # the 400 (unknown-id) path raises before the generation block; the DB handle must still be
    # closed (a single try/finally around the whole body), not leaked.
    import app.controllers.generation as gen
    base = gen.GeneratorAccess
    closed = []

    def factory(*a, **k):
        acc = base(*a, **k)
        orig_close = acc.db.close

        def tracked():
            closed.append(1)
            orig_close()

        acc.db.close = tracked
        return acc

    monkeypatch.setattr(gen, "GeneratorAccess", factory)
    r = client.post("/v1/characters", json={"species": "nope", "classes": [{"class": "class-a", "level": 1}]})
    assert r.status_code == 400
    assert closed == [1]           # closed exactly once, on the 400 path


def test_post_characters_model_error_502(client, monkeypatch):
    # a model/backend failure is an upstream error, not a server bug → 502, not 500
    import app.generation.client as model_client
    def boom(*a, **k):
        raise model_client.ModelError("backend down")
    monkeypatch.setattr(model_client, "generate", boom)
    r = client.post("/v1/characters", json={"species": "species-a",
                    "classes": [{"class": "class-a", "level": 3}], "background": "bg-a"})
    assert r.status_code == 502 and "model backend" in r.json()["detail"].lower()


def test_post_backstory_ok(client):
    r = client.post("/v1/backstory", json={"character": {"species": "species-a",
                    "classes": [{"class": "class-a", "level": 5}], "name": "Tester"}})
    assert r.status_code == 200
    fl = r.json()["flavour"]
    assert fl["backstory"] and len(fl["personality_traits"]) == 2
    assert 16 <= fl["age"] <= 90          # within the species bounds


def test_post_backstory_missing_fields_400(client):
    r = client.post("/v1/backstory", json={"character": {"name": "Nameless"}})
    assert r.status_code == 400


def test_post_backstory_unknown_species_400(client):
    r = client.post("/v1/backstory", json={"character": {"species": "nope",
                    "classes": [{"class": "class-a", "level": 1}]}})
    assert r.status_code == 400 and "species" in r.json()["detail"].lower()


def test_post_backstory_unknown_class_400(client):
    r = client.post("/v1/backstory", json={"character": {"species": "species-a",
                    "classes": [{"class": "nope", "level": 1}]}})
    assert r.status_code == 400 and "class" in r.json()["detail"].lower()
