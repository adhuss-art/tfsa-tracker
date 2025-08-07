import streamlit as st
import pandas as pd
from datetime import datetime

# ----------------------------
# App State Initialization
# ----------------------------
if 'transactions' not in st.session_state:
    st.session_state.transactions = []

# ----------------------------
# Settings
# ----------------------------
current_year = datetime.now().year
st.title("TFSA Monthly Tracker with Carryover Support")

# ----------------------------
# TFSA Room Estimator
# ----------------------------
st.subheader("📅 Contribution Room Estimator")
dob = st.date_input("Enter your date of birth:", value=datetime(1990, 1, 1))
ever_contributed = st.radio("Have you ever contributed to a TFSA before?", ["Yes", "No"])

tfsa_start_year = max(dob.year + 18, 2009)
estimated_room = 0

if ever_contributed == "No":
    limits_by_year = {
        2009: 5000, 2010: 5000, 2011: 5000, 2012: 5000, 2013: 5500,
        2014: 5500, 2015: 10000, 2016: 5500, 2017: 5500, 2018: 5500,
        2019: 6000, 2020: 6000, 2021: 6000, 2022: 6000, 2023: 6500, 2024: 7000, 2025: 7000
    }
    for year in range(tfsa_start_year, current_year + 1):
        estimated_room += limits_by_year.get(year, 0)
    st.success(f"✅ Your estimated available contribution room is: ${estimated_room:,.2f}")
    with st.expander("ℹ️ Why is this your estimated room?"):
        st.markdown("""
        This estimate is based on your date of birth and assumes you've **never contributed** to a TFSA.
        
        Contribution room is calculated by adding together the annual TFSA limits from the year you turned 18 until the current year:
        
        - 2009: $5,000  
        - 2010: $5,000  
        - 2011: $5,000  
        - 2012: $5,000  
        - 2013: $5,500  
        - 2014: $5,500  
        - 2015: $10,000  
        - 2016: $5,500  
        - 2017: $5,500  
        - 2018: $5,500  
        - 2019: $6,000  
        - 2020: $6,000  
        - 2021: $6,000  
        - 2022: $6,000  
        - 2023: $6,500  
        - 2024: $7,000  
        - 2025: $7,000  

        If you’ve made any contributions in previous years, your actual room may be less. Withdrawals create new room, but **only in the following calendar year**.
        """)
else:
    estimated_room = st.number_input("Enter your unused TFSA room (manually, if known):", min_value=0, step=500, value=0)

# ----------------------------
# Log a New Transaction
# ----------------------------
# Use estimated_room for now
yearly_limit = 7000
total_contribution_room = estimated_room + yearly_limit

st.subheader("➕ Add a Transaction")
with st.form("transaction_form"):
    t_date = st.date_input("Transaction Date", value=datetime.today())
    t_type = st.radio("Type", ["deposit", "withdrawal"])
    t_amount = st.number_input("Amount", min_value=0.0, step=100.0)
    submitted = st.form_submit_button("Add Transaction")

    if submitted and t_amount > 0:
        st.session_state.transactions.append({
            "date": t_date.strftime("%Y-%m-%d"),
            "type": t_type,
            "amount": t_amount
        })

        if len(st.session_state.transactions) == 1 and t_type == "deposit":
            st.success("💸💸💸 Congrats! You’ve just made your first deposit!")
        else:
            st.success("✅ Transaction added!")

# ----------------------------
# Display Live Transaction Log
# ----------------------------
if st.session_state.transactions:
    st.subheader("🧾 Logged Transactions")
    df_log = pd.DataFrame(st.session_state.transactions)
    st.dataframe(df_log.sort_values(by="date"))

# ----------------------------
# Convert Session Transactions to DataFrame
# ----------------------------
if st.session_state.transactions:
    df = pd.DataFrame(st.session_state.transactions)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M").astype(str)

    # Filter for current year
    df_current = df[df["year"] == current_year]

    # Monthly totals
    monthly = df_current.groupby(["month", "type"])["amount"].sum().unstack().fillna(0).reset_index()
    if 'deposit' not in monthly.columns:
        monthly['deposit'] = 0.0
    if 'withdrawal' not in monthly.columns:
        monthly['withdrawal'] = 0.0

    monthly["net_contribution"] = monthly["deposit"]  # Withdrawals don't reduce room this year
    monthly["cumulative_contribution"] = monthly["deposit"].cumsum()
    monthly["room_left"] = total_contribution_room - monthly["cumulative_contribution"]

    # ----------------------------
    # Display Summary Table
    # ----------------------------
    st.subheader("📋 Monthly Summary Table")
    st.dataframe(monthly.style.format({
        "deposit": "${:,.2f}",
        "withdrawal": "${:,.2f}",
        "net_contribution": "${:,.2f}",
        "cumulative_contribution": "${:,.2f}",
        "room_left": "${:,.2f}"
    }))

    # ----------------------------
    # Charts
    # ----------------------------
        st.subheader("📊 Deposits & Withdrawals by Month")    st.bar_chart(monthly.set_index("month")[["deposit", "withdrawal"]])

    st.subheader("🪙 Contribution Room Left Over Time (Current Year)")
    st.line_chart(monthly.set_index("month")["room_left"])

# Optional: Full contribution room over time (all years)
    df_all = df.copy()
    all_months = df_all.groupby(["month", "type"])["amount"].sum().unstack().fillna(0).reset_index()
    if 'deposit' not in all_months.columns:
        all_months['deposit'] = 0.0
    if 'withdrawal' not in all_months.columns:
        all_months['withdrawal'] = 0.0

    all_months["net_contribution"] = all_months["deposit"]
    all_months["cumulative_contribution"] = all_months["deposit"].cumsum()
    all_months["room_left"] = total_contribution_room - all_months["cumulative_contribution"]

    st.subheader("📈 Total Contribution Room Left Over Time (All Transactions)")    st.line_chart(all_months.set_index("month")["room_left"])


