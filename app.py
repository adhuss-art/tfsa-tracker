import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, date
import streamlit.components.v1 as components

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
        "first_deposit_banner_shown": False,
        "_flash_money": None,       # {"kind": "deposit"|"withdrawal", "text": "..."}
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
        return pd.DataFrame(columns=["id", "date", "type", "amount", "year", "month_ts", "month"])
    df = pd.DataFrame(txns)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["year"] = df["date"].dt.year
    df["month_ts"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["month"] = df["month_ts"].dt.strftime("%Y-%m")
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
# Floating "money" badge (Option B)
# -------------------------
def trigger_money_badge(kind: str, text: str):
    """kind='deposit' or 'withdrawal'"""
    st.session_state["_flash_money"] = {"kind": kind, "text": text}
    st.rerun()

def show_money_badge_if_any():
    data = st.session_state.get("_flash_money")
    if not data:
        return
    kind = data.get("kind", "deposit")
    text = data.get("text", "Updated")
    # colors
    bg = "#16a34a" if kind == "deposit" else "#ef4444"  # green / red
    emoji = "💵" if kind == "deposit" else "🔻"
    components.html(
        f"""
        <div id="money-badge" style="
            position: fixed; right: 18px; bottom: 18px; z-index: 9999;
            background: {bg}; color: white; padding: 10px 14px;
            border-radius: 999px; font: 600 14px/1.2 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto;
            box-shadow: 0 8px 24px rgba(0,0,0,0.18); opacity: 0; transform: translateY(10px);
            transition: all .25s ease; display: inline-flex; align-items: center; gap: 8px;
        ">
          <span style="font-size:18px">{emoji}</span><span>{text}</span>
        </div>
        <script>
          const badge = document.getElementById('money-badge');
          setTimeout(()=>{{ badge.style.opacity=1; badge.style.transform='translateY(0)'; }}, 10);
          setTimeout(()=>{{ badge.style.opacity=0; badge.style.transform='translateY(10px)'; }}, 2300);
          setTimeout(()=>{{ badge.remove(); }}, 2700);
        </script>
        """,
        height=0
    )
    st.session_state["_flash_money"] = None

# -------------------------
# Smart usage bar (fills to limit, changes color, glow near full)
# -------------------------
def usage_bar(used: float, total: float, label: str = "Room used"):
    pct = 0.0 if total <= 0 else min(100.0, max(0.0, used / total * 100.0))
    # Color logic: 0-60 green, 60-85 amber, 85-100 red with glow
    if pct < 60:
        color, glow = "#16a34a", "none"         # green
    elif pct < 85:
        color, glow = "#f59e0b", "none"         # amber
    else:
        color, glow = "#ef4444", "0 0 16px rgba(239,68,68,0.45)"  # red + glow

    components.html(
        f"""
        <div style="margin: 6px 0 16px 0;">
          <div style="display:flex; justify-content:space-between; font: 500 13px/1.3 ui-sans-serif,system-ui; color:#475569;">
            <span>{label}</span>
            <span>{pct:.1f}%</span>
          </div>
          <div style="height:12px; background:#e5e7eb; border-radius:999px; overflow:hidden;">
            <div style="height:100%; width:{pct}%; background:{color};
                        box-shadow:{glow}; transition: width .25s ease; border-radius:999px;"></div>
          </div>
        </div>
        """,
        height=40
    )

# =========================
# --------- UI ------------
# =========================
st.title("TFSA Contribution Tracker")
show_money_badge_if_any()

current_year = datetime.now().year

# --- Estimator Header / Explainer ---
with st.expander("ℹ️ How TFSA contribution room works", expanded=False):
    # Build the clean “selected limits” line so it doesn’t space weirdly in markdown
    selected = [2009, 2013, 2015, 2019, 2023, 2024, 2025]
    pieces = [f"{y} ${LIMITS_BY_YEAR[y]:,}" for y in selected if y in LIMITS_BY_YEAR]
    nice_line = " • ".join(pieces)

    st.markdown(
        f"""
**Key rules (simplified):**
- Your TFSA room starts accruing from the year you turn **18** (or **2009**, whichever is later).
- **Deposits** reduce this year’s available room.
- **Withdrawals** do **not** give room back until **January 1 of the next year**.
- CRA is the source of truth. This app is an educational helper; confirm with CRA if you’re unsure.

**Annual limits by year (selected):** {nice_line}
        """
    )

# --- Estimator / Input ---
st.subheader("📅 Contribution Room Estimator")

colA, colB = st.columns([1, 1])
with colA:
    dob = st.date_input("Your date of birth", value=date(1990, 1, 1), min_value=date(1900, 1, 1), max_value=date.today())
with colB:
    st.session_state.ever_contributed = st.radio(
        "Have you ever contributed to a TFSA before?", ["No", "Yes"],
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

# --- Top Metrics & Usage Bar ---
df_all = df_from_txns(st.session_state.transactions)
deposits_ytd = current_year_deposits(df_all, current_year)
room_used_pct = (deposits_ytd / estimated_room_total * 100.0) if estimated_room_total > 0 else 0.0
room_left = max(0.0, estimated_room_total - deposits_ytd)

# Nice custom usage bar with color & glow
usage_bar(used=deposits_ytd, total=estimated_room_total, label="Contribution room used")

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
        st.session_state.type_input = st.radio(
            "Type", ["deposit", "withdrawal"],
            index=(0 if st.session_state.type_input == "deposit" else 1),
            horizontal=True
        )

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
                    total_allowed_this_year = carryover_prior + year_limit
                    allowed_room = max(0.0, total_allowed_this_year - deposits_that_year)
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

                    # first deposit celebration (balloons via badge text)
                    msg = "💵 Deposit added"
                    if not st.session_state.first_deposit_banner_shown and \
                       len([t for t in st.session_state.transactions if t["type"] == "deposit"]) == 1:
                        st.session_state.first_deposit_banner_shown = True
                        msg = "🎉 First deposit! Nice."

                    trigger_money_badge("deposit", msg)

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
                    trigger_money_badge("withdrawal", "🔻 Withdrawal added")

# =========================
# --- Logged Transactions ---
# =========================
with st.expander(f"🧾 Logged transactions ({len(st.session_state.transactions)})", expanded=False):
    df_all = df_from_txns(st.session_state.transactions)
    if df_all.empty:
        st.info("No transactions yet. Add your first deposit to get started.")
    else:
        df_log = df_all.sort_values(by="date", ascending=False).copy()
        for _, row in df_log.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.5])
                c1.write(f"**{row['date'].strftime('%Y-%m-%d')}**")
                if row["type"] == "deposit":
                    c2.markdown("<span style='color:#16a34a;'>💵 Deposit</span>", unsafe_allow_html=True)
                else:
                    c2.markdown("<span style='color:#ef4444;'>🔻 Withdrawal</span>", unsafe_allow_html=True)
                c3.write(f"${row['amount']:,.2f}")
                if c4.button("✖️", key=f"del_{int(row['id'])}", help="Delete this transaction"):
                    st.session_state.transactions = [tx for tx in st.session_state.transactions if tx["id"] != int(row["id"])]
                    trigger_money_badge("withdrawal", "🗑️ Transaction deleted")

        # Clear-all with confirmation
        st.write("---")
        if not st.session_state.confirming_clear:
            if st.button("💣 Clear all transactions", type="secondary"):
                st.session_state.confirming_clear = True
                st.rerun()
        else:
            st.warning("Are you sure you want to delete **all** transactions? This cannot be undone.")
            c_yes, c_no = st.columns([1, 1])
            with c_yes:
                if st.button("Yes, delete all", type="primary"):
                    st.session_state.transactions = []
                    st.session_state.confirming_clear = False
                    trigger_money_badge("withdrawal", "⚠️ All transactions cleared")
            with c_no:
                if st.button("No, keep them"):
                    st.session_state.confirming_clear = False
                    st.rerun()

# =========================
# ------- Analytics -------
# =========================
st.subheader("📊 Monthly Summary & Charts")

df_all = df_from_txns(st.session_state.transactions)
if df_all.empty:
    st.info("No data yet. Add a transaction to see summary and charts.")
else:
    # --- Build a full month grid for THIS YEAR so charts always show ---
    start_month = pd.Timestamp(year=current_year, month=1, day=1)
    end_month = pd.Timestamp(year=current_year, month=12, day=1)
    month_grid = pd.DataFrame({"month_ts": pd.date_range(start=start_month, end=end_month, freq="MS")})

    df_curr = df_all[df_all["year"] == current_year].copy()
    monthly = (
        df_curr
        .pivot_table(index="month_ts", columns="type", values="amount", aggfunc="sum", fill_value=0.0)
        .reset_index()
    )

    # Ensure columns present
    for col in ["deposit", "withdrawal"]:
        if col not in monthly.columns:
            monthly[col] = 0.0

    # Merge onto full grid, so months w/ no txns appear as zeros
    monthly = month_grid.merge(monthly, on="month_ts", how="left").fillna(0.0)
    monthly = monthly.sort_values("month_ts")
    monthly["month_label"] = monthly["month_ts"].dt.strftime("%b %Y")

    # Room math for the year (withdrawals don't restore in-year)
    total_room_this_year = carryover_prior + current_year_limit(current_year)
    monthly["net_contribution"] = monthly["deposit"]
    monthly["cumulative_contribution"] = monthly["net_contribution"].cumsum()
    monthly["room_left"] = (total_room_this_year - monthly["cumulative_contribution"]).clip(lower=0.0)

    # ---- Summary table (pre-formatted strings) ----
    table_cols = ["month_label", "deposit", "withdrawal", "net_contribution", "cumulative_contribution", "room_left"]
    table_to_show = monthly[table_cols].rename(columns={"month_label": "Month"}).copy()
    for c in ["deposit", "withdrawal", "net_contribution", "cumulative_contribution", "room_left"]:
        table_to_show[c] = table_to_show[c].map(lambda x: f"${x:,.2f}")
    st.dataframe(table_to_show, use_container_width=True)

    # ---- Bars (green = deposits, red = withdrawals) ----
    bar_df = monthly[["month_ts", "deposit", "withdrawal"]].melt(
        id_vars="month_ts", value_vars=["deposit", "withdrawal"],
        var_name="type", value_name="amount"
    )
    bars = (
        alt.Chart(bar_df, title="Deposits & Withdrawals by Month")
        .mark_bar()
        .encode(
            x=alt.X("month_ts:T", title="Month"),
            y=alt.Y("amount:Q", title="Amount ($)", stack=None),
            color=alt.Color("type:N", title="Type",
                            scale=alt.Scale(domain=["deposit", "withdrawal"], range=["#16a34a", "#ef4444"])),
            tooltip=[alt.Tooltip("month_ts:T", title="Month"),
                     alt.Tooltip("type:N", title="Type"),
                     alt.Tooltip("amount:Q", title="Amount", format="$.2f")]
        )
        .properties(height=280)
        .interactive()
    )
    st.altair_chart(bars, use_container_width=True)

    # ---- Contribution Room Left line (now always shows due to month grid) ----
    line = (
        alt.Chart(monthly, title="Contribution Room Left (This Year)")
        .mark_line(point=True)
        .encode(
            x=alt.X("month_ts:T", title="Month"),
            y=alt.Y("room_left:Q", title="Room Left ($)"),
            tooltip=[alt.Tooltip("month_ts:T", title="Month"),
                     alt.Tooltip("room_left:Q", title="Room Left", format="$.0f")]
        )
        .properties(height=280)
        .interactive()
    )
    shaded = alt.Chart(monthly).mark_area(opacity=0.12).encode(x="month_ts:T", y="room_left:Q")
    st.altair_chart(shaded + line, use_container_width=True)

# =========================
# Tiny CSS polish
# =========================
st.markdown("""
<style>
.block-container { padding-top: 1.25rem; padding-bottom: 2.25rem; }
[data-testid="stMetricLabel"] { color: #6b7280; }
</style>
""", unsafe_allow_html=True)
