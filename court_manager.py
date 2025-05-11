import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
import json
import logging
from typing import Dict, Tuple
from discord_client import get_discord_client

import discord
from pytz import utc, timezone
import requests
from requests.exceptions import HTTPError

from mindbody_manager import LoginManager


PACIFIC_TIMEZONE = timezone("US/Pacific")
TIMESTAMP_FORMAT = "%Y-%m-%d %I:%M:%S %p"
DATE_FMT = "%a %m/%d"
TIME_FMT = "%I:%M %p"
INTERVAL_MINS = 15
INTERVAL = timedelta(minutes=INTERVAL_MINS)


class CourtManager():
    SERVICE_REF = {
        "mb_appointment_type_id": 44,
        "mb_service_category_id": 8,
        "mb_site_id": 255904,
        "inventory_source": "MB",
        "inventory_category": "appointment",
    }

    LOCATION_REF = {
        "mb_site_id": 255904,
        "mb_location_id": 1,
        "mb_master_location_id": 2170439,
        "inventory_source": "MB",
    }

    STAFF_REF = {"gateway_id": -1, "inventory_source": "MB"}

    AVAILABILITY_URL = (
        "https://prod-mkt-gateway.mindbody.io/"
        "v1/location/appointment_services/availability"
    )

    def __init__(
        self,
        wait_seconds: int = 15,
        login_manager: LoginManager = None,
        discord_client: discord.Client = None,
        publish_to_discord: bool = True,
    ):
        self.access_token = None
        self.login_manager = login_manager or LoginManager()
        self.discord_client = discord_client

        self.publish_to_discord = publish_to_discord
        self.wait_seconds = wait_seconds

        self.court_data = None
        self.old_data = None

    def refresh_access_token(self) -> None:
        self.access_token = self.login_manager.get_access_token()

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    @staticmethod
    def format_timestamp(ts: datetime) -> str:
        return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @classmethod
    def body(cls) -> dict:
        now = datetime.now(utc)
        this_week = now + timedelta(days=7)

        return {
            "appointment_service_ref_json": json.dumps(cls.SERVICE_REF),
            "inventory_source": "MB",
            "location_ref_json": json.dumps(cls.LOCATION_REF),
            "staff_ref_json": json.dumps(cls.STAFF_REF),
            "start_time_from": cls.format_timestamp(now),
            "start_time_to": cls.format_timestamp(this_week),
        }

    async def run(self) -> None:
        """
        Main entrypoint.

        Requests the mindbody API every 15 seconds in order to get all the
        courts available to book, then compares against the previous result
        to see if there is anything new. If so, publish the new times to the
        discord channel.
        """
        if self.access_token is None:
            logging.error("No access token found... Requesting one now...")
            self.refresh_access_token()
            logging.error("New token acquired.")

        await self.send("Checking for court openings...")

        while True:
            logging.error(f"Requesting: {self.AVAILABILITY_URL}")
            try:
                res = requests.post(
                    self.AVAILABILITY_URL,
                    json=self.body(),
                    headers=self.headers(),
                )
                res.raise_for_status()
            except HTTPError as e:
                if res.status_code in (400, 401):
                    logging.error("Access token expired. Refreshing...")
                    self.refresh_access_token()
                else:
                    logging.exception(f"HTTP error occurred: {e}")
                continue
            except Exception as e:
                logging.exception(f"Other error occurred: {e}")
                continue

            logging.info("Checking for new availabilities...")
            # Parse API response
            self.parse_availabilities(res)

            # Compare new court availabilities to old ones
            new_availabilities = self.check_for_new_openings()

            # Notify users of any new openings
            await self.notify(new_availabilities)

            # Save new availabilities
            self.old_data = self.court_data

            # Wait for 15 seconds
            logging.info(f"Sleeping for {self.wait_seconds} seconds.")
            await asyncio.sleep(self.wait_seconds)

    async def init_discord_client(self) -> None:
        """
        Setup discord client
        """
        logging.error("Connecting to discord...")
        self.discord_client = await get_discord_client()
        logging.error("Connected")

    async def send(self, message: str) -> None:
        """
        Send message to discord.
        """
        if not self.publish_to_discord:
            logging.error(f"Skipping discord message: {message}")
            return

        if not self.discord_client:
            await self.init_discord_client()

        await self.discord_client.send(message)

    @staticmethod
    def output_str(result: Dict[str, list]) -> str:
        """
        Formats message that is sent to discord.
        """
        def day_fmt(day: str, periods: Tuple[datetime]) -> str:
            logging.error(f"{day=} {periods=}")
            if len(periods) > 2:
                return f"{day}: Lots of courts open now!"

            times = ", ".join(
                f"{time_fmt(start)} - {time_fmt(end)}"
                for start, end in periods
            )
            return f"{day}: {times}"

        def time_fmt(x: datetime) -> str:
            return x.strftime(TIME_FMT).lstrip("0")

        return "\n".join(day_fmt(d, v) for d, v in result.items())

    async def notify(self, new_availabilities: list) -> None:
        """
        Formats a message to send to discord. If the message is too large, it
        tries to consolidate it and write a smaller message.
        """
        if new_availabilities:
            datetimes = sorted(
                [
                    datetime.strptime(dt[0], TIMESTAMP_FORMAT)
                    for dt in new_availabilities
                ]
            )
            result = defaultdict(list)
            start = end = datetimes[0]
            date_str = start.strftime(DATE_FMT)
            for current in datetimes[1:]:
                if current - end == INTERVAL:
                    end = current
                    continue
                date_str = start.strftime(DATE_FMT)
                result[date_str].append((start, end + INTERVAL))
                start = end = current

            if len(datetimes) > 1:
                result[date_str].append((start, end + INTERVAL))

            logging.error(f"{result=}")

            msg = (
                "New availabilities!! Bookings freed up on:\n"
                + CourtManager.output_str(result)
            )
            try:
                await self.send(msg)
            except Exception:
                logging.exception("Failed to post to discord.")

                # Try sending a shorter message
                msg = (
                    "New availabilities!! Bookings freed up on:\n"
                    + "\n".join(d for d in result.keys())
                )
                await self.send("New availabilities!!")

            logging.error(
                "New availabilities!!\n"
                + ("\n".join(str(a) for a in new_availabilities))
            )
            # Send sound
            print("\a")

        else:
            logging.info("No new availabilities :(")

    def check_for_new_openings(self) -> list:
        """
        Compares the previous court availabilities to the new courts open
        to book. So any court time that has opened in the last 15 seconds,
        would be returned.

        Returns:
            List[Tuple[datetime, List[int]]] - timestamps with open courts
        """
        # On the first run, we just want to get the data so we don't notify
        # of all the existing openings
        if self.old_data is None:
            return []

        new_availabilities = []
        for court_time, courts in self.court_data.items():
            # New times are available
            if self.old_data is None or court_time not in self.old_data:
                new_availabilities.append((court_time, courts))
                continue

            # New courts available at a time
            new_courts = [
                c for c in courts if c not in self.old_data[court_time]
            ]
            if new_courts:
                new_availabilities.append((court_time, new_courts))
                continue

        return new_availabilities

    def parse_availabilities(self, res: requests.Response) -> dict:
        """
        Parses the API response from mindbody into a dictionary of times with
        a list of any court open to book at that time.

        Example return:
        {"2025-05-10 11:11:11 PM": [1, 2, 3]}
        """
        availabilities = res.json()["data"]["attributes"]["startTimes"]
        self.court_data = {}

        for a in availabilities:
            cleaned_time = a["startTime"].replace("Z", "-00:00")
            utc_time = datetime.fromisoformat(cleaned_time)
            pt_time = (
                utc_time.astimezone(PACIFIC_TIMEZONE)
                .strftime(TIMESTAMP_FORMAT)
            )

            # eg. '255904:3'
            # Indoor courts are the staffId - 2
            court_nums = [int(c.split(":")[1]) - 2 for c in a["staffIds"]]

            # Filter out beach courts (ie. 10, 11, 12)
            available_courts = [c for c in court_nums if c < 8]

            self.court_data[pt_time] = available_courts

    def close(self) -> None:
        if self.discord_client:
            self.discord_client.close()
