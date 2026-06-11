from __future__ import annotations

import argparse
import csv
import re
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "p3"
SOURCE_URL = "https://fdp.fifa.org/assetspublic/ce281/pdf/SquadLists-English.pdf"

CSV_FIELDS = [
    "team",
    "player_name",
    "position",
    "age",
    "club",
    "minutes_recent",
    "goals_recent",
    "assists_recent",
    "xg_recent",
    "xa_recent",
    "injury_status",
    "expected_return",
    "source",
    "retrieved_at",
    "confidence",
    "notes",
    "dob",
    "height_cm",
    "caps",
    "national_team_goals",
    "team_code",
    "shirt_name",
]


def extract_rows(pdf_path: Path, retrieved_at: str | None = None) -> list[dict[str, str]]:
    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required to extract the FIFA squad PDF") from exc

    retrieved_at = retrieved_at or date.today().isoformat()
    players: list[dict[str, str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            team, team_code = _parse_team_header(page.extract_text() or "")
            if not team:
                continue
            for table in page.extract_tables() or []:
                for raw_row in table:
                    row = parse_table_row(raw_row, team=team, team_code=team_code, page_index=page_index, retrieved_at=retrieved_at)
                    if row:
                        players.append(row)
    return players


def parse_table_row(
    raw_row: list[Any],
    *,
    team: str,
    team_code: str,
    page_index: int,
    retrieved_at: str,
) -> dict[str, str] | None:
    cells = ["" if value is None else str(value).strip() for value in raw_row]
    if len(cells) < 15 or not cells[0].isdigit():
        return None
    dob = cells[8]
    height = cells[12]
    caps = cells[13]
    goals = cells[14]
    return {
        "team": team,
        "player_name": cells[2],
        "position": cells[1],
        "age": _age_from_dob(dob),
        "club": cells[10],
        "minutes_recent": "",
        "goals_recent": "",
        "assists_recent": "",
        "xg_recent": "",
        "xa_recent": "",
        "injury_status": "",
        "expected_return": "",
        "source": SOURCE_URL,
        "retrieved_at": retrieved_at,
        "confidence": "high",
        "notes": (
            f"FIFA official squad list page {page_index}; team_code={team_code}; shirt={cells[7]}; "
            f"first_names={cells[4]}; last_names={cells[5]}; dob={dob}; height_cm={height}; caps={caps}; goals={goals}"
        ),
        "dob": dob,
        "height_cm": height,
        "caps": caps,
        "national_team_goals": goals,
        "team_code": team_code,
        "shirt_name": cells[7],
    }


def write_real_csvs(rows: list[dict[str, str]], output_dir: Path = DATA_DIR) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "squad": output_dir / "manual_real_squad.csv",
        "player_stats": output_dir / "manual_real_player_stats.csv",
        "injuries": output_dir / "manual_real_injuries.csv",
    }
    for section, path in paths.items():
        section_rows = [_section_row(row, section) for row in rows]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(section_rows)
    return paths


def _section_row(row: dict[str, str], section: str) -> dict[str, str]:
    output = {field: row.get(field, "") for field in CSV_FIELDS}
    if section == "player_stats":
        output["notes"] = (
            output["notes"]
            + "; FIFA PDF includes caps/goals/height, but not recent club minutes/xG/xA; recent performance fields intentionally blank"
        )
    elif section == "injuries":
        output["injury_status"] = "unknown"
        output["notes"] = output["notes"] + "; no source-backed injury status in FIFA squad PDF; unknown is not assumed healthy"
    return output


def _parse_team_header(text: str) -> tuple[str, str]:
    for line in text.splitlines():
        match = re.fullmatch(r"(.+?)\s+\(([A-Z]{3})\)", line.strip())
        if match:
            return match.group(1).strip(), match.group(2).strip()
    return "", ""


def _age_from_dob(dob: str, today: date | None = None) -> str:
    today = today or date.today()
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", dob.strip())
    if not match:
        return ""
    day, month, year = (int(part) for part in match.groups())
    born = date(year, month, day)
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return str(age)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract official FIFA squad PDF into P3 manual real CSV files.")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--retrieved-at", default=date.today().isoformat())
    args = parser.parse_args(argv)

    rows = extract_rows(args.pdf, retrieved_at=args.retrieved_at)
    paths = write_real_csvs(rows, output_dir=args.output_dir)
    teams = sorted({row["team"] for row in rows})
    print("P3 FIFA Squad PDF Extraction Report")
    print(f"- rows: {len(rows)}")
    print(f"- teams: {len(teams)}")
    for name, path in paths.items():
        print(f"- {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
