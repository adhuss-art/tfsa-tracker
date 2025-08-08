import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
import altair as alt

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(page_title="TFSA Tracker", page_icon="🧮", layout="wide")

# -------------------------
# Session Defaults
# -------------------------
def init_state():

    # -- compat helper for older Streamlit builds (no vertical_alignment)
def columns_va(spec, vertical_alignment="center"):
    try:
        return st.columns(spec, vertical_alignment=vertical_alignment)
    except TypeError:  # older Streamlit
        return st.columns(spec)
        
    defaults = {
        "transactions": [],         # list of dicts with id, date, type, amount
        "next_id": 1,               # autoincrement id for transaction rows
        "confirming_clear": False,  # for the clear-all confirmation UI
        "ever_contributed": "No",   # default for estimator
        "carryover_manual": 0.0,    # manual carryover when ever_contributed == "Yes"
        "amount_input": 0.0,        # form inputs (helps reset)
        "type_input": "deposit",
        "notifs": [],               # stacked toast-like notifications
        "fx": None,                 # floating emoji effect dict: {"emoji": "💰", "ts": time.time()}
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
LIMIT_CHIPS = [2009, 2013, 2015, 2019, 2023, 2024, 2025]  # highlights to display

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

def add_notif(text: str, icon: str):
    st.session_state.notifs.append({"text": text, "icon": icon, "ts": time.time()})

def trigger_fx(emoji: str):
    st.session_state.fx = {"emoji": emoji, "ts": time.time()}

# =========================
# --------- CSS -----------
# =========================
st.markdown("""
<style>
/* Tighten header spacing */
.block-container { padding-top: 1.1rem; }

/* Global dark text */
html, body, [class*="css"] { color: #e5e7eb; }

/* Title spacing */
h1 { margin-bottom: .5rem; }

/* Expander spacing */
.streamlit-expanderHeader {
  font-weight: 700 !important;
}

/* Annual chips */
.limit-chips { display:flex; flex-wrap:wrap; gap:.4rem; margin-top:.25rem; }
.limit-chip {
  background: #1f2937; color:#e5e7eb; border:1px solid #374151;
  padding:.15rem .5rem; border-radius:.6rem; font-variant-numeric: tabular-nums;
}

/* Animated contribution bar container */
.room-wrap { margin-top:.25rem; }
.room-label { display:flex; justify-content:space-between; font-weight:600; }
.room-bar {
  position: relative; height: 14px; background:#2a2f39; border-radius: 999px; overflow: hidden;
}
.room-fill {
  position:absolute; top:0; left:0; height:100%; width:0%;
  border-radius:999px;
  transition: width 600ms ease-in-out, box-shadow 600ms ease-in-out, background 300ms ease-in-out;
}

/* Glow near full */
.room-fill.glow { box-shadow: 0 0 10px rgba(239,68,68,.45), 0 0 22px rgba(239,68,68,.35); }

/* Toast stack (top-right) */
.toasts {
  position: fixed; top: 80px; right: 20px; z-index: 9999;
  display: flex; flex-direction: column; gap: .5rem;
}
.toast {
  background: #2b2f36; border:1px solid #3a3f46; color:#e5e7eb;
  padding:.65rem .8rem; border-radius:.6rem; display:flex; align-items:center; gap:.5rem;
  min-width: 220px; animation: toastIn .2s ease-out;
}
@keyframes toastIn { from {opacity:0; transform: translateY(-4px);} to {opacity:1; transform:none;} }

/* Floating emoji effect */
.fx {
  position: fixed; top: 90px; right: 28px; z-index: 9998; font-size: 30px;
  animation: fly 1.6s ease-in-out forwards;
}
@keyframes fly {
  0%   { transform: translate(0,0) scale(1); opacity: .95; }
  50%  { transform: translate(-10px,-32px) scale(1.25); opacity: .9; }
  100% { transform: translate(-20px,-70px) scale(1.35); opacity: 0; }
}

/* Bomb area and confirmation */
.bomb-row { display:flex; justify-content:flex-end; align-items:flex-start; gap: .75rem; }
.bomb-btn { border-radius:.8rem; background:#111827; border:1px solid #374151; padding:.45rem .55rem; }
.bomb-btn:hover { background:#1f2937; }
.confirm-card {
  max-width: 340px; background:#3b3a25; border:1px solid #665f2a; color:#fff;
  padding:.8rem .9rem; border-radius:.8rem;
}
.confirm-actions { display:flex; gap:.6rem; margin-top:.5rem; }
.btn-danger {
  background:#ef4444; color:white; border:none; padding:.55rem .8rem; border-radius:.6rem; font-weight:700;
}
.btn-ghost {
  background:#111827; color:#e5e7eb; border:1px solid #374151; padding:.55rem .8rem; border-radius:.6rem;
}

/* Chart panel */
.panel { border:1px solid #2f333a; border-radius:.7rem; padding: .8rem; background:#14181f; }

/* Numbers nice */
.big-num { font-size: 2.1rem; font-weight: 800; letter-spacing: .3px; }
.subtle { color:#9ca3af; }

/* Reduce huge gap under title */
h2, h3 { margin-top: .4rem; }

/* Fix bullet spacing inside expander */
ul li { margin-bottom: .45rem; }
</style>
""", unsafe_allow_html=True)

# =========================
# --------- UI ------------
# =========================
st.title("TFSA Contribution Tracker")

current_year = datetime.now().year

# --- Explainer ---
with st.expander("ℹ️ How TFSA contribution room works", expanded=False):
    st.markdown("""
**Key rules (simplified):**
- Your TFSA room starts accruing from the year you turn **18** (or **2009**, whichever is later).
- **Deposits** reduce this year’s available room.
- **Withdrawals** do **not** give room back until **January 1 of the next year**.
- CRA is the source of truth. This app is an educational helper; confirm with CRA if you’re unsure.

**Annual limits (highlights):**
""")
    chips = " ".join(
        f"<span class='limit-chip'>{y}: ${LIMITS_BY_YEAR[y]:,}</span>" for y in LIMIT_CHIPS
    )
    st.markdown(f"<div class='limit-chips'>{chips}</div>", unsafe_allow_html=True)

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

# --- Top Metrics + Animated Bar ---
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

# animated bar
fill_pct = max(0, min(100, room_used_pct))
# color stage
if fill_pct < 60:
    fill_color = "#22c55e"        # green
elif fill_pct < 85:
    fill_color = "#f59e0b"        # yellow
elif fill_pct < 95:
    fill_color = "#f97316"        # orange
else:
    fill_color = "#ef4444"        # red
glow_class = "glow" if fill_pct >= 95 else ""

st.markdown(f"""
<div class="room-wrap">
  <div class="room-label">
    <div>Contribution room used</div>
    <div>{fill_pct:.1f}%</div>
  </div>
  <div class="room-bar">
    <div class="room-fill {glow_class}" style="width:{fill_pct}%; background:{fill_color};"></div>
  </div>
</div>
""", unsafe_allow_html=True)

m1, m2, m3 = st.columns(3)
m1.metric("This year's limit", f"${current_year_limit(current_year):,.0f}")
m2.metric("Carryover into this year", f"${carryover_prior:,.0f}")
m3.metric("Room left (est.)", f"${room_left:,.0f}")

st.markdown("---")

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
    submitted = st.form_submit_button("Add", type="primary", use_container_width=True)

    if submitted:
        df_all = df_from_txns(st.session_state.transactions)
        if t_amount <= 0:
            add_notif("Enter an amount > $0", "⚠️")
        else:
            if st.session_state.type_input == "deposit":
                deposit_year = t_date.year
                deposits_that_year = current_year_deposits(df_all, deposit_year)
                year_limit = current_year_limit(deposit_year)
                if deposit_year == current_year:
                    allowed_room = max(0.0, (carryover_prior if st.session_state.ever_contributed == "Yes" else carryover_prior) + year_limit - deposits_that_year)
                else:
                    allowed_room = max(0.0, year_limit - deposits_that_year)

                if t_amount > allowed_room:
                    add_notif(f"Deposit exceeds available room for {deposit_year}. Avail: ${allowed_room:,.0f}", "❌")
                else:
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "deposit",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0
                    add_notif("Deposit added", "✅")
                    trigger_fx("💰")  # money bag for deposit
            else:
                bal = lifetime_balance(df_all)
                if t_amount > bal:
                    add_notif(f"Withdrawal exceeds balance. Balance: ${bal:,.0f}", "❌")
                else:
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "withdrawal",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0
                    add_notif("Withdrawal added", "✅")
                    trigger_fx("💸")  # flying money for withdraw

# =========================
# --- Logged Transactions ---
# =========================
st.subheader("🧾 Logged transactions")
st.caption("Most recent first. Delete individual rows with the **✖** buttons.")

# bomb + confirm lives on the right
right_holder = st.container()
with right_holder:
    st.markdown("<div class='bomb-row'>", unsafe_allow_html=True)
    col_bomb, col_confirm = st.columns([0.14, 1], vertical_alignment="start")
    with col_bomb:
        if not st.session_state.confirming_clear:
            if st.button("💣", key="bomb", help="Clear all transactions", use_container_width=False):
                st.session_state.confirming_clear = True
                st.rerun()
        else:
            # show smaller toggle to cancel
            if st.button("✖", key="cancel_clear", help="Cancel", use_container_width=False):
                st.session_state.confirming_clear = False
                st.rerun()
    with col_confirm:
        if st.session_state.confirming_clear:
            st.markdown("<div class='confirm-card'>Delete all transactions? <br/>This cannot be undone.</div>", unsafe_allow_html=True)
            st.markdown("<div class='confirm-actions'>", unsafe_allow_html=True)
            c_yes, c_no = st.columns([0.2, 0.2])
            with c_yes:
                if st.button("Yes, delete all", key="yes_delete_all", use_container_width=True, type="primary"):
                    st.session_state.transactions = []
                    st.session_state.confirming_clear = False
                    add_notif("All transactions cleared", "⚠️")
                    st.rerun()
            with c_no:
                if st.button("No, keep them", key="no_keep_all", use_container_width=True):
                    st.session_state.confirming_clear = False
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

df_all = df_from_txns(st.session_state.transactions)
if df_all.empty:
    st.info("No transactions yet. Add your first deposit to get started.")
else:
    df_log = df_all.sort_values(by="date", ascending=False).copy()
    # list-style rows
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

    # room math
    deposits_ytd = float(monthly["deposit"].sum()) if not monthly.empty else 0.0
    total_room_this_year = (carryover_prior + current_year_limit(current_year)) if st.session_state.ever_contributed == "Yes" else (total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1) + carryover_prior if current_year > 2009 else current_year_limit(current_year))
    monthly["net_contribution"] = monthly["deposit"]
    monthly["cumulative_contribution"] = monthly["deposit"].cumsum()
    monthly["room_left"] = (total_room_this_year - monthly["cumulative_contribution"]).clip(lower=0.0)

    # nice month order by date
    if not monthly.empty:
        monthly_sorted = monthly.copy()
        monthly_sorted["month_dt"] = pd.to_datetime(monthly_sorted["month"])
        monthly_sorted = monthly_sorted.sort_values("month_dt")

        base = alt.Chart(monthly_sorted).encode(x=alt.X("month_dt:T", title="Month"))
        bar = base.mark_bar(cornerRadius=4).encode(
            y=alt.Y("amount:Q", aggregate="sum", title="Amount ($)"),
            color=alt.Color("type:N",
                            scale=alt.Scale(domain=["deposit", "withdrawal"],
                                            range=["#22c55e", "#ef4444"]),
                            legend=alt.Legend(title="Type")),
        )
        data_for_bar = df_curr.copy()
        chart_data = data_for_bar.assign(month_dt=pd.to_datetime(data_for_bar["month"]))

        chart = alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("month_dt:T", title="Month"),
            y=alt.Y("amount:Q", aggregate="sum", title="Amount ($)"),
            color=alt.Color("type:N",
                            scale=alt.Scale(domain=["deposit", "withdrawal"],
                                            range=["#22c55e", "#ef4444"]),
                            legend=alt.Legend(title="Type")),
            tooltip=[alt.Tooltip("type:N"), alt.Tooltip("amount:Q", format="$.2f"), alt.Tooltip("month_dt:T", title="Month")]
        ).properties(height=320)

        st.markdown("<div class='panel'>", unsafe_allow_html=True)
        st.altair_chart(chart, use_container_width=True)
        with st.expander("Show table", expanded=False):
            st.dataframe(
                monthly_sorted.drop(columns=["month_dt"]).style.format({
                    "deposit": "${:,.2f}",
                    "withdrawal": "${:,.2f}",
                    "net_contribution": "${:,.2f}",
                    "cumulative_contribution": "${:,.2f}",
                    "room_left": "${:,.2f}",
                }),
                use_container_width=True
            )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No current-year transactions for charting yet.")

# =========================
# ---- Notifications & FX -
# =========================
# show stacked toasts (keep latest ~4 and auto-trim > 12 to avoid growth)
now = time.time()
st.session_state.notifs = [n for n in st.session_state.notifs if now - n["ts"] < 6]
if len(st.session_state.notifs) > 12:
    st.session_state.notifs = st.session_state.notifs[-12:]

if st.session_state.notifs:
    st.markdown("<div class='toasts'>", unsafe_allow_html=True)
    for n in reversed(st.session_state.notifs[-4:]):  # show last 4
        st.markdown(f"<div class='toast'><span>{n['icon']}</span><span>{n['text']}</span></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# floating emoji fx lives ~1.6s; we simply render it when recent
if st.session_state.fx and (now - st.session_state.fx["ts"] < 1.6):
    st.markdown(f"<div class='fx'>{st.session_state.fx['emoji']}</div>", unsafe_allow_html=True)
