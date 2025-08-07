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
yearly_limit = 7000  # TFSA limit for 2025, change if needed

st.title("TFSA Monthly Tracker with Carryover Support")

# ----------------------------
# User Input: Carryover Room
# ----------------------------
carryover_room = st.number_input(
    f"Enter your unused TFSA room from previous years (before {current_year}):",
    min_value=0,
    step=500,
    value=0
)

# Total available room = carryover + this year's limit
total_contribution_room = carryover_room + yearly_limit

# ----------------------------
# Log a New Transaction
# ----------------------------
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
        st.success("Transaction added!")

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

    monthly["net_contribution"] = monthly["deposit"] - monthly["withdrawal"]
    monthly["cumulative_contribution"] = monthly["net_contribution"].cumsum()
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
    st.subheader("📊 Deposits & Withdrawals by Month")
    st.bar_chart(monthly.set_index("month")[["deposit", "withdrawal"]])

    st.subheader("🪙 Contribution Room Left Over Time")
    st.line_chart(monthly.set_index("month")["room_left"])

else:
    st.info("No transactions logged yet. Use the form above to begin tracking.")
