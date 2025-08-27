import requests
import pandas as pd
from datetime import datetime
import time
import json
import os
import streamlit as st

# ==============================
# Config
# ==============================
API_KEY = "WXuRfmS31yugy8TcIks2AJ77l78tbzVF"  # put your Polygon.io key here
BASE_URL = "https://api.polygon.io/v3/snapshot/options"


# ==============================
# Data Processing
# ==============================
def _process_results(data):
    """Convert raw option results into a DataFrame."""
    processed = []
    for item in data:
        det = item.get("details", {})
        greeks = item.get("greeks", {})
        exp_str = det.get("expiration_date")

        # expiration date
        expiration = None
        if exp_str:
            try:
                expiration = pd.to_datetime(exp_str).date()
            except Exception:
                expiration = None

        processed.append({
            "ticker": det.get("ticker"),
            "type": det.get("contract_type"),
            "expiration": expiration,
            "strike": det.get("strike_price"),
            "delta": greeks.get("delta"),
            "gamma": greeks.get("gamma"),
            "theta": greeks.get("theta"),
            "vega": greeks.get("vega"),
            "iv": item.get("implied_volatility"),
            "mid": item.get("last_quote", {}).get("midpoint"),
            "open_interest": item.get("open_interest"),
            "underlying": item.get("underlying_asset", {}).get("price"),
        })

    df = pd.DataFrame(processed)

    if not df.empty and "expiration" in df:
        df["expiration"] = pd.to_datetime(df["expiration"], errors="coerce")
        today = pd.to_datetime(datetime.today().date())
        df["dte"] = (df["expiration"] - today).dt.days

    return df


def _load_mock(mock_file="mock_soxl.json"):
    """Load data from local mock JSON file."""
    if not os.path.exists(mock_file):
        st.error(f"⚠ Mock file {mock_file} not found")
        return pd.DataFrame()
    with open(mock_file, "r") as f:
        raw = json.load(f)
    return _process_results(raw.get("results", []))


def fetch_chain_with_greeks(symbol, max_retries=3, pause=2, mock_file="mock_soxl.json"):
    """Fetch option chain snapshot from Polygon.io with greeks, fallback to mock file."""
    url = f"{BASE_URL}/{symbol}"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params={"apiKey": API_KEY}, timeout=10)
            if resp.status_code == 429:
                wait = pause * attempt
                st.warning(f"Rate limited on {symbol}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code in (401, 403):
                st.error(f"Unauthorized/Forbidden for {symbol}, using mock data…")
                return _load_mock(mock_file)

            resp.raise_for_status()
            data = resp.json().get("results", [])
            if not data:
                st.info(f"No options data for {symbol}")
                return pd.DataFrame()

            return _process_results(data)

        except Exception as e:
            st.error(f"Error fetching {symbol}: {e}")
            st.info(f"➡ Falling back to mock file {mock_file}")
            return _load_mock(mock_file)

    return pd.DataFrame()


def filter_contracts(df, max_dte=50, delta_min=0.10, delta_max=0.50):
    """Filter options by DTE and delta safely."""
    if df.empty:
        return df
    df = df.dropna(subset=["delta", "expiration"])
    return df[
        (df["dte"] <= max_dte) &
        (df["delta"].abs() >= delta_min) &
        (df["delta"].abs() <= delta_max)
    ]


# ==============================
# Streamlit App
# ==============================
@st.cache_data(ttl=300)
def get_chain(symbol):
    return fetch_chain_with_greeks(symbol)


def main():
    st.set_page_config(page_title="Options Chain Explorer", layout="wide")
    st.title("📈 Options Chain Explorer with Greeks")

    symbols = st.multiselect("Choose symbols:", ["SOXL", "SPY", "QQQ", "AAPL"], default=["SOXL"])

    max_dte = st.slider("Max Days to Expiry (DTE)", 5, 90, 50)
    delta_range = st.slider("Delta Range", 0.0, 1.0, (0.1, 0.5))

    for sym in symbols:
        st.subheader(f"🔎 {sym}")
        df = get_chain(sym)
        if df.empty:
            st.warning(f"No data returned for {sym}")
            continue

        filtered = filter_contracts(df, max_dte=max_dte, delta_min=delta_range[0], delta_max=delta_range[1])
        if filtered.empty:
            st.info(f"No contracts passed filters for {sym}")
            continue

        st.dataframe(filtered[["ticker", "expiration", "strike", "dte", "delta", "iv", "open_interest"]].head(20))


if __name__ == "__main__":
    main()
