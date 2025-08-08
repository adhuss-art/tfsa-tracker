import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
import altair as alt

# =========================
# ---- App Configuration --
# =========================
st.set_page_config(page_title="TFSA Tracker", page_icon="🧮", layout="wide")

# =========================
# ----- Global Styles -----
# =========================
st.markdown(
    """
    <style>
      /* Tighter top spacing */
      .block-container { padding-top: .6rem !important; padding-bottom: 3rem !important; }

      h1, h2, h3 { letter-spacing: .2px; }

      .small-muted { opacity:.8; font-size:.9rem; }

      /* Chips for annual limits */
      .chip {
        display:inline-block; padding:.18rem .55rem; border-radius:12px;
        background:rgba(255,255,255,.06); margin:.12rem .25rem .12rem 0;
        border:1px solid rgba(255,255,255,.08); font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }

      /* Contribution room bar */
      .room-wrap { margin: .25rem 0 .6rem 0; }
      .room-label { display:flex; align-items:center; justify-content:space-between; margin-bottom:.25rem; }
      .room-bar {
        position: relative; width: 100%; height: 14px; border-radius: 999px;
        background: rgba(255,255,255,.08); overflow:hidden;
      }
      .room-fill {
        height:100%; width:0%;
        border-radius: 999px;
        transition: width .45s ease;
        box-shadow: none;
      }
      .room-fill.glow { box-shadow: 0 0 10px rgba(255,80,80,.55), 0 0 20px rgba(255,80,80,.35); }

      /* Transaction FX (emoji) */
      .fx {
        position: fixed; z-index: 1000; font-size: 2.2rem; pointer-events: none;
        opacity: 0; transform: translateY(12px) scale(.92);
        animation: floatUp VAR_DURs ease-out forwards;
        text-shadow: 0 0 8px rgba(255,255,255,.08);
      }
      @keyframes floatUp {
        0% { opacity:0; transform: translateY(14px) scale(.9); }
        10% { opacity:1; }
        80% { opacity:1; }
        100% { opacity:0; transform: translateY(-48px) scale(1); }
      }

      /* Bomb & header row */
      .right-action { display:flex; justify-content:flex-end; }
      .bomb { border-radius: 12px; padding:.45rem .7rem; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08); }
      .bomb:hover { background: rgba(255,255,255,.09); cursor:pointer; }

      /* Slightly tighter expanders */
      .stExpander > div > div { padding-top: .2rem; padding-bottom: .55rem; }

      /* Prevent black-on-dark issues */
      .stMarkdown, .stMarkdown p, .stMarkdown span { color: inherit !important; }
    </style>
    """.replace("VAR_DUR", "1.8"),
    unsafe_allow_html=True,
)

# -------------------------
# Compat wrappers / helpers
# -------------------------
def columns_va(spec, vertical_alignment="center"):
    """Back-compat for Streamlit versions without vertical_alignment."""
    try:
        return st.columns(spec, vertical_alignment=vertical_alignment)
    except TypeError:
        return st.columns(spec)

# -------------------------
# Session Defaults
# -------------------------
def init_state():
    defaults = {
        "transactions": [],           # list of dicts with id, date, type, amount
        "next_id": 1,                 # autoincrement id
        "confirming_clear": False,    # for the clear-all confirmation UI
        "ever_contributed": "No",     # estimator radio
        "carryover_manual": 0.0,      # manual carryover if Yes
        "amount_input": 0.0,          # form amount
        "type_input": "deposit",      # form type
        "prefs": {"emoji_fx": True, "fx_duration": 1.8},  # effects settings
        "fx_queue": [],               # stacked floating emoji
        "clear_click_guard": False,   # prevent double-submits on clear-all
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
init_state()

# Sync CSS animation duration to slider value on every run
dur_css = float(st.session_state.prefs.get("fx_duration", 1.8))
st.markdown(f"<style>.fx {{ animation-duration: {dur_css:.2f}s !important; }}</style>", unsafe_allow_html=True)

def trigger_fx(emoji: str):
    """Queue a floating emoji effect."""
    if st.session_state.prefs.get("emoji_fx", True):
        st.session_state.fx_queue.append({"emoji": emoji, "ts": time.time()})

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
    st.markdown("**Annual limits (highlights):**", unsafe_allow_html=True)
    chip_years = [2009, 2013, 2015, 2019, 2023, 2024, 2025]
    chip_html = " ".join(f"<span class='chip'>{y} ${LIMITS_BY_YEAR[y]:,}</span>" for y in chip_years)
    st.markdown(chip_html, unsafe_allow_html=True)

# --- Settings / Effects (collapsed by default) ---
with st.expander("⚙️ Settings (effects panel)", expanded=False):
    st.caption("Toggle the floating emoji effects and tweak their duration.")
    left, right = st.columns(2)
    with left:
        st.session_state.prefs["emoji_fx"] = st.checkbox(
            "Show emoji effects on transactions",
            value=st.session_state.prefs.get("emoji_fx", True),
        )
    with right:
        new_dur = st.slider(
            "Emoji effect duration (seconds)",
            0.8, 3.0, float(st.session_state.prefs.get("fx_duration", 1.8)), 0.1
        )
        if new_dur != st.session_state.prefs.get("fx_duration", 1.8):
            st.session_state.prefs["fx_duration"] = float(new_dur)

# --- Estimator / Input ---
st.subheader("📅 Contribution Room Estimator")

colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio(
        "Have you ever contributed to a TFSA before?",
        ["No", "Yes"], index=(0 if st.session_state.ever_contributed == "No" else 1)
    )

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

# --- Top Metrics & Contribution Bar ---
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

pct = room_used_pct
if pct < 60: color = "#22c55e"     # green
elif pct < 80: color = "#eab308"   # yellow
elif pct < 95: color = "#f97316"   # orange
else: color = "#ef4444"            # red
glow_class = "glow" if pct >= 95 else ""

st.markdown(
    f"""
    <div class="room-wrap">
      <div class="room-label">
        <div style="font-weight:600;">Contribution room used</div>
        <div style="font-weight:600;">{pct:.1f}%</div>
      </div>
      <div class="room-bar">
        <div class="room-fill {glow_class}" style="width:{min(100,pct):.1f}%; background:{color};"></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

m1, m2, m3 = st.columns(3)
m1.metric("This year's limit", f"${current_year_limit(current_year):,.0f}")
m2.metric("Carryover into this year", f"${carryover_prior:,.0f}")
m3.metric("Room left (est.)", f"${room_left:,.0f}")

# === Always-on room summary panel ===
def _status_color(p):
    if p < 60: return "#22c55e"   # green
    if p < 80: return "#eab308"   # yellow
    if p < 95: return "#f97316"   # orange
    return "#ef4444"              # red

# Total room this year (consistent with estimator logic)
total_room_this_year = (
    (carryover_prior + current_year_limit(current_year))
    if st.session_state.ever_contributed == "Yes"
    else (
        total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1) + carryover_prior
        if current_year > 2009 else current_year_limit(current_year)
    )
)
pct_used = (deposits_ytd / total_room_this_year * 100.0) if total_room_this_year > 0 else 0.0
colchip = _status_color(pct_used)

with st.container(border=True):
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.35rem;">
          <div style="font-weight:700;">This year’s room breakdown</div>
          <div style="padding:.15rem .5rem;border-radius:999px;background:{colchip}26;border:1px solid {colchip}44;color:{colchip};font-weight:700;">
            Used {pct_used:.1f}% • Left ${room_left:,.0f}
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    c1s, c2s, c3s = st.columns(3)
    c1s.metric("Total room (carryover + limit)", f"${total_room_this_year:,.0f}")
    c2s.metric("Deposits YTD", f"${deposits_ytd:,.0f}")
    c3s.metric("Remaining (est.)", f"${room_left:,.0f}")

    with st.expander("What if I deposit an amount today?", expanded=False):
        preview_amt = st.number_input("Preview deposit amount", min_value=0.0, step=100.0, value=0.0, key="preview_deposit")
        if preview_amt > 0:
            remaining_now = max(0.0, total_room_this_year - deposits_ytd)
            if preview_amt > remaining_now:
                st.error(f"That would exceed your estimated remaining room by ${preview_amt - remaining_now:,.0f}.")
            else:
                new_used = deposits_ytd + preview_amt
                new_pct = (new_used / total_room_this_year * 100.0) if total_room_this_year > 0 else 0.0
                new_left = max(0.0, total_room_this_year - new_used)
                new_col = _status_color(new_pct)
                st.markdown(
                    f"<div style='margin-top:.25rem;padding:.4rem .6rem;border-radius:.5rem;background:{new_col}1A;border:1px solid {new_col}55;'>"
                    f"After a ${preview_amt:,.0f} deposit: <b>Used {new_pct:.1f}%</b> • <b>Left ${new_left:,.0f}</b>"
                    f"</div>",
                    unsafe_allow_html=True
                )

# =========================
# --- Add a Transaction ---
# =========================
st.subheader("➕ Add a Transaction")

with st.form("txn_form", clear_on_submit=False):
    c1, c2 = st.columns([1, 1])
    with c1:
        t_date = st.date_input("Date", value=date.today(), min_value=date(2009, 1, 1), max_value=date.today(), key="form_date")
    with c2:
        st.session_state.type_input = st.radio(
            "Type", ["deposit", "withdrawal"],
            index=(0 if st.session_state.type_input == "deposit" else 1),
            horizontal=True, key="form_type"
        )
    t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=float(st.session_state.amount_input), key="form_amount")
    submitted = st.form_submit_button("Add", type="primary", use_container_width=True)

    if submitted:
        df_all = df_from_txns(st.session_state.transactions)
        if t_amount <= 0:
            st.error("Please enter an amount greater than $0.")
        else:
            if st.session_state.type_input == "deposit":
                # Deposit can't exceed available room for the deposit's calendar year
                deposit_year = t_date.year
                deposits_that_year = current_year_deposits(df_all, deposit_year)
                year_limit = current_year_limit(deposit_year)
                if deposit_year == current_year:
                    base_carry = carryover_prior if st.session_state.ever_contributed == "No" else st.session_state.carryover_manual
                    allowed_room = max(0.0, base_carry + year_limit - deposits_that_year)
                else:
                    # For past years, conservative: only that year's limit
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
                    trigger_fx("💰")  # money bag for deposit
                    st.stop()
            else:
                # Withdrawal can't exceed balance
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
                    trigger_fx("💸")  # flying money for withdrawal
                    st.stop()

# =========================
# --- Logged Transactions ---
# =========================
count = len(st.session_state.transactions)
hdr_left, hdr_right = columns_va([0.82, 0.18])
with hdr_left:
    st.subheader(f"🧾 Logged transactions ({count})")
    st.caption("Most recent first. Delete individual rows with the **✖️** buttons.")
with hdr_right:
    # Bomb + single-click confirm flow stays visible even if list is collapsed
    if not st.session_state.confirming_clear:
        if st.button("💣", help="Clear all transactions", use_container_width=True, key="bomb_btn"):
            st.session_state.confirming_clear = True
            st.stop()  # re-render immediately to show confirm
    else:
        st.warning("Delete all transactions? This cannot be undone.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            disabled = st.session_state.get("clear_click_guard", False)
            if st.button("Yes, delete all", type="primary", use_container_width=True, disabled=disabled, key="confirm_yes"):
                st.session_state.clear_click_guard = True
                st.session_state.transactions = []
                st.session_state.confirming_clear = False
                st.session_state.clear_click_guard = False
                st.stop()
        with col_no:
            if st.button("No, keep them", use_container_width=True, key="confirm_no"):
                st.session_state.confirming_clear = False
                st.stop()

# The list itself is inside an expander so the page doesn't keep growing
with st.expander("Show / hide transactions", expanded=False):
    df_all = df_from_txns(st.session_state.transactions)
    if df_all.empty:
        st.info("No transactions yet. Add your first deposit to get started.")
    else:
        df_log = df_all.sort_values(by="date", ascending=False).copy()
        for _, row in df_log.iterrows():
            line = st.container(border=True)
            with line:
                c1, c2, c3, c4 = columns_va([1.2, 1, 1, 0.5], vertical_alignment="center")
                c1.write(f"**{row['date'].strftime('%Y-%m-%d')}**")
                if row["type"] == "deposit":
                    c2.markdown("<span style='color:#22c55e;'>💵 Deposit</span>", unsafe_allow_html=True)
                else:
                    c2.markdown("<span style='color:#ef4444;'>💸 Withdrawal</span>", unsafe_allow_html=True)
                c3.write(f"${row['amount']:,.2f}")
                if c4.button("✖️", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                    st.session_state.transactions = [
                        tx for tx in st.session_state.transactions if tx["id"] != int(row["id"])
                    ]
                    st.stop()

# =========================
# ------- Analytics -------
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

    # Chart: deposits (green) vs withdrawals (red)
    chart_df = monthly.melt(id_vars=["month"], value_vars=["deposit", "withdrawal"], var_name="type", value_name="amount")
    color_scale = alt.Scale(domain=["deposit", "withdrawal"], range=["#22c55e", "#ef4444"])
    bar = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=alt.X("month:N", title="Month"),
            y=alt.Y("amount:Q", title="Amount ($)", stack=None),
            color=alt.Color("type:N", scale=color_scale, title="Type"),
            tooltip=["month", "type", alt.Tooltip("amount:Q", format="$.2f")]
        )
        .properties(height=280)
    )
    st.altair_chart(bar, use_container_width=True)

    # The table is collapsible under the chart
    with st.expander("Show data table", expanded=False):
        st.dataframe(
            monthly.style.format({
                "deposit": "${:,.2f}",
                "withdrawal": "${:,.2f}",
            }),
            use_container_width=True
        )

# =========================
# --- Render stacked FX ---
# =========================
now = time.time()
dur = float(st.session_state.prefs.get("fx_duration", 1.8))
# keep only live effects
st.session_state.fx_queue = [fx for fx in st.session_state.fx_queue if now - fx["ts"] < dur]
# render last three, stacked so no UI jump
for i, fx in enumerate(st.session_state.fx_queue[-3:]):
    top = 90 + (i * 18)
    right = 30 + (i * 6)
    st.markdown(f"<div class='fx' style='top:{top}px;right:{right}px'>{fx['emoji']}</div>", unsafe_allow_html=True)
