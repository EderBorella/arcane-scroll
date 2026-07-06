from validator.report import Violation, build_report


def test_legal_and_complete_when_empty():
    r = build_report([])
    assert r["legal"] is True and r["complete"] is True
    assert r["summary"] == {"total": 0, "errors": 0, "warnings": 0}


def test_illegal_sets_legal_false():
    r = build_report([Violation("identity", "unknown-class", "illegal", "x")])
    assert r["legal"] is False and r["complete"] is True
    assert r["violations"][0]["severity"] == "ERROR"


def test_incomplete_sets_complete_false_but_stays_legal():
    r = build_report([Violation("identity", "subclass-missing", "incomplete", "x")])
    assert r["legal"] is True and r["complete"] is False
    assert r["violations"][0]["severity"] == "WARNING"


def test_violations_sorted_by_domain_then_code():
    r = build_report([
        Violation("vitals", "a", "illegal", "x"),
        Violation("identity", "z", "illegal", "x"),
        Violation("identity", "a", "illegal", "x"),
    ])
    keys = [(v["domain"], v["code"]) for v in r["violations"]]
    assert keys == [("identity", "a"), ("identity", "z"), ("vitals", "a")]
