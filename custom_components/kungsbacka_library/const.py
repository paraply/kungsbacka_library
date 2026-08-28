"""Constants for the Kungsbacka Library integration."""

from datetime import timedelta

DOMAIN = "kungsbacka_library"

CONF_LIBRARY_CARD = "library_card"
CONF_PIN = "pin"

DEFAULT_SCAN_INTERVAL = timedelta(hours=1)

# Axiell Arena web interface
ARENA_BASE_URL = "https://bibliotek.kungsbacka.se"
