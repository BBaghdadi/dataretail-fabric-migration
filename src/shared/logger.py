"""
logger.py
---------
Logger structuré compatible Windows (cp1252) et Linux/Mac (UTF-8).
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str, log_file: str = None) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler console — encodage explicite UTF-8
    console_handler = logging.StreamHandler(
        stream=open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
    )
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Handler fichier UTF-8
    if log_file:
        Path("logs").mkdir(exist_ok=True)
        file_handler = logging.FileHandler(
            f"logs/{log_file}", encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger