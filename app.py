import streamlit as st

st.sidebar.title("Dashboard Filters")

region = st.sidebar.selectbox(
    "Select Region",
    ["All", "North", "South", "East", "West"]
)

st.write("Selected region:", region)
