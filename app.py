import streamlit as st
import pandas as pd
from datetime import datetime, date
import time

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(page_title="TFSA Tracker", page_icon="🧮", layout="centered")

# -------------------------
# Session Defaults
# -------------------------
def init_state():
    defaults = {
        "transactions": [],
        "next_id": 1,
        "confirming_clear": False,
        "ever_contributed": "No",
        "carryover_manual": 0.0,
        "amount_input": 0.0,
        "type_input": "deposit",
        # local pop state (emoji next to Add button)
        "local_pop": None,  # dict: {"kind": "deposit"/"withdrawal", "t": epoch_secs}
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

# -------------------------
# Inline emoji pop CSS (next to Add button)
# -------------------------
LOCAL_POP_CSS = """
<style>
.inline-pop {
  display:inline-grid;
  place-items:center;
  width:40px;height:40px;
  border-radius:999px;
  margin-left:10px;
  background: rgba(20,20,20,0.45);
  animation: popIn 420ms cubic-bezier(.2,.8,.2,1), floatFade 1400ms ease 420ms forwards;
  filter: drop-shadow(0 0 8px rgba(16,185,129,.55));
}
.inline-pop.withdrawal { filter: drop-shadow(0 0 8px rgba(239,68,68,.55)); }
.inline-pop span { font-size:24px; line-height:1; }

@keyframes popIn {
  0%   { transform: scale(.8); opacity: .0; }
  60%  { transform: scale(1.25); opacity: 1; }
  100% { transform: scale(1.0); opacity: 1; }
}
@keyframes floatFade {
  0%   { transform: translateY(0px); opacity: 1; }
  70%  { transform: translateY(-6px); opacity: .95; }
  100% { transform: translateY(-10px); opacity: 0; }
}
.bar-wrap { width: 100%; height: 14px; background: rgba(255,255,255,.08); border-radius: 999px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 999px; transition: width .35s ease; }
</style>
"""
st.markdown(LOCAL_POP_CSS, unsafe_allow_html=True)

def now_s() -> float:
    return time.time()

def render_local_pop(placeholder, kind: str | None):
    """
    Render emoji next to the Add button for ~1.8s even across reruns.
    """
    # Show pop if it's fresh
    pop = st.session_state.local_pop
    show = False
    emoji = ""
    cls = "inline-pop"
    if pop is not None:
        age = now_s() - pop["t"]
        if age <= 1.8:
            show = True
            kind = pop["kind"]
            emoji = "💰" if kind == "deposit" else "💸"
            if kind == "withdrawal":
                cls += " withdrawal"
        else:
            # too old, clear it
            st.session_state.local_pop = None

    if show:
        placeholder.markdown(f'<div class="{cls}"><span>{emoji}</span></div>', unsafe_allow_html=True)
    else:
        placeholder.empty()

# =========================
# --------- UI ------------
# =========================
st.markdown(
    """
    <style>
    .muted { opacity: .85 }
    .metric-big { font-size: 46px; font-weight: 800; }
    </style>
    """,
    unsafe_allow_html=True,
)

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

**Annual limits by year (highlights):** 2009 $5,000 • 2015 $10,000 • 2019 $6,000 • 2023 $6,500 • 2024 $7,000 • 2025 $7,000
        """
    )

# --- Estimator / Input ---
st.subheader("📅 Contribution Room Estimator")

colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio("Have you ever contributed to a TFSA before?", ["No", "Yes"], index=(0 if st.session_state.ever_contributed == "No" else 1))

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

# --- Top Metrics ---
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

def pct_color(p):
    if p < 70:
        return "linear-gradient(90deg, #16a34a, #22c55e)"
    elif p < 90:
        return "linear-gradient(90deg, #f59e0b, #fbbf24)"
    else:
        return "linear-gradient(90deg, #ef4444, #dc2626)"

st.write("")
st.markdown("**Contribution room used**")
st.markdown(
    f"""
    <div class="bar-wrap">
      <div class="bar-fill" style="width:{min(room_used_pct,100):.1f}%; background:{pct_color(room_used_pct)};"></div>
    </div>
    <div class="muted" style="text-align:right; margin-top:6px;">{room_used_pct:.1f}%</div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3 = st.columns(3)
m1.metric("This year's limit", f"${current_year_limit(current_year):,.0f}")
m2.metric("Carryover into this year", f"${carryover_prior:,.0f}")
m3.metric("Room left (est.)", f"${room_left:,.0f}")

st.markdown("### This year’s room breakdown")
b1, b2, b3 = st.columns(3)
b1.metric("Total room (carryover + limit)", f"${estimated_room_total:,.0f}")
b2.metric("Deposits YTD", f"${deposits_ytd:,.0f}")
b3.metric("Remaining (est.)", f"${room_left:,.0f}")

# =========================
# --- Add a Transaction ---
# =========================
st.subheader("➕ Add a Transaction")

with st.form("txn_form", clear_on_submit=False):
    c1, c2 = st.columns([1, 1])
    with c1:
        t_date = st.date_input("Date", value=date.today(), min_value=date(2009, 1, 1), max_value=date.today())
    with c2:
        st.session_state.type_input = st.radio("Type", ["deposit", "withdrawal"], index=(0 if st.session_state.type_input == "deposit" else 1), horizontal=True)

    t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=float(st.session_state.amount_input))

    # Place Add button and the emoji placeholder *side by side*
    add_col, pop_col = st.columns([0.88, 0.12])
    with add_col:
        submitted = st.form_submit_button("Add", type="primary", use_container_width=True)
    # pop placeholder (we render after processing too)
    pop_placeholder = pop_col.empty()

    # Process submission
    if submitted:
        df_all = df_from_txns(st.session_state.transactions)
        if t_amount <= 0:
            st.error("Please enter an amount greater than $0.")
        else:
            if st.session_state.type_input == "deposit":
                deposit_year = t_date.year
                deposits_that_year = current_year_deposits(df_all, deposit_year)
                year_limit = current_year_limit(deposit_year)
                if deposit_year == current_year:
                    allowed_room = max(
                        0.0,
                        (st.session_state.carryover_manual if st.session_state.ever_contributed == "Yes" else (estimated_room_total - current_year_limit(current_year)))
                        + year_limit - deposits_that_year
                    )
                else:
                    allowed_room = max(0.0, year_limit - deposits_that_year)

                if t_amount > allowed_room:
                    st.error(f"❌ Deposit exceeds available contribution room for {deposit_year}. Available: ${allowed_room:,.0f}.")
                else:
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "deposit",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0
                    # mark local pop
                    st.session_state.local_pop = {"kind": "deposit", "t": now_s()}

            else:
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
                    # mark local pop
                    st.session_state.local_pop = {"kind": "withdrawal", "t": now_s()}

    # Render emoji next to the button (persists ~1.8s across reruns)
    render_local_pop(pop_placeholder, None)

# =========================
# --- Logged Transactions ---
# =========================
with st.expander(f"🧾 Logged transactions ({len(st.session_state.transactions)})", expanded=False):
    df_all = df_from_txns(st.session_state.transactions)
    if df_all.empty:
        st.info("No transactions yet. Add your first deposit to get started.")
    else:
        df_log = df_all.sort_values(by="date", ascending=False).copy()
        header_cols = st.columns([1.2, 1, 1, 0.5])
        header_cols[0].markdown("**Date**")
        header_cols[1].markdown("**Type**")
        header_cols[2].markdown("**Amount**")
        header_cols[3].markdown("")

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
                if c4.button("✖️", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                    st.session_state.transactions = [tx for tx in st.session_state.transactions if tx["id"] != int(row["id"])]
                    st.rerun()

        st.write("---")
        r1, r2 = st.columns([0.85, 0.15])
        with r2:
            if not st.session_state.confirming_clear:
                if st.button("💣", help="Clear all transactions"):
                    st.session_state.confirming_clear = True
                    st.rerun()
            else:
                warn = st.warning("Delete all transactions? This cannot be undone.")
                cc1, cc2 = st.columns(2)
                if cc1.button("Yes, delete all", type="primary"):
                    st.session_state.transactions = []
                    st.session_state.confirming_clear = False
                    st.rerun()
                if cc2.button("No, keep them"):
                    st.session_state.confirming_clear = False
                    st.rerun()

# =========================
# ------- Charts ----------
# =========================
st.subheader("📊 Monthly Summary")

df_all = df_from_txns(st.session_state.transactions)
if df_all.empty:
    st.info("No data yet. Add a transaction to see charts.")
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
    deposits_ytd = float(monthly["deposit"].sum()) if not monthly.empty else 0.0
    total_room_this_year = (carryover_prior + current_year_limit(current_year)) if st.session_state.ever_contributed == "Yes" else (total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1) + carryover_prior if current_year > 2009 else current_year_limit(current_year))
    monthly["net_contribution"] = monthly["deposit"]
    monthly["cumulative_contribution"] = monthly["deposit"].cumsum()
    monthly["room_left"] = (total_room_this_year - monthly["cumulative_contribution"]).clip(lower=0.0)

    st.bar_chart(
        monthly.set_index("month")[["deposit", "withdrawal"]],
        use_container_width=True
    )

    with st.expander("Show table", expanded=False):
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
