import streamlit as st
import pandas as pd
import polars as pl
st.set_page_config(page_title="Excel Viewer", page_icon=":clipboard:", layout="wide")
st.header("Excel Viewer :clipboard:")
st.sidebar.title("Excel Viewer")
st.sidebar.write("Upload your Excel file to view its contents")
uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx", "xls"])
st.sidebar.write("You can upload an Excel file to view its contents.")
header_index = st.number_input("Adjust header index", min_value=0, max_value=10, value=0, step=1)
col1, col2 = st.columns(2)
if uploaded_file:
    xls=pd.ExcelFile(uploaded_file)
    sheet=st.selectbox("Select a sheet to view", xls.sheet_names)
    df=pd.read_excel(uploaded_file,sheet_name=sheet,header=header_index)
    with col1:
        try:
            column=st.selectbox("Select columns to filter", xls.parse(sheet_name=sheet,header=header_index).columns.tolist(),key="columns")
        except:
            st.warning("No columns available for selection.")
    with col2:
        try:
            val=st.selectbox("Select values to filter",df[column].unique().tolist(),key="values") 
        except:
            st.selectbox("No columns available for selection.", ["No values available"], key="values")
col3,col4,col5 = st.columns(3,gap='xxsmall')
with col3:
    btn1=st.button("View File",key="view")
with col4:
    btn2=st.button("Filter File",key="filter")
with col5:
    st.empty()
if btn1:
    st.write("### Preview")
    st.caption(f'Showing {len(df)} out of {len(df)} rows')
    st.dataframe(df,hide_index=True)
elif btn2:
    df_filtered=df[df[column]==val]
    st.write("### Filtered Results")
    st.caption(f'Showing {len(df_filtered)} out of {len(df)} rows')
    st.dataframe(df_filtered,hide_index=True)
