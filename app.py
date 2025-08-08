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
      /* Tighter top spacing & general polish */
      .block-container { padding-top: .55rem !important; padding-bottom: 3rem !important; }
      h1, h2, h3 { letter-spacing: .2px; }
      .small-muted { opacity:.8; font-size:.9rem; }

      /* Annual limit "chips" */
      .chip {
        display:inline-block; padding:.18rem .55rem; border-radius:12px;
        background:rgba(255,255,255,.06); margin:.12rem .25rem .12rem 0;
        border:1px solid rgba(255,255,255,.08); font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }

      /* Contribution room bar */
      .room-wrap { margin: .15rem 0 .5rem 0; }
      .room-label { display:flex; align-items:center; justify-content:space-between; margin-bottom:.22rem; }
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

      /* Transaction FX (emoji + bubble) */
      .fxwrap {
        position: fixed; z-index: 1000; right: 28px;
        display: flex; align-items: center; gap: .5rem;
        opacity: 0; transform: translateY(10px);
        animation: fxIn VAR_DURs ease-out forwards;
        pointer-events: none;
      }
      .fxemoji {
        font-size: 2.15rem; line-height: 1;
        text-shadow: 0 0 8px rgba(255,255,255,.08);
      }
      .fxbubble {
        font-size: .92rem; padding: .35rem .55rem; border-radius: 10px;
        border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.06);
        font-variant-numeric: tabular-nums; white-space: nowrap;
      }
      @keyframes fxIn {
        0% { opacity:0; transform: translateY(12px); }
        10% { opacity:1; }
        80% { opacity:1; }
        100% { opacity:0; transform: translateY(-44px); }
      }

      /* Bomb button look */
      .bomb { border-radius: 12px; padding:.45rem .7rem;
              background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08); }
      .bomb:hover { background: rgba(255,255,255,.09); cursor:pointer; }

      /* Streamlit dark text fix */
      .stMarkdown, .stMarkdown p, .stMarkdown span { color: inherit !important; }

      /* Tighter expanders a bit */
      .stExpander > div > div { padding-top: .2rem; padding-bottom: .55rem; }
    </style>
    """.replace("VAR_DUR", "2.2"),
    unsafe_allow_html=True,
)

# -------------------------
# Back-compat helper
# -------------------------
def columns_va(spec, vertical_alignment="center"):
    """Use vertical_alignment when available; otherwise fall back."""
    try:
        return st.columns(spec, vertical_alignment=vertical_alignment)
    except TypeError:
        return st.columns(spec)

# -------------------------
# Session Defaults
# -------------------------
def init_state():
    defaults = {
        "transactions": [],           # list of {id, date, type, amount}
        "next_id": 1,                 # autoincrement id
        "confirming_clear": False,    # for the clear-all confirmation UI
        "ever_contributed": "No",     # estimator radio
        "carryover_manual": 0.0,      # manual carryover if Yes
        "amount_input": 0.0,          # form amount
        "type_input": "deposit",      # form type
        "prefs": {"emoji_fx": True, "fx_duration": 2.2},  # effects settings
        "fx_queue": [],               # stacked floating notifications
        "clear_click_guard": False,   # prevent double click on confirm
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
init_state()

# Sync CSS animation duration to slider value on every run
dur_css = float(st.session_state.prefs.get("fx_duration", 2.2))
st.markdown(f"<style>.fxwrap {{ animation-duration: {dur_css:.2f}s !important; }}</style>", unsafe_allow_html=True)

def queue_fx(emoji: str, text: str, tone: str = "neutral"):
    """Queue a floating emoji + bubble message."""
    if not st.session_state.prefs.get("emoji_fx", True):
        return
    # tone colors
    if tone == "pos":
        border = "rgba(34,197,94,.35)"   # green
        bg = "rgba(34,197,94,.12)"
        color = "#22c55e"
    elif tone == "neg":
        border = "rgba(239,68,68,.35)"   # red
        bg = "rgba(239,68,68,.12)"
        color = "#ef4444"
    else:
        border = "rgba(255,255,255,.25)"
        bg = "rgba(255,255,255,.08)"
        color = "inherit"
    st.session_state.fx_queue.append({
        "emoji": emoji,
        "text": text,
        "style": f"color:{color};background:{bg};border:1px solid {border};",
        "ts": time.time()
    })

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
    deposits = float(df.loc[df["type"] == "deposit", "amount"].sum())
    withdrawals = float(df.loc[df["type"] == "withdrawal", "amount"].sum())
    return deposits - withdrawals

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
    st.markdown("**Annual limits (highlights):**", unsafe_allow_html=True)
    chip_years = [2009, 2013, 2015, 2019, 2023, 2024, 2025]
    chip_html = " ".join(f"<span class='chip'>{y} ${LIMITS_BY_YEAR[y]:,}</span>" for y in chip_years)
    st.markdown(chip_html, unsafe_allow_html=True)

# --- Settings (collapsed; clearly a settings panel) ---
with st.expander("🎛 Display & Effects (Settings)", expanded=False):
    st.caption("Toggle the floating emoji notifications and tune their duration.")
    left, right = st.columns(2)
    with left:
        st.session_state.prefs["emoji_fx"] = st.checkbox(
            "Show emoji notifications when adding transactions",
            value=st.session_state.prefs.get("emoji_fx", True),
        )
    with right:
        new_dur = st.slider(
            "Notification duration (seconds)",
            0.8, 4.0, float(st.session_state.prefs.get("fx_duration", 2.2)), 0.1
        )
        if new_dur != st.session_state.prefs.get("fx_duration", 2.2):
            st.session_state.prefs["fx_duration"] = float(new_dur)
            # CSS duration is refreshed at top each run

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

# A clean “this year” breakdown always visible
def _status_color(p):
    if p < 60: return "#22c55e"   # green
    if p < 80: return "#eab308"   # yellow
    if p < 95: return "#f97316"   # orange
    return "#ef4444"              # red

total_room_this_year = (
    (carryover_prior + current_year_limit(current_year))
    if st.session_state.ever_contributed == "Yes"
    else (
        total_room_from_inception(dob, current_year) - total_room_from_inception(dob, current_year - 1) + carryover_prior
        if current_year > 2009 else current_year_limit(current_year)
    )
)
pct_used = (deposits_ytd / total_room_this_year * 100.0) if total_room_this_year > 0 else 0.0
chip_color = _status_color(pct_used)

with st.container(border=True):
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.35rem;">
          <div style="font-weight:700;">This year’s room breakdown</div>
          <div style="padding:.15rem .5rem;border-radius:999px;background:{chip_color}26;border:1px solid {chip_color}44;color:{chip_color};font-weight:700;">
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
                # Validate room for the deposit's year
                deposit_year = t_date.year
                deposits_that_year = current_year_deposits(df_all, deposit_year)
                year_limit = current_year_limit(deposit_year)
                if deposit_year == current_year:
                    base_carry = carryover_prior if st.session_state.ever_contributed == "No" else st.session_state.carryover_manual
                    allowed_room = max(0.0, base_carry + year_limit - deposits_that_year)
                else:
                    allowed_room = max(0.0, year_limit - deposits_that_year)

                if t_amount > allowed_room:
                    st.error(f"❌ Deposit exceeds available contribution room for {deposit_year}. Available: ${allowed_room:,.0f}.")
                else:
                    # Add deposit
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "deposit",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0

                    # Build updated status (for current year)
                    df2 = df_from_txns(st.session_state.transactions)
                    dep2 = current_year_deposits(df2, current_year)
                    room_left2 = max(0.0, estimated_room_total - dep2)
                    pct2 = (dep2 / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
                    queue_fx("💰", f"+${t_amount:,.0f} • Used {pct2:.1f}% • Left ${room_left2:,.0f}", tone="pos")

                    st.stop()
            else:
                # Validate withdrawal vs balance
                bal = lifetime_balance(df_all)
                if t_amount > bal:
                    st.error(f"❌ Withdrawal exceeds available balance. Current balance: ${bal:,.0f}.")
                else:
                    # Add withdrawal
                    st.session_state.transactions.append({
                        "id": st.session_state.next_id,
                        "date": t_date.strftime("%Y-%m-%d"),
                        "type": "withdrawal",
                        "amount": float(t_amount)
                    })
                    st.session_state.next_id += 1
                    st.session_state.amount_input = 0.0

                    # Updated balance
                    df2 = df_from_txns(st.session_state.transactions)
                    bal2 = lifetime_balance(df2)
                    queue_fx("💸", f"-${t_amount:,.0f} • Balance ${bal2:,.0f}", tone="neg")

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

    # Data table collapsible under the chart
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
dur = float(st.session_state.prefs.get("fx_duration", 2.2))
# keep only live notifications
st.session_state.fx_queue = [fx for fx in st.session_state.fx_queue if now - fx["ts"] < dur]
# render last three stacked (top offsets so they don't jump)
for i, fx in enumerate(st.session_state.fx_queue[-3:]):
    top_px = 90 + (i * 22)
    # wrapper with emoji + bubble
    st.markdown(
        f"""
        <div class="fxwrap" style="top:{top_px}px;">
          <div class="fxemoji">{fx['emoji']}</div>
          <div class="fxbubble" style="{fx['style']}">{fx['text']}</div>
        </div>
        """,
        unsafe_allow_html=True
    )
