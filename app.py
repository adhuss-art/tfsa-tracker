import streamlit as st
import pandas as pd
from datetime import datetime, date

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(page_title="TFSA Tracker", page_icon="🧮", layout="centered")

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

def current_year_deposits(df: pd.DataFrame, year: int) -> float:
    if df.empty:
        return 0.0
    filt = (df["year"] == year) & (df["type"] == "deposit")
    return float(df.loc[filt, "amount"].sum())

def lifetime_balance(df: pd.DataFrame) -> float:
    # "Available cash" / balance inside the app: deposits - withdrawals, all time
    if df.empty:
        return 0.0
    deposits = float(df.loc[df["type"] == "deposit", "amount"].sum()) if "type" in df else 0.0
    withdrawals = float(df.loc[df["type"] == "withdrawal", "amount"].sum()) if "type" in df else 0.0
    return deposits - withdrawals

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

**Annual limits by year (selected):**
2009 $5,000 • 2013 $5,500 • 2015 $10,000 • 2019 $6,000 • 2023 $6,500 • 2024 $7,000 • 2025 $7,000
        """
    )

# --- Estimator / Input ---
st.subheader("📅 Contribution Room Estimator")

colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio("Have you ever contributed to a TFSA before?", ["No", "Yes"], index=0)

if st.session_state.ever_contributed == "No":
    # If never contributed, your available room = sum of all years from start to current
    estimated_room_total = total_room_from_inception(dob, current_year)
    carryover_prior = estimated_room_total - current_year_limit(current_year)
    st.success(f"Estimated available room (all-time if you've truly never contributed): **${estimated_room_total:,.0f}**")
else:
    # If you *have* contributed, we need a manual carryover (until we add import)
    st.session_state.carryover_manual = st.number_input(
        "Enter your unused TFSA room carried into this year (best estimate):",
        min_value=0.0, step=500.0, value=float(st.session_state.carryover_manual)
    )
    estimated_room_total = st.session_state.carryover_manual + current_year_limit(current_year)
    carryover_prior = st.session_state.carryover_manual
    st.info(f"Estimated total room available **this year** (carryover + {current_year} limit): **${estimated_room_total:,.0f}**")

# --- Top Metrics ---
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

st.write("")  # small spacer
st.progress(min(1.0, room_used_pct / 100.0), text=f"Room used: {room_used_pct:.1f}%   •   Room left: ${room_left:,.0f}")

metric1, metric2, metric3 = st.columns(3)
metric1.metric("This year's limit", f"${current_year_limit(current_year):,.0f}")
metric2.metric("Carryover into this year", f"${carryover_prior:,.0f}")
metric3.metric("Room left (est.)", f"${room_left:,.0f}")

# =========================
# --- Add a Transaction ---
# =========================
st.subheader("➕ Add a Transaction")

# Form lives in a container so we can keep the transaction list right under it
with st.form("txn_form", clear_on_submit=False):
    c1, c2 = st.columns([1, 1])
    with c1:
        t_date = st.date_input("Date", value=date.today(), min_value=date(2009, 1, 1), max_value=date.today())
    with c2:
        st.session_state.type_input = st.radio("Type", ["deposit", "withdrawal"], index=(0 if st.session_state.type_input == "deposit" else 1), horizontal=True)

    t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=float(st.session_state.amount_input))
    submitted = st.form_submit_button("Add", type="primary", use_container_width=True)

    if submitted:
        # Recompute df after any prior changes
        df_all = df_from_txns(st.session_state.transactions)
        # VALIDATIONS
        if t_amount <= 0:
            st.error("Please enter an amount greater than $0.")
        else:
            if st.session_state.type_input == "deposit":
                # Deposit cannot exceed remaining contribution room for the current year
                # We check cumulative deposits in the deposit's *calendar year* (t_date.year)
                deposit_year = t_date.year
                deposits_that_year = current_year_deposits(df_all, deposit_year)
                year_limit = current_year_limit(deposit_year)
                # For years prior to current, we can't know carryover precisely—it’s complex.
                # To keep logic consistent, use the *estimated_room_total* only for current year;
                # for past years default to annual limit only (conservative).
                if deposit_year == current_year:
                    allowed_room = (carryover_prior + year_limit) - deposits_that_year if st.session_state.ever_contributed == "Yes" else (total_room_from_inception(dob, current_year) - (total_room_from_inception(dob, current_year - 1) if current_year > 2009 else 0) - deposits_that_year + carryover_prior)
                    # The expression above ensures current-year allowed room is (carryover + current year limit) - deposits_ytd
                    allowed_room = max(0.0, (st.session_state.carryover_manual if st.session_state.ever_contributed == "Yes" else carryover_prior) + year_limit - deposits_that_year)
                else:
                    allowed_room = max(0.0, year_limit - deposits_that_year)

                if t_amount > allowed_room:
                    st.error(f"❌ Deposit exceeds available contribution room for {deposit_year}. Available: ${allowed_room:,.0f}.")
                else:
                    # Valid deposit — add it
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "deposit",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0  # reset input
                    st.toast("💵 Deposit added", icon="✅")
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
                    st.session_state.amount_input = 0.0  # reset input
                    st.toast("🔻 Withdrawal added", icon="❗")

# =========================
# --- Logged Transactions (collapsible under Add) ---
# =========================
with st.expander(f"🧾 Logged transactions ({len(st.session_state.transactions)})", expanded=False):
    df_all = df_from_txns(st.session_state.transactions)
    if df_all.empty:
        st.info("No transactions yet. Add your first deposit to get started.")
    else:
        # Nice compact list with per-row delete
        df_log = df_all.sort_values(by="date", ascending=False).copy()
        for _, row in df_log.iterrows():
            line = st.container(border=True)
            with line:
                c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.5])
                c1.write(f"**{row['date'].strftime('%Y-%m-%d')}**")
                if row["type"] == "deposit":
                    c2.markdown(f"<span style='color:#22c55e;'>💵 Deposit</span>", unsafe_allow_html=True)
                else:
                    c2.markdown(f"<span style='color:#ef4444;'>🔻 Withdrawal</span>", unsafe_allow_html=True)
                c3.write(f"${row['amount']:,.2f}")
                # Delete button for this row
                if c4.button("✖️", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                    # Remove by ID
                    st.session_state.transactions = [tx for tx in st.session_state.transactions if tx["id"] != int(row["id"])]
                    st.experimental_rerun()

        # Clear-all with confirmation
        st.write("---")
        if not st.session_state.confirming_clear:
            if st.button("💣 Clear all transactions", type="secondary"):
                st.session_state.confirming_clear = True
                st.experimental_rerun()
        else:
            warn = st.warning("Are you sure you want to delete **all** transactions? This cannot be undone.")
            c_yes, c_no = st.columns([1, 1])
            with c_yes:
                if st.button("Yes, delete all", type="primary"):
                    st.session_state.transactions = []
                    st.session_state.confirming_clear = False
                    st.toast("All transactions cleared", icon="⚠️")
                    st.experimental_rerun()
            with c_no:
                if st.button("No, keep them"):
                    st.session_state.confirming_clear = False
                    st.experimental_rerun()

# =========================
# ------- Analytics -------
# =========================
st.subheader("📊 Monthly Summary & Charts")

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
    deposits_ytd = float(monthly["deposit"].sum()) if not monthly.empty else 0.0
    total_room_this_year = (carryover_prior + current_year_limit(current_year)) if st.session_state.ever_contributed == "Yes" else (total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1) + carryover_prior if current_year > 2009 else current_year_limit(current_year))
    monthly["net_contribution"] = monthly["deposit"]
    monthly["cumulative_contribution"] = monthly["deposit"].cumsum()
    monthly["room_left"] = (total_room_this_year - monthly["cumulative_contribution"]).clip(lower=0.0)

    # Summary table
    st.dataframe(
        monthly.style.format({
            "deposit": "${:,.2f}",
            "withdrawal": "${:,.2f}",
            "net_contribution": "${:,.2f}",
            "cumulative_contribution": "${:,.2f}",
            "room_left": "${:,.2f}",
        }),
        use_container_width=True
    )

    # Bars
    st.markdown("**Deposits & Withdrawals by Month**")
    if not monthly.empty:
        st.bar_chart(monthly.set_index("month")[["deposit", "withdrawal"]])
    else:
        st.info("No current-year transactions for charting yet.")

    # Trend needs at least 2 months
    if not monthly.empty and monthly["month"].nunique() >= 2:
        st.markdown("**Contribution Room Left (This Year)**")
        st.line_chart(monthly.set_index("month")[["room_left"]])
    else:
        st.info("📉 Not enough data to show contribution room trend over time. Add deposits across multiple months to activate this chart.")
