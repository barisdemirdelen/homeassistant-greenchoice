DOMAIN = "greenchoice"

CONF_PROFILE = "profile"
CONF_CUSTOMER_NUMBER = "customer_number"
CONF_AGREEMENT_ID = "agreement_id"

DEFAULT_NAME = "Greenchoice"

# How many days of history to import on the first refresh after each start.
# Seven days is what the API reliably keeps warm. A longer horizon costs one
# API call per extra day on *every* restart and reload, because the
# "backfilled" marker is per-coordinator and lives in memory only — hence
# opt-in per account rather than the default.
CONF_BACKFILL_DAYS = "backfill_days"
DEFAULT_BACKFILL_DAYS = 7
MAX_BACKFILL_DAYS = 1096  # three years
