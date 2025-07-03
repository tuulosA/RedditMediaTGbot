# redditcommand/utils/logging_utils.py

import logging
from redditcommand.config import LogConfig

def setup_skip_logger():
    logger = logging.getLogger("skip_debug")
    if not logger.handlers:
        handler = logging.FileHandler(LogConfig.SKIP_LOG_PATH, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False  # prevent logging to terminal
    return logger

def setup_accepted_logger():
    logger = logging.getLogger("accepted_debug")
    if not logger.handlers:
        handler = logging.FileHandler(LogConfig.ACCEPTED_LOG_PATH, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False  # prevent logging to terminal
    return logger
