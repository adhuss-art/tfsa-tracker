# app.py
import time
from datetime import datetime, date

import pandas as pd
import streamlit as st
import altair as alt
import streamlit.components.v1 as components

# =============================================================================
# Page setup
# =============================================================================
st.set_page_config(
    page_title="TFSA Contribution Tracker",
    page_icon="🧮",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# Session state
# =============================================================================
def init_state():
    defaults = {
        "transactions": [],
        "next_id": 1,
        "ever_contributed": "No",
        "carryover_manual": 0.0,
        "amount_input": 0.0,
        "type_input": "deposit",
        "confirming_clear": False,
        "notifications": [],
        "last_fx": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# =============================================================================
# Constants & helpers
# =============================================================================
LIMITS_BY_YEAR = {
    2009: 5000, 2010: 5000, 2011: 5000, 2012: 5000, 2013: 5500,
    2014: 5500, 2015: 10000, 2016: 5500, 2017: 5500, 2018: 5500,
    2019: 6000, 2020: 6000, 2021: 6000, 2022: 6000, 2023: 6500,
    2024: 7000, 2025: 7000,
}

def tfsa_start_year_from_dob(dob: date) -> int:
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

def push_notification(kind: str, text: str):
    st.session_state.notifications.append((time.time(), kind, text))
    st.session_state.notifications = st.session_state.notifications[-6:]

def emoji_fx(kind: str):
    st.session_state.last_fx = (kind, time.time())

# =============================================================================
# Global CSS & small HTML helpers
# =============================================================================
def render_global_css():
    components.html(
        """
        <style>
        /* tighter top spacing + expander spacing */
        section.main > div { padding-top: 0.6rem; }
        h1 { margin-top: .2rem !important; margin-bottom: .2rem !important; }
        details { margin-top: .35rem; }

        /* notification stack */
        .tfsa-notify-stack {
          position: fixed; top: 76px; right: 24px; z-index: 9999;
          display: flex; flex-direction: column; gap: 10px; pointer-events: none;
        }
        .tfsa-note {
          min-width: 280px; max-width: 520px;
          background: rgba(38,41,46,0.96); border: 1px solid rgba(255,255,255,0.06);
          box-shadow: 0 8px 28px rgba(0,0,0,0.45);
          border-radius: 12px; padding: 12px 14px; color: #eee;
          display: grid; grid-template-columns: 26px 1fr; gap: 10px; align-items: center;
          animation: tfsa-fade-slide 4s forwards ease-in-out; pointer-events: auto;
        }
        .tfsa-note.ok .icon { filter: drop-shadow(0 0 .5px #22c55e); }
        .tfsa-note.warn .icon { filter: drop-shadow(0 0 .5px #eab308); }
        .tfsa-note.err .icon { filter: drop-shadow(0 0 .5px #ef4444); }
        .tfsa-note.deposit .icon { filter: drop-shadow(0 0 .5px #22c55e); }
        .tfsa-note.withdrawal .icon { filter: drop-shadow(0 0 .5px #ef4444); }
        @keyframes tfsa-fade-slide {
          0% { opacity: 0; transform: translateY(-8px); }
          8% { opacity: 1; transform: translateY(0); }
          80% { opacity: 1; }
          100% { opacity: 0; transform: translateY(-8px); }
        }

        /* floating emoji fx bottom-right */
        .tfsa-fx {
          position: fixed; right: 28px; bottom: 28px; z-index: 9998;
          font-size: 28px; line-height: 1;
          animation: tfsa-fx-rise 1.6s ease-out forwards; pointer-events: none;
        }
        @keyframes tfsa-fx-rise {
          0% { opacity: 0; transform: translateY(10px) scale(.96); }
          10% { opacity: 1; transform: translateY(0) scale(1); }
          80% { opacity: 1; transform: translateY(-16px) scale(1); }
          100% { opacity: 0; transform: translateY(-26px) scale(.98); }
        }

        /* contribution bar */
        .tfsa-bar-wrap { width: 100%; margin: .1rem 0 .9rem 0; }
        .tfsa-bar-track {
          width: 100%; height: 14px; background: rgba(255,255,255,0.09);
          border-radius: 999px; overflow: hidden; position: relative;
        }
        .tfsa-bar-fill { height: 100%; width: 0%; border-radius: 999px; transition: width .35s ease; }
        .tfsa-bar-fill.green { background: linear-gradient(90deg,#16a34a,#22c55e); }
        .tfsa-bar-fill.amber { background: linear-gradient(90deg,#d97706,#f59e0b); }
        .tfsa-bar-fill.red {
          background: linear-gradient(90deg,#ef4444,#f87171);
          box-shadow: 0 0 10px rgba(239,68,68,.55), 0 0 20px rgba(239,68,68,.30);
        }
        .tfsa-bar-label {
          position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
          font-size: 12px; color: #e5e7eb; opacity: .95;
        }

        /* limits chips (fix weird spacing, force tabular numerals) */
        .tfsa-limits-row {
          display: flex; flex-wrap: wrap; gap: 8px 10px; margin-top: 6px;
        }
        .tfsa-chip {
          font-variant-numeric: tabular-nums;
          letter-spacing: normal;
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(255,255,255,0.10);
          border-radius: 999px;
          padding: 6px 10px;
          color: #e5e7eb;
          white-space: nowrap;
        }
        .tfsa-chip .yr { opacity: .8; margin-right: 6px; }
        .tfsa-chip .amt { font-weight: 700; }
        </style>
        """,
        height=0,
    )

def render_notifications():
    notes = st.session_state.notifications[-6:]
    if not notes:
        components.html("<div class='tfsa-notify-stack'></div>", height=0)
        return
    icon_map = {"ok": "✅", "warn": "⚠️", "err": "⛔", "deposit": "💵", "withdrawal": "🔻"}
    now = time.time()
    parts = ["<div class='tfsa-notify-stack'>"]
    for ts, kind, text in notes:
        if now - ts <= 12:
            parts.append(f"<div class='tfsa-note {kind}'><div class='icon'>{icon_map.get(kind,'ℹ️')}</div><div>{text}</div></div>")
    parts.append("</div>")
    components.html("".join(parts), height=0)

def render_fx():
    fx = st.session_state.last_fx
    if not fx:
        return
    kind, ts = fx
    if time.time() - ts > 1.6:
        return
    components.html(f"<div class='tfsa-fx'>{'💵' if kind=='deposit' else '🔻'}</div>", height=0)

def render_limits_chips():
    # highlights we want to show as chips
    highlights = [2009, 2013, 2015, 2019, 2023, 2024, 2025]
    chips = []
    for y in highlights:
        amt = f"${LIMITS_BY_YEAR[y]:,}"
        chips.append(f"<span class='tfsa-chip'><span class='yr'>{y}</span><span class='amt'>{amt}</span></span>")
    components.html(
        "<div class='tfsa-limits-row'>" + "".join(chips) + "</div>",
        height=0,
    )

render_global_css()

# =============================================================================
# Header
# =============================================================================
st.title("TFSA Contribution Tracker")

# =============================================================================
# Help accordion (now with clean chips)
# =============================================================================
with st.expander("ℹ️ How TFSA contribution room works", expanded=False):
    st.markdown(
        """
**Key rules (simplified):**
- Your TFSA room starts accruing from the year you turn **18** (or **2009**, whichever is later).
- **Deposits** reduce this year’s available room.
- **Withdrawals** do **not** give room back until **January 1 of the next year**.
- CRA is the source of truth. This app is an educational helper; confirm with CRA if you’re unsure.

**Annual limits (highlights):**
        """
    )
    render_limits_chips()

# =============================================================================
# Estimator
# =============================================================================
st.subheader("📅 Contribution Room Estimator")
current_year = datetime.now().year

colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio(
        "Have you ever contributed to a TFSA before?",
        ["No", "Yes"],
        index=(0 if st.session_state.ever_contributed == "No" else 1),
    )

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

df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

bar_color = "green"
if room_used_pct >= 60: bar_color = "amber"
if room_used_pct >= 90: bar_color = "red"

components.html(
    f"""
    <div class="tfsa-bar-wrap">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <div style="font-weight:600;opacity:.95;">Contribution room used</div>
        <div style="font-weight:700;opacity:.95;">{room_used_pct:.1f}%</div>
      </div>
      <div class="tfsa-bar-track">
        <div class="tfsa-bar-fill {bar_color}" style="width:{min(100,room_used_pct):.2f}%"></div>
        <div class="tfsa-bar-label">${room_left:,.0f} room left</div>
      </div>
    </div>
    """,
    height=64,
)

m1, m2, m3 = st.columns(3)
m1.metric("This year's limit", f"${current_year_limit(current_year):,.0f}")
m2.metric("Carryover into this year", f"${carryover_prior:,.0f}")
m3.metric("Room left (est.)", f"${room_left:,.0f}")

# =============================================================================
# Add transaction
# =============================================================================
st.subheader("➕ Add a Transaction")
with st.form("txn_form", clear_on_submit=False):
    c1, c2 = st.columns([1, 1])
    with c1:
        t_date = st.date_input("Date", value=date.today(), min_value=date(2009, 1, 1), max_value=date.today())
    with c2:
        st.session_state.type_input = st.radio(
            "Type", ["deposit", "withdrawal"],
            index=(0 if st.session_state.type_input == "deposit" else 1),
            horizontal=True
        )
    t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=float(st.session_state.amount_input))
    submitted = st.form_submit_button("Add", type="primary", use_container_width=True)

    if submitted:
        df_all = df_from_txns(st.session_state.transactions)
        if t_amount <= 0:
            push_notification("warn", "Please enter an amount greater than $0.")
        else:
            if st.session_state.type_input == "deposit":
                deposit_year = t_date.year
                deposits_that_year = current_year_deposits(df_all, deposit_year)
                year_limit = current_year_limit(deposit_year)
                if deposit_year == current_year:
                    allowed_room = max(0.0, (st.session_state.carryover_manual if st.session_state.ever_contributed == "Yes" else (estimated_room_total - current_year_limit(current_year))) + year_limit - deposits_that_year)
                else:
                    allowed_room = max(0.0, year_limit - deposits_that_year)
                if t_amount > allowed_room:
                    push_notification("err", f"Deposit exceeds available room for {deposit_year}. Available: ${allowed_room:,.0f}.")
                else:
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "deposit",
                        "amount": float(t_amount),
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0
                    push_notification("deposit", "Deposit added")
                    emoji_fx("deposit")
            else:
                bal = lifetime_balance(df_all)
                if t_amount > bal:
                    push_notification("err", f"Withdrawal exceeds available balance. Current balance: ${bal:,.0f}.")
                else:
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "withdrawal",
                        "amount": float(t_amount),
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0
                    push_notification("withdrawal", "Withdrawal added")
                    emoji_fx("withdrawal")

# notifications & fx
render_notifications()
render_fx()

# =============================================================================
# Logged transactions (bomb icon)
# =============================================================================
row = st.container()
with row:
    c_left, c_right = st.columns([0.8, 0.2])
    with c_left:
        open_exp = st.expander(f"🧾 Logged transactions ({len(st.session_state.transactions)})", expanded=False)
    with c_right:
        if st.button("💣", help="Clear all transactions", use_container_width=True):
            st.session_state.confirming_clear = True

with open_exp:
    df_all = df_from_txns(st.session_state.transactions)
    if df_all.empty:
        st.info("No transactions yet. Add your first deposit to get started.")
    else:
        df_log = df_all.sort_values(by="date", ascending=False).copy()
        for _, row in df_log.iterrows():
            line = st.container(border=True)
            with line:
                c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.5])
                c1.write(f"**{row['date'].strftime('%Y-%m-%d')}**")
                if row["type"] == "deposit":
                    c2.markdown("<span style='color:#22c55e;'>💵 Deposit</span>", unsafe_allow_html=True)
                else:
                    c2.markdown("<span style='color:#ef4444;'>🔻 Withdrawal</span>", unsafe_allow_html=True)
                c3.write(f"${row['amount']:,.2f}")
                if c4.button("✖️", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                    st.session_state.transactions = [tx for tx in st.session_state.transactions if tx["id"] != int(row["id"])]
                    push_notification("warn", "Transaction deleted")
                    st.experimental_rerun()

        if st.session_state.confirming_clear:
            warn = st.warning("Delete **all** transactions? This cannot be undone.")
            cc1, cc2 = st.columns([1, 1])
            with cc1:
                if st.button("Yes, delete all", type="primary"):
                    st.session_state.transactions = []
                    st.session_state.confirming_clear = False
                    push_notification("warn", "All transactions cleared")
                    st.experimental_rerun()
            with cc2:
                if st.button("No, keep them"):
                    st.session_state.confirming_clear = False
                    st.experimental_rerun()

# =============================================================================
# Analytics — collapsible
# =============================================================================
st.subheader("📊 Monthly Summary")
with st.expander("Show charts & table", expanded=False):
    df_all = df_from_txns(st.session_state.transactions)
    if df_all.empty:
        st.info("No data yet. Add a transaction to see summary and charts.")
    else:
        df_curr = df_all[df_all["year"] == current_year].copy()
        monthly = (
            df_curr.groupby(["month", "type"])["amount"]
            .sum()
            .unstack()
            .reindex(columns=["deposit", "withdrawal"], fill_value=0.0)
            .fillna(0.0)
            .reset_index()
        )

        if not monthly.empty:
            melted = monthly.melt(id_vars="month", value_vars=["deposit", "withdrawal"], var_name="kind", value_name="amount")
            color_scale = alt.Scale(domain=["deposit", "withdrawal"], range=["#22c55e", "#ef4444"])
            chart = (
                alt.Chart(melted)
                .mark_bar()
                .encode(
                    x=alt.X("month:N", sort=None, title="Month"),
                    y=alt.Y("amount:Q", title="Amount ($)"),
                    color=alt.Color("kind:N", scale=color_scale, legend=alt.Legend(title="Type", orient="top")),
                    tooltip=["month", "kind", alt.Tooltip("amount:Q", format="$.2f")],
                )
                .properties(height=260)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No current-year transactions for charting yet.")

        if not monthly.empty:
            total_room_this_year = (
                (st.session_state.carryover_manual + current_year_limit(current_year))
                if st.session_state.ever_contributed == "Yes"
                else total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1)
            )
            monthly["net_contribution"] = monthly["deposit"]
            monthly["cumulative_contribution"] = monthly["deposit"].cumsum()
            monthly["room_left"] = (total_room_this_year - monthly["cumulative_contribution"]).clip(lower=0.0)
            st.dataframe(
                monthly.style.format({
                    "deposit": "${:,.2f}",
                    "withdrawal": "${:,.2f}",
                    "net_contribution": "${:,.2f}",
                    "cumulative_contribution": "${:,.2f}",
                    "room_left": "${:,.2f}",
                }),
                use_container_width=True,
            )

# final notifications pass
render_notifications()
render_fx()
