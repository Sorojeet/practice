import streamlit as st

col1, col2, col3 = st.columns(3)

col1.metric("Total Sales", "₹85,000", "-12%")
col2.metric("Total Orders", "850", "+8%")
col3.metric("Refunds", "₹2,500", "-3%")
