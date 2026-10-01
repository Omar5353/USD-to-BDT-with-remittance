"""
USD -> BDT remittance calculator.

Pick between TapTap Send and Remitly, enter a USD amount, and see what lands
in BDT after a 2.5% remittance bonus is added on top.

Note: TapTap Send and Remitly do not publish public rate APIs that work
from a server, so this app uses the live open-market USD -> BDT rate
(open.er-api.com, with exchangerate-api.com as a fallback) as the base rate
for both options. For USD -> BDT both providers typically quote within a
fraction of a percent of this.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, Tuple

import requests
import streamlit as st

REMITTANCE_BONUS_PCT = 2.5


@st.cache_data(ttl=300, show_spinner=False)
def fetch_mid_market_rate():
    """Fetch the current USD -> BDT open-market rate."""
    sources = [
        "https://open.er-api.com/v6/latest/USD",
        "https://api.exchangerate-api.com/v4/latest/USD",
    ]
    for url in sources:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            rate = data.get("rates", {}).get("BDT")
            if rate:
                return float(rate)
        except Exception:
            continue
    return None


def get_rate(provider):
    """Return (rate, source_label) for the chosen provider."""
    rate = fetch_mid_market_rate()
    if rate is None:
        return None, "Unavailable"
    label = f"{provider} (open-market USD/BDT)"
    return rate, label


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
        rate, source = get_rate(provider)

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
        st.caption(
            f"Fetched {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}. "
            "Live rate cached for ~5 minutes."
        )

st.divider()
st.caption(
    "Rate source: live open-market USD/BDT (open.er-api.com with "
    "exchangerate-api.com as a fallback). TapTap Send and Remitly do not "
    "offer a public rate API that works from a server, so both options "
    "use the same mid-market base; both providers typically quote within "
    "a fraction of a percent of this for USD -> BDT."
)
