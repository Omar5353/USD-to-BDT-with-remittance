"""
USD -> BDT remittance calculator.

Fetches live USD -> BDT rates from TapTap Send and Remitly on each visit.
Tries three strategies for TapTap in order, because api.taptapsend.com can
block server-side requests behind Cloudflare on some IPs:
  1) curl_cffi with Chrome TLS impersonation (clean path)
  2) plain requests with aggressive browser-like headers
  3) scrape rate out of www.taptapsend.com/en homepage HTML (last resort)
Remitly's rate is scraped from their Bangladesh landing page HTML.
A 2.5% remittance bonus is added on top.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Optional, Tuple

import requests
import streamlit as st

try:
    from curl_cffi import requests as cf_requests
    _HAS_CF = True
except Exception:
    _HAS_CF = False

REMITTANCE_BONUS_PCT = 2.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.taptapsend.com",
    "Referer": "https://www.taptapsend.com/en",
}


def _taptap_from_json(data) -> Optional[float]:
    for origin in data:
        if origin.get("id") == "US-USD-ORIGIN":
            for c in origin.get("corridors", []):
                if c.get("currency") == "BDT":
                    return float(c["fxRate"])
    return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_taptap_rate() -> Tuple[Optional[float], str]:
    """Return (rate, debug_note). debug_note explains the path taken."""
    notes = []

    # Strategy 1: curl_cffi
    if _HAS_CF:
        try:
            r = cf_requests.get(
                "https://api.taptapsend.com/api/fxRates",
                impersonate="chrome124",
                timeout=15,
                headers=HEADERS,
            )
            notes.append(f"cf_requests status={r.status_code}")
            if r.status_code == 200:
                rate = _taptap_from_json(r.json())
                if rate:
                    return rate, "cf_requests ok"
        except Exception as e:
            notes.append(f"cf_requests err={type(e).__name__}: {str(e)[:80]}")
    else:
        notes.append("curl_cffi not installed")

    # Strategy 2: plain requests
    try:
        r = requests.get(
            "https://api.taptapsend.com/api/fxRates", headers=HEADERS, timeout=15,
        )
        notes.append(f"requests status={r.status_code}")
        if r.status_code == 200:
            rate = _taptap_from_json(r.json())
            if rate:
                return rate, "plain requests ok"
    except Exception as e:
        notes.append(f"requests err={type(e).__name__}: {str(e)[:80]}")

    # Strategy 3: scrape HTML homepage
    try:
        r = requests.get("https://www.taptapsend.com/en", headers=HEADERS, timeout=15)
        notes.append(f"html status={r.status_code}")
        if r.status_code == 200:
            m = re.search(r"1\s*USD\s*=\s*([\d.]+)\s*BDT", r.text)
            if m:
                return float(m.group(1)), "html scrape ok"
            notes.append("html had no USD->BDT line")
    except Exception as e:
        notes.append(f"html err={type(e).__name__}: {str(e)[:80]}")

    return None, " | ".join(notes)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_remitly_rate() -> Tuple[Optional[float], str]:
    try:
        r = requests.get(
            "https://www.remitly.com/us/en/money-transfer/send-money-to-bangladesh",
            headers={"User-Agent": HEADERS["User-Agent"], "Accept-Language": "en-US,en;q=0.9"},
            timeout=10,
        )
        if r.status_code != 200:
            return None, f"remitly status={r.status_code}"
        m = re.search(r"1\s*USD\s*=\s*([\d.]+)\s*BDT", r.text)
        if m:
            return float(m.group(1)), "ok"
        return None, "no rate line in HTML"
    except Exception as e:
        return None, f"err={type(e).__name__}: {str(e)[:80]}"


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
        if provider == "TapTap Send":
            rate, note = fetch_taptap_rate()
        else:
            rate, note = fetch_remitly_rate()

    if rate is None:
        st.error(f"Could not fetch the live {provider} rate right now.")
        st.code(f"debug: {note}", language="text")
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
            f"Fetched {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} "
            f"via {note}. Cached for 5 minutes."
        )

with st.expander("See both providers side by side"):
    tt, tt_note = fetch_taptap_rate()
    rm, rm_note = fetch_remitly_rate()
    c1, c2 = st.columns(2)
    c1.metric("TapTap Send", f"{tt:,.4f} BDT" if tt else "n/a", help=f"per 1 USD. {tt_note}")
    c2.metric("Remitly", f"{rm:,.4f} BDT" if rm else "n/a", help=f"per 1 USD. {rm_note}")

st.divider()
st.caption(
    "Rates are scraped from each provider's public page on every visit "
    "(cached for 5 minutes). If either provider changes their page layout "
    "or blocks the scrape, it may need a quick update."
)
