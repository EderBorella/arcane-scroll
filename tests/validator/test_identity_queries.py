from access.validator import identity as q


def test_subclass_parent(access):
    assert q.subclass_parent(access, "sub-a") == "class-a"
    assert q.subclass_parent(access, "nope") is None


def test_subclass_unlock_level(access):
    assert q.subclass_unlock_level(access, "class-a") == 3


def test_species_creature_type(access):
    assert q.species_creature_type(access, "species-a") == "type-a"


def test_xp_min(access):
    assert q.xp_min(access, 3) == 900
    assert q.xp_min(access, 99) is None


def test_resolve_shortcut(access):
    assert access.resolve("subclass", "Sub A") == "sub-a"
