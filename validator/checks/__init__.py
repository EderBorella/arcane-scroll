"""Registry of check callables. Each is `check(sheet, access) -> list[Violation]`. Add a domain by
importing its check and appending it here — the orchestrator runs every entry."""
# Task 5 wires the identity check in immediately after this lands.
ALL_CHECKS = []
