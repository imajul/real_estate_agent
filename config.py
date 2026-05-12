"""
Application configuration.
"""

import os

# Supported neighborhoods (for CLI autocomplete / validation)
SUPPORTED_NEIGHBORHOODS = [
    "palermo",
    "belgrano",
    "recoleta",
    "villa_crespo",
    "caballito",
    "flores",
    "almagro",
    "san_telmo",
    "puerto_madero",
    "nunez",
    "villa_urquiza",
    "colegiales",
    "chacarita",
    "boedo",
    "liniers",
]

# Sources to scrape
SOURCES = ["zonaprop", "mercadolibre"]

# Default thresholds
DEFAULT_MAX_RESULTS = 100        # max props to scrape per source
DEFAULT_TOP_N = 10               # top N to rank and analyze
DEFAULT_DETAIL_COUNT = 3         # how many detail cards to show
DEFAULT_DISCOUNT_THRESHOLD = -8  # % below market to consider "interesting"

# AI model
AI_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# Renovation premium used for ARV calculation
ARV_PREMIUM_PCT = float(os.getenv("ARV_PREMIUM_PCT", "10"))
