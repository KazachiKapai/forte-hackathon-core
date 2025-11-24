import logging
import os


def configure_logging() -> logging.Logger:
	level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
	try:
		level = getattr(logging, level_name, logging.INFO)
	except Exception:
		level = logging.INFO
	logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
	return logging.getLogger("mr_reviewer")


