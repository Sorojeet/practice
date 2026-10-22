
import streamlit as st
import pandas as pd

st.title("Student Information System")
name=st.text_input("Enter Student Name")
marks=st.slider("Select Marks:",0,100,10)
if st.button("Submit"):
  st.success(f"{name} got {marks} marks.")
