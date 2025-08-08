import streamlit as st
import pandas as pd
from datetime import datetime, date
import time

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(
    page_title="TFSA Tracker",
    page_icon="🧮",
    layout="centered",
)

# Global CSS: tighten top spacing, dark-friendly tweaks, progress bar, cards, fx stack
st.markdown("""
<style>
/* Reduce giant gap under the title */
.block-container { padding-top: 1.2rem; }

/* Card-like boxes */
.card {
  border: 1px solid rgba(148,163,184,.2);
  border-radius: 14px;
  background: rgba(17,24,39,.4);
  padding: 1rem 1.25rem;
}

/* Headline metric formatting */
.big-num { font-size: 2.8rem; font-weight: 700; letter-spacing: .01em; }

/* Custom progress wrapper */
.roombar { margin: .25rem 0 0.35rem 0; }
.roombar-track {
  height: 14px; width: 100%; border-radius: 999px;
  background: rgba(148,163,184,.25);
  position: relative; overflow: hidden;
}
.roombar-fill {
  height: 100%; border-radius: 999px;
  transition: width .25s ease-out, background .25s ease-out, box-shadow .25s ease-out;
}

/* Sticky emoji stack (bottom-right) */
.fx-stack {
  position: fixed; right: 22px; bottom: 22px;
  display: flex; flex-direction: column; gap: 10px;
  z-index: 9999;
}
.fx-note {
  background: rgba(30, 41, 59, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.25);
  padding: 10px 14px; border-radius: 12px;
  box-shadow: 0 6px 24px rgba(0,0,0,0.35);
  backdrop-filter: blur(6px);
  font-size: 0.95rem; line-height: 1.3;
  color: #e5e7eb;
  animation: fxFade .25s ease-out;
}
@keyframes fxFade { from {opacity: 0; transform: translateY(6px);} to {opacity:1; transform: translateY(0);} }

/* Small “badge” */
.badge {
  display: inline-block; padding: .35rem .6rem; border-radius: .75rem;
  font-weight: 600; font-size: .9rem; color: #d1fae5;
  background: #065f46;
}

/* Inline icon button (bomb) */
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; border-radius: 10px;
  background: rgba(31,41,55,.6); border: 1px solid rgba(148,163,184,.25);
  cursor: pointer; user-select: none;
}
.icon-btn:hover { background: rgba(55,65,81,.75); }

/* Expander title weight */
.streamlit-expanderHeader { font-weight: 700 !important; }

/* Tighten rows list spacing a bit */
.element-container:has(> div > div[data-testid="stHorizontalBlock"]) { margin-bottom: .25rem; }

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

        # Visual FX + UX helpers
        "fx_queue": [],             # stacked emoji notes (persist across reruns)
        "last_action": None,        # 'add_deposit' | 'add_withdrawal' | None
        "keep_add_open": True,      # keep the Add expander open feeling
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

def fmt_money(v: float) -> str:
    return f"${v:,.0f}"

def pct_color_and_glow(pct: float):
    """
    Returns (css_color_string, css_box_shadow or 'none') for progress fill.
    Green -> Yellow/Orange -> Red with glow near full.
    """
    if pct < 60:
        color = "#22c55e"  # green
        glow = "none"
    elif pct < 85:
        color = "#f59e0b"  # amber
        glow = "none"
    elif pct < 95:
        color = "#ef4444"  # red
        glow = "0 0 12px rgba(239,68,68,.35)"
    else:
        color = "#ef4444"
        glow = "0 0 22px rgba(239,68,68,.55)"
    return color, glow

# -------------------------
# Sticky emoji stack
# -------------------------
FX_TTL_SECONDS = 3.5
FX_MAX = 4

def fx_push(kind: str, amount: float, used_pct: float, room_left: float):
    emoji = "💰" if kind == "deposit" else "💸"
    used_txt = f"{used_pct:.1f}% used"
    left_txt = f"left {fmt_money(room_left)}"
    msg = f"{emoji} {kind.capitalize()} {fmt_money(amount)} • {used_txt} • {left_txt}"
    st.session_state.fx_queue.append({"ts": time.time(), "kind": kind, "text": msg})
    st.session_state.fx_queue = st.session_state.fx_queue[-FX_MAX:]

def render_fx_stack():
    now = time.time()
    st.session_state.fx_queue = [fx for fx in st.session_state.fx_queue if (now - fx["ts"]) <= FX_TTL_SECONDS]
    if not st.session_state.fx_queue:
        return
    html = ['<div class="fx-stack">']
    for fx in st.session_state.fx_queue[::-1]:
        html.append(f'<div class="fx-note">{fx["text"]}</div>')
    html.append('</div>')
    st.markdown("".join(html), unsafe_allow_html=True)

# Render the stack immediately so it's present no matter where on the page we are
render_fx_stack()

# =========================
# --------- UI ------------
# =========================
st.markdown("# TFSA Contribution Tracker")

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
    # Clean “annual limits (highlights)”
    highlights = [2009, 2013, 2015, 2019, 2023, 2024, 2025]
    chips = " • ".join([f"**{y}** {fmt_money(LIMITS_BY_YEAR[y])}" for y in highlights])
    st.markdown(f"**Annual limits (highlights):** {chips}")

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
    st.markdown(f'<div class="card"><span class="badge">New TFSA (est.)</span> Estimated total room available **this year**: {fmt_money(estimated_room_total)}</div>', unsafe_allow_html=True)
else:
    st.session_state.carryover_manual = st.number_input(
        "Enter your unused TFSA room carried into this year (best estimate):",
        min_value=0.0, step=500.0, value=float(st.session_state.carryover_manual)
    )
    estimated_room_total = st.session_state.carryover_manual + current_year_limit(current_year)
    carryover_prior = st.session_state.carryover_manual
    st.markdown(
        f'<div class="card"><span class="badge">Carryover + {current_year} limit</span> Estimated total room available **this year**: {fmt_money(estimated_room_total)}</div>',
        unsafe_allow_html=True
    )

# --- Top Metrics, Progress ---
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)
color, glow = pct_color_and_glow(room_used_pct)
pct_str = f"{room_used_pct:.1f}%"

st.markdown("#### Contribution room used")
st.markdown(
    f"""
<div class="roombar">
  <div class="roombar-track">
    <div class="roombar-fill" style="width:{min(room_used_pct,100):.2f}%; background:{color}; box-shadow:{glow};"></div>
  </div>
  <div style="text-align:right; opacity:.85; margin-top:.25rem;">{pct_str}</div>
</div>
""",
    unsafe_allow_html=True
)

m1, m2, m3 = st.columns(3)
m1.metric("This year's limit", fmt_money(current_year_limit(current_year)))
m2.metric("Carryover into this year", fmt_money(carryover_prior))
m3.metric("Room left (est.)", fmt_money(room_left))

# A clearer yearly breakdown card
st.markdown("### This year’s room breakdown")
with st.container():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption("Total room (carryover + limit)")
        st.markdown(f'<div class="big-num">{fmt_money(estimated_room_total)}</div>', unsafe_allow_html=True)
    with c2:
        st.caption("Deposits YTD")
        st.markdown(f'<div class="big-num">{fmt_money(deposits_ytd)}</div>', unsafe_allow_html=True)
    with c3:
        st.caption("Remaining (est.)")
        st.markdown(f'<div class="big-num">{fmt_money(room_left)}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# --- Add a Transaction ---
# =========================
st.markdown("### ➕ Add a Transaction")

add_open = st.session_state.get("last_action") in ("add_deposit", "add_withdrawal") or st.session_state.keep_add_open
with st.expander("Open add form", expanded=add_open):
    with st.form("txn_form", clear_on_submit=False):
        c1, c2 = st.columns([1, 1])
        with c1:
            t_date = st.date_input("Date", value=date.today(), min_value=date(2009, 1, 1), max_value=date.today())
        with c2:
            st.session_state.type_input = st.radio("Type", ["deposit", "withdrawal"], index=(0 if st.session_state.type_input == "deposit" else 1), horizontal=True)

        t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=float(st.session_state.amount_input))
        submitted = st.form_submit_button("Add", type="primary", use_container_width=True)

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
                        allowed_room = max(0.0, (carryover_prior + year_limit) - deposits_that_year)
                    else:
                        allowed_room = max(0.0, year_limit - deposits_that_year)

                    if t_amount > allowed_room:
                        st.error(f"❌ Deposit exceeds available contribution room for {deposit_year}. Available: {fmt_money(allowed_room)}.")
                    else:
                        st.session_state.transactions.append({
                            "id": st.session_state.next_id,
                            "date": t_date.strftime("%Y-%m-%d"),
                            "type": "deposit",
                            "amount": float(t_amount)
                        })
                        st.session_state.next_id += 1
                        st.session_state.amount_input = 0.0
                        # Visual FX bubble
                        df_after = df_from_txns(st.session_state.transactions)
                        dep_ytd_after = current_year_deposits(df_after, current_year)
                        used_pct_after = (dep_ytd_after / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
                        left_after = max(0.0, estimated_room_total - dep_ytd_after)
                        fx_push("deposit", float(t_amount), used_pct_after, left_after)
                        st.session_state.last_action = "add_deposit"

                else:
                    bal = lifetime_balance(df_all)
                    if t_amount > bal:
                        st.error(f"❌ Withdrawal exceeds available balance. Current balance: {fmt_money(bal)}.")
                    else:
                        st.session_state.transactions.append({
                            "id": st.session_state.next_id,
                            "date": t_date.strftime("%Y-%m-%d"),
                            "type": "withdrawal",
                            "amount": float(t_amount)
                        })
                        st.session_state.next_id += 1
                        st.session_state.amount_input = 0.0
                        df_after = df_from_txns(st.session_state.transactions)
                        dep_ytd_after = current_year_deposits(df_after, current_year)
                        used_pct_after = (dep_ytd_after / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
                        left_after = max(0.0, estimated_room_total - dep_ytd_after)
                        fx_push("withdrawal", float(t_amount), used_pct_after, left_after)
                        st.session_state.last_action = "add_withdrawal"

# =========================
# --- Logged Transactions (collapsible & compact) ---
# =========================
st.markdown("### 🧾 Logged transactions")
log_open = False  # collapsed by default to prevent page from growing infinitely
with st.expander("Show / hide list", expanded=log_open):
    df_all = df_from_txns(st.session_state.transactions)
    if df_all.empty:
        st.info("No transactions yet. Add your first deposit to get started.")
    else:
        # top bar with bomb on right
        bar_l, bar_r = st.columns([1,0.12])
        with bar_l:
            st.caption("Most recent first. Delete individual rows with the **✖️** buttons.")
        with bar_r:
            # bomb toggle
            if not st.session_state.confirming_clear:
                if st.button("💣", help="Clear all transactions", use_container_width=True):
                    st.session_state.confirming_clear = True
            else:
                st.button("💣", help="Cancel", use_container_width=True, disabled=True)

        # confirmation block sits right under the bomb if toggled
        if st.session_state.confirming_clear:
            st.warning("Delete all transactions? This cannot be undone.")
            c_yes, c_no = st.columns([0.18, 0.22])
            if c_yes.button("Yes, delete all", type="primary"):
                st.session_state.transactions = []
                st.session_state.confirming_clear = False
            if c_no.button("No, keep them"):
                st.session_state.confirming_clear = False

        # list rows
        df_log = df_all.sort_values(by="date", ascending=False).copy()
        for _, row in df_log.iterrows():
            line = st.container()
            c1, c2, c3, c4 = line.columns([1.2, 1, 1, 0.4])
            c1.write(f"**{row['date'].strftime('%Y-%m-%d')}**")
            if row["type"] == "deposit":
                c2.markdown(f"<span style='color:#22c55e;'>💰 Deposit</span>", unsafe_allow_html=True)
            else:
                c2.markdown(f"<span style='color:#ef4444;'>💸 Withdrawal</span>", unsafe_allow_html=True)
            c3.write(f"{fmt_money(row['amount'])}")
            if c4.button("✖️", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                st.session_state.transactions = [tx for tx in st.session_state.transactions if tx["id"] != int(row["id"])]

# =========================
# ------- Analytics -------
# =========================
df_all = df_from_txns(st.session_state.transactions)
st.markdown("### 📊 Charts & table")
with st.expander("Show charts", expanded=not df_all.empty):
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
        # green for deposits, red for withdrawals
        st.bar_chart(
            monthly.set_index("month")[["deposit", "withdrawal"]],
            height=320
        )
        with st.expander("Show monthly table", expanded=False):
            # add columns for clarity
            total_room_this_year = carryover_prior + current_year_limit(current_year) if st.session_state.ever_contributed == "Yes" \
                else (total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1) + carryover_prior if current_year > 2009 else current_year_limit(current_year))
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
                height=280
            )
