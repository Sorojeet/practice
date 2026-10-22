
import streamlit as st

st.set_page_config(
    page_title="My First App",
    page_icon="🚀",
    layout="wide"
)

st.title("My First Streamlit App")

st.write("Welcome! I am learning to build web applications with Python.")

st.header("User Information")

name = st.text_input("Enter your name")
age = st.slider("Select your age", 18, 80, 25)

if st.button("Submit"):
    st.success(f"Hello {name}! You are {age} years old.")

st.info("This application was built entirely with Python.")
