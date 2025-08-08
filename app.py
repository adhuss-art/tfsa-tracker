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
        "confirming_clear": False,  # legacy flag (unused but kept to avoid KeyErrors)
        "show_clear_confirm": False,
        "ever_contributed": "No",   # default for estimator
        "carryover_manual": 0.0,    # manual carryover when ever_contributed == "Yes"
        "amount_input": 0.0,        # form inputs (helps reset)
        "type_input": "deposit",
        # stacked notifications
        "notif": [],                # list of {ts, ttl, icon, text}
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
    # Available cash/balance inside the app: deposits - withdrawals (all time)
    if df.empty:
        return 0.0
    deposits = float(df.loc[df["type"] == "deposit", "amount"].sum()) if "type" in df else 0.0
    withdrawals = float(df.loc[df["type"] == "withdrawal", "amount"].sum()) if "type" in df else 0.0
    return deposits - withdrawals

# -------------------------
# Global CSS (dark-mode safe)
# -------------------------
st.markdown("""
<style>
/* tighten big title spacing */
.block-container { padding-top: 0.75rem !important; }
h1 { margin-bottom: 0.6rem !important; }

/* explainer & pills */
.tfsa-pill {
  background: rgba(38, 84, 62, 0.6);
  border: 1px solid rgba(115, 208, 173, 0.25);
  padding: .9rem 1.1rem; border-radius: .8rem;
  color: var(--text-color, #e5e7eb); font-weight: 600;
}

/* progress bar container */
.progress-wrap {
  margin: 6px 0 12px 0;
  padding: 10px 14px 2px 14px;
  border-radius: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
}
.progress-head {
  display:flex; justify-content:space-between; align-items:center;
  font-weight: 700; letter-spacing:.2px;
  color: #e5e7eb;
}
.progress-sub {
  margin-top: 2px; opacity:.85; color:#e5e7eb;
}
.progress-outer {
  width: 100%; height: 16px; border-radius: 999px;
  background: rgba(255,255,255,0.08);
  overflow: hidden; margin-top: 8px;
}
.progress-inner {
  height: 100%; width: 0%;
  border-radius: 999px;
  background: linear-gradient(90deg,#22c55e, #16a34a);
  transition: width .45s ease;
  box-shadow: none;
}
.progress-inner.yellow { background: linear-gradient(90deg,#f59e0b,#d97706); }
.progress-inner.orange { background: linear-gradient(90deg,#fb923c,#f97316); }
.progress-inner.red { background: linear-gradient(90deg,#ef4444,#dc2626); }

/* glow near full */
@keyframes pulseGlow {
  0% { box-shadow: 0 0 0px rgba(239,68,68,0.0); }
  50% { box-shadow: 0 0 12px rgba(239,68,68,0.55), 0 0 24px rgba(239,68,68,0.35); }
  100% { box-shadow: 0 0 0px rgba(239,68,68,0.0); }
}
.progress-inner.glow { animation: pulseGlow 1.8s infinite; }

/* stacked toasts (top-right) */
.toast-stack {
  position: fixed; top: 72px; right: 24px; z-index: 9999;
  display: flex; flex-direction: column; gap: 10px;
}
.toast {
  background: rgba(30, 32, 38, .92);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 12px 14px; min-width: 260px; color:#e5e7eb;
  box-shadow: 0 8px 30px rgba(0,0,0,.35);
  display:flex; gap:.6rem; align-items:center;
  backdrop-filter: blur(4px);
}

/* little floating emoji (deposit/withdraw) */
.float-emoji {
  position: fixed;
  right: 26px;
  top: 110px;
  font-size: 24px;
  opacity: 0.0;
  transform: translateY(8px);
  transition: opacity .25s ease, transform .25s ease;
  z-index: 9999;
}
.float-emoji.show { opacity: 1.0; transform: translateY(0); }

/* tiny badge labels */
.badge {
  font-size: 12px; padding: 2px 8px; border-radius: 999px;
  background: rgba(255,255,255,.08); color:#e5e7eb;
  border: 1px solid rgba(255,255,255,.08);
}

/* remove weird black text in dark theme */
html, body, [class^="css"], .stMarkdown, .stText, .stCaption, p, span, label {
  color: #e5e7eb !important;
}

/* keep inputs readable in dark theme */
input, select, textarea {
  color: #e5e7eb !important;
}
</style>
""", unsafe_allow_html=True)

# ===== helpers for UI bits =====
def render_limits_inline():
    # compact “highlights” string, consistent type
    highlights = [(2009, 5000), (2013, 5500), (2015, 10000), (2019, 6000), (2023, 6500), (2024, 7000), (2025, 7000)]
    row = " • ".join([f"<span class='badge'>{y}&nbsp;${amt:,.0f}</span>" for (y, amt) in highlights])
    st.markdown(f"<div style='margin-top:.3rem;'>**Annual limits (highlights):** {row}</div>", unsafe_allow_html=True)

def render_progress(percent: float, room_left: float):
    pct_str = f"{percent:.1f}%"
    # color stage
    cls = "green"
    if percent >= 95: cls = "red glow"
    elif percent >= 85: cls = "orange"
    elif percent >= 60: cls = "yellow"

    width = max(0.0, min(100.0, percent))
    html = f"""
    <div class="progress-wrap">
      <div class="progress-head">
        <div>Contribution room used</div>
        <div>{pct_str}</div>
      </div>
      <div class="progress-outer">
        <div class="progress-inner {cls}" style="width:{width}%;"></div>
      </div>
      <div class="progress-sub">${room_left:,.0f} room left</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def push_toast(text: str, icon: str = "✅", ttl: float = 4.0):
    st.session_state.notif.append({
        "ts": datetime.now().timestamp(),
        "ttl": ttl,
        "icon": icon,
        "text": text
    })

def render_toasts():
    # purge expired and render remaining (stacked)
    now = datetime.now().timestamp()
    st.session_state.notif = [n for n in st.session_state.notif if now - n["ts"] < n["ttl"]]
    if not st.session_state.notif:
        return
    with st.container():
        st.markdown("<div class='toast-stack'>", unsafe_allow_html=True)
        for n in st.session_state.notif:
            st.markdown(f"<div class='toast'><div>{n['icon']}</div><div>{n['text']}</div></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

def flash_emoji(kind: str):
    # just drop the element; CSS handles fade
    emoji = "💵" if kind == "deposit" else "🔻"
    st.markdown(f"<div class='float-emoji show'>{emoji}</div>", unsafe_allow_html=True)

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
        """
    )
    render_limits_inline()

# --- Settings / Estimator ---
st.subheader("📅 Contribution Room Estimator")

colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio("Have you ever contributed to a TFSA before?", ["No", "Yes"], index=(0 if st.session_state.ever_contributed == "No" else 1))

if st.session_state.ever_contributed == "No":
    estimated_room_total = total_room_from_inception(dob, current_year)
    carryover_prior = estimated_room_total - current_year_limit(current_year)
    st.markdown(f"<div class='tfsa-pill'>Estimated available room (all-time if you've truly never contributed): <strong>${estimated_room_total:,.0f}</strong></div>", unsafe_allow_html=True)
else:
    st.session_state.carryover_manual = st.number_input(
        "Enter your unused TFSA room carried into this year (best estimate):",
        min_value=0.0, step=500.0, value=float(st.session_state.carryover_manual)
    )
    estimated_room_total = st.session_state.carryover_manual + current_year_limit(current_year)
    carryover_prior = st.session_state.carryover_manual
    st.markdown(f"<div class='tfsa-pill'>Estimated total room available this year (carryover + {current_year} limit): <strong>${estimated_room_total:,.0f}</strong></div>", unsafe_allow_html=True)

# --- Top Metrics & Progress ---
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

render_progress(room_used_pct, room_left)

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
                    # allowed = carryover + this year's limit - deposits_ytd
                    carry = (st.session_state.carryover_manual if st.session_state.ever_contributed == "Yes" else
                             (estimated_room_total - current_year_limit(current_year)))
                    allowed_room = max(0.0, carry + year_limit - deposits_that_year)
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
                    flash_emoji("deposit")
                    push_toast("💵 Deposit added", "✅", ttl=5.0)
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
                    flash_emoji("withdrawal")
                    push_toast("🔻 Withdrawal added", "❗", ttl=5.0)
                    st.rerun()

# =========================
# --- Logged Transactions ---
# =========================
st.subheader("🧾 Logged transactions")

left, right = st.columns([0.8, 0.2])
with left:
    st.caption("Most recent first. Delete individual rows with the ✖️ buttons.")
with right:
    bomb = st.button("💣", key="clear_bomb", help="Clear all transactions", type="secondary")
    if bomb:
        st.session_state.show_clear_confirm = True

    if st.session_state.show_clear_confirm:
        st.warning("Delete **all** transactions? This cannot be undone.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("Yes, delete all", type="primary", key="yes_clear"):
                st.session_state.transactions = []
                st.session_state.show_clear_confirm = False
                push_toast("All transactions cleared", "⚠️", ttl=5.0)
                st.rerun()
        with cc2:
            if st.button("No, keep them", key="no_clear"):
                st.session_state.show_clear_confirm = False

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
                c2.markdown(f"<span style='color:#22c55e;'>💵 Deposit</span>", unsafe_allow_html=True)
            else:
                c2.markdown(f"<span style='color:#ef4444;'>🔻 Withdrawal</span>", unsafe_allow_html=True)
            c3.write(f"${row['amount']:,.2f}")
            if c4.button("✖️", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                st.session_state.transactions = [
                    tx for tx in st.session_state.transactions
                    if tx["id"] != int(row["id"])
                ]
                st.rerun()

# =========================
# ------- Analytics -------
# =========================
st.subheader("📊 Charts")

df_all = df_from_txns(st.session_state.transactions)
if df_all.empty:
    st.info("No data yet. Add a transaction to see charts.")
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

    # room math for table
    total_room_this_year = (carryover_prior + current_year_limit(current_year)) if st.session_state.ever_contributed == "Yes" else (
        total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1) + carryover_prior
        if current_year > 2009 else current_year_limit(current_year)
    )
    monthly["net_contribution"] = monthly["deposit"]
    monthly["cumulative_contribution"] = monthly["deposit"].cumsum()
    monthly["room_left"] = (total_room_this_year - monthly["cumulative_contribution"]).clip(lower=0.0)

    # pretty bar (green/red)
    import altair as alt
    long = monthly.melt(id_vars=["month"], value_vars=["deposit", "withdrawal"], var_name="type", value_name="amount")
    color_scale = alt.Scale(domain=["deposit", "withdrawal"], range=["#22c55e", "#ef4444"])
    chart = (
        alt.Chart(long)
        .mark_bar()
        .encode(
            x=alt.X("month:N", title="Month", axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("amount:Q", title="Amount ($)"),
            color=alt.Color("type:N", scale=color_scale, legend=alt.Legend(title="Type")),
            tooltip=["month", "type", alt.Tooltip("amount:Q", format="$.2f")]
        )
        .properties(height=280)
    )
    st.altair_chart(chart, use_container_width=True)

    with st.expander("Show data table", expanded=False):
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

# Render any stacked toasts last so they sit above everything
render_toasts()


