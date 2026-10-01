"""
USD -> BDT remittance calculator.

Pick between TapTap Send and Remitly, enter a USD amount, and see what lands
in BDT after a 2.5% remittance bonus is added on top.

Rate source: live open-market USD -> BDT, refreshed about once an hour by
the Fawaz Ahmed currency-api project. Falls back to open.er-api.com (daily)
if that is briefly unreachable.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, Tuple

import requests
import streamlit as st

REMITTANCE_BONUS_PCT = 2.5


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mid_market_rate() -> Tuple[Optional[float], Optional[str]]:
    """Fetch the current USD -> BDT rate. Returns (rate, source_date)."""
    # Primary: fawazahmed0/currency-api, Cloudflare Pages mirror, hourly.
    primary_urls = [
        "https://latest.currency-api.pages.dev/v1/currencies/usd.json",
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
    ]
    for url in primary_urls:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            rate = data.get("usd", {}).get("bdt")
            if rate:
                return float(rate), data.get("date")
        except Exception:
            continue

    # Fallback: open.er-api.com, daily refresh, no key required.
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        r.raise_for_status()
        data = r.json()
        rate = data.get("rates", {}).get("BDT")
        if rate:
            return float(rate), data.get("time_last_update_utc")
    except Exception:
        pass

    return None, None


def get_rate(provider: str) -> Tuple[Optional[float], str, Optional[str]]:
    """Return (rate, source_label, as_of)."""
    rate, as_of = fetch_mid_market_rate()
    if rate is None:
        return None, "Unavailable", None
    return rate, f"{provider} (open-market USD/BDT)", as_of


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="USD to BDT with Remittance", page_icon="💵", layout="centered")

st.title("USD to BDT, with 2.5% remittance bonus")
st.caption(
    "Pick a provider, enter a USD amount, and see what lands in BDT "
    "after a 2.5% remittance bonus is applied."
)

col_a, col_b = st.columns(2)

with col_a:
    usd_amount = st.number_input(
        "USD amount",
        min_value=0.0,
        value=100.0,
        step=10.0,
        format="%.2f",
    )

with col_b:
    provider = st.radio(
        "Rate source",
        options=["TapTap Send", "Remitly"],
        index=0,
        horizontal=True,
    )

if st.button("Convert", type="primary", use_container_width=True):
    with st.spinner("Fetching live rate..."):
        rate, source, as_of = get_rate(provider)

    if rate is None:
        st.error("Could not fetch a live rate right now. Try again in a moment.")
    else:
        base_bdt = usd_amount * rate
        bonus_bdt = base_bdt * (REMITTANCE_BONUS_PCT / 100.0)
        total_bdt = base_bdt + bonus_bdt

        st.success(f"Rate used: 1 USD = {rate:,.4f} BDT  ({source})")

        m1, m2, m3 = st.columns(3)
        m1.metric("Converted (base)", f"{base_bdt:,.2f} BDT")
        m2.metric(f"Remittance bonus (+{REMITTANCE_BONUS_PCT}%)", f"{bonus_bdt:,.2f} BDT")
        m3.metric("Total you receive", f"{total_bdt:,.2f} BDT")

        st.divider()
        st.markdown(
            f"**Summary**  \n"
            f"- You send: **${usd_amount:,.2f} USD**  \n"
            f"- Provider: **{provider}**  \n"
            f"- Rate: **1 USD = {rate:,.4f} BDT**  \n"
            f"- Base BDT: **{base_bdt:,.2f} BDT**  \n"
            f"- + 2.5% remittance bonus: **{bonus_bdt:,.2f} BDT**  \n"
            f"- **Total: {total_bdt:,.2f} BDT**"
        )
        if as_of:
            st.caption(f"Rate as of {as_of}. Source refreshes ~hourly; app re-fetches at most once per hour.")
        else:
            st.caption("App re-fetches the rate at most once per hour.")

st.divider()
st.caption(
    "Rate source: live open-market USD/BDT from fawazahmed0/currency-api "
    "(refreshes ~hourly), with open.er-api.com as a daily fallback. TapTap "
    "Send and Remitly do not offer a public rate API that works from a "
    "server, so both options use the same mid-market base; both providers "
    "typically quote within a fraction of a percent of this for USD -> BDT."
)
