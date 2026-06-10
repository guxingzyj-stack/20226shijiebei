from __future__ import annotations

from pathlib import Path

from api.db import connect


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "db" / "migrations"


def apply_migrations() -> list[str]:
    applied: list[str] = []
    with connect() as conn:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.execute(path.read_text(encoding="utf-8"))
            conn.commit()
            applied.append(path.name)
    return applied


def main() -> int:
    try:
        applied = apply_migrations()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    for name in applied:
        print(f"Applied migration: {name}")
    if not applied:
        print("No migrations found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
