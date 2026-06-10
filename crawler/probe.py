from __future__ import annotations

import json
from datetime import UTC, datetime

import requests

from sources import m500


def main() -> int:
    session = requests.Session()
    results = m500.probe_play_pages(session)
    for result in results:
        status = "OK" if result.ok else "BLOCKED"
        suffix = "" if result.ok else f" reason={result.reason}"
        print(
            f"RESULT: play={result.play} {status} selector={result.selector} "
            f"url={result.url} rows={result.rows} matches={result.matches} shape={result.data_shape}{suffix}"
        )
    try:
        url, status, prefix, matches = m500.probe(session)
        print(f"SOURCE: m500 url={url} status={status} prefix={prefix}")
        if matches:
            print("SAMPLE_MATCH_JSON:")
            print(json.dumps(m500.sample_match_json(matches[0]), ensure_ascii=False, indent=2, sort_keys=True))
    except Exception as exc:
        print(f"SOURCE: m500 FAIL error={exc}")
    print(f"PROBED_AT: {datetime.now(UTC).isoformat()}")
    return 0 if all(result.ok for result in results if result.play in {"had", "hhad"}) else 2


if __name__ == "__main__":
    raise SystemExit(main())
