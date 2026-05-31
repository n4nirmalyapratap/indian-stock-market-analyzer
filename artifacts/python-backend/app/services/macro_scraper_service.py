"""Removed.

The TradingEconomics + data.gov.in scrape pipeline used to live here. It
was deleted because TE's Cloudflare blocked our server IP and the
data.gov.in resource IDs we tried returned nothing useful. The macro
orchestrator now goes Manual override → IMF → DBnomics → FRED → World
Bank, which is reliable but stale.

This module is kept as an empty stub so that anything that still imports
`app.services.macro_scraper_service` gets a clear ImportError on the
member they're trying to use rather than a confusing AttributeError on
the package import itself. The file can be safely deleted from disk.
"""
