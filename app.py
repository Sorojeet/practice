import streamlit as st
import pandas as pd
import polars as pl
st.set_page_config(page_title="Excel Viewer", page_icon=":clipboard:", layout="wide")
st.sidebar.title("Excel Viewer")
st.sidebar.write("Upload your Excel file to view its contents")
uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx", "xls"])
st.sidebar.write("You can upload an Excel file to view its contents.")
st.
if uploaded_file:
    xls=pd.ExcelFile(uploaded_file)
    sheet=st.selectbox("Select a sheet to view", xls.sheet_names)
if st.button("View Excel File") and uploaded_file is not None:
    df=pl.read_excel(uploaded_file,sheet_name=sheet)
    df=df.to_pandas()
    st.dataframe(df,hide_index=True,width=10000)
else:
    st.warning("Please upload an Excel file to view its contents.")