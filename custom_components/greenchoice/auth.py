import logging
import re
from urllib.parse import parse_qs, urlparse

import aiohttp
import bs4


class LoginError(Exception):
    pass


class Auth:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.sso_url = base_url.replace("mijn.", "sso.")
        self._username = username
        self._password = password

        self.logger = logging.getLogger(__name__)
        self._session: aiohttp.ClientSession | None = None

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

    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession()
        await self.refresh_session()  # Authenticate on entry
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_session()

    @property
    def session(self):
        """Get the current session."""
        return self._session

    async def _get_antiforgery_token(self) -> str:
        """Get the antiforgery token from the API."""
        async with self._session.get(f"{self.sso_url}/api/antiforgery") as response:
            response.raise_for_status()
            data = await response.json()
            return data["requestToken"]

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

    def is_session_expired(self, response: aiohttp.ClientResponse) -> bool:
        # Check if the final URL indicates a redirect to SSO login
        if response.history:
            for history_response in response.history:
                if history_response.status != 302:
                    continue
                location_header = history_response.headers.get("Location")
                if location_header and re.search(
                    f"^.*://{urlparse(self.sso_url).netloc}/connect/authorize.*$",
                    location_header,
                ):
                    return True

        # Sometimes we get Forbidden on token expiry
        if response.status == 403:
            return True

        return False

    async def _activate_session(self) -> None:
        """Activate the session by logging in."""
        self.logger.info("Retrieving login cookies")

        # Get the antiforgery token
        antiforgery_token = await self._get_antiforgery_token()

        # Get the login page to extract returnUrl
        async with self._session.get(self.base_url) as login_page:
            login_url = str(login_page.url)
            return_url_params = parse_qs(urlparse(login_url).query)
            return_url = return_url_params.get("ReturnUrl", [""])[0]

        # Perform actual sign in with new parameters
        self.logger.debug("Logging in with username and password")
        login_data = {
            "username": self._username,
            "password": self._password,
            "returnUrl": return_url,
            "rememberMe": True,
        }

        # Set the required headers
        headers = {
            "requestverificationtoken": antiforgery_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": self.sso_url,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        # Send login request to the correct endpoint
        login_url = f"{self.sso_url}/api/login"
        async with self._session.post(
            login_url, json=login_data, headers=headers
        ) as auth_page:
            auth_page.raise_for_status()
            login_response = await auth_page.json()

        # Handle the JSON response with redirect URI
        if login_response.get("validationProblemDetails"):
            raise LoginError(
                f"Login validation failed: {login_response['validationProblemDetails']}"
            )

        redirect_uri = login_response.get("redirectUri")
        if not redirect_uri:
            raise LoginError("No redirect URI received from login")

        # Follow the redirect to complete OAuth flow
        self.logger.debug("Following OAuth redirect")
        async with self._session.get(f"{self.sso_url}{redirect_uri}") as oauth_response:
            oauth_response.raise_for_status()
            oauth_text = await oauth_response.text()

        # Continue with OIDC flow
        self.logger.debug("Signing in using OIDC")
        oidc_params = self._get_oidc_params(oauth_text)
        async with self._session.post(
            f"{self.base_url}/signin-oidc", data=oidc_params
        ) as response:
            response.raise_for_status()

        self.logger.debug("Login success")

    async def refresh_session(self) -> None:
        """Refresh the session by re-authenticating."""
        self.logger.debug("Session possibly expired, triggering refresh")
        try:
            await self._activate_session()
        except aiohttp.ClientError as e:
            self.logger.error(
                "Login failed! Please check your credentials and try again."
            )
            raise LoginError(f"Authentication failed: {e}")

    async def close_session(self):
        if self._session:
            await self._session.close()
            self._session = None
