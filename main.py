from datetime import datetime, timedelta
import json
import logging
import os
import time
from urllib.parse import unquote

from dotenv import load_dotenv
from pytz import utc, timezone
import requests
from requests.exceptions import HTTPError
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")

FILE_NAME = "court_availabilities.json"

PACIFIC_TIMEZONE = timezone("US/Pacific")
TIMESTAMP_FORMAT = "%Y-%m-%d %I:%M:%S %p"


class LoginManager():
    DEFAULT_TIMEOUT = 10
    HOME_URL = "https://www.mindbodyonline.com/explore/"

    def __init__(self):
        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--disable-gpu")

        self.driver = None

    def init_driver(self) -> None:
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=self.options,
        )

    def wait_for(self, by, id: str):
        return WebDriverWait(self.driver, self.DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((by, id))
        )

    def go_to_mindbody_home(self) -> None:
        logging.info("Navigating to home page")
        self.driver.get(self.HOME_URL)

    def accept_cookies(self) -> None:
        logging.info("Waiting to accept cookies...")
        cookie_accept = self.wait_for(By.ID, "truste-consent-button")
        cookie_accept.click()
        logging.info("Accepted cookies.")

    def go_to_login_page(self) -> None:
        logging.info("Waiting for login button to appear...")
        sign_in = self.wait_for(
            By.CSS_SELECTOR,
            '[data-name="NavigationBar.Login.Button"]',
        )
        sign_in.click()
        logging.info("Login button found. Navigating to login page.")

    def sign_in(self) -> None:
        logging.info("Signing in...")
        username = self.wait_for(By.ID, "username")
        username.send_keys(USERNAME)
        continue_btn = self.wait_for(By.ID, "mui-1")
        continue_btn.click()

        logging.info("Entering password...")
        password = self.wait_for(By.ID, "password")
        password.send_keys(PASSWORD)

        sign_in = self.wait_for(By.ID, "mui-3")
        sign_in.click()

        logging.info("Logged in. Waiting for cookies...")
        time.sleep(1)

    def parse_access_token(self) -> str:
        user_session = self.driver.get_cookie("USER-SESSION")
        user_session_data = json.loads(unquote(user_session["value"]))
        access_token = user_session_data["accessToken"]
        logging.info("Found access token.")
        return access_token

    def get_access_token(self) -> str:
        if self.driver is None:
            self.init_driver()

        try:
            self.go_to_mindbody_home()
            self.accept_cookies()
            self.go_to_login_page()
            self.sign_in()
            return self.parse_access_token()
        finally:
            self.driver.quit()


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
        file_name: str = FILE_NAME,
        wait_seconds: int = 15,
        login_manager: LoginManager = None,
    ):
        self.access_token = None
        self.login_manager = login_manager or LoginManager()

        self.file_name = file_name
        self.wait_seconds = wait_seconds

        self.court_data = None
        self.old_data = self.read_file()

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

    def check_availability(self) -> None:
        if self.access_token is None:
            logging.info("No access token found... Requesting one now...")
            self.refresh_access_token()

        while True:
            logging.info(f"Requesting: {self.AVAILABILITY_URL}")
            try:
                res = requests.post(
                    self.AVAILABILITY_URL,
                    json=self.body(),
                    headers=self.headers(),
                )
                res.raise_for_status()
            except HTTPError as e:
                if res.status_code == 401:
                    logging.error("Access token expired. Refreshing...")
                    self.refresh_access_token()
                else:
                    logging.exception(f"HTTP error occurred: {e}")
                continue
            except Exception as e:
                logging.exception(f"Other error occurred: {e}")
                continue

            logging.info("Checking for new availabilities...")
            self.parse_availabilities(res)
            new_availabilities = self.check_for_new_openings()
            self.notify(new_availabilities)

            logging.info(f"Sleeping for {self.wait_seconds} seconds.")
            time.sleep(self.wait_seconds)

    def notify(self, new_availabilities: list) -> None:
        if new_availabilities:
            for _ in range(3):
                print("/a")
                time.sleep(.5)

            logging.info("New court availabilites!")
            logging.info(new_availabilities)
            logging.info("\n")

        else:
            logging.info("No new availabilities :(")

    def write_file(self) -> None:
        with open(self.file_name, "w") as f:
            json.dump(self.court_data, f, indent=4)
        logging.info(f"Wrote to: {self.file_name}")

    def read_file(self) -> dict:
        logging.info(f"Reading: {self.file_name}")
        with open(self.file_name) as f:
            return json.load(f)

    def check_for_new_openings(self) -> list:
        # Read in old data
        if not os.path.exists(FILE_NAME):
            self.write_file()
            self.old_data = self.court_data

        new_availabilities = []
        for court_time, courts in self.court_data.items():
            # New times are available
            if court_time not in self.old_data:
                new_availabilities.append((court_time, courts))
                continue

            # New courts available at a time
            new_courts = [
                c for c in courts if c not in self.old_data[court_time]
            ]
            if new_courts:
                new_availabilities.append((court_time, new_courts))
                continue

        # Re-write file if it's changed
        if new_availabilities:
            self.write_file()

        return new_availabilities

    def parse_availabilities(self, res: requests.Response) -> dict:
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


def main() -> None:
    CourtManager().check_availability()


if __name__ == "__main__":
    main()
