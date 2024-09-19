import logging
import re
from urllib.parse import parse_qs, urlparse

import bs4
import requests


class LoginError(Exception):
    pass


class Auth:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self._username = username
        self._password = password

        self.logger = logging.getLogger(__name__)
        self.session = None
        self.session = self.refresh_session()

        if not self._check_config():
            raise AttributeError("Configuration is incomplete")

    def _check_config(self) -> bool:
        if not self._username:
            self.logger.error("Need a username!")
            return False
        if not self._password:
            self.logger.error("Need a password!")
            return False
        return True

    @staticmethod
    def _get_verification_token(html_txt: str) -> str:
        soup = bs4.BeautifulSoup(html_txt, "html.parser")
        token_elem = soup.find("input", {"name": "__RequestVerificationToken"})

        return token_elem.attrs.get("value")

    @staticmethod
    def _get_oidc_params(html_txt: str) -> dict[str, str]:
        soup = bs4.BeautifulSoup(html_txt, "html.parser")

        code_elem = soup.find("input", {"name": "code"})
        scope_elem = soup.find("input", {"name": "scope"})
        state_elem = soup.find("input", {"name": "state"})
        session_state_elem = soup.find("input", {"name": "session_state"})

        if not (code_elem and scope_elem and state_elem and session_state_elem):
            raise LoginError("Login failed, check your credentials?")

        return {
            "code": code_elem.attrs.get("value"),
            "scope": scope_elem.attrs.get("value").replace(" ", "+"),
            "state": state_elem.attrs.get("value"),
            "session_state": session_state_elem.attrs.get("value"),
        }

    @staticmethod
    def is_session_expired(response: requests.Response) -> bool:
        # If the session expired, the client is redirected to the SSO login.
        for history_response in response.history:
            if history_response.status_code != 302:
                continue
            location_header: str = history_response.headers.get("Location")
            if location_header is not None and re.search(
                "^.*://sso.greenchoice.nl/connect/authorize.*$", location_header
            ):
                return True

        # Sometimes we get Forbidden on token expiry
        if response.status_code == 403:
            return True

    def _activate_session(self) -> requests.Session:
        if self.session:
            self.session.close()

        self.session = requests.Session()
        self.logger.info("Retrieving login cookies")

        # first, get the login cookies and form data
        login_page = self.session.get(self.base_url)

        login_url = login_page.url
        return_url = parse_qs(urlparse(login_url).query).get("ReturnUrl", "")
        token = self._get_verification_token(login_page.text)

        # perform actual sign in
        self.logger.debug("Logging in with username and password")
        login_data = {
            "ReturnUrl": return_url,
            "Username": self._username,
            "Password": self._password,
            "__RequestVerificationToken": token,
            "RememberLogin": True,
        }
        auth_page = self.session.post(login_page.url, data=login_data)
        auth_page.raise_for_status()

        # exchange oidc params for a login cookie (automatically saved in session)
        self.logger.debug("Signing in using OIDC")
        oidc_params = self._get_oidc_params(auth_page.text)
        response = self.session.post(f"{self.base_url}/signin-oidc", data=oidc_params)
        response.raise_for_status()

        self.logger.debug("Login success")

        return self.session

    def refresh_session(self) -> requests.Session:
        self.logger.debug("Session possibly expired, triggering refresh")
        try:
            self._activate_session()
        except requests.HTTPError:
            self.logger.error(
                "Login failed! Please check your credentials and try again."
            )
            raise
        return self.session
