import time
from datetime import datetime, date

import pandas as pd
import streamlit as st

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(page_title="TFSA Tracker", page_icon="🧮", layout="centered")

# Small global CSS to tighten spacing and style our custom progress bar & emoji pops
st.markdown(
    """
    <style>
      .tight { margin-top: 0.25rem; margin-bottom: 0.25rem; }
      .title-tight h1 { margin-bottom: 0.4rem !important; }
      /* Custom progress bar */
      .bar-wrap {width:100%; height:14px; background:rgba(255,255,255,0.08); border-radius:10px; position:relative; overflow:hidden;}
      .bar-fill {height:100%; border-radius:10px; transition:width .6s ease;}
      .bar-pill {display:flex; justify-content:space-between; align-items:center; font-weight:600; margin-bottom:.35rem;}
      /* Glow when nearly full */
      .glow { box-shadow: 0 0 10px rgba(255, 77, 77,.6), 0 0 20px rgba(255, 77, 77,.4); }
      /* Add/Withdraw emoji pop next to the button */
      .pop-emoji { font-size: 1.6rem; line-height:1; padding-left:.5rem; animation: hop .75s ease-out 1; display:inline-block; }
      @keyframes hop { 0%{ transform: translateY(6px) scale(.8); opacity:.2 } 40%{ transform: translateY(-6px) scale(1.05); opacity:1 } 100%{ transform: translateY(0) scale(1); opacity:.85 } }
      /* Compact table header cells left-aligned */
      table thead th { text-align:left !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

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
        # simple flash next to Add button
        "flash": None,              # {"type": "deposit"/"withdrawal", "ts": float}
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

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
        return pd.DataFrame(columns=["id", "date", "type", "amount", "year", "month"])
    df = pd.DataFrame(txns)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M").astype(str)
    return df

def deposits_in_year(df: pd.DataFrame, year: int) -> float:
    if df.empty:
        return 0.0
    return float(df.query("year == @year and type == 'deposit'")["amount"].sum())

def lifetime_balance(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    deposits = float(df.loc[df["type"] == "deposit", "amount"].sum())
    withdrawals = float(df.loc[df["type"] == "withdrawal", "amount"].sum())
    return deposits - withdrawals

# ---------- Limits table helpers ----------
def limits_df() -> pd.DataFrame:
    df = pd.DataFrame(
        [{"Year": y, "Limit ($)": LIMITS_BY_YEAR[y]} for y in sorted(LIMITS_BY_YEAR.keys())]
    )
    df["Limit ($)"] = df["Limit ($)"].map(lambda x: f"${x:,.0f}")
    return df

def compact_table(df: pd.DataFrame):
    # Use a Pandas Styler so we can tighten spacing & left-align; hide index (no counts)
    styler = (
        df.style
        .set_properties(**{"text-align": "left", "padding": "6px 10px", "font-size": "0.95rem"})
        .hide(axis="index")
        .set_table_styles([
            {"selector": "th", "props": [("text-align", "left"), ("padding", "6px 10px")]},
            {"selector": "tbody td", "props": [("border-bottom", "1px solid rgba(255,255,255,0.06)")]},
            {"selector": "thead th", "props": [("border-bottom", "1px solid rgba(255,255,255,0.12)")]},
        ])
    )
    return styler

# =========================
# --------- UI ------------
# =========================
st.markdown('<div class="title-tight"></div>', unsafe_allow_html=True)
st.title("TFSA Contribution Tracker")

current_year = datetime.now().year

# --- Explainer ---
with st.expander("ℹ️ How TFSA contribution room works", expanded=False):
    st.markdown(
        """
**Key rules (simplified):**
- Your TFSA room starts accruing from the year you turn **18** (or **2009**, whichever is later).
- **Deposits** reduce this year’s available room.
- **Withdrawals** do **not** give room back until **January 1 of the next year**.
- CRA is the source of truth. This app is an educational helper; confirm with CRA if you’re unsure.

**Annual limits (selected key years):** 2009 $5,000 • 2013 $5,500 • 2015 $10,000 • 2019 $6,000 • 2023 $6,500 • 2024 $7,000 • 2025 $7,000
        """
    )
    with st.expander("Show full annual TFSA limits (2009–2025)", expanded=False):
        st.caption("Complete list from inception. Values are per CRA yearly announcements.")
        st.table(compact_table(limits_df()))

# --- Estimator / Input ---
st.subheader("📅 Contribution Room Estimator")

colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio("Have you ever contributed to a TFSA before?", ["No", "Yes"], index=(0 if st.session_state.ever_contributed == "No" else 1))

# Estimation
if st.session_state.ever_contributed == "No":
    estimated_room_total = total_room_from_inception(dob, current_year)
    carryover_prior = estimated_room_total - current_year_limit(current_year)
    st.success(f"Estimated available room (all-time if you've truly never contributed): **${estimated_room_total:,.0f}**")
else:
    st.session_state.carryover_manual = st.number_input(
        "Enter your unused TFSA room carried into this year (best estimate):",
        min_value=0.0, step=500.0, value=float(st.session_state.carryover_manual)
    )
    estimated_room_total = st.session_state.carryover_manual + current_year_limit(current_year)
    carryover_prior = st.session_state.carryover_manual
    st.info(f"Estimated total room available **this year** (carryover + {current_year} limit): **${estimated_room_total:,.0f}**")

# Top Metrics
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = deposits_in_year(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

# Custom gradient progress bar
st.write("")  # spacer
left_label, right_label = st.columns([4, 1])
with left_label:
    st.markdown(f'<div class="bar-pill">Contribution room used</div>', unsafe_allow_html=True)
with right_label:
    st.markdown(f'<div style="text-align:right; font-weight:600;" class="tight">{room_used_pct:.1f}%</div>', unsafe_allow_html=True)

bar_color = "#22c55e"  # green
if room_used_pct >= 80:
    bar_color = "#ef4444"  # red
elif room_used_pct >= 60:
    bar_color = "#f59e0b"  # amber

glow = "glow" if room_used_pct >= 95 else ""
st.markdown(
    f'''
    <div class="bar-wrap">
        <div class="bar-fill {glow}" style="background:{bar_color}; width:{min(room_used_pct,100):.2f}%"></div>
    </div>
    ''',
    unsafe_allow_html=True,
)

metric1, metric2, metric3 = st.columns(3)
metric1.metric("This year's limit", f"${current_year_limit(current_year):,.0f}")
metric2.metric("Carryover into this year", f"${carryover_prior:,.0f}")
metric3.metric("Room left (est.)", f"${room_left:,.0f}")

# =========================
# --- Add a Transaction ---
# =========================
st.subheader("➕ Add a Transaction")

with st.form("txn_form", clear_on_submit=False):
    c1, c2 = st.columns([1, 1])
    with c1:
        t_date = st.date_input("Date", value=date.today(), min_value=date(2009, 1, 1), max_value=date.today())
    with c2:
        st.session_state.type_input = st.radio("Type", ["deposit", "withdrawal"],
                                               index=(0 if st.session_state.type_input == "deposit" else 1),
                                               horizontal=True)

    t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=float(st.session_state.amount_input))
    # Add button row with emoji flash placeholder
    btn_col, emoji_col = st.columns([0.15, 0.85])
    with btn_col:
        submitted = st.form_submit_button("Add", type="primary", use_container_width=True)
    with emoji_col:
        # Show small emoji pop next to button when we have a recent flash event (< 1.4s)
        flash = st.session_state.flash
        if flash:
            since = time.time() - flash["ts"]
            if since < 1.4:
                emj = "💰" if flash["type"] == "deposit" else "💸"
                st.markdown(f'<span class="pop-emoji">{emj}</span>', unsafe_allow_html=True)
            else:
                st.session_state.flash = None  # auto-clear

    if submitted:
        df_all = df_from_txns(st.session_state.transactions)

        if t_amount <= 0:
            st.error("Please enter an amount greater than $0.")
        else:
            if st.session_state.type_input == "deposit":
                # Allow deposit up to (carryover + current year limit) for the *deposit
