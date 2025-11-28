import logging
import os


def configure_logging() -> logging.Logger:
	level_name = os.environ.get("LOG_LEVEL", "DEBUG").upper()
	logging.basicConfig(level=level_name, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
	return logging.getLogger()


