"""Local news aggregation — the home news ticker + the /news page.

A no-migration feature: the merged headline list lives as JSON in the shared
``ExternalConditionsCache`` (see :mod:`app.news.store`), so nothing here touches
the schema. Headlines link out to their original source; article bodies are
never stored (paywall/copyright rule 6 — see ``app/contrib/news_herald.py``).
"""
