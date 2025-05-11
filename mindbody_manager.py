import json
import logging
import os
import time
from urllib.parse import unquote

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")


class LoginManager():
    """
    This class is used to get the credentials needed to login
    to the mindbody API. It opens a Chrome driver, logs in with
    the USERNAME & PASSWORD provided in the env variables, then
    returns the access token that can be used to authenticate API requests

    Example:

        manager = LoginManager()
        token = manager.get_access_token()
    """
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

    def wait_for_disappear(self, element):
        return WebDriverWait(self.driver, self.DEFAULT_TIMEOUT).until(
            EC.invisibility_of_element(element)
        )

    def go_to_mindbody_home(self) -> None:
        logging.info("Navigating to home page")
        self.driver.get(self.HOME_URL)

    def accept_cookies(self) -> None:
        logging.info("Waiting to accept cookies...")
        cookie_accept = self.wait_for(By.ID, "truste-consent-button")
        cookie_accept.click()
        self.wait_for_disappear(cookie_accept)
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

    def parse_access_token(self) -> str:
        user_session = self.driver.get_cookie("USER-SESSION")
        while user_session is None:
            time.sleep(.5)
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
            self.driver = None
