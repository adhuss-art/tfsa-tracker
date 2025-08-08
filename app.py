# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, date

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(page_title="TFSA Tracker", page_icon="🧮", layout="wide")

# -------------------------
# Session Defaults
# -------------------------
def init_state():
    defaults = {
        "transactions": [],          # list of dicts: id, date, type, amount
        "next_id": 1,
        "ever_contributed": "No",
        "carryover_manual": 0.0,
        "amount_input": 0.0,
        "type_input": "deposit",
        "show_table": False,
        "log_open": False,           # logged transactions expander persist
        "anim_stack": [],            # queued emoji animations
        "just_added": None,          # ("deposit"|"withdrawal", amount)
        "confirming_clear": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
init_state()

# Tiny helper to check Streamlit version feature
def supports_hide_index() -> bool:
    try:
        import streamlit as _s
        # hide_index available in 1.24+
        return tuple(map(int, _s.__version__.split(".")[:2])) >= (1, 24)
    except Exception:
        return False

# -------------------------
# Constants / Helpers
# -------------------------
highlights = [
    (2009, 5000),
    (2013, 5500),
    (2015, 10000),
    (2019, 6000),
    (2023, 6500),
    (2024, 7000),
    (2025, 7000),
]

st.markdown("**Annual limits (highlights):**")
for year, amt in highlights:
    st.markdown(f"- **{year}**: ${amt:,}")


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

# =========================
# --------- UI ------------
# =========================
# Compact header
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.2rem;}
      /* Progress rail + glow */
      .room-rail {height:14px;background:rgba(255,255,255,0.08);border-radius:999px;position:relative;overflow:hidden}
      .room-fill {height:100%;border-radius:999px;transition:width .4s ease}
      .glow {box-shadow:0 0 12px 2px rgba(255, 86, 86, .55)}
      /* Emoji burst next to Add button */
      .burst-wrap {position:relative;display:inline-block;min-width:0}
      .burst {position:absolute;right:-6px;top:-10px;font-size:20px;opacity:0;animation:pop .9s ease forwards}
      .burst.delay {animation-delay:.05s}
      @keyframes pop {
        0% {transform:translateY(6px) scale(.7); opacity:0}
        20% {transform:translateY(-2px) scale(1.1); opacity:1}
        70% {transform:translateY(-8px) scale(1); opacity:.95}
        100% {transform:translateY(-18px); opacity:0}
      }
      /* Tighten expander header */
      section[data-testid="stExpander"] > div:first-child {padding: .4rem .75rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

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

# --- Estimator / Input ---
st.subheader("📅 Contribution Room Estimator")
colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio("Have you ever contributed to a TFSA before?", ["No", "Yes"], horizontal=True, index=(0 if st.session_state.ever_contributed == "No" else 1))

if st.session_state.ever_contributed == "No":
    estimated_room_total = total_room_from_inception(dob, current_year)
    carryover_prior = estimated_room_total - current_year_limit(current_year)
    st.success(f"Estimated total room available **this year** (if you've truly never contributed): **${estimated_room_total:,.0f}**")
else:
    st.session_state.carryover_manual = st.number_input(
        "Enter your unused TFSA room carried into this year (best estimate):",
        min_value=0.0, step=500.0, value=float(st.session_state.carryover_manual)
    )
    estimated_room_total = st.session_state.carryover_manual + current_year_limit(current_year)
    carryover_prior = st.session_state.carryover_manual
    st.info(f"Estimated total room **this year** (carryover + {current_year} limit): **${estimated_room_total:,.0f}**")

# --- Top Metrics + Progress ---
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

# custom progress bar with color ramp
def bar_color(p):
    if p < 70:  # green to lime
        return "linear-gradient(90deg,#22c55e,#84cc16)"
    if p < 90:  # amber
        return "linear-gradient(90deg,#eab308,#f59e0b)"
    # red
    return "linear-gradient(90deg,#ef4444,#f43f5e)"

fill_w = min(100.0, room_used_pct)
st.markdown(
    f"""
    <div class="room-rail">
      <div class="room-fill {'glow' if fill_w>=95 else ''}" style="width:{fill_w}%; background:{bar_color(fill_w)}"></div>
    </div>
    <div style="display:flex;justify-content:space-between;opacity:.85;margin:.25rem 2px 0 2px;">
      <small><b>Contribution room used</b></small>
      <small><b>{room_used_pct:.1f}%</b></small>
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3 = st.columns(3)
m1.metric("This year's limit", f"${current_year_limit(current_year):,.0f}")
m2.metric("Carryover into this year", f"${carryover_prior:,.0f}")
m3.metric("Room left (est.)", f"${room_left:,.0f}")

# =========================
# --- Add a Transaction ---
# =========================
st.markdown("### ➕ Add a Transaction")

with st.form("txn_form", clear_on_submit=False):
    c1, c2 = st.columns([1, 1])
    with c1:
        t_date = st.date_input("Date", value=date.today(), min_value=date(2009, 1, 1), max_value=date.today(), key="t_date")
    with c2:
        st.session_state.type_input = st.radio("Type", ["deposit", "withdrawal"], index=(0 if st.session_state.type_input == "deposit" else 1), horizontal=True, key="t_type")

    t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=float(st.session_state.amount_input), key="t_amount")
    # Add button with emoji burst holder
    add_col, burst_col = st.columns([0.12, 0.88])
    with add_col:
        submitted = st.form_submit_button("Add", type="primary", use_container_width=True)
    with burst_col:
        # Reserved span next to the button for emoji bursts
        st.markdown('<div id="burst-anchor" class="burst-wrap"></div>', unsafe_allow_html=True)

    if submitted:
        df_all = df_from_txns(st.session_state.transactions)
        if t_amount <= 0:
            st.error("Please enter an amount greater than $0.")
        else:
            if st.session_state.type_input == "deposit":
                deposit_year = t_date.year
                deposits_that_year = current_year_deposits(df_all, deposit_year)
                year_limit = current_year_limit(deposit_year)

                # For current year, allow carryover + limit – deposits YTD
                if deposit_year == current_year:
                    allowed_room = (carryover_prior + year_limit) - deposits_that_year
                else:
                    # conservative for past years (limit of that year minus deposits in that year)
                    allowed_room = year_limit - deposits_that_year

                if t_amount > max(0.0, allowed_room):
                    st.error(f"❌ Deposit exceeds available contribution room for {deposit_year}. Available: ${max(0.0, allowed_room):,.0f}.")
                else:
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "deposit",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0
                    st.session_state.just_added = ("deposit", float(t_amount))
                    # queue emoji(s)
                    st.session_state.anim_stack.append("💰")
                    st.session_state.anim_stack.append("💵")
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
                    st.session_state.just_added = ("withdrawal", float(t_amount))
                    # queue emoji(s)
                    st.session_state.anim_stack.append("💸")
                    st.session_state.anim_stack.append("🏃‍♂️")

# Render emoji bursts (next to Add) every run if we have items
if st.session_state.anim_stack:
    # render the top 2 for a tight, Instagram-heart vibe
    seq = st.session_state.anim_stack[:2]
    html = "".join([f'<span class="burst{" delay" if i else ""}">{e}</span>' for i, e in enumerate(seq)])
    st.markdown(f"""<script>
      const el = window.parent.document.querySelector('#burst-anchor');
      if (el) {{ el.innerHTML = `{html}`; }}
    </script>""", unsafe_allow_html=True)
    # pop what we showed
    st.session_state.anim_stack = st.session_state.anim_stack[2:]

# =========================
# --- Logged Transactions + Clear ---
# =========================
st.markdown("### 🧾 Logged transactions")

top_line = st.container()
with top_line:
    left, right = st.columns([1, 0.06])
    with left:
        st.caption("Most recent first. Delete individual rows with the **✖️** buttons.")
    with right:
        if not st.session_state.confirming_clear:
            if st.button("💣", help="Clear all transactions", key="bomb"):
                st.session_state.confirming_clear = True
        else:
            st.warning("Delete all transactions? This cannot be undone.")
            c_yes, c_no = st.columns([1, 1])
            with c_yes:
                if st.button("Yes, delete all", type="primary", key="yes_del_all"):
                    st.session_state.transactions = []
                    st.session_state.next_id = 1
                    st.session_state.confirming_clear = False
            with c_no:
                if st.button("No, keep them", key="no_del_all"):
                    st.session_state.confirming_clear = False

with st.expander("Show / hide transaction list", expanded=st.session_state.log_open):
    df_all = df_from_txns(st.session_state.transactions)
    if df_all.empty:
        st.info("No transactions yet. Add your first deposit to get started.")
    else:
        df_log = df_all.sort_values(by="date", ascending=False).copy()
        # Compact per-row card
        for _, row in df_log.iterrows():
            line = st.container(border=True)
            with line:
                c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.4])
                c1.write(f"**{row['date'].strftime('%Y-%m-%d')}**")
                if row["type"] == "deposit":
                    c2.markdown("<span style='color:#22c55e;'>💵 Deposit</span>", unsafe_allow_html=True)
                else:
                    c2.markdown("<span style='color:#ef4444;'>💸 Withdrawal</span>", unsafe_allow_html=True)
                c3.write(f"${row['amount']:,.2f}")
                if c4.button("✖️", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                    st.session_state.transactions = [tx for tx in st.session_state.transactions if tx["id"] != int(row["id"])]
                    # keep expander open
                    st.session_state.log_open = True

# =========================
# ------- Analytics -------
# =========================
st.subheader("📊 Monthly Summary")

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
    # Room math
    total_room_this_year = (carryover_prior + current_year_limit(current_year)) if st.session_state.ever_contributed == "Yes" else (total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1) + carryover_prior if current_year > 2009 else current_year_limit(current_year))
    monthly["net_contribution"] = monthly["deposit"]
    monthly["cumulative_contribution"] = monthly["deposit"].cumsum()
    monthly["room_left"] = (total_room_this_year - monthly["cumulative_contribution"]).clip(lower=0.0)

    # Chart (Altair) with intuitive colors
    import altair as alt
    base = pd.melt(
        monthly[["month", "deposit", "withdrawal"]],
        id_vars="month", var_name="type", value_name="amount"
    )
    color_scale = alt.Scale(
        domain=["deposit", "withdrawal"],
        range=["#22c55e", "#ef4444"]
    )
    chart = (
        alt.Chart(base)
        .mark_bar()
        .encode(
            x=alt.X("month:N", title="Month"),
            y=alt.Y("amount:Q", title="Amount ($)"),
            color=alt.Color("type:N", scale=color_scale, title="Type"),
            tooltip=["month", "type", alt.Tooltip("amount:Q", format="$,.2f")]
        )
        .properties(height=280)
    )
    st.altair_chart(chart, use_container_width=True)

    # Table (collapsible)
    with st.expander("Show table", expanded=st.session_state.show_table):
        if supports_hide_index():
            st.dataframe(
                monthly,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.dataframe(
                monthly.style.hide(axis="index").format({
                    "deposit": "${:,.2f}",
                    "withdrawal": "${:,.2f}",
                    "net_contribution": "${:,.2f}",
                    "cumulative_contribution": "${:,.2f}",
                    "room_left": "${:,.2f}",
                }),
                use_container_width=True
            )

# =========================
# ---- Full annual limits (neat, no index) ----
# =========================
st.markdown("### Full annual TFSA limits")
limits_df = pd.DataFrame(sorted(LIMITS_BY_YEAR.items()), columns=["Year", "Limit ($)"])
limits_df["Limit ($)"] = limits_df["Limit ($)"].map(lambda x: f"${x:,.0f}")
if supports_hide_index():
    st.dataframe(limits_df, use_container_width=True, hide_index=True)
else:
    st.dataframe(limits_df.style.hide(axis="index"), use_container_width=True)
