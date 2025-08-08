import streamlit as st
import pandas as pd
from datetime import datetime, date
import time

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(page_title="TFSA Tracker", page_icon="🧮", layout="wide")

# -------------------------
# Session Defaults
# -------------------------
def init_state():
    defaults = {
        "transactions": [],         # list of dicts with id, date, type, amount
        "next_id": 1,               # autoincrement id for transaction rows
        "ever_contributed": "No",   # default for estimator
        "carryover_manual": 0.0,    # manual carryover when ever_contributed == "Yes"
        "amount_input": 0.0,        # form inputs (helps reset)
        "type_input": "deposit",
        "log_open": True,           # remember expander state for Logged transactions
        "show_table_open": False,   # remember expander state for monthly table
        "confirming_clear": False,  # inline confirm for clear-all
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# -------------------------
# Compact / UI tweaks (CSS)
# -------------------------
st.markdown(
    """
    <style>
      /* tighten the huge top gap under the H1 */
      section.main > div:first-child { padding-top: 0.25rem !important; }
      h1 { margin-bottom: 0.4rem; }

      /* Compact DataFrame look */
      .stDataFrame table { font-size: 0.95rem; }
      .stDataFrame [data-testid="stDataFrameResizable"] { gap: 0.25rem; }

      /* Pretty metric labels */
      .muted { opacity: 0.9; }

      /* Custom progress bar track */
      .room-wrap {
          width: 100%;
          background: rgba(255,255,255,0.07);
          height: 16px;
          border-radius: 999px;
          position: relative;
          overflow: hidden;
      }
      .room-fill {
          height: 100%;
          border-radius: 999px;
          transition: width 600ms ease;
          box-shadow: none;
      }
      .room-fill.glow {
          box-shadow: 0 0 12px rgba(255,60,60,0.55), 0 0 24px rgba(255,60,60,0.35);
      }

      /* Small helper text line under the bar */
      .room-line {
          display:flex; justify-content: space-between; font-weight:600; margin-top: 6px;
      }

      /* Inline bomb confirm card */
      .danger-card {
          background: #3a3824;
          border-radius: 10px;
          padding: 12px 14px;
          color: #efecc2;
      }

      /* Align numbers in monthly table left (Streamlit centers by default) */
      .stDataFrame tbody td div { justify-content: flex-start !important; }

    </style>
    """,
    unsafe_allow_html=True,
)

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

def current_year_deposits(df: pd.DataFrame, year: int) -> float:
    if df.empty:
        return 0.0
    filt = (df["year"] == year) & (df["type"] == "deposit")
    return float(df.loc[filt, "amount"].sum())

def lifetime_balance(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    deposits = float(df.loc[df["type"] == "deposit", "amount"].sum()) if "type" in df else 0.0
    withdrawals = float(df.loc[df["type"] == "withdrawal", "amount"].sum()) if "type" in df else 0.0
    return deposits - withdrawals

def color_for_pct(p: float) -> str:
    """Return a hex for the fill based on used%."""
    # green -> yellow -> red
    if p < 60:
        return "#22c55e"   # green
    elif p < 85:
        return "#fbbf24"   # amber
    else:
        return "#ef4444"   # red

def glow_needed(p: float) -> bool:
    return p >= 92.0

def annual_limits_df():
    rows = [{"Year": y, "Limit ($)": f"${LIMITS_BY_YEAR[y]:,}"} for y in sorted(LIMITS_BY_YEAR)]
    return pd.DataFrame(rows)

# =========================
# --------- UI ------------
# =========================
st.title("TFSA Contribution Tracker")

current_year = datetime.now().year

# --- Estimator Header / Explainer ---
with st.expander("ℹ️ How TFSA contribution room works", expanded=False):
    st.markdown(
        """
**Key rules (simplified):**
- Your TFSA room starts accruing from the year you turn **18** (or **2009**, whichever is later).
- **Deposits** reduce this year’s available room.
- **Withdrawals** do **not** give room back until **January 1 of the next year**.
- CRA is the source of truth. This app is an educational helper; confirm with CRA if you’re unsure.
        """
    )
    st.markdown("**Full annual TFSA limits (2009 → 2025):**")
    st.dataframe(
        annual_limits_df(),
        use_container_width=True,
        hide_index=True
    )

# --- Estimator / Input ---
st.subheader("📅 Contribution Room Estimator")

colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio("Have you ever contributed to a TFSA before?", ["No", "Yes"], index=(0 if st.session_state.ever_contributed == "No" else 1))

if st.session_state.ever_contributed == "No":
    # If never contributed, your available room = sum of all years from start to current
    estimated_room_total = total_room_from_inception(dob, current_year)
    carryover_prior = estimated_room_total - current_year_limit(current_year)
    st.success(f"Estimated available room (all-time if you've truly never contributed): **${estimated_room_total:,.0f}**")
else:
    # If you *have* contributed, ask for carryover
    st.session_state.carryover_manual = st.number_input(
        "Enter your unused TFSA room carried into this year (best estimate):",
        min_value=0.0, step=500.0, value=float(st.session_state.carryover_manual)
    )
    estimated_room_total = st.session_state.carryover_manual + current_year_limit(current_year)
    carryover_prior = st.session_state.carryover_manual
    st.info(f"Estimated total room available **this year** (carryover + {current_year} limit): **${estimated_room_total:,.0f}**")

# --- Top Metrics / Progress ---
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

st.write("")  # spacer

# Custom progress bar with color + glow near full
fill_color = color_for_pct(room_used_pct)
glow_cls = "glow" if glow_needed(room_used_pct) else ""
st.markdown(
    f"""
    <div class="room-line"><div>Contribution room used</div><div>{room_used_pct:.1f}%</div></div>
    <div class="room-wrap">
      <div class="room-fill {glow_cls}" style="width:{min(room_used_pct,100):.1f}%; background:{fill_color};"></div>
    </div>
    """,
    unsafe_allow_html=True,
)

metric1, metric2, metric3 = st.columns(3)
metric1.metric("This year's limit", f"${current_year_limit(current_year):,.0f}")
metric2.metric("Carryover into this year", f"${carryover_prior:,.0f}")
metric3.metric("Room left (est.)", f"${room_left:,.0f}")

# Breakdown card (short + clear, no redundant badge)
with st.container(border=True):
    st.markdown("### This year’s room breakdown")
    k1, k2, k3 = st.columns(3)
    with k1:
        st.caption("Total room (carryover + limit)")
        st.subheader(f"${estimated_room_total:,.0f}")
    with k2:
        st.caption("Deposits YTD")
        st.subheader(f"${deposits_ytd:,.0f}")
    with k3:
        st.caption("Remaining (est.)")
        st.subheader(f"${room_left:,.0f}")

# =========================
# --- Add a Transaction ---
# =========================
st.markdown("### ➕ Add a Transaction")

with st.form("txn_form", clear_on_submit=False):
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        t_date = st.date_input("Date", value=date.today(), min_value=date(2009, 1, 1), max_value=date.today())
    with c2:
        st.session_state.type_input = st.radio("Type", ["deposit", "withdrawal"], index=(0 if st.session_state.type_input == "deposit" else 1), horizontal=True)
    with c3:
        t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=float(st.session_state.amount_input))
    # Add button + emoji slot to its right
    btn_col, emoji_col = st.columns([0.2, 0.8])
    with btn_col:
        submitted = st.form_submit_button("Add", type="primary", use_container_width=True)
    with emoji_col:
        # placeholder where the emoji burst will appear next to the button
        emoji_slot = st.empty()

    if submitted:
        df_all = df_from_txns(st.session_state.transactions)
        if t_amount <= 0:
            st.error("Please enter an amount greater than $0.")
        else:
            if st.session_state.type_input == "deposit":
                # Allow deposit as long as **current-year** total deposits <= total available this year.
                # This lets a single deposit exceed the single-year limit if carryover covers it.
                deposit_year = t_date.year
                deposits_that_year = current_year_deposits(df_all, deposit_year)
                if deposit_year == current_year:
                    allowed_room = max(0.0, (carryover_prior + current_year_limit(current_year)) - deposits_that_year)
                else:
                    # For prior years, be conservative: cap to that year's limit minus any logged deposits for that year.
                    allowed_room = max(0.0, current_year_limit(deposit_year) - deposits_that_year)

                if t_amount > allowed_room and deposit_year == current_year:
                    st.error(f"❌ Deposit would exceed your remaining room for {deposit_year}. Available: ${allowed_room:,.0f}.")
                elif t_amount > allowed_room and deposit_year != current_year:
                    st.error(f"❌ Deposit exceeds that year's limit. Available for {deposit_year}: ${allowed_room:,.0f}.")
                else:
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "deposit",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0
                    # Emoji burst (💰) right next to button – always shows on click
                    emoji_slot.markdown("<div style='font-size:28px'>💰</div>", unsafe_allow_html=True)
                    time.sleep(1.0)
                    emoji_slot.empty()
            else:
                # Withdrawal cannot exceed balance (lifetime deposits - withdrawals)
                bal = lifetime_balance(df_all)
                if t_amount > bal:
                    st.error(f"❌ Withdrawal exceeds available balance. Current balance: ${bal:,.0f}.")
                else:
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "withdrawal",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0
                    # Emoji burst (💸) right next to button – always shows on click
                    emoji_slot.markdown("<div style='font-size:28px'>💸</div>", unsafe_allow_html=True)
                    time.sleep(1.0)
                    emoji_slot.empty()

# =========================
# --- Logged Transactions --
# =========================
head_left, head_right = st.columns([1, 0.08])
with head_left:
    st.subheader("🧾 Logged transactions")
    st.caption("Most recent first. Delete individual rows with the ✖ buttons.")

with head_right:
    # Bomb icon toggles confirm UI
    if not st.session_state.confirming_clear:
        if st.button("💣", help="Clear all transactions"):
            st.session_state.confirming_clear = True
    else:
        pass  # confirmation card will render below list

df_all = df_from_txns(st.session_state.transactions)

with st.expander(f"Show transactions ({len(st.session_state.transactions)})", expanded=st.session_state.log_open):
    # Remember their choice
    st.session_state.log_open = True
    if df_all.empty:
        st.info("No transactions yet. Add your first deposit to get started.")
    else:
        df_log = df_all.sort_values(by="date", ascending=False).copy()
        for _, row in df_log.iterrows():
            line = st.container(border=True)
            with line:
                c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.4])
                c1.write(f"**{row['date'].strftime('%Y-%m-%d')}**")
                if row["type"] == "deposit":
                    c2.markdown(f"<span style='color:#22c55e;'>💵 Deposit</span>", unsafe_allow_html=True)
                else:
                    c2.markdown(f"<span style='color:#ef4444;'>🔻 Withdrawal</span>", unsafe_allow_html=True)
                c3.write(f"${row['amount']:,.2f}")
                if c4.button("✖", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                    # delete by ID (no rerun -> keeps expander open)
                    st.session_state.transactions = [tx for tx in st.session_state.transactions if tx["id"] != int(row["id"])]
                    # force re-render of this block by just writing a tiny placeholder
                    st.write("")

        # Inline clear-all confirmation (appears under the bomb)
        if st.session_state.confirming_clear:
            st.write("")
            st.markdown('<div class="danger-card">Delete all transactions? This cannot be undone.</div>', unsafe_allow_html=True)
            cc1, cc2 = st.columns([0.16, 0.18])
            with cc1:
                if st.button("Yes, delete all", type="primary"):
                    st.session_state.transactions = []
                    st.session_state.confirming_clear = False
                    st.success("All transactions cleared.")
            with cc2:
                if st.button("No, keep them"):
                    st.session_state.confirming_clear = False

# =========================
# ------- Analytics -------
# =========================
st.subheader("📊 Monthly Summary")

df_all = df_from_txns(st.session_state.transactions)
if df_all.empty:
    st.info("No data yet. Add a transaction to see summary and charts.")
else:
    # Current-year monthly summary
    df_curr = df_all[df_all["year"] == current_year].copy()
    monthly = (
        df_curr.groupby(["month", "type"])["amount"]
        .sum()
        .unstack()
        .reindex(columns=["deposit", "withdrawal"], fill_value=0.0)
        .fillna(0.0)
        .reset_index()
    )

    # Room math (deposits consume room; withdrawals don't restore in-year)
    total_room_this_year = (carryover_prior + current_year_limit(current_year)) if st.session_state.ever_contributed == "Yes" \
        else (total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1) + carryover_prior if current_year > 2009 else current_year_limit(current_year))

    monthly["net_contribution"] = monthly["deposit"]
    monthly["cumulative_contribution"] = monthly["deposit"].cumsum()
    monthly["room_left"] = (total_room_this_year - monthly["cumulative_contribution"]).clip(lower=0.0)

    # Intuitive chart: deposits (green) vs withdrawals (red)
    st.bar_chart(
        monthly.set_index("month")[["deposit", "withdrawal"]],
        use_container_width=True,
    )

    with st.expander("Show table", expanded=st.session_state.show_table_open):
        st.session_state.show_table_open = True
        # Compact table with currency formatting
        fmt = {
            "deposit": "${:,.2f}",
            "withdrawal": "${:,.2f}",
            "net_contribution": "${:,.2f}",
            "cumulative_contribution": "${:,.2f}",
            "room_left": "${:,.2f}",
        }
        st.dataframe(
            monthly.style.format(fmt),
            use_container_width=True,
            hide_index=True
        )
