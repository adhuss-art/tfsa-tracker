import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, date
import time

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(page_title="TFSA Tracker", page_icon="🧮", layout="centered")

# Tighten top spacing + custom styles
st.markdown("""
<style>
section[data-testid="stHeader"] { height: 56px; }
main .block-container { padding-top: 1.05rem; }

/* Contribution meter */
.room-wrap { position: relative; margin: .15rem 0 .6rem 0; }
.room-track {
  width: 100%; height: 14px; border-radius: 999px;
  background: linear-gradient(90deg,#1f2937 0%, #0b1220 100%); opacity:.9;
}
.room-fill {
  position:absolute; top:0; left:0; height:14px; border-radius:999px;
  background: linear-gradient(90deg, #22c55e 0%, #84cc16 55%, #f59e0b 80%, #ef4444 100%);
  box-shadow: 0 0 10px rgba(239,68,68,0.0);
  transition: width .35s ease;
}
.room-fill.glow { box-shadow: 0 0 16px rgba(239,68,68,.55); }

/* Button emoji burst (always shows near the Add button) */
.fx-wrap { position: relative; display:inline-block; }
.fx-emoji {
  position: absolute; right: -8px; top: -6px;
  font-size: 26px; line-height: 1; user-select: none; pointer-events: none;
  animation: fx-pop 1.05s ease-out forwards;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,.35));
  z-index: 9999;
}
@keyframes fx-pop {
  0%   { transform: translate(8px, 6px) scale(.55); opacity: 0; }
  20%  { transform: translate(0px, 0px) scale(1.15); opacity: 1; }
  60%  { transform: translate(-2px, -10px) scale(1.0); opacity: 1; }
  100% { transform: translate(-2px, -26px) scale(.9); opacity: 0; }
}

/* Compact expander headers */
div[data-testid="stExpander"] > details > summary { padding: .55rem .9rem; }

/* Right-aligned bomb button */
.bomb-btn { text-align:right; }

/* Help text readability in dark mode */
small, .helptext { color: rgba(255,255,255,.65); }

/* Reduce top gap between title and first expander */
h1 + div[data-testid="stExpander"] { margin-top: .35rem; }

/* Altair tooltip font */
.vega-tooltip { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# -------------------------
# Session Defaults
# -------------------------
def init_state():
    defaults = {
        "transactions": [],         # list of {id, date, type, amount}
        "next_id": 1,
        "confirming_clear": False,  # for the clear-all confirmation UI
        "ever_contributed": "No",
        "carryover_manual": 0.0,
        "amount_input": 0.0,
        "type_input": "deposit",
        "log_open": True,           # keep transactions expander open
        # emoji burst state
        "fx_burst_counter": 0,
        "fx_burst_until": 0.0,
        "fx_burst_emoji": "💰",
        # advanced checks toggle
        "adv_checks": False,
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
    filt = (df["type"] == "deposit") & (df["year"] == year)
    return float(df.loc[filt, "amount"].sum())

def all_deposits_any_year(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(df.loc[df["type"] == "deposit", "amount"].sum())

def lifetime_balance(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    deposits = float(df.loc[df["type"] == "deposit", "amount"].sum()) if "type" in df else 0.0
    withdrawals = float(df.loc[df["type"] == "withdrawal", "amount"].sum()) if "type" in df else 0.0
    return deposits - withdrawals

def trigger_burst(emoji: str, ms: int = 1050):
    st.session_state.fx_burst_counter += 1
    st.session_state.fx_burst_emoji = emoji
    st.session_state.fx_burst_until = time.time() + (ms / 1000.0)

# =========================
# --------- UI ------------
# =========================
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

**Annual limits (highlights):** 2009 $5,000 • 2013 $5,500 • 2015 $10,000 • 2019 $6,000 • 2023 $6,500 • 2024 $7,000 • 2025 $7,000
        """
    )

# --- Estimator ---
st.subheader("📅 Contribution Room Estimator")

colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio(
        "Have you ever contributed to a TFSA before?",
        ["No", "Yes"],
        index=(0 if st.session_state.ever_contributed == "No" else 1)
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

# --- Top Meter + Metrics ---
df_all = df_from_txns(st.session_state.transactions)

# "What can I contribute right now?" logic — count ALL deposits logged so far
deposits_counted_now = all_deposits_any_year(df_all)
room_used_pct = (deposits_counted_now / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_counted_now)

st.write("**Contribution room used**")
st.markdown('<div class="room-wrap"><div class="room-track"></div>', unsafe_allow_html=True)
width_pct = min(100.0, room_used_pct)
glow_class = " glow" if width_pct >= 90 else ""
st.markdown(f'<div class="room-fill{glow_class}" style="width:{width_pct}%;"></div></div>', unsafe_allow_html=True)
st.caption(f"Used {room_used_pct:,.1f}% • Left ${room_left:,.0f}")

m1, m2, m3 = st.columns(3)
m1.metric("This year's limit", f"${current_year_limit(current_year):,.0f}")
m2.metric("Carryover into this year", f"${carryover_prior:,.0f}")
m3.metric("Room left (est.)", f"${room_left:,.0f}")

# Advanced checks (optional, info-only)
with st.expander("⚙️ Advanced checks (optional)", expanded=False):
    st.session_state.adv_checks = st.checkbox("Show inception-cap warning", value=st.session_state.adv_checks,
                                              help="Adds a soft warning if lifetime deposits exceed total TFSA room from your DOB to the current year.")
    if st.session_state.adv_checks:
        inception_cap = total_room_from_inception(dob, current_year)
        lifetime_deposits = all_deposits_any_year(df_all)
        if lifetime_deposits > inception_cap:
            st.warning(f"Lifetime deposits (${lifetime_deposits:,.0f}) exceed estimated inception room (${inception_cap:,.0f}). Consider double-checking with CRA.")

# =========================
# --- Add a Transaction ---
# =========================
st.subheader("➕ Add a Transaction")
with st.form("txn_form", clear_on_submit=False):
    c1, c2 = st.columns([1, 1])
    with c1:
        t_date = st.date_input(
            "Date",
            value=date.today(),
            min_value=date(2009, 1, 1),
            max_value=date.today()
        )
        st.caption(
            f"Room checks use your **current-year available room** "
            f"(carryover + {current_year} limit) **regardless of the date you pick**."
        )
    with c2:
        st.session_state.type_input = st.radio(
            "Type", ["deposit", "withdrawal"],
            index=(0 if st.session_state.type_input == "deposit" else 1),
            horizontal=True
        )

    t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=float(st.session_state.amount_input))

    # Emoji appears right beside the Add button
    btn_col1, _ = st.columns([1, 3])
    with btn_col1:
        st.markdown('<div class="fx-wrap">', unsafe_allow_html=True)
        submitted = st.form_submit_button("Add", type="primary", use_container_width=True)
        fx_anchor = st.empty()  # emoji anchor
        st.markdown('</div>', unsafe_allow_html=True)

    if submitted:
        df_all = df_from_txns(st.session_state.transactions)

        if t_amount <= 0:
            st.error("Please enter an amount greater than $0.")
        else:
            if st.session_state.type_input == "deposit":
                # Hard check (now logic): carryover + this-year limit − ALL deposits already logged
                deposits_now = all_deposits_any_year(df_all)
                allow_now = max(0.0, (carryover_prior + current_year_limit(current_year)) - deposits_now)

                # Soft nudge if amount exceeds current-year limit alone but still allowed due to carryover
                if t_amount > current_year_limit(current_year) and t_amount <= allow_now:
                    st.info(f"Over the {current_year} annual limit (${current_year_limit(current_year):,.0f}), "
                            "but allowed because you have carryover.")

                if t_amount > allow_now:
                    st.error(f"❌ Deposit exceeds your available contribution room for {current_year}. "
                             f"Available now: ${allow_now:,.0f}.")
                else:
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "deposit",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0
                    st.session_state.log_open = True
                    trigger_burst("💰")  # deposit emoji
                    st.rerun()
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
                    st.session_state.log_open = True
                    trigger_burst("💸")  # withdrawal emoji
                    st.rerun()

# Render the emoji burst during its short “alive” window on rerun
if "fx_anchor" in locals():
    if time.time() < float(st.session_state.fx_burst_until):
        fx_anchor.markdown(
            f'<div class="fx-emoji" key="{st.session_state.fx_burst_counter}">{st.session_state.fx_burst_emoji}</div>',
            unsafe_allow_html=True
        )
    else:
        fx_anchor.empty()

# =========================
# --- Logged Transactions ---
# =========================
st.subheader("🧾 Logged transactions")

info_col, bomb_col = st.columns([10, 1])
with info_col:
    st.caption("Most recent first. Delete individual rows with the ✖️ buttons.")
with bomb_col:
    if not st.session_state.confirming_clear:
        if st.button("💣", help="Clear ALL transactions", use_container_width=True):
            st.session_state.confirming_clear = True
            st.session_state.log_open = True
            st.rerun()

df_all = df_from_txns(st.session_state.transactions)

with st.expander(f"Show transactions ({len(st.session_state.transactions)})", expanded=st.session_state.log_open):
    if st.session_state.confirming_clear:
        st.warning("Delete all transactions? This cannot be undone.")
        c_yes, c_no = st.columns([1, 1])
        with c_yes:
            if st.button("Yes, delete all", type="primary"):
                st.session_state.transactions = []
                st.session_state.confirming_clear = False
                st.session_state.log_open = True
                st.rerun()
        with c_no:
            if st.button("No, keep them"):
                st.session_state.confirming_clear = False
                st.session_state.log_open = True
                st.rerun()

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
                    c2.markdown(f"<span style='color:#22c55e;'>💵 Deposit</span>", unsafe_allow_html=True)
                else:
                    c2.markdown(f"<span style='color:#ef4444;'>🔻 Withdrawal</span>", unsafe_allow_html=True)
                c3.write(f"${row['amount']:,.2f}")
                if c4.button("✖️", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                    st.session_state.transactions = [tx for tx in st.session_state.transactions if tx["id"] != int(row["id"])]
                    st.session_state.log_open = True  # keep expander open
                    st.rerun()

# =========================
# ------- Analytics -------
# =========================
st.subheader("📊 Monthly Summary")

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

    # Info series for current-year only (descriptive)
    monthly["net_contribution"] = monthly["deposit"]
    monthly["cumulative_contribution"] = monthly["deposit"].cumsum()

    # Chart: green deposits vs red withdrawals
    chart_df = monthly.melt(id_vars="month", value_vars=["deposit", "withdrawal"], var_name="type", value_name="amount")
    color_scale = alt.Scale(domain=["deposit", "withdrawal"], range=["#22c55e", "#ef4444"])

    bar = alt.Chart(chart_df).mark_bar().encode(
        x=alt.X('month:N', title="Month", sort=None),
        y=alt.Y('amount:Q', title='Amount ($)'),
        color=alt.Color('type:N', scale=color_scale, legend=alt.Legend(title="Type")),
        tooltip=['month', 'type', alt.Tooltip('amount:Q', format="$,")]
    ).properties(height=260)

    st.altair_chart(bar, use_container_width=True)

    with st.expander("Show table", expanded=False):
        st.dataframe(
            monthly.style.format({
                "deposit": "${:,.2f}",
                "withdrawal": "${:,.2f}",
                "net_contribution": "${:,.2f}",
                "cumulative_contribution": "${:,.2f}",
            }),
            use_container_width=True
        )
