# VMEWS On-Demand Architecture

User requests specify symbol and date range. The API fetches only the required market window plus indicator warm-up from Vnstock, enriches it with market regime, macro/cross-asset context, news sentiment, and fundamentals, then returns an auditable Early Warning result. The current scanner is a separate lightweight path for GREEN / YELLOW / RED watchlists.
