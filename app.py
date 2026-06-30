"""
AutoTrader Main Application
"""

from engine.logger import logger
from engine.startup import StartupManager
from config.settings import APP_NAME, APP_VERSION


def main():

    logger.info("=" * 60)

    logger.info(f"{APP_NAME}  Version : {APP_VERSION}")

    startup = StartupManager()

    startup.initialize()

    logger.success("AutoTrader Ready.")

    logger.info("=" * 60)


if __name__ == "__main__":

    main()