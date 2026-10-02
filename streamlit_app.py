"""
USD -> BDT remittance calculator.

Fetches the live USD -> BDT rate from TapTap Send and Remitly on each visit.
TapTap uses curl_cffi (Chrome TLS impersonation) because api.taptapsend.com
sits behind Cloudflare and rejects plain Python requests. Remitly's rate is
scraped from their public Bangladesh landing page HTML.

A 2.5% remittance bonus is added on top. (That matches Remitly's current
cashback promo for Bangladesh; adjust the constant if that changes.)
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Optional

import requests
import streamlit as st
from curl_cffi import requests as cf_requests

REMITTANCE_BONUS_PCT = 2.5


@st.cache_data(ttl=300, show_spinner=False)
def fetch_taptap_rate() -> Optional[float]:
    """TapTap Send USD -> BDT, via their fxRates JSON (Cloudflare-fronted)."""
    try:
        r = cf_requests.get(
            "https://api.taptapsend.com/api/fxRates",
            impersonate="chrome124",
            timeout=15,
            headers={
                "Origin": "https://www.taptapsend.com",
                "Referer": "https://www.taptapsend.com/en",
            },
        )
        if r.status_code != 200:
            return None
        data = r.json()
        for origin in data:
            if origin.get("id") == "US-USD-ORIGIN":
                for c in origin.get("corridors", []):
                    if c.get("currency") == "BDT":
                        return float(c["fxRate"])
    except Exception:
        return None
    return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_remitly_rate() -> Optional[float]:
    """Remitly USD -> BDT, scraped from their Bangladesh landing page."""
    try:
        r = requests.get(
            "https://www.remitly.com/us/en/money-transfer/send-money-to-bangladesh",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=10,
        )
        r.raise_for_status()
        m = re.search(r"1\s*USD\s*=\s*([\d.]+)\s*BDT", r.text)
        if m:
            return float(m.group(1))
    except Exception:
        return None
    return None


def get_rate(provider: str) -> Optional[float]:
    if provider == "TapTap Send":
        return fetch_taptap_rate()
    return fetch_remitly_rate()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="USD to BDT with Remittance", page_icon="💵", layout="centered")

st.title("USD to BDT, with 2.5% remittance bonus")
st.caption(
    "Live rates scraped from TapTap Send and Remitly on each visit. "
    "A 2.5% remittance bonus is added on top of the converted amount."
)

col_a, col_b = st.columns(2)

with col_a:
    usd_amount = st.number_input(
        "USD amount", min_value=0.0, value=100.0, step=10.0, format="%.2f",
    )

with col_b:
    provider = st.radio(
        "Rate source",
        options=["TapTap Send", "Remitly"],
        index=0, horizontal=True,
    )

if st.button("Convert", type="primary", use_container_width=True):
    with st.spinner(f"Fetching live {provider} rate..."):
        rate = get_rate(provider)

    if rate is None:
        st.error(
            f"Could not fetch the live {provider} rate right now. "
            "Try again in a moment, or switch providers."
        )
    else:
        base_bdt = usd_amount * rate
        bonus_bdt = base_bdt * (REMITTANCE_BONUS_PCT / 100.0)
        total_bdt = base_bdt + bonus_bdt

        st.success(f"{provider} rate: 1 USD = {rate:,.4f} BDT")

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
        st.caption(
            f"Fetched {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}. "
            "Live rate is cached for 5 minutes."
        )

with st.expander("See both providers side by side"):
    tt = fetch_taptap_rate()
    rm = fetch_remitly_rate()
    c1, c2 = st.columns(2)
    c1.metric("TapTap Send", f"{tt:,.4f} BDT" if tt else "n/a", help="per 1 USD")
    c2.metric("Remitly", f"{rm:,.4f} BDT" if rm else "n/a", help="per 1 USD")

st.divider()
st.caption(
    "Rates are scraped from each provider's public page on every visit "
    "(cached for 5 minutes). If either provider changes their page layout "
    "or blocks the scrape, it may need a quick update."
)
