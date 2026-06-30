"""
AutoTrader Startup Manager

Responsible for

✓ Creating folders

✓ Creating database

✓ Validating configuration

✓ Preparing project before trading starts
"""

from pathlib import Path
from loguru import logger

from config.constants import (
    DATABASE_FOLDER,
    REPORT_FOLDER,
    CSV_FOLDER,
    LOG_FOLDER,
    DATABASE_PATH,
)


class StartupManager:
    """
    Initializes the AutoTrader project.
    """

    def initialize(self):

        logger.info("Initializing AutoTrader...")

        self.create_directories()

        self.create_database()

        logger.success("Project initialization completed.")

    def create_directories(self):

        folders = [
            DATABASE_FOLDER,
            REPORT_FOLDER,
            CSV_FOLDER,
            LOG_FOLDER,
        ]

        for folder in folders:

            Path(folder).mkdir(parents=True, exist_ok=True)

            logger.info(f"Checked folder : {folder}")

    def create_database(self):

        DATABASE_PATH.touch(exist_ok=True)

        logger.info(f"Database Ready : {DATABASE_PATH}")