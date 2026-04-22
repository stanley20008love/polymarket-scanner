"""Polymarket Scanner Dashboard - Minimal version for deployment testing"""
import streamlit as st

st.set_page_config(page_title="Polymarket Scanner", page_icon="📊", layout="wide")

st.title("📊 Polymarket Scanner + Options Vol Surface")
st.success("✅ Service is running!")

st.markdown("---")
st.subheader("Status")
st.info("Scanner is initializing. Full features will be available shortly.")

st.markdown("---")
st.subheader("System Info")
import sys
st.json({
    "Python Version": sys.version.split()[0],
    "Status": "ONLINE",
    "Scanner Mode": "READ-ONLY"
})
