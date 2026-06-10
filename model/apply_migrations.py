from __future__ import annotations

from pathlib import Path

from model.db import get_conn


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "db" / "migrations"


def apply_migrations() -> None:
    migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_paths:
        print("No migrations found.")
        return
    with get_conn() as conn:
        for path in migration_paths:
            sql = path.read_text(encoding="utf-8")
            conn.execute(sql)
            conn.commit()
            print(f"Applied migration: {path.name}")


def main() -> int:
    try:
        apply_migrations()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
