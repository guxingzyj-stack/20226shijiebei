from __future__ import annotations

import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from model.apply_predictions import predict_once
from model.train import train_once


LOGGER = logging.getLogger("model-worker")


def run_prediction_job() -> None:
    try:
        result = predict_once()
        LOGGER.info("prediction job ok predictions=%s ev_signals=%s", result["predictions"], result["ev_signals"])
    except Exception:
        LOGGER.exception("prediction job failed")


def run_training_job() -> None:
    try:
        result = train_once()
        LOGGER.info("training job ok %s", result)
    except Exception:
        LOGGER.exception("training job failed")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_prediction_job, "interval", minutes=30, max_instances=1, coalesce=True)
    scheduler.add_job(run_training_job, CronTrigger(hour=4, minute=0, timezone="UTC"), max_instances=1, coalesce=True)
    scheduler.start()
    run_prediction_job()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown(wait=False)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
