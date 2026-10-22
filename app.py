
import streamlit as st

st.set_page_config(
    page_title="Lesson 2",
    page_icon="🎯",
    layout="wide"
)

st.title("Lesson 2: Interactive Widgets")

name = st.text_input("Enter your name")

region = st.selectbox(
    "Choose a region",
    ["North", "South", "East", "West"]
)

departments = st.multiselect(
    "Choose departments",
    ["Sales", "Finance", "IT", "Operations"]
)

amount = st.slider(
    "Select an amount",
    min_value=0,
    max_value=100000,
    value=25000,
    step=5000
)

approved = st.checkbox("Approved")

if st.button("Show Details"):
    st.write("Name:", name)
    st.write("Region:", region)
    st.write("Departments:", departments)
    st.write("Amount:", amount)
    st.write("Approved:", approved)
