import streamlit as st
import pandas as pd
from datetime import datetime

# ----------------------------
# Sample transactions
# ----------------------------
transactions = [
    {"date": "2025-01-15", "type": "deposit", "amount": 1000},
    {"date": "2025-01-30", "type": "withdrawal", "amount": 200},
    {"date": "2025-02-10", "type": "deposit", "amount": 1500},
    {"date": "2025-03-05", "type": "withdrawal", "amount": 300},
    {"date": "2025-03-25", "type": "deposit", "amount": 2000},
    {"date": "2025-04-01", "type": "deposit", "amount": 1000},
]

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
# Process Data
# ----------------------------
df = pd.DataFrame(transactions)
df["date"] = pd.to_datetime(df["date"])
df["year"] = df["date"].dt.year
df["month"] = df["date"].dt.to_period("M").astype(str)

# Filter for current year
df_current = df[df["year"] == current_year]

# Monthly totals
monthly = df_current.groupby(["month", "type"])["amount"].sum().unstack(fill_value=0).reset_index()
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
