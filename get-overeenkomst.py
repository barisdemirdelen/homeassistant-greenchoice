from urllib.parse import urlparse, parse_qs

import bs4
import requests


def _get_verification_token(html_txt: str):
    soup = bs4.BeautifulSoup(html_txt, "html.parser")
    token_elem = soup.find("input", {"name": "__RequestVerificationToken"})

    return token_elem.attrs.get("value")


def _get_oidc_params(html_txt: str):
    soup = bs4.BeautifulSoup(html_txt, "html.parser")

    code_elem = soup.find("input", {"name": "code"})
    scope_elem = soup.find("input", {"name": "scope"})
    state_elem = soup.find("input", {"name": "state"})
    session_state_elem = soup.find("input", {"name": "session_state"})

    if not (code_elem and scope_elem and state_elem and session_state_elem):
        raise RuntimeError("Login failed, check your credentials?")

    return {
        "code": code_elem.attrs.get("value"),
        "scope": scope_elem.attrs.get("value").replace(" ", "+"),
        "state": state_elem.attrs.get("value"),
        "session_state": session_state_elem.attrs.get("value"),
    }


def main():
    user = input("Enter username > ")
    password = input("Enter password > ")
    print()

    sess = requests.Session()

    # first, get the login cookies and form data
    login_page = sess.get("https://mijn.greenchoice.nl")

    login_url = login_page.url
    return_url = parse_qs(urlparse(login_url).query).get("ReturnUrl", "")
    token = _get_verification_token(login_page.text)

    # perform actual sign in
    login_data = {
        "ReturnUrl": return_url,
        "Username": user,
        "Password": password,
        "__RequestVerificationToken": token,
        "RememberLogin": True,
    }
    auth_page = sess.post(login_page.url, data=login_data)

    # exchange oidc params for a login cookie (automatically saved in session)
    oidc_params = _get_oidc_params(auth_page.text)
    sess.post("https://mijn.greenchoice.nl/signin-oidc", data=oidc_params)

    # retrieve overeenkomsten
    init_data = sess.get("https://mijn.greenchoice.nl/microbus/init").json()

    customer_number = init_data["profile"]["voorkeursOvereenkomst"]["klantnummer"]
    customer = next(
        (
            customer
            for customer in init_data["klantgegevens"]
            if customer["klantnummer"] == customer_number
        ),
        None,
    )
    if customer is None:
        print(f"Could not find customer details with ID {customer_number}")

    addresses = customer["adressen"]
    for address in addresses:
        postcode = address.get("postcode", "")
        city = address.get("plaats", "").capitalize()
        location = f"{postcode}, {city}".ljust(30, " ")

        print(f'{location} => {address["overeenkomstId"]}')


if __name__ == "__main__":
    main()
