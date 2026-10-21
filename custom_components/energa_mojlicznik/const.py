"""Constants for the Energa Mój Licznik integration."""

from __future__ import annotations

DOMAIN = "energa_mojlicznik"

CONF_SCAN_INTERVAL = "scan_interval_hours"
CONF_IMPORT_STATISTICS = "import_statistics"
# Prefix of external statistic ids: "" for the first meter (energa_mojlicznik:pobor_strefa_1),
# the PPE number for any further meter. Stored in the entry so it never changes.
CONF_STAT_PREFIX = "statistic_prefix"

# Energa publishes one reading a day (around midnight), so there is no point in
# asking more often. Keep the default low to avoid account lockouts.
DEFAULT_SCAN_INTERVAL = 4
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 24
DEFAULT_IMPORT_STATISTICS = True

CONFIGURATION_URL = "https://mojlicznik.energa-operator.pl"
