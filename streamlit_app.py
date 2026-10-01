"""
USD -> BDT remittance calculator.

Lets the user pick between TapTap Send and Remitly's current rate,
converts a USD amount to BDT at that rate, and adds a 2.5%
remittance bonus on top of the converted amount.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import requests
import streamlit as st

REMITTANCE_BONUS_PCT = 2.5

# ---------------------------------------------------------------------------
# Rate fetchers
# ---------------------------------------------------------------------------


@st.cache_data(ttl=120, show_spinner=False)
def fetch_remitly_rate():
    """Fetch the current USD -> BDT rate shown on Remitly's calculator."""
    url = "https://api.rtly.app/v3/calculator/estimate"
    params = {
        "conduit": "USA:USD-BGD:BDT",
        "anchor": "SEND",
        "amount": "1000.00",
        "purpose": "OTHER",
        "customer_segment": "UNKNOWN",
        "strict_promo": "false",
    }
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        rate = (
            data.get("estimate", {})
            .get("exchange_rate", {})
            .get("base_rate")
        )
        if rate is None:
            rate = data.get("estimate", {}).get("exchange_rate", {}).get("rate")
        return float(rate) if rate is not None else None
    except Exception:
        return None


@st.cache_data(ttl=120, show_spinner=False)
def fetch_taptap_rate():
    """Fetch the current USD -> BDT rate shown on TapTap Send's calculator."""
    url = "https://api.taptapsend.com/api/v2/calculateQuote"
    payload = {
        "sendingCurrency": "USD",
        "receivingCurrency": "BDT",
        "sendingAmount": 1000,
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        rate = data.get("exchangeRate") or data.get("rate")
        if rate is None and "receivingAmount" in data:
            rate = float(data["receivingAmount"]) / 1000.0
        return float(rate) if rate is not None else None
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fallback_rate():
    """Open market USD -> BDT rate, used only if a provider lookup fails."""
    try:
        r = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "USD", "symbols": "BDT"},
            timeout=10,
        )
        r.raise_for_status()
        return float(r.json()["rates"]["BDT"])
    except Exception:
        return None


def get_rate(provider):
    """Return (rate, source_label) for the chosen provider."""
    if provider == "TapTap Send":
        rate = fetch_taptap_rate()
        if rate is not None:
            return rate, "TapTap Send live rate"
    else:
        rate = fetch_remitly_rate()
        if rate is not None:
            return rate, "Remitly live rate"
    fallback = fetch_fallback_rate()
    if fallback is not None:
        return fallback, "Open-market fallback (provider lookup failed)"
    return None, "Unavailable"


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
    with st.spinner(f"Fetching live rate from {provider}..."):
        rate, source = get_rate(provider)

    if rate is None:
        st.error(
            "Could not fetch a live rate right now. "
            "Try again in a moment or switch providers."
        )
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
            f"- Rate ({provider}): **1 USD = {rate:,.4f} BDT**  \n"
            f"- Base BDT: **{base_bdt:,.2f} BDT**  \n"
            f"- + 2.5% remittance bonus: **{bonus_bdt:,.2f} BDT**  \n"
            f"- **Total: {total_bdt:,.2f} BDT**"
        )
        st.caption(
            f"Fetched {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}. "
            "Live rates are cached for ~2 minutes."
        )

st.divider()
st.caption(
    "Note: provider endpoints change without notice. If a provider's live rate "
    "cannot be fetched, the app falls back to the open-market USD/BDT rate "
    "and clearly labels it."
)
