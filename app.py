
import streamlit as st
import pandas as pd
import polars as pl
st.set_page_config(page_title="Excel Viewer", page_icon=":clipboard:", layout="wide")
st.sidebar.title("Excel Viewer")
st.sidebar.write("Upload your Excel file to view its contents")
uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx", "xls"])
st.sidebar.write("You can upload an Excel file to view its contents.")
#selected_option = st.sidebar.slider("Slide the header row (0-indexed)", min_value=0, max_value=10, value=0, step=1)
if st.sidebar.button("View Excel File") and uploaded_file is not None:
    df=pl.read_excel(uploaded_file)
    df=df.to_pandas()
    st.dataframe(df,hide_index=True,width=10000)
elif uploaded_file is None:
    st.warning("Please upload an Excel file to view its contents.")