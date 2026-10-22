
import streamlit as st
import pandas as pd

st.title("Sales Dashboard")

df = pd.DataFrame({
    "Region": ["North", "South", "East", "West"],
    "Sales": [12000, 18000, 9000, 15000],
    "Orders": [120, 180, 90, 150]
})

st.subheader("Sales Records")
st.dataframe(df, use_container_width=True)

st.subheader("Sales by Region")
st.bar_chart(df, x="Region", y="Sales")

st.metric("Total Sales", f"{df['Sales'].sum():,}")
