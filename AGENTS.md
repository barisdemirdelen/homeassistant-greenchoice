# Agent notes

Home Assistant custom integration for the Greenchoice customer portal API (`custom_components/greenchoice/`).

## Tools

- Version bumps: set the version in `pyproject.toml` and `custom_components/greenchoice/manifest.json`, run `uv lock`, and commit all three files.
- Live API probing: open `GreenchoiceApi(username, password)` from `api.py` and fetch raw responses via `api._auth.session.get(BASE_URL + path)`.
- Verify API claims against the live API before trusting fixtures or reporter descriptions.

## Checks

CI runs none of these; run all before committing:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check custom_components tests
uv run pytest -q
```

## Greenchoice API

- Base `https://mijn.greenchoice.nl`. Each endpoint's model in `model.py` has a nested `Request.build_url()`.
- Endpoints: `v2/account`, `v2/.../meter-readings/{year}/`, `v3/.../rate-details?Start=&End=`, `v3/.../consumptions?interval=Hour&start=&end=` (always a one-day range).
- `request()` turns a 404 into `{}` unless called with `raise_not_found=True`, which raises `NotFoundError`. Rate-details and consumptions use `raise_not_found`.
- Consumptions:
  - A day without data is a 200 with 24 periods and `products: []`.
  - `consumedOn` carries a UTC offset.
  - Per product, `consumptionCost + feedInCompensation + fixedCost + variableCost == totalCost`. `variableCost` is the feed-in cost (`VariableFeedIn`). Feed-in quantities and compensation are negative.
  - An hourly range containing the 25-hour DST day returns 500.
- Meter readings: one object per day carries electricity and gas fields together.
- Rate-details returns 404 for any date no agreement covers, e.g. after the supply ended. The integration logs that at INFO.

## Tests

- Fixtures live in `tests/test_data/`. `*_live.json` fixtures are real captures from the live API; new API response fixtures are captured the same way.
- `mock_api` in `tests/conftest.py` mocks every endpoint; `consumptions={date: payload}` per day, `None` for a 404.
