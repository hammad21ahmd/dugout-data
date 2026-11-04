"""
Home.py - Dugout Data: entry point and page router (main file for Streamlit Cloud).
READ-ONLY: the pages read psl.sqlite only (Insights reads its aggregate file); data_files.py
finds them locally or, on Streamlit Cloud, downloads them once per server.

Sets the page config and CSS, draws the same header on every page (brand, tagline, season
filter), then runs the chosen page from views/. Design rules: docs/STYLE.md.
The Insights (beta) page exists only when common.SHOW_INSIGHTS is True and its file is
available: otherwise it is not in the menu, has no URL and no data file is opened for it.

Run locally from the project folder (so .streamlit/config.toml is read):
  py -3.13 -m streamlit run app/Home.py
"""

import os
from pathlib import Path

import streamlit as st

import common as c
import data_files

st.set_page_config(page_title="Dugout Data", layout="wide", initial_sidebar_state="collapsed")
if st.get_option("theme.base") != "dark":
    # .streamlit/config.toml was not loaded (Streamlit reads it from the folder it starts in).
    print("Dugout Data: dark theme not loaded. Start Streamlit from the project folder.")
st.markdown(c.CSS, unsafe_allow_html=True)

if not os.environ.get("DD_DB"):
    psl, insights, problem = data_files.paths()
    if problem:
        st.markdown('<div class="dd-brand"><b>Dugout Data</b></div>', unsafe_allow_html=True)
        c.empty(problem)
        st.stop()
    c.DB = psl
    c.INSIGHTS_DB = insights or Path("no-insights-file")     # Insights hides itself without its file

pages = [
    st.Page("views/home.py", title="Home", default=True),
    st.Page("views/player.py", title="Player", url_path="player"),
    st.Page("views/matchups.py", title="Matchups", url_path="matchups"),
    st.Page("views/compare.py", title="Compare", url_path="compare"),
    st.Page("views/teams.py", title="Teams", url_path="teams"),
    st.Page("views/venues.py", title="Venues", url_path="venues"),
]
if c.SHOW_INSIGHTS and c.insights_available():
    pages.append(st.Page("views/insights.py", title="Insights (beta)", url_path="insights"))
pages.append(st.Page("views/method.py", title="Method", url_path="method"))

nav = st.navigation(pages, position="top")
c.header()
nav.run()
