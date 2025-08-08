import streamlit as st
import pandas as pd
from datetime import datetime

# ============================
# Session state init (prevents errors)
# ============================
if "transactions" not in st.session_state:
    st.session_state.transactions = []
if "amount_input" not in st.session_state:
    st.session_state.amount_input = 0.0
if "estimated_room" not in st.session_state:
    st.session_state.estimated_room = 0.0
if "confirm_clear" not in st.session_state:
    st.session_state.confirm_clear = False

# Helper: parse year from stored txn
def _year_of(txn):
    try:
        return datetime.strptime(txn["date"], "%Y-%m-%d").year
    except Exception:
        return None

current_year = datetime.now().year

st.title("TFSA Monthly Tracker with Carryover Support")

# ============================
# Contribution Room Estimator
# ============================
st.subheader("📅 Contribution Room Estimator")
c1, c2 = st.columns(2)

with c1:
    dob = st.date_input(
        "Enter your date of birth:",
        value=datetime(1990, 1, 1),
        min_value=datetime(1900, 1, 1),
        max_value=datetime.today(),
        key="dob_picker"
    )
with c2:
    ever_contributed = st.radio(
        "Have you ever contributed to a TFSA before?",
        ["Yes", "No"],
        horizontal=True,
        key="contrib_radio"
    )

age_18_year = dob.year + 18
if age_18_year > current_year:
    st.error("❌ You aren’t TFSA-eligible yet (must be 18+).")
else:
    st.info(f"You became TFSA-eligible in: {age_18_year}")

# CRA annual limits (kept local for the estimator)
LIMITS_BY_YEAR = {
    2009: 5000, 2010: 5000, 2011: 5000, 2012: 5000, 2013: 5500,
    2014: 5500, 2015: 10000, 2016: 5500, 2017: 5500, 2018: 5500,
    2019: 6000, 2020: 6000, 2021: 6000, 2022: 6000, 2023: 6500,
    2024: 7000, 2025: 7000
}

tfsa_start_year = max(age_18_year, 2009)
estimated_room_calc = 0

if ever_contributed == "No" and age_18_year <= current_year:
    for yr in range(tfsa_start_year, current_year + 1):
        estimated_room_calc += LIMITS_BY_YEAR.get(yr, 0)
    st.metric("Estimated Contribution Room", f"${estimated_room_calc:,.2f}")
    st.session_state.estimated_room = float(estimated_room_calc)
    with st.expander("ℹ️ Why is this your estimated room?", expanded=True):
        st.markdown(
            """
This estimate uses your date of birth and assumes you’ve **never contributed**.
It sums the CRA TFSA limit for each year since you turned 18 (not earlier than 2009).

🔗 [Official CRA TFSA contribution rules](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/contributions.html)
            """
        )
else:
    manual_room = st.number_input(
        "Enter your unused TFSA room (if known):",
        min_value=0,
        step=500,
        value=int(st.session_state.estimated_room) if st.session_state.estimated_room else 0,
        help="You can get this from CRA My Account. Withdrawals add room next calendar year."
    )
    st.metric("Manual Contribution Room", f"${manual_room:,.2f}")
    st.session_state.estimated_room = float(manual_room)

total_contribution_room = float(st.session_state.estimated_room)

if total_contribution_room <= 0:
    st.warning("Set your available contribution room above to start logging deposits.")

# ============================
# Add a Transaction (form)
# ============================
st.subheader("➕ Add a Transaction")

with st.form("transaction_form"):
    f1, f2, f3 = st.columns([1.2, 1, 1])
    with f1:
        t_date = st.date_input(
            "Transaction Date",
            value=datetime.today(),
            min_value=datetime(2009, 1, 1),
            max_value=datetime(current_year, 12, 31),
        )
    with f2:
        t_type = st.radio("Type", ["deposit", "withdrawal"], horizontal=True)
    with f3:
        t_amount = st.number_input(
            "Amount",
            min_value=0.0,
            step=100.0,
            value=st.session_state.amount_input,
            key="amount_input",
            help="After submit, this resets to 0."
        )
    submitted = st.form_submit_button("Add Transaction")

    if submitted and t_amount > 0:
        txns = st.session_state.transactions

        # deposits used THIS YEAR only (CRA room is a this-year thing)
        used_room_this_year = sum(
            t["amount"] for t in txns
            if t["type"] == "deposit" and _year_of(t) == current_year
        )
        remaining_room = max(0.0, total_contribution_room - used_room_this_year)

        # withdrawals allowed up to total net deposited balance (lifetime within this tracker)
        total_deposits_all = sum(t["amount"] for t in txns if t["type"] == "deposit")
        total_withdrawals_all = sum(t["amount"] for t in txns if t["type"] == "withdrawal")
        available_withdraw_balance = max(0.0, total_deposits_all - total_withdrawals_all)

        if t_type == "deposit" and t_amount > remaining_room:
            st.error(f"❌ You can’t deposit more than your remaining room (${remaining_room:,.2f}).")
        elif t_type == "withdrawal" and t_amount > available_withdraw_balance:
            st.error(f"❌ You can’t withdraw more than your deposited balance (${available_withdraw_balance:,.2f}).")
        else:
            st.session_state.transactions.append({
                "date": t_date.strftime("%Y-%m-%d"),
                "type": t_type,
                "amount": float(t_amount),
            })
            st.toast("💸 Deposit added!" if t_type == "deposit" else "🔻 Withdrawal added!")
            # Reset input and refresh so UI is clearly updated
            st.session_state.amount_input = 0.0
            st.rerun()

# ============================
# Collapsible deletable list (under Add Transaction)
# ============================
if st.session_state.transactions:
    df = pd.DataFrame(st.session_state.transactions)
    df["date"] = pd.to_datetime(df["date"])

    with st.expander("🧾 Logged Transactions", expanded=False):
        # Newest first
        for i, row in df.sort_values(by="date", ascending=False).iterrows():
            ca, cb, cc, cd = st.columns([2, 2, 2, 1])
            ca.write(row["date"].strftime("%Y-%m-%d"))
            cb.markdown(
                f"<span style='font-weight:600; color:{'#00e676' if row['type']=='deposit' else '#ff5252'}'>{row['type'].capitalize()}</span>",
                unsafe_allow_html=True
            )
            cc.markdown(f"<strong>${row['amount']:,.2f}</strong>", unsafe_allow_html=True)
            if cd.button("❌", key=f"del_{i}"):
                # delete by original index
                del st.session_state.transactions[i]
                st.rerun()

# ============================
# Summary & Graphics
# ============================
if st.session_state.transactions:
    df = pd.DataFrame(st.session_state.transactions)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M").astype(str)

    # Current-year deposits drive room usage
    deposits_this_year = df[(df["year"] == current_year) & (df["type"] == "deposit")]["amount"].sum()
    remaining_room_now = max(0.0, total_contribution_room - deposits_this_year)
    percent_used = 0.0
    if total_contribution_room > 0:
        percent_used = min(1.0, deposits_this_year / total_contribution_room)

    # Metrics
    m1, m2 = st.columns(2)
    with m1:
        st.metric("Total Deposits (This Year)", f"${deposits_this_year:,.2f}")
    with m2:
        st.metric("Remaining Room (This Year)", f"${remaining_room_now:,.2f}")

    # Progress meter + label
    st.progress(percent_used)
    st.markdown(
        f"<strong>{int(percent_used*100)}% of your contribution room used</strong>",
        unsafe_allow_html=True
    )

    # Contribution room trend (this year): room left by month (withdrawals don’t add room this year)
    df_year = df[df["year"] == current_year]
    if not df_year.empty:
        # Build monthly deposits only, then cumulative to derive room_left
        monthly_deposits = (
            df_year[df_year["type"] == "deposit"]
            .groupby("month")["amount"]
            .sum()
            .reindex(sorted(df_year["month"].unique()))
        )
        if monthly_deposits.size >= 2:
            cum_deposits = monthly_deposits.cumsum()
            room_left = total_contribution_room - cum_deposits
            room_df = pd.DataFrame({"room_left": room_left})
            room_df.index.name = "month"
            st.subheader("📈 Contribution Room Left (This Year)")
            st.line_chart(room_df)
        else:
            st.info(
                "📉 Not enough data to show contribution room trend over time. "
                "Add deposits across multiple months to activate this chart."
            )

# ============================
# Controls: Clear All (with confirm)
# ============================
st.subheader("📋 Transaction Controls")
cta1, cta2 = st.columns([1, 2])

with cta1:
    if not st.session_state.confirm_clear:
        if st.button("💣  Clear All Transactions"):
            st.session_state.confirm_clear = True
            st.rerun()
    else:
        st.warning("⚠️ Are you sure you want to delete **all** transactions?")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("Yes, nuke them"):
                st.session_state.transactions = []
                st.session_state.confirm_clear = False
                st.success("All transactions cleared.")
                st.rerun()
        with cc2:
            if st.button("No, keep them"):
                st.session_state.confirm_clear = False
                st.info("Cancelled.")
                st.rerun()

with cta2:
    st.caption("Tip: Deleting is permanent. Use the ❌ next to individual rows to remove specific entries.")
