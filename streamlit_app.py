"""
USD <-> BDT remittance calculator using Remitly's live rate, or a rate you
enter yourself.

Scrapes the current USD -> BDT rate from Remitly's "Send money to Bangladesh"
landing page on each visit, cached for 60 seconds so repeat clicks are
instant. Remitly's page sometimes shows a promotional "welcome" rate
alongside the standard rate, or the displayed rate can drift between visits,
so if the scraped number doesn't match what you see on Remitly yourself,
switch to "Enter rate manually" and type in the rate you want to use.

Two modes:
- USD to BDT: you enter a USD amount to send, and see exactly how much BDT
  the recipient in Bangladesh receives after the 2.5% remittance bonus.
- BDT to USD: you enter the BDT amount you want the recipient to receive,
  and the app works backwards to tell you exactly how much USD you need
  to send (so that amount, plus the 2.5% bonus, lands on your target BDT).

The 2.5% bonus matches Remitly's current cashback promo for Bangladesh and
only ever benefits the recipient's BDT amount, never the sender's USD cost.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Optional, Tuple

import requests
import streamlit as st

REMITTANCE_BONUS_PCT = 2.5
DEFAULT_RATE = 122.75

REMITLY_URL = "https://www.remitly.com/us/en/money-transfer/send-money-to-bangladesh"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_remitly_rate() -> Tuple[Optional[float], str]:
    """Return (rate, note). rate is None on failure, note explains why."""
    try:
        r = requests.get(REMITLY_URL, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code} from Remitly"
        matches = re.findall(r"1\s*USD\s*=\s*([\d.,]+)\s*BDT", r.text)
        if matches:
            # Remitly's page can list more than one rate (for example a
            # first-time "welcome" promo rate alongside the standard rate).
            # The first one in the raw page HTML is the standard rate; take
            # that one rather than whichever happens to render first on
            # screen.
            rate_str = matches[0].replace(",", "")
            return float(rate_str), "ok"
        return None, "rate line not found in Remitly HTML (page layout may have changed)"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:100]}"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="USD to BDT with Remittance", page_icon="💵", layout="centered")

# Shrink Streamlit's default metric font sizes so large amounts fit
# without being truncated/ellipsized on narrower columns.
st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.07);
        border-radius: 8px;
        padding: 10px 6px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.3rem;
        white-space: normal;
        overflow-wrap: break-word;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("USD <-> BDT, with 2.5% remittance bonus")
st.caption(
    "Live Remitly rate for USD and Bangladesh, with a 2.5% remittance "
    "bonus added on top of the converted amount, in either direction."
)

rate_source = st.radio(
    "Exchange rate source",
    options=["Live Remitly rate", "Enter rate manually"],
    index=0,
    horizontal=True,
)

manual_rate = None
if rate_source == "Enter rate manually":
    col_rate, col_fetch = st.columns([3, 1])
    # The fetch button's column is handled first so that, if it updates
    # session_state["manual_rate_input"], that happens *before* the
    # number_input widget below is (re-)created with that same key this
    # run. Streamlit only honors a widget's "value=" argument the very
    # first time its key appears in session_state; on every later run the
    # widget's current session_state entry wins, so the only reliable way
    # to make a button "prefill" a keyed widget is to write to that exact
    # key before the widget is instantiated, then st.rerun().
    with col_fetch:
        st.write("")
        st.write("")
        if st.button("Use live rate", use_container_width=True):
            fetched_rate, fetch_note = fetch_remitly_rate()
            if fetched_rate is not None:
                st.session_state["manual_rate_input"] = fetched_rate
                st.rerun()
            else:
                st.error(f"Could not fetch: {fetch_note}")
    with col_rate:
        manual_rate = st.number_input(
            "1 USD = ? BDT",
            min_value=0.01,
            value=st.session_state.get("manual_rate_input", DEFAULT_RATE),
            step=0.01,
            format="%.4f",
            key="manual_rate_input",
        )
    st.caption(
        "Type in whatever rate you see on Remitly (or anywhere else) if the "
        "live-fetched rate above doesn't match what's shown on their site."
    )

st.divider()

direction = st.radio(
    "Direction",
    options=["USD to BDT", "BDT to USD"],
    index=0,
    horizontal=True,
)

if direction == "USD to BDT":
    amount = st.number_input(
        "USD amount to send", min_value=0.0, value=100.0, step=10.0, format="%.2f",
    )
else:
    amount = st.number_input(
        "BDT amount you want the recipient to receive",
        min_value=0.0, value=10000.0, step=100.0, format="%.2f",
    )

if st.button("Convert", type="primary", use_container_width=True):
    rate: Optional[float]
    rate_label: str

    if rate_source == "Enter rate manually":
        rate = manual_rate
        rate_label = "manually entered rate"
    else:
        with st.spinner("Fetching live Remitly rate..."):
            rate, note = fetch_remitly_rate()
        rate_label = "Remitly rate"
        if rate is None:
            st.error("Could not fetch the live Remitly rate right now.")
            st.code(f"debug: {note}", language="text")
            st.info("Switch to \"Enter rate manually\" above to use a rate of your own.")

    if rate is not None:
        st.success(f"Using {rate_label}: 1 USD = {rate:,.4f} BDT")

        if direction == "USD to BDT":
            base_bdt = amount * rate
            bonus_bdt = base_bdt * (REMITTANCE_BONUS_PCT / 100.0)
            total_bdt = base_bdt + bonus_bdt

            m1, m2, m3 = st.columns(3)
            m1.metric("Converted (base)", f"{base_bdt:,.2f} BDT")
            m2.metric(f"Remittance bonus (+{REMITTANCE_BONUS_PCT}%)", f"{bonus_bdt:,.2f} BDT")
            m3.metric("Total you receive", f"{total_bdt:,.2f} BDT")

            st.divider()
            st.markdown(
                f"**Summary**\n\n"
                f"- You send: **${amount:,.2f} USD**\n"
                f"- Rate ({rate_label}): **1 USD = {rate:,.4f} BDT**\n"
                f"- Base BDT: **{base_bdt:,.2f} BDT**\n"
                f"- + 2.5% remittance bonus: **{bonus_bdt:,.2f} BDT**\n"
                f"- **Total: {total_bdt:,.2f} BDT**"
            )
        else:
            # The 2.5% bonus is added to the BDT the recipient gets, not
            # subtracted from the USD you send. So the recipient's total
            # BDT = (usd_sent * rate) * 1.025, which means to land on a
            # specific target BDT amount you need to send less USD than a
            # plain rate conversion would suggest:
            #   usd_needed = target_bdt / (rate * 1.025)
            target_bdt = amount
            effective_rate = rate * (1 + REMITTANCE_BONUS_PCT / 100.0)
            usd_needed = target_bdt / effective_rate
            base_bdt_from_usd = usd_needed * rate
            bonus_bdt = base_bdt_from_usd * (REMITTANCE_BONUS_PCT / 100.0)

            m1, m2, m3 = st.columns(3)
            m1.metric("USD you need to send", f"${usd_needed:,.2f} USD")
            m2.metric(f"Remittance bonus recipient gets (+{REMITTANCE_BONUS_PCT}%)", f"{bonus_bdt:,.2f} BDT")
            m3.metric("Recipient receives", f"{target_bdt:,.2f} BDT")

            st.divider()
            st.markdown(
                f"**Summary**\n\n"
                f"- You want the recipient to receive: **{target_bdt:,.2f} BDT**\n"
                f"- Rate ({rate_label}): **1 USD = {rate:,.4f} BDT**\n"
                f"- Converted before bonus: **{base_bdt_from_usd:,.2f} BDT**\n"
                f"- + 2.5% remittance bonus (recipient's gain, not a discount for you): **{bonus_bdt:,.2f} BDT**\n"
                f"- **You need to send: ${usd_needed:,.2f} USD**"
            )

        st.caption(
            f"Fetched {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}. "
            + ("Live rate cached for 1 minute." if rate_source == "Live Remitly rate" else "Using your manually entered rate.")
        )

st.divider()
st.caption(
    "Live rate is scraped from Remitly's public page on every visit "
    "(cached for 1 minute). If it doesn't match what Remitly shows you, "
    "use \"Enter rate manually\" above. The 2.5% bonus matches Remitly's "
    "current cashback promo for Bangladesh and may change over time."
)
