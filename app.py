
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Sales Analytics",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Sales Analytics Dashboard")
st.caption("Lesson 2 — Widgets and Layouts")

# Sample dataset
df = pd.DataFrame({
    "Region": [
        "North", "South", "East", "West",
        "North", "South", "East", "West"
    ],
    "Sales": [
        12000, 18000, 9000, 15000,
        14000, 17000, 11000, 21000
    ],
    "Orders": [120, 180, 90, 150, 140, 170, 110, 210]
})

# Sidebar
st.sidebar.header("Filters")

regions = st.sidebar.multiselect(
    "Select regions",
    options=sorted(df["Region"].unique()),
    default=sorted(df["Region"].unique())
)

min_sales = st.sidebar.slider(
    "Minimum sales",
    min_value=0,
    max_value=int(df["Sales"].max()),
    value=0,
    step=1000
)

# Apply filters
filtered = df[
    df["Region"].isin(regions)
    & (df["Sales"] >= min_sales)
]

# KPI metrics
total_sales = filtered["Sales"].sum()
total_orders = filtered["Orders"].sum()
total_records = len(filtered)

c1, c2, c3 = st.columns(3)

c1.metric("Total Sales", f"₹{total_sales:,.0f}")
c2.metric("Total Orders", f"{total_orders:,}")
c3.metric("Records", f"{total_records:,}")

# Tabs
tab1, tab2 = st.tabs(["📈 Chart", "📋 Data"])

with tab1:
    chart_data = (
        filtered.groupby("Region", as_index=False)["Sales"]
        .sum()
    )

    st.bar_chart(chart_data, x="Region", y="Sales")

with tab2:
    st.dataframe(filtered, use_container_width=True)

    st.download_button(
        "Download filtered CSV",
        data=filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name="filtered_sales.csv",
        mime="text/csv"
    )
