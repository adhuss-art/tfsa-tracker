# ----------------------------
# Log a New Transaction
# ----------------------------
# Ensure estimated_room exists; default to 0 if not set
estimated_room = st.session_state.get('estimated_room', 0)
total_contribution_room = estimated_room

st.subheader("➕ Add a Transaction")
with st.form("transaction_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        t_date = st.date_input("Transaction Date", value=datetime.today(), min_value=datetime(2009, 1, 1), max_value=datetime.now().replace(month=12, day=31))
    with col2:
        t_type = st.radio("Type", ["deposit", "withdrawal"], horizontal=True)
    with col3:
        t_amount = st.number_input("Amount", min_value=0.0, step=100.0, value=st.session_state.get('amount_input', 0.0), key='amount_input')
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
            st.toast("Deposit added!" if t_type == "deposit" else "Withdrawal added!", icon="💸" if t_type == "deposit" else "🔻")
            st.session_state.amount_input = 0.0

# Collapsible deletable list under Add Transaction
if st.session_state.transactions:
    df = pd.DataFrame(st.session_state.transactions)
    df["date"] = pd.to_datetime(df["date"])

    with st.expander("🧾 Logged Transactions", expanded=False):
        for i, row in df.sort_values(by="date", ascending=False).iterrows():
            col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 1])
            col_a.write(row['date'].strftime('%Y-%m-%d'))
            col_b.write(row['type'].capitalize())
            col_c.write(f"${row['amount']:,.2f}")
            if col_d.button("❌", key=f"del_{i}"):
                del st.session_state.transactions[i]
                st.experimental_rerun()
