from __future__ import annotations

import logging
import os
import signal
import time

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

import db
from sources import m500, sporttery
from sources.common import SourceError


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("crawler")


STOP = False


def source_module(name: str):
    normalized = name.strip().lower()
    if normalized == "sporttery":
        return sporttery
    if normalized in {"m500", "500"}:
        return m500
    raise ValueError(f"unknown source: {name}")


def source_priority() -> list[str]:
    raw = os.getenv("SOURCE_PRIORITY", "m500,sporttery")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def fetch_with_retries(source_name: str):
    delays = [0, 5, 15]
    last_error: Exception | None = None
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            matches = source_module(source_name).fetch_all(requests.Session())
            if not matches:
                raise SourceError(f"{source_name} parsed 0 matches")
            return matches
        except Exception as exc:
            last_error = exc
            LOGGER.warning("fetch failed source=%s error=%s", source_name, exc)
    raise RuntimeError(f"{source_name} failed after retries: {last_error}") from last_error


def choose_source_for_round() -> tuple[str, list]:
    errors: list[str] = []
    for source_name in source_priority():
        try:
            matches = fetch_with_retries(source_name)
            LOGGER.info("selected source=%s for this round from SOURCE_PRIORITY=%s", source_name, ",".join(source_priority()))
            return source_name, matches
        except Exception as exc:
            errors.append(f"{source_name}: {exc}")
            LOGGER.warning("source unavailable source=%s error=%s", source_name, exc)
    raise RuntimeError(f"no source available; {'; '.join(errors)}")


def crawl_once() -> None:
    active_source = ",".join(source_priority())
    error_text: str | None = None
    matches = []
    rows_written = 0
    conn = db.connect()
    try:
        db.init_db(conn)
        run_id = db.start_run(conn, active_source)
        try:
            active_source, matches = choose_source_for_round()
        except Exception as source_error:
            error_text = str(source_error)
            raise
        db.upsert_matches(conn, matches)
        db_source = source_module(active_source).SOURCE_NAME
        rows_written = db.write_odds_snapshots(conn, matches, db_source)
        db.finish_run(conn, run_id, db_source, len(matches), rows_written, True, error_text)
        LOGGER.info("crawl ok source=%s matches=%s rows_written=%s", active_source, len(matches), rows_written)
    except Exception as exc:
        LOGGER.exception("crawl failed")
        try:
            if "run_id" in locals():
                db.finish_run(conn, run_id, active_source, len(matches), rows_written, False, str(exc))
        except Exception:
            LOGGER.exception("failed to record crawl failure")
    finally:
        conn.close()


def stop(*_: object) -> None:
    global STOP
    STOP = True


def main() -> int:
    load_dotenv()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    crawl_once()
    scheduler = BackgroundScheduler()
    scheduler.add_job(crawl_once, "interval", minutes=10, max_instances=1, coalesce=True)
    scheduler.start()
    LOGGER.info("crawler started interval=10m source_priority=%s", ",".join(source_priority()))
    try:
        while not STOP:
            time.sleep(1)
    finally:
        scheduler.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
