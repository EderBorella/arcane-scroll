from validator.report import Violation
from validator import validate as V


def test_runs_all_checks_and_aggregates(monkeypatch):
    def ok(sheet, access):
        return [Violation("d1", "c1", "illegal", "x")]

    def also(sheet, access):
        return [Violation("d2", "c2", "incomplete", "y")]

    monkeypatch.setattr(V, "ALL_CHECKS", [ok, also])
    r = V.validate({}, access=None)
    assert r["summary"]["total"] == 2
    assert r["legal"] is False and r["complete"] is False


def test_a_raising_check_becomes_internal_and_never_aborts(monkeypatch):
    def boom(sheet, access):
        raise RuntimeError("kaboom")

    def fine(sheet, access):
        return [Violation("d", "c", "illegal", "x")]

    monkeypatch.setattr(V, "ALL_CHECKS", [boom, fine])
    r = V.validate({}, access=None)
    codes = {v["code"] for v in r["violations"]}
    assert any(c.startswith("check-raised") for c in codes)   # boom captured
    assert "c" in codes                                        # fine still ran
    assert r["legal"] is False                                 # the internal finding is advisory; 'c' is illegal
