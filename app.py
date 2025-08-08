import streamlit as st
import pandas as pd
from datetime import datetime

# ----------------------------
# App State Initialization
# ----------------------------
if 'transactions' not in st.session_state:
    st.session_state.transactions = []
if 'amount_input' not in st.session_state:
    st.session_state.amount_input = 0.0

# Function to reset transactions when key info changes
def reset_transactions():
    st.session_state.transactions.clear()
    st.session_state.amount_input = 0.0

# ----------------------------
# Settings
# ----------------------------
current_year = datetime.now().year
st.title("TFSA Monthly Tracker with Carryover Support")

# ----------------------------
# TFSA Room Estimator
# ----------------------------
st.subheader("📅 Contribution Room Estimator")
col1, col2 = st.columns(2)
with col1:
    dob = st.date_input("Enter your date of birth:", value=datetime(1990, 1, 1), min_value=datetime(1900, 1, 1), max_value=datetime.today(), on_change=reset_transactions)
with col2:
    ever_contributed = st.radio("Have you ever contributed to a TFSA before?", ["Yes", "No"], on_change=reset_transactions)

# Show year turned 18
age_18_year = dob.year + 18
if age_18_year > current_year:
    st.error("❌ You are not eligible for a TFSA yet. You must be at least 18 years old.")
else:
    st.info(f"You became TFSA-eligible in: {age_18_year}")

tfsa_start_year = max(dob.year + 18, 2009)
estimated_room = 0

limits_by_year = {
    2009: 5000, 2010: 5000, 2011: 5000, 2012: 5000, 2013: 5500,
    2014: 5500, 2015: 10000, 2016: 5500, 2017: 5500, 2018: 5500,
    2019: 6000, 2020: 6000, 2021: 6000, 2022: 6000, 2023: 6500, 2024: 7000, 2025: 7000
}

if ever_contributed == "No" and age_18_year <= current_year:
    for year in range(tfsa_start_year, current_year + 1):
        estimated_room += limits_by_year.get(year, 0)
    st.metric(label="Estimated Contribution Room", value=f"${estimated_room:,.2f}")
    with st.expander("ℹ️ Why is this your estimated room?", expanded=True):
        st.markdown("""
        This estimate is based on your date of birth and assumes you've **never contributed** to a TFSA.
        
        Contribution room is calculated by adding together the annual TFSA limits from the year you turned 18 until the current year.
        
        🔗 [Official CRA TFSA Contribution Limits](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/contributions.html)
        """)
else:
    estimated_room = st.number_input("Enter your unused TFSA room (manually, if known):", min_value=0, step=500, value=0)
    st.metric(label="Manual Contribution Room", value=f"${estimated_room:,.2f}")

# Future contribution room preview
if ever_contributed == "No" and age_18_year <= current_year:
    future_years = list(range(current_year + 1, 2027))
    future_room = sum(limits_by_year.get(year, 0) for year in future_years)
    if future_room > 0:
        with st.expander("📅 Estimated Future Contribution Room"):
            for year in future_years:
                if year in limits_by_year:
                    st.markdown(f"- {year}: ${limits_by_year[year]:,}")
            st.markdown(f"**Total (2026): ${future_room:,}**")

# ----------------------------
# Log a New Transaction
# ----------------------------
total_contribution_room = estimated_room

st.subheader("➕ Add a Transaction")
with st.form("transaction_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        t_date = st.date_input("Transaction Date", value=datetime.today(), min_value=datetime(2009, 1, 1), max_value=datetime(current_year, 12, 31))
    with col2:
        t_type = st.radio("Type", ["deposit", "withdrawal"], horizontal=True)
    with col3:
        t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=st.session_state.amount_input, key='amount_input')
    submitted = st.form_submit_button("Add Transaction")

    if submitted and t_amount > 0:
        total_deposits_made = sum(t['amount'] for t in st.session_state.transactions if t['type'] == 'deposit')
        total_withdrawals_made = sum(t['amount'] for t in st.session_state.transactions if t['type'] == 'withdrawal')
        remaining_room = total_contribution_room - total_deposits_made
        available_withdraw_balance = total_deposits_made - total_withdrawals_made

        if t_type == 'deposit' and t_amount > remaining_room:
            st.error(f"❌ You cannot deposit more than your available contribution room (${remaining_room:,.2f}).")
        elif t_type == 'withdrawal' and t_amount > available_withdraw_balance:
            st.error(f"❌ You cannot withdraw more than your current deposited balance (${available_withdraw_balance:,.2f}).")
        else:
            st.session_state.transactions.append({"date": t_date.strftime("%Y-%m-%d"), "type": t_type, "amount": t_amount})
            if t_type == "deposit":
                st.toast("Deposit added!", icon="💸")
            elif t_type == "withdrawal":
                st.toast("Withdrawal added!", icon="🔻")
            st.session_state.amount_input = 0.0

# ----------------------------
# Display & Summary
# ----------------------------
if st.session_state.transactions:
    df = pd.DataFrame(st.session_state.transactions)
    df["date"] = pd.to_datetime(df["date"])
    monthly_totals = df.groupby(["type"])["amount"].sum().to_dict()
    total_deposits = monthly_totals.get("deposit", 0)
    contribution_percent = min(100, int((total_deposits / total_contribution_room) * 100))
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Total Deposits", value=f"${total_deposits:,.2f}")
    with col2:
        st.metric(label="Remaining Room", value=f"${total_contribution_room - total_deposits:,.2f}")

    st.progress(contribution_percent / 100)
    st.markdown(f"<strong>{contribution_percent}% of your contribution room used</strong>", unsafe_allow_html=True)
    remaining_room_val = total_contribution_room - total_deposits
    st.markdown(f"<div style='color:{'#2e7d32' if contribution_percent < 90 else '#d32f2f'}; font-weight:bold;'>💡 You have ${remaining_room_val:,.2f} in room remaining.</div>", unsafe_allow_html=True)

    st.line_chart(df.groupby(df['date'].dt.to_period('M')).sum(numeric_only=True).to_timestamp())

    # Transaction list
    st.subheader("🧾 Logged Transactions")
    st.dataframe(df.sort_values(by="date", ascending=False))
