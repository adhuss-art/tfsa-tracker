import streamlit as st
import pandas as pd
from datetime import datetime

# ----------------------------
# Session state init (prevents AttributeError)
# ----------------------------
if 'transactions' not in st.session_state:
    st.session_state.transactions = []
if 'amount_input' not in st.session_state:
    st.session_state.amount_input = 0.0
if 'estimated_room' not in st.session_state:
    st.session_state.estimated_room = 0.0

# ----------------------------
# Log a New Transaction
# ----------------------------
estimated_room = float(st.session_state.get('estimated_room', 0.0))
total_contribution_room = estimated_room  # your estimator sets this upstream

st.subheader("➕ Add a Transaction")
with st.form("transaction_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        t_date = st.date_input(
            "Transaction Date",
            value=datetime.today(),
            min_value=datetime(2009, 1, 1),
            max_value=datetime.now().replace(month=12, day=31),
        )
    with col2:
        t_type = st.radio("Type", ["deposit", "withdrawal"], horizontal=True)
    with col3:
        t_amount = st.number_input(
            "Amount",
            min_value=0.0,
            step=100.0,
            value=st.session_state.amount_input,
            key='amount_input'
        )

    submitted = st.form_submit_button("Add Transaction")

    if submitted and t_amount > 0:
        # Safe totals even if transactions list is empty
        txns = st.session_state.transactions
        total_deposits_made = sum(t['amount'] for t in txns if t['type'] == 'deposit')
        total_withdrawals_made = sum(t['amount'] for t in txns if t['type'] == 'withdrawal')

        remaining_room = total_contribution_room - total_deposits_made
        remaining_room = max(0.0, remaining_room)  # never show negative
        available_withdraw_balance = max(0.0, total_deposits_made - total_withdrawals_made)

        # Guards
        if t_type == 'deposit' and t_amount > remaining_room:
            st.error(f"❌ You cannot deposit more than your available contribution room (${remaining_room:,.2f}).")
        elif t_type == 'withdrawal' and t_amount > available_withdraw_balance:
            st.error(f"❌ You cannot withdraw more than your current deposited balance (${available_withdraw_balance:,.2f}).")
        else:
            st.session_state.transactions.append({
                "date": t_date.strftime("%Y-%m-%d"),
                "type": t_type,
                "amount": float(t_amount)
            })
            # Toasters
            if t_type == "deposit":
                st.toast("💸 Deposit added!")
            else:
                st.toast("🔻 Withdrawal added!")

            # Reset amount field to 0 after successful submission
            st.session_state.amount_input = 0.0
            st.rerun()

# ----------------------------
# Collapsible deletable list under Add Transaction
# ----------------------------
if st.session_state.transactions:
    df = pd.DataFrame(st.session_state.transactions)
    df["date"] = pd.to_datetime(df["date"])

    with st.expander("🧾 Logged Transactions", expanded=False):
        for i, row in df.sort_values(by="date", ascending=False).iterrows():
            col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 1])
            col_a.write(row['date'].strftime('%Y-%m-%d'))
            # colour code
            col_b.markdown(
                f"<span style='color:{'#00e676' if row['type']=='deposit' else '#ff5252'};'>{row['type'].capitalize()}</span>",
                unsafe_allow_html=True
            )
            col_c.markdown(
                f"<strong>${row['amount']:,.2f}</strong>",
                unsafe_allow_html=True
            )
            if col_d.button("❌", key=f"del_{i}"):
                # delete by original index (works because we're iterating on df index)
                del st.session_state.transactions[i]
                st.rerun()
else:
    st.caption("No transactions yet. Add one above to get started.")
