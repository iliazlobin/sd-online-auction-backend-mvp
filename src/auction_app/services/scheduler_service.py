"""SchedulerService — APScheduler lifecycle driver.

Polls PostgreSQL for auctions whose start_ts or end_ts has been reached
and dispatches start_auction / close_auction calls.
"""

from __future__ import annotations


# Stub for the MVP scaffold. Full implementation comes in a later card.
# Poll interval: 1 second.  Each poll processes up to 100 auctions.
