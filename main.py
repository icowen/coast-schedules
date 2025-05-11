from argparse import ArgumentParser
import asyncio
import logging

from court_manager import CourtManager
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


async def main() -> None:
    """
    Parse CLI arguments and start running the service to poll
    the mindbody API.
    """
    parser = ArgumentParser()
    parser.add_argument(
        "--no_discord",
        action="store_true",
        help="Don't send to discord",
    )
    args = parser.parse_args()
    publish_to_discord = not args.no_discord

    try:
        manager = CourtManager(publish_to_discord=publish_to_discord)
        await manager.run()
    finally:
        if manager.discord_client:
            await manager.send("Bot stopped running.")
        await manager.close()
        print("\a")


if __name__ == "__main__":
    asyncio.run(main())
