import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, date
import streamlit.components.v1 as components

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(page_title="TFSA Tracker", page_icon="🧮", layout="centered")

# Small CSS polish + glow for the utilization bar when near-full
st.markdown("""
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 2.25rem; }
[data-testid="stMetricLabel"] { color: #6b7280; }

/* Utilization bar container */
.util-wrap {
  width: 100%;
  background: #e5e7eb;
  border-radius: 9999px;
  height: 16px;
  position: relative;
  overflow: hidden;
  border: 1px solid #d1d5db;
}
.util-fill {
  height: 100%;
  width: 0%;
  border-radius: 9999px;
  transition: width .4s ease;
}
.util-fill.glow {
  box-shadow: 0 0 12px rgba(239, 68, 68, 0.7), 0 0 24px rgba(239, 68, 68, 0.35);
}

/* A tidy inline list for the annual limits */
.limits-row {
  display: flex; flex-wrap: wrap; gap: .5rem .8rem; line-height: 1.8;
}
.limits-chip {
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 9999px;
  padding: .15rem .6rem; font-size: .875rem;
}
</style>
""", unsafe_allow_html=True)

# -------------------------
# Session Defaults
# -------------------------
def init_state():
    defaults = {
        "transactions": [],         # list of dicts with id, date, type, amount
        "next_id": 1,               # autoincrement id for transaction rows
        "confirming_clear": False,  # for the clear-all confirmation UI
        "ever_contributed": "No",   # default for estimator
        "carryover_manual": 0.0,    # manual carryover when ever_contributed == "Yes"
        "amount_input": 0.0,        # form inputs (helps reset)
        "type_input": "deposit",
        # flash flags for floating badges
        "_flash_money_badge": None, # "deposit" | "withdrawal" | None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# -------------------------
# Flash helpers (floating badges)
# -------------------------
def trigger_money_badge(kind: str):
    """kind: 'deposit' | 'withdrawal'"""
    st.session_state["_flash_money_badge"] = kind
    st.rerun()

def floating_money_badge():
    kind = st.session_state.get("_flash_money_badge")
    if not kind:
        return
    # Green badge for deposit, red for withdrawal
    bg = "#16a34a" if kind == "deposit" else "#ef4444"
    emoji = "💵" if kind == "deposit" else "🔻"
    text = "Deposit added" if kind == "deposit" else "Withdrawal added"
    components.html(
        f"""
        <div id="money-badge" style="
            position: fixed; right: 18px; bottom: 18px; z-index: 9999;
            background: {bg}; color: white; padding: 10px 14px;
            border-radius: 999px; font: 600 14px/1.2 ui-sans-serif,system-ui;
            box-shadow: 0 6px 18px rgba(0,0,0,0.18); opacity: 0; transform: translateY(10px);
            transition: all .25s ease;
        ">
          <span style="font-size:18px; margin-right:8px">{emoji}</span> {text}
        </div>
        <script>
          const badge = document.getElementById('money-badge');
          setTimeout(()=>{{ badge.style.opacity=1; badge.style.transform='translateY(0)'; }}, 10);
          setTimeout(()=>{{ badge.style.opacity=0; badge.style.transform='translateY(10px)'; }}, 2200);
          setTimeout(()=>{{ badge.remove(); }}, 2600);
        </script>
        """,
        height=0
    )
    st.session_state["_flash_money_badge"] = None

# -------------------------
# Constants / Helpers
# -------------------------
LIMITS_BY_YEAR = {
    2009: 5000, 2010: 5000, 2011: 5000, 2012: 5000, 2013: 5500,
    2014: 5500, 2015: 10000, 2016: 5500, 2017: 5500, 2018: 5500,
    2019: 6000, 2020: 6000, 2021: 6000, 2022: 6000, 2023: 6500,
    2024: 7000, 2025: 7000,
}

def tfsa_start_year_from_dob(dob: date) -> int:
    # TFSA starts at the later of 2009 or the year you turn 18
    return max(dob.year + 18, 2009)

def total_room_from_inception(dob: date, through_year: int) -> float:
    start = tfsa_start_year_from_dob(dob)
    return float(sum(LIMITS_BY_YEAR.get(y, 0) for y in range(start, through_year + 1)))

def current_year_limit(year: int) -> float:
    return float(LIMITS_BY_YEAR.get(year, 0))

def df_from_txns(txns: list) -> pd.DataFrame:
    if not txns:
        return pd.DataFrame(columns=["id", "date", "type", "amount", "year", "month_ts", "month"])
    df = pd.DataFrame(txns)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["year"] = df["date"].dt.year
    df["month_ts"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["month"] = df["month_ts"].dt.strftime("%Y-%m")
    return df

def current_year_deposits(df: pd.DataFrame, year: int) -> float:
    if df.empty:
        return 0.0
    filt = (df["year"] == year) & (df["type"] == "deposit")
    return float(df.loc[filt, "amount"].sum())

def lifetime_balance(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    deposits = float(df.loc[df["type"] == "deposit", "amount"].sum())
    withdrawals = float(df.loc[df["type"] == "withdrawal", "amount"].sum())
    return deposits - withdrawals

# =========================
# --------- UI ------------
# =========================
st.title("TFSA Contribution Tracker")
# Show any pending floating badge right away (so it follows the viewport)
floating
