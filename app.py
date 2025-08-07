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
dob = st.date_input("Enter your date of birth:", value=datetime(1990, 1, 1), min_value=datetime(1900, 1, 1), max_value=datetime.today())

# Show year turned 18
age_18_year = dob.year + 18
if age_18_year > current_year:
    st.error("❌ You are not eligible for a TFSA yet. You must be at least 18 years old.")
else:
    st.info(f"You became TFSA-eligible in: {age_18_year}")
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

# Future contribution room preview
if ever_contributed == "No" and age_18_year <= current_year:
    future_years = list(range(current_year + 1, 2027))
    future_room = sum(limits_by_year.get(year, 0) for year in future_years)
    if future_room > 0:
        with st.expander("📅 Estimated Future Contribution Room"):
            st.markdown("""
            Here's what your TFSA room could grow to in the coming years:
            """)
            for year in future_years:
                if year in limits_by_year:
                    st.markdown(f"- {year}: ${limits_by_year[year]:,}")
            st.markdown(f"**Total (2026): ${future_room:,}**")

        with st.expander("📊 Visual TFSA Growth Timeline"):
            tfsa_growth = pd.DataFrame({
                "Year": [year for year in future_years if year in limits_by_year],
                "Limit": [limits_by_year[year] for year in future_years if year in limits_by_year]
            })
            tfsa_growth = tfsa_growth.set_index("Year")
            st.bar_chart(tfsa_growth)

# ----------------------------
# Log a New Transaction
# ----------------------------
# Use estimated_room for now
total_contribution_room = estimated_room

st.subheader("➕ Add a Transaction")
with st.form("transaction_form"):
    t_date = st.date_input("Transaction Date", value=datetime.today(), min_value=datetime(2009, 1, 1), max_value=datetime(current_year, 12, 31))
    t_type = st.radio("Type", ["deposit", "withdrawal"])
    t_amount = st.number_input("Amount", min_value=0.0, step=100.0)
    submitted = st.form_submit_button("Add Transaction")

    if submitted and t_amount > 0:
        # Calculate used room so far
        used_room = sum(t['amount'] for t in st.session_state.transactions if t['type'] == 'deposit')
        remaining_room = total_contribution_room - used_room

        if t_type == 'deposit' and t_amount > remaining_room:
            st.error(f"❌ You cannot deposit more than your available contribution room (${remaining_room:,.2f}). Reduce the amount or check your entries.")
        else:
            st.session_state.transactions.append({
                "date": t_date.strftime("%Y-%m-%d"),
                "type": t_type,
                "amount": t_amount
            })

            if len(st.session_state.transactions) == 1 and t_type == "deposit":
                st.success("💸💸💸 Congrats! You’ve just made your first deposit!")
            with st.spinner("Logging transaction..."):
                if t_type == "deposit":
                    st.toast("Deposit added!", icon="💸")
                elif t_type == "withdrawal":
                    st.toast("Withdrawal added!", icon="🔻")
                    st.markdown("<span style='color:red;'>🔻 Withdrawal recorded</span>", unsafe_allow_html=True)

        

# ----------------------------
# Undo / Delete Last Transaction
# ----------------------------
if st.session_state.transactions:
    if st.button("❌ Undo Last Transaction"):
        removed = st.session_state.transactions.pop()
        st.toast(f"Removed last transaction: {removed['type']} of ${removed['amount']:,.2f}", icon="🗑️")

# ----------------------------
# Clear All Transactions (Nuke Button)
# ----------------------------
if st.session_state.transactions:
    if st.button("💣 Clear All Transactions"):
        st.session_state.transactions.clear()
        st.toast("All transactions cleared!", icon="💣")

# ----------------------------
# Display Live Transaction Log with delete buttons
# ----------------------------
if st.session_state.transactions:
    st.subheader("🧾 Logged Transactions")
    df_log = pd.DataFrame(st.session_state.transactions)
    df_log_sorted = df_log.sort_values(by="date").reset_index(drop=True)

    for i, row in df_log_sorted.iterrows():
        col1, col2, col3, col4 = st.columns([4, 2, 2, 1])
        with col1:
            st.markdown(f"**{row['date']}**")
        with col2:
            color = 'green' if row['type'] == 'deposit' else 'red'
            st.markdown(f"<span style='color:{color};'>{row['type'].capitalize()}</span>", unsafe_allow_html=True)
        with col3:
            color = 'green' if row['type'] == 'deposit' else 'red'
            st.markdown(f"<span style='color:{color};'>${row['amount']:,.2f}</span>", unsafe_allow_html=True)
        with col4:
            if st.button("❌", key=f"delete_{i}"):
                st.session_state.transactions.remove(row.to_dict())
                st.toast(f"Deleted {row['type']} of ${row['amount']:,.2f} from {row['date']}", icon="🗑️")
                st.experimental_rerun()



# ----------------------------
# Carryforward Tracker: Room from Withdrawals (for next year)
# ----------------------------
if st.session_state.transactions:
    total_withdrawals_this_year = sum(
        t['amount'] for t in st.session_state.transactions
        if t['type'] == 'withdrawal' and pd.to_datetime(t['date']).year == current_year
    )
    if total_withdrawals_this_year > 0:
        st.markdown(f"<span style='color:orange;'>⚠️ ${total_withdrawals_this_year:,.2f} of room will be added to your TFSA limit next year due to withdrawals made this year.</span>", unsafe_allow_html=True)

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
    st.subheader("📊 Deposits & Withdrawals by Month")
    st.bar_chart(monthly.set_index("month")[["deposit", "withdrawal"]])

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

    st.subheader("📈 Total Contribution Room Left Over Time (All Transactions)")
    st.line_chart(all_months.set_index("month")["room_left"])





