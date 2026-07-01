"""Per-layer legality checks. Each exposes `check(sheet, rules) -> list[Violation]`, collects ALL of
its findings (never returns early), and never raises to stop the overall run."""
