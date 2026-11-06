"""
common.py - shared code for the Dugout Data app (design system: docs/STYLE.md).

READ-ONLY: opens psl.sqlite (and, for Insights, the aggregate file) in read-only mode; where
they are found or downloaded is decided by data_files.py. No MySQL, no writes.
Protection: for visitors no download buttons except the branded share card (a PNG with "Dugout Data"
and "Data: Cricsheet.org"), dataframe toolbar hidden, at most 50 rows per table,
"Dugout Data" watermark on every chart.
Data rules (CLAUDE.md): innings 1 and 2 only; phase = over_no + 1 mapped to this_phases;
balls in delivery_no order; ball faced excludes wides; legal ball excludes wides and
no-balls; runs conceded include wides and no-ball extras, not byes or leg-byes (no-ball
with byes: 1 run to the bowler); bowler wickets are bowled, caught, lbw, stumped,
caught and bowled, hit wicket. Styles come only from public_style (Wikipedia/DBpedia/Wikidata,
or developer verified).
"""

import hmac
import html
import io
import os
import re
import sqlite3
import urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_files  # noqa: E402

# DD_DB is only set by tools/build_records.py (to fill a fresh export). On Streamlit Cloud, Home.py
# replaces DB and INSIGHTS_DB with the downloaded files (data_files.paths()).
DB = Path(os.environ.get("DD_DB") or data_files.LOCAL_PSL)

# ---- Insights: one switch. False removes the page completely (menu, URL, data).
SHOW_INSIGHTS = True
# Aggregates only (never ball by ball); never committed to Git. See data_files.py.
INSIGHTS_DB = data_files.LOCAL_INSIGHTS
INSIGHTS_CREDIT = "Data: ESPNcricinfo ball-by-ball"
MAX_ROWS = 50
COPYRIGHT = "Analysis and charts (c) Hammad Ahmad, Dugout Data. Ball-by-ball data: Cricsheet.org (ODC-BY)."
SEASONS = list(range(2016, 2027))
BRAND = "Dugout Data"
TAGLINE = "PSL player value, ball by ball"
FOOTER = "Dugout Data | Data: Cricsheet.org | Analysis by Hammad"
SITE = "dugoutdata.streamlit.app"      # printed under owner-mode image exports
BOWLER_KINDS = ["bowled", "caught", "lbw", "stumped", "caught and bowled", "hit wicket"]
NOT_OUT_KINDS = ["retired hurt", "retired not out"]
STYLE_ORDER = ["Right-arm Pace", "Left-arm Pace", "Right-arm Off-spin", "Right-arm Leg-spin",
               "Left-arm Orthodox", "Left-arm Chinaman", "Unknown"]
UNKNOWN = "Unknown"
TEAM_CODES = {"Karachi Kings": "KK", "Lahore Qalandars": "LQ", "Islamabad United": "IU", "Peshawar Zalmi": "PZ",
              "Quetta Gladiators": "QG", "Multan Sultans": "MS", "Hyderabad Kingsmen": "HK", "Rawalpindiz": "RP"}
TEAM_LEGEND = ", ".join(f"{v} {k}" for k, v in TEAM_CODES.items())

# ---- Colours (docs/STYLE.md): light theme, blue and white. UI: one accent. Charts: fixed data palette.
ACCENT = "#1565C0"            # the one UI accent: links, active tab and chip, sliders, card rules
PAGE_BG, SURFACE, SURFACE_2, BORDER = "#FFFFFF", "#F3F6FB", "#E8EEF7", "#D9E2EF"
INK, MUTED, FAINT = "#0F1B2D", "#5B6B82", "#5B6B82"
HEADER_BG, HEADER_INK = "#0B3D91", "#FFFFFF"        # top navigation strip
CHART_BG, GRID, ZERO, MARK = "#FFFFFF", "#E3E9F2", "#9AA8BC", "#8593A8"   # chart ground, grid, zero line, watermark
BAT, BOWL = "#1F6FD0", "#DD6C26"                    # batting blue, bowling orange (both at least 3:1 on white)
SERIES = [BAT, BOWL, "#18A06B"]                     # batting, bowling, third series (fixed order)
POS, NEG = "#18A06B", "#D64545"                     # diverging poles: above / below average

# ---- One help line per metric (docs/STYLE.md section 8).
HELP = {
    "RAA": "Runs above average: runs added compared with an average men's T20 player in the same season and phase.",
    "WPA": "Win probability added: how much the player's balls changed the team's chance of winning (1.00 = one win).",
    "SR": "Strike rate: runs per 100 balls faced.",
    "Econ": "Economy: runs conceded per over; wides and no-balls count, byes and leg-byes do not.",
    "Dot %": "Dot ball %: share of balls with no run off the bat (batting) or no run conceded (bowling).",
    "Boundary %": "Share of balls faced that went for four or six.",
    "Avg": "Average: runs per dismissal.",
    "Balls per dismissal": "Balls faced (or bowled) for each dismissal.",
    "Wins": "RAA turned into wins with the runs that make one win in that season.",
    "per 100 balls": "The same value per 100 balls, so players with different workloads compare fairly.",
}

CSS = f"""
<style>
/* ---- frame: hide Streamlit chrome (menu, toolbar, deploy, footer, badges) ---- */
#MainMenu, footer, [data-testid="stMainMenu"], [data-testid="stAppDeployButton"],
[data-testid="stToolbarActions"], [data-testid="stDecoration"], [class*="viewerBadge"],
[data-testid="stStatusWidget"] a {{ display: none !important; }}
/* Protection: no dataframe toolbar (download as CSV, search, fullscreen). */
[data-testid="stElementToolbar"], [data-testid="stElementToolbarButton"],
[data-testid="stDataFrame"] [data-testid="stElementToolbar"] {{ display: none !important; }}

.stApp {{ background: {PAGE_BG}; color: {INK}; font-variant-numeric: tabular-nums; }}
[data-testid="stHeader"] {{ background: {HEADER_BG}; color: {HEADER_INK}; border-bottom: 1px solid {HEADER_BG}; }}
[data-testid="stHeader"] [data-testid="stStatusWidget"], [data-testid="stHeader"] [data-testid="stStatusWidget"] * {{
    color: {HEADER_INK} !important; }}
.block-container {{ max-width: 1120px; padding: 4.25rem 1.5rem 3rem 1.5rem !important; }}
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
a {{ color: {ACCENT}; }}

/* ---- top navigation: white text on the deep blue strip, subtle hover, clear active page
   (works even without config.toml) ---- */
[data-testid="stTopNav"] {{ gap: .15rem; }}
[data-testid="stTopNavLink"] {{ color: {HEADER_INK} !important; background: transparent !important;
    border-radius: 8px; border-bottom: 2px solid transparent; }}
[data-testid="stTopNavLink"] * {{ color: {HEADER_INK} !important; }}
[data-testid="stTopNavLink"]:hover {{ background: rgba(255, 255, 255, 0.12) !important; }}
[data-testid="stTopNavLink"][aria-current="page"] {{ background: rgba(255, 255, 255, 0.16) !important;
    border-bottom-color: {HEADER_INK}; }}
[data-testid="stTopNavLink"][aria-current="page"] * {{ color: {HEADER_INK} !important; font-weight: 700; }}
[data-testid="stSidebarNavLink"] {{ color: {INK} !important; background: transparent !important; border-radius: 8px; }}
[data-testid="stSidebarNavLink"] * {{ color: {INK} !important; }}
[data-testid="stSidebarNavLink"][aria-current="page"] * {{ color: {ACCENT} !important; font-weight: 700; }}

/* ---- widget labels and tabs: readable (WCAG AA) ---- */
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] * {{ color: {INK} !important; }}
[data-testid="stTab"] p, [data-testid="stTab"] {{ color: {MUTED} !important; }}
[data-testid="stTab"][aria-selected="true"] p, [data-testid="stTab"][aria-selected="true"] {{ color: {ACCENT} !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: {ACCENT} !important; }}
.stTabs [data-baseweb="tab-border"] {{ background-color: {BORDER} !important; }}
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{
    color: {ACCENT} !important; }}
.stSlider [role="slider"] {{ background-color: {ACCENT} !important; box-shadow: none !important; }}

/* ---- header (every page) ---- */
.dd-brand {{ display: flex; align-items: baseline; gap: .75rem; flex-wrap: wrap; margin: .25rem 0 .1rem 0; }}
.dd-brand b {{ font-size: 1.4rem; font-weight: 700; color: {INK}; letter-spacing: -0.02em; }}
.dd-brand b span {{ color: {ACCENT}; }}
.dd-seasons {{ display: inline-block; color: {MUTED}; font-size: .85rem; font-weight: 600; background: {SURFACE_2};
               border: 1px solid {BORDER}; border-radius: 6px; padding: .1rem .5rem; white-space: nowrap; }}
.dd-rule {{ border: 0; border-top: 1px solid {BORDER}; margin: .6rem 0 1.4rem 0; }}

/* ---- page title ---- */
[data-testid="stMarkdownContainer"] p.dd-title, .dd-title {{ font-size: 1.65rem; font-weight: 700; color: {INK};
    margin: 0 0 .2rem 0; line-height: 1.2; }}
.dd-sub {{ color: {MUTED}; font-size: 1rem; margin: 0 0 1.25rem 0; }}
[data-testid="stMarkdownContainer"] p.dd-section, .dd-section {{ font-size: 1.08rem; font-weight: 600; color: {INK};
    margin: 2rem 0 .25rem 0; }}
.dd-section-help {{ color: {MUTED}; font-size: .88rem; margin: 0 0 .75rem 0; }}

/* ---- cards ---- */
.dd-cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(165px, 1fr)); gap: .75rem; margin: .25rem 0 1rem 0; }}
.dd-card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: .85rem 1rem; min-width: 0; }}
.dd-card.lead {{ border-top: 3px solid {ACCENT}; }}
.dd-card-label {{ color: {MUTED}; font-size: .74rem; text-transform: uppercase; letter-spacing: .04em; font-weight: 600;
                  overflow-wrap: anywhere; }}
.dd-card-value {{ color: {INK}; font-size: 1.65rem; font-weight: 700; line-height: 1.2; margin-top: .15rem;
                  font-variant-numeric: tabular-nums; white-space: nowrap; }}
/* A name or phrase in a card: smaller type; it wraps onto more lines rather than being cut (no ellipsis). */
.dd-card-value.text {{ font-size: 1.12rem; line-height: 1.35; white-space: normal; overflow-wrap: break-word; }}
.dd-card-help {{ color: {FAINT}; font-size: .78rem; line-height: 1.35; margin-top: .2rem; }}
.dd-card-detail {{ color: {MUTED}; font-size: .8rem; margin-top: .15rem; overflow-wrap: break-word;
                   font-variant-numeric: tabular-nums; }}
.dd-card-sub {{ color: {ACCENT}; font-size: .9rem; font-weight: 700; margin-top: .15rem; line-height: 1.3;
                overflow-wrap: break-word; font-variant-numeric: tabular-nums; }}

/* ---- text blocks ---- */
.dd-note {{ color: {FAINT}; font-size: .82rem; margin: .35rem 0 .9rem 0; }}
.dd-lede {{ font-size: 1.05rem; color: {INK}; margin: 0 0 .3rem 0; }}
.dd-meta {{ color: {MUTED}; font-size: .92rem; margin: 0 0 .6rem 0; }}
.dd-empty {{ background: {SURFACE}; border: 1px dashed {BORDER}; border-radius: 10px; padding: 1.25rem 1.25rem;
            color: {MUTED}; margin: .5rem 0 1rem 0; }}
.dd-empty b {{ color: {INK}; display: block; margin-bottom: .2rem; }}
.dd-chip {{ display: inline-block; background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 999px;
            padding: .1rem .6rem; font-size: .8rem; color: {MUTED}; margin: 0 .3rem .3rem 0; }}
.dd-team {{ display: inline-block; background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px;
            padding: .05rem .4rem; font-size: .74rem; font-weight: 700; letter-spacing: .04em; color: {INK};
            margin: 0 .3rem .3rem 0; cursor: default; }}
.dd-teams {{ display: inline-block; }}
.dd-teams .dd-team:first-child {{ border-color: {ACCENT}; color: {ACCENT}; }}

/* ---- compare table ---- */
.dd-compare {{ width: 100%; border-collapse: separate; border-spacing: 0; background: {SURFACE};
               border: 1px solid {BORDER}; border-radius: 10px; overflow: hidden; margin: .25rem 0 1rem 0; }}
.dd-compare th, .dd-compare td {{ padding: .5rem .75rem; border-bottom: 1px solid {BORDER}; font-size: .92rem; }}
.dd-compare tr:last-child td {{ border-bottom: 0; }}
.dd-compare th {{ color: {MUTED}; font-weight: 600; text-align: right; font-size: .8rem; }}
.dd-compare th:first-child, .dd-compare td:first-child {{ text-align: left; color: {MUTED}; }}
.dd-compare td {{ text-align: right; color: {INK}; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.dd-compare td.best {{ color: {ACCENT}; font-weight: 700; }}

/* ---- tables, tabs, charts ---- */
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 10px; overflow: hidden; background: {SURFACE}; }}
.stTabs [data-baseweb="tab-list"] {{ gap: .25rem; overflow-x: auto; }}
.stTabs [data-baseweb="tab"] {{ padding: .4rem .7rem; }}
[data-testid="stPlotlyChart"] {{ background: {CHART_BG}; border: 1px solid {BORDER}; border-radius: 10px; padding: 0;
                                 box-sizing: border-box; }}

/* ---- phone copy of every table (common.phone_table): hidden on desktop, with its element box so the
   desktop page keeps its spacing; at 640 px or less it replaces the grid ---- */
[data-testid="stElementContainer"]:has(.dd-mtable) {{ display: none !important; }}
.dd-mtable table {{ width: 100%; border-collapse: separate; border-spacing: 0; background: {SURFACE};
                    border: 1px solid {BORDER}; border-radius: 10px; overflow: hidden; table-layout: auto; }}
.dd-mtable th, .dd-mtable td {{ padding: .35rem .28rem; border-bottom: 1px solid {BORDER}; font-size: .78rem;
                                line-height: 1.3; vertical-align: top; overflow-wrap: break-word; }}
.dd-mtable th {{ color: {MUTED}; font-weight: 600; background: {SURFACE_2}; }}
.dd-mtable td {{ color: {INK}; font-variant-numeric: tabular-nums; }}
.dd-mtable .n {{ text-align: right; }}
.dd-mtable .t {{ text-align: left; }}
.dd-mtable tr:last-child td {{ border-bottom: 0; }}
.dd-mcard {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: .45rem .6rem;
             margin: 0 0 .4rem 0; }}
.dd-mcard > p {{ margin: 0 0 .25rem 0; font-weight: 700; font-size: .88rem; color: {INK}; overflow-wrap: break-word; }}
.dd-mpairs {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(88px, 1fr)); gap: .15rem .5rem; }}
.dd-mpairs > div {{ display: flex; justify-content: space-between; gap: .3rem; font-size: .78rem; min-width: 0;
                    border-bottom: 1px dotted {BORDER}; }}
.dd-mpairs span {{ color: {MUTED}; min-width: 0; overflow-wrap: break-word; }}
.dd-mpairs b {{ color: {INK}; font-weight: 600; font-variant-numeric: tabular-nums; text-align: right;
                white-space: nowrap; }}
@media (max-width: 640px) {{
  [data-testid="stElementContainer"]:has(.dd-mtable) {{ display: block !important; }}
  [data-testid="stElementContainer"]:has([data-testid="stDataFrame"]) {{ display: none !important; }}
}}

/* ---- footer ---- */
.dd-footer {{ color: {MUTED}; font-size: .85rem; border-top: 1px solid {BORDER}; margin-top: 3rem; padding-top: .9rem; }}
.dd-footer-credit {{ display: block; color: {MUTED}; }}
.dd-footer-small {{ display: block; color: {FAINT}; font-size: .78rem; margin-top: .3rem; line-height: 1.45; }}

/* ---- phone first ---- */
@media (max-width: 640px) {{
  .block-container {{ padding: 4rem .9rem 2.5rem .9rem !important; }}
  .dd-brand b {{ font-size: 1.25rem; }}
  [data-testid="stMarkdownContainer"] p.dd-title, .dd-title {{ font-size: 1.3rem; }}
  .dd-cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem; }}
  .dd-card {{ padding: .7rem .75rem; }}
  .dd-card-value {{ font-size: 1.35rem; }}
  .dd-card-value.text {{ font-size: .98rem; line-height: 1.35; }}
  .dd-section {{ margin-top: 1.6rem; }}
  .dd-compare th, .dd-compare td {{ padding: .45rem .5rem; font-size: .85rem; }}
  /* tabs: all fit on one line */
  .stTabs [role="tablist"] {{ gap: 0; }}
  .stTabs [role="tab"] {{ padding: .4rem .3rem; }}
  .stTabs [role="tab"] p {{ font-size: .84rem; }}
}}
@media (max-width: 380px) {{
  .stTabs [role="tab"] {{ padding: .4rem .2rem; }}
  .stTabs [role="tab"] p {{ font-size: .78rem; }}
}}
/* ---- phone navigation: page chips, always visible (hidden on desktop, where the top menu shows) ---- */
/* Streamlit wraps the chip row in a layout box: hidden too, or the empty box adds a 16 px gap on desktop */
.st-key-dd_mobile_nav, .st-key-dd_season_phone,
[data-testid="stLayoutWrapper"]:has(> .st-key-dd_mobile_nav) {{ display: none !important; }}
@media (max-width: 768px) {{
  /* phone: the empty blue strip (the top menu is folded away here) becomes a thin 6 px band; the page
     starts just below it */
  [data-testid="stHeader"] {{ height: 6px !important; min-height: 0 !important; overflow: hidden; }}
  .block-container {{ padding-top: 1.25rem !important; }}
  [data-testid="stLayoutWrapper"]:has(> .st-key-dd_mobile_nav) {{ display: block !important; }}
  /* all eight chips at once: two rows of four, nothing cut or hidden off screen */
  .st-key-dd_mobile_nav {{ display: grid !important; grid-template-columns: repeat(4, minmax(0, 1fr));
                           gap: .4rem !important; margin: 0 0 1rem 0; padding: 2px 0; overflow: visible; }}
  .st-key-dd_mobile_nav > div {{ width: auto !important; min-width: 0 !important; margin: 0 !important; }}
  .st-key-dd_mobile_nav > div:has(style) {{ display: none !important; }}
  .st-key-dd_mobile_nav [data-testid="stPageLink"] {{ width: 100%; }}
  .st-key-dd_mobile_nav [data-testid="stPageLink-NavLink"] {{ background: {SURFACE}; border: 1px solid {BORDER};
        border-radius: 999px; padding: .3rem .25rem; min-height: 2.1rem; white-space: nowrap; width: 100%;
        justify-content: center; margin: 0; }}
  .st-key-dd_mobile_nav [data-testid="stPageLink-NavLink"] p {{ color: {INK}; font-size: .84rem; white-space: nowrap; }}
  .dd-rule {{ margin: .2rem 0 .2rem 0 !important; }}
  /* seasons: one dropdown (presets and Custom range inside) showing only the current choice; the desktop
     preset buttons, Custom button and range label are hidden */
  [data-testid="stHorizontalBlock"]:has(.st-key-dd_season_bar) {{ flex-wrap: nowrap !important; gap: .5rem !important; }}
  [data-testid="stHorizontalBlock"]:has(.st-key-dd_season_bar) > [data-testid="stColumn"] {{
      width: auto !important; flex: 1 1 auto !important; min-width: 0 !important; }}
  .st-key-dd_season_bar {{ justify-content: flex-end !important; flex-wrap: nowrap !important; }}
  .st-key-dd_season_bar > div:not(.st-key-dd_season_phone) {{ display: none !important; }}
  .st-key-dd_season_bar > .st-key-dd_season_phone {{ display: block !important; flex: 0 0 auto !important; }}
  .st-key-dd_season_phone button {{ min-height: 2.1rem; padding: .25rem .7rem; }}
  .st-key-dd_season_phone button p {{ font-size: .88rem !important; font-weight: 600; white-space: nowrap; }}
  /* the side menu behind the ">>" button is replaced by the chips above */
  [data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"],
  [data-testid="stSidebar"], [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
  /* Streamlit's box around a chart is a few px shorter than the chart and scrolls (overflow auto): a finger
     swipe on a chart then scrolled that tiny box, not the page. clip shows the same and never scrolls. */
  [data-testid="stElementContainer"]:has([data-testid="stPlotlyChart"]) {{ overflow-y: clip !important; }}
}}
/* a finger on a chart scrolls the page (no zoom box) */
[data-testid="stPlotlyChart"] .draglayer, [data-testid="stPlotlyChart"] .draglayer * {{ touch-action: pan-y !important; }}
</style>
"""


# ------------------------------------------------------------------ shareable links (query parameters)
def link_default(key, param, options, default, cast=str):
    """Before a widget: start it from the URL (?param=...) once, and keep its value valid."""
    if key not in st.session_state:
        raw = st.query_params.get(param)
        try:
            val = cast(raw) if raw is not None else default
        except (TypeError, ValueError):
            val = default
        st.session_state[key] = val if val in options else default
    elif st.session_state[key] not in options:
        st.session_state[key] = default


def link_set(**params):
    """After a widget: write the current view into the URL so it can be shared."""
    for k, v in params.items():
        if v is None:
            st.query_params.pop(k, None)
        elif st.query_params.get(k) != str(v):
            st.query_params[k] = str(v)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


# ------------------------------------------------------------------ page frame
def header(show_seasons=True):
    """Same header on every page: brand, tagline, season filter. Drawn once by Home.py.
    The season range is in the URL as ?seasons=2016-2026 (no ?seasons= means DEFAULT_RANGE, the latest season).
    show_seasons=False (Method, where no number depends on the seasons): brand only; the chosen range is kept
    for the next page."""
    # The link wins on the first run, and when a ?seasons= link that differs from what this session last
    # wrote is opened inside a running session. An empty link (page switches clear it) changes nothing.
    st.session_state.setdefault("_slider_gen", 0)
    url = st.query_params.get("seasons", "")
    if "season_range" not in st.session_state or (url and url != st.session_state.get("_seasons_url")):
        rng = DEFAULT_RANGE
        m = re.fullmatch(r"(\d{4})-(\d{4})", url)
        if m and int(m.group(1)) in SEASONS and int(m.group(2)) in SEASONS and int(m.group(1)) <= int(m.group(2)):
            rng = (int(m.group(1)), int(m.group(2)))
        st.session_state.season_range = rng
        st.session_state._slider_gen += 1
        st.session_state._season_custom_m = False

    def keep(key):
        st.session_state.season_range = tuple(st.session_state[key])

    def pick():
        choice = st.session_state._season_preset
        if choice in SEASON_PRESETS:
            st.session_state.season_range = SEASON_PRESETS[choice]
            st.session_state._slider_gen += 1
            st.session_state._season_custom_m = False

    # The highlighted preset follows the range (from a link, the slider or a preset). The Custom slider
    # gets a new key whenever the range changes outside it (preset or link), so it always opens on the
    # range shown. Before, a slider opened once kept its old range: after a preset, choosing that old
    # range again was no change at all, so the page stayed on the preset (bug report 2026-11-03).
    st.session_state._season_preset = preset_for(st.session_state.season_range)
    slider_key = f"_season_widget_{st.session_state._slider_gen}"
    left, right = st.columns([2, 3], vertical_alignment="center")
    left.markdown('<div class="dd-brand"><b>Dugout<span> </span>Data</b></div>', unsafe_allow_html=True)
    if not show_seasons:
        st.markdown('<hr class="dd-rule">', unsafe_allow_html=True)
        return st.session_state.season_range
    with right.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small",
                         key="dd_season_bar"):
        # Desktop: one dropdown of the presets (13 do not fit as buttons); empty with "Custom" when the range
        # is a custom one, which the Custom button beside it sets.
        st.selectbox("Seasons", list(SEASON_PRESETS), key="_season_preset", on_change=pick,
                     placeholder="Custom", label_visibility="collapsed", width=150,
                     help="Every page shows the PSL seasons chosen here.")
        with st.popover("Custom", type="tertiary" if preset_for(st.session_state.season_range) else "primary"):
            st.select_slider("Seasons", options=SEASONS, value=tuple(st.session_state.season_range),
                             key=slider_key, on_change=keep, args=(slider_key,),
                             help="Choose the first and last season.")
        lo, hi = st.session_state.season_range
        rng_txt = str(lo) if lo == hi else f"{lo}-{hi}"
        st.markdown(f'<span class="dd-seasons">{rng_txt}</span>', unsafe_allow_html=True)
        # Phone only (CSS, 768 px or less): the whole control is one dropdown showing only the current choice
        # ("2026", "Last 3", "2019", "All seasons" or the custom range). Inside: the presets and "Custom range" with
        # the same slider. Hidden on desktop, where the preset buttons, Custom and the label show as before.
        now = preset_for(st.session_state.season_range)
        if now:
            st.session_state._season_choice_m = PHONE_CUSTOM if st.session_state.get("_season_custom_m") else now
        else:
            st.session_state._season_choice_m = PHONE_CUSTOM

        def pick_phone():
            choice = st.session_state._season_choice_m
            st.session_state._season_custom_m = choice == PHONE_CUSTOM
            if choice in SEASON_PRESETS:
                st.session_state.season_range = SEASON_PRESETS[choice]
                st.session_state._slider_gen += 1

        phone_key = f"_season_widget_m_{st.session_state._slider_gen}"
        with st.popover(now or rng_txt, key="dd_season_phone"):
            st.radio("Seasons", list(SEASON_PRESETS) + [PHONE_CUSTOM], key="_season_choice_m",
                     on_change=pick_phone, label_visibility="collapsed")
            if st.session_state._season_choice_m == PHONE_CUSTOM:
                st.select_slider("Seasons", options=SEASONS, value=tuple(st.session_state.season_range),
                                 key=phone_key, on_change=keep, args=(phone_key,),
                                 help="Choose the first and last season.")
    st.markdown('<hr class="dd-rule">', unsafe_allow_html=True)
    want = f"{lo}-{hi}" if (lo, hi) != DEFAULT_RANGE else ""
    link_set(seasons=want or None)
    st.session_state._seasons_url = want
    return lo, hi


def mobile_nav(pages, current=None):
    """Phone navigation: one row of page chips under the header, always visible. Streamlit's own top menu
    folds into a hidden side menu on phones; CSS shows this row only on screens up to 768 px wide, so the
    desktop page is exactly as before. `current` is the page st.navigation returned: its chip is drawn in
    the accent. st.page_link has no key and no "current page" mark, so a one-rule <style> picks the chip
    by position (st.html with only a <style> takes no space on the page)."""
    i = next((n for n, p in enumerate(pages, 1) if current is not None and p.url_path == current.url_path), 0)
    with st.container(key="dd_mobile_nav"):
        for p in pages:
            st.page_link(p, label=p.title)
        if i:
            # Inside the chip row (last, hidden), so on desktop it adds no gap: the page starts where it did
            # before the phone chips existed (a style block outside the row pushed desktop 16 px down).
            chip = f'.st-key-dd_mobile_nav > div:nth-child({i}) [data-testid="stPageLink-NavLink"]'
            st.html(f'<style>{chip} {{ border-color: {ACCENT} !important; }}'
                    f' {chip} p {{ color: {ACCENT} !important; font-weight: 600; }}</style>')



# Order agreed 2026-11-05 (revised): All seasons first, then the latest season (the default), Last 3, then every
# season newest first. The default stays the latest season although All seasons is listed above it.
SEASON_PRESETS = {"All seasons": (SEASONS[0], SEASONS[-1]), str(SEASONS[-1]): (SEASONS[-1], SEASONS[-1]),
                  "Last 3": (SEASONS[-3], SEASONS[-1]), **{str(y): (y, y) for y in reversed(SEASONS[:-1])}}
DEFAULT_RANGE = SEASON_PRESETS[str(SEASONS[-1])]     # a page opened without ?seasons= shows the latest season
PHONE_CUSTOM = "Custom range"


def record_minimums(lo, hi):
    """Default minimums of Home's Best economy (overs) and Best strike rate and Boundaries (balls faced).
    One season: 20 overs and 120 balls (40 and 300 left only 2 to 6 players in a season); a range of
    seasons: 40 overs and 300 balls. The one place these numbers live (the app and tools/audit_records.py)."""
    return (20, 120) if lo == hi else (40, 300)


def preset_for(rng):
    """The preset that matches a season range, or None for a custom range."""
    return next((k for k, v in SEASON_PRESETS.items() if v == tuple(rng)), None)


def season_label(lo, hi):
    return f"PSL {lo}" if lo == hi else f"PSL {lo}-{hi}"


def page(title, subtitle=""):
    """Page title and one sentence on what the page answers (the header is drawn by Home.py)."""
    st.markdown(f'<p class="dd-title">{html.escape(title)}</p>'
                + (f'<p class="dd-sub">{html.escape(subtitle)}</p>' if subtitle else ""), unsafe_allow_html=True)


def season_filter():
    """Current season range (the widget is drawn once in the header)."""
    st.session_state.setdefault("season_range", DEFAULT_RANGE)
    return st.session_state.season_range


season_widget = header   # older name


def section(title, help_text=""):
    if is_owner():
        st.session_state["_x_section"] = title          # the default title of the next image export
    st.markdown(f'<p class="dd-section">{html.escape(title)}</p>'
                + (f'<p class="dd-section-help">{html.escape(help_text)}</p>' if help_text else ""),
                unsafe_allow_html=True)


def footer(copyright=False, extra=""):
    info = export_info()
    # Credit line, then the details on their own lines (separate blocks, so they never run together).
    lines = ([html.escape(extra)] if extra else []) + ([html.escape(COPYRIGHT)] if copyright else []) + [
        f'Data export {html.escape(date_fmt(info.get("exported_at_utc", "")[:10]))}. Cricsheet data is shared '
        f'under the ODC-BY licence; batting and bowling styles come from Wikipedia, DBpedia and Wikidata (CC BY-SA) or are '
        f'developer verified.']
    st.markdown(f'<div class="dd-footer"><div class="dd-footer-credit">{FOOTER}</div>'
                + "".join(f'<div class="dd-footer-small">{x}</div>' for x in lines) + '</div>',
                unsafe_allow_html=True)


def cards(items, lead=False, detail=False, export=None):
    """items: (label, value, note). By default a card shows its label and value only; the note
    becomes the card's hover tooltip. A value that is not a number (a name, a role) is shown on
    one line in smaller type, with the note as one short figure below it (e.g. '+2,033 RAA').
    detail=True (Player, Matchups) shows the note as a short second line under the number too,
    because phones cannot show hover tooltips ('3,377 balls', 'HS 115', '10 fours, 5 sixes').
    lead=True adds the accent rule (headline cards). export="Title": owner mode adds 'Save as image'."""
    cls = "dd-card lead" if lead else "dd-card"
    cells = []
    for k, v, n in items:
        is_text = not re.fullmatch(r"[+\-]?[\d,]*\.?\d*%?|-", str(v).strip())
        vcls = "dd-card-value text" if is_text else "dd-card-value"
        tip = f' title="{html.escape(n)}"' if n and not is_text else ""
        second = ""
        if n and is_text:
            second = f'<div class="dd-card-sub">{html.escape(n)}</div>'
        elif n and detail:
            second = f'<div class="dd-card-detail">{html.escape(n)}</div>'
        cells.append(f'<div class="{cls}"{tip}><div class="dd-card-label">{html.escape(k)}</div>'
                     f'<div class="{vcls}" title="{html.escape(str(v))}">{html.escape(str(v))}</div>'
                     + second + '</div>')
    st.markdown(f'<div class="dd-cards">{"".join(cells)}</div>', unsafe_allow_html=True)
    if export and is_owner():
        shown = [(k, v, n) for k, v, n in items]
        t, sub, credits, key, fname = _export_context(export)
        _save_button(lambda: cards_png(t, sub, credits, shown), key, fname)


tiles = cards   # older name


def note(text):
    st.markdown(f'<p class="dd-note">{html.escape(text)}</p>', unsafe_allow_html=True)


def empty(title, hint=""):
    """Friendly empty state."""
    st.markdown(f'<div class="dd-empty"><b>{html.escape(title)}</b>{html.escape(hint)}</div>', unsafe_allow_html=True)


# ---- tables: printf formats in column_config become Python formats with thousands separators
_PY_FMT = {"%d": "{:,.0f}", "%.1f": "{:,.1f}", "%.2f": "{:,.2f}", "%.1f%%": "{:,.1f}%", "%+.2f": "{:+,.2f}"}


def table(df, column_config=None, title=None, **kwargs):
    """st.dataframe with protection (at most MAX_ROWS rows, toolbar hidden by CSS, no index) and
    the house number formats: thousands separators; RAA columns without decimals once any value
    reaches 100; Season and # without separators. Values stay numbers, so they sort and align right."""
    n = len(df)
    if n > MAX_ROWS:
        df = df.head(MAX_ROWS)
    kwargs.setdefault("width", "stretch")
    kwargs.setdefault("hide_index", True)
    cfg = dict(column_config or {})
    fmts = {}
    for col, conf in list(cfg.items()):
        f = (conf or {}).get("type_config", {}).get("format") if isinstance(conf, dict) else None
        if not f or col not in df.columns:
            continue
        if col in ("Season", "#"):
            fmts[col] = "{:.0f}"
        elif f == "%+.1f":
            big = pd.to_numeric(df[col], errors="coerce").abs().max()
            fmts[col] = "{:+,.0f}" if pd.notna(big) and big >= 100 else "{:+,.1f}"
        elif f in _PY_FMT:
            fmts[col] = _PY_FMT[f]
        else:
            continue
        conf = {**conf, "type_config": {**conf["type_config"], "format": None}}
        cfg[col] = conf
    data = df.style.format(fmts, na_rep="-") if fmts else df
    st.dataframe(data, column_config=cfg, **kwargs)
    # Phone (CSS, 640 px or less): the grid above is hidden and this plain HTML copy shows instead. A canvas
    # grid cannot wrap text, so on a phone the last columns and long text (Method's Meaning) were cut off.
    st.markdown(phone_table(df, cfg, fmts, index=not kwargs["hide_index"]), unsafe_allow_html=True)
    if is_owner():                     # owner mode only: "Save as image" (title: `title`, else the section's)
        export_table(df, cfg, fmts, title=title, index=not kwargs["hide_index"])
    if n > MAX_ROWS:
        note(f"Showing the first {MAX_ROWS} of {n} rows. Narrow the seasons or raise the minimum to see others.")


PHONE_WIDTH = 326       # px of table at 360 px wide (block padding .9rem a side, 1 px border)
_CHAR_PX, _CELL_PAD = 6.9, 9   # 12.5 px type: about 6.9 px per character; cell padding left plus right


def _cell_text(v, py_fmt, conf):
    """The text a grid cell shows: the house format, else the column's printf format, else the value."""
    if v is None or (isinstance(v, float) and np.isnan(v)) or (not isinstance(v, str) and pd.isna(v)):
        return "-"
    try:
        if py_fmt:
            return py_fmt.format(v)
        f = (conf or {}).get("type_config", {}).get("format") if isinstance(conf, dict) else None
        if f and f.startswith("%"):
            return f % v
    except (TypeError, ValueError):
        pass
    return str(v)


def phone_table(df, cfg, fmts, index=False):
    """The phone copy of a table, as HTML that never needs sideways scrolling. If its columns fit in 360 px
    (each column as wide as its longest word, header or cell), a table whose headers and cells wrap; else
    (wide record tables) one small card per row: the row's name on top, then label and value pairs."""
    if index:
        df = df.reset_index()
    cols = list(df.columns)
    heads = [str((cfg.get(c) or {}).get("label") or c) if isinstance(cfg.get(c), dict) else str(c) for c in cols]
    rows = [[_cell_text(v, fmts.get(c), cfg.get(c)) for c, v in zip(cols, r)] for r in df.itertuples(index=False)]
    numeric = [pd.api.types.is_numeric_dtype(df[c]) or (isinstance(cfg.get(c), dict) and
               (cfg[c].get("alignment") == "right" or cfg[c].get("type_config", {}).get("type") == "number"))
               for c in cols]

    def longest_word(t):
        return max((len(w) for w in str(t).split()), default=1)

    need = sum(max([longest_word(h)] + [longest_word(r[i]) for r in rows]) * _CHAR_PX + _CELL_PAD
               for i, h in enumerate(heads))
    esc = html.escape
    if need <= PHONE_WIDTH:
        th = "".join(f'<th class="{"n" if n else "t"}">{esc(h)}</th>' for h, n in zip(heads, numeric))
        body = "".join("<tr>" + "".join(f'<td class="{"n" if n else "t"}">{esc(v)}</td>' for v, n in zip(r, numeric))
                       + "</tr>" for r in rows)
        return f'<div class="dd-mtable"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'
    # cards: the title is "#" (if any) and the first text column; every other column is a label and value
    rank = cols.index("#") if "#" in cols else None
    name = next((i for i, n in enumerate(numeric) if not n and i != rank), 0)
    cards = []
    for r in rows:
        title = (f"{r[rank]}. " if rank is not None else "") + (f"{heads[name]} {r[name]}" if numeric[name] else r[name])
        pairs = "".join(f'<div><span>{esc(h)}</span><b>{esc(v)}</b></div>'
                        for i, (h, v) in enumerate(zip(heads, r)) if i not in (rank, name))
        cards.append(f'<div class="dd-mcard"><p>{esc(title)}</p><div class="dd-mpairs">{pairs}</div></div>')
    return f'<div class="dd-mtable dd-mcards">{"".join(cards)}</div>'


# ---- column formats (docs/STYLE.md section 7). Numbers right-aligned, text left-aligned.
def col_int(label=None, help=None, width="small"):
    return st.column_config.NumberColumn(label, format="%d", help=help, width=width)


def col_1(label=None, help=None, width="small"):
    return st.column_config.NumberColumn(label, format="%.1f", help=help, width=width)


def col_2(label=None, help=None, width="small"):
    return st.column_config.NumberColumn(label, format="%.2f", help=help, width=width)


def col_pct(label=None, help=None, width="small"):
    return st.column_config.NumberColumn(label, format="%.1f%%", help=help, width=width)


def col_raa(label=None, help=HELP["RAA"], width="small"):
    return st.column_config.NumberColumn(label, format="%+.1f", help=help, width=width)


def col_wpa(label=None, help=HELP["WPA"], width="small"):
    return st.column_config.NumberColumn(label, format="%+.2f", help=help, width=width)


def col_text(label=None, help=None, width="medium"):
    return st.column_config.TextColumn(label, help=help, width=width)


def col_teams(label=None, width="small"):
    return st.column_config.TextColumn(label, help=f"Latest team first. {TEAM_LEGEND}", width=width)


# ---- writing rules (docs/STYLE.md section 6)
def date_fmt(d):
    """'2017-02-26' -> '26 Feb 2017'."""
    if d is None or d == "" or (isinstance(d, float) and np.isnan(d)):
        return ""
    t = pd.Timestamp(d)
    return f"{t.day} {t:%b %Y}"


def ground(venue_name):
    """'Gaddafi Stadium, Lahore' -> 'Gaddafi Stadium'."""
    return str(venue_name).split(",")[0]


def match_title(team1, team2):
    return f"{team1} v {team2}"


def num_fmt(v):
    """Whole number with thousands separators."""
    return f"{int(v):,}"


def raa_fmt(v):
    """RAA: one decimal, or none once it reaches 100 (+2,033)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:+,.0f}" if abs(v) >= 100 else f"{v:+,.1f}"


def _fielder(name_text, match_id, team):
    """Cricsheet fielder text -> display name (via the match squad); falls back to the text."""
    if not isinstance(name_text, str) or not name_text:
        return ""
    first = name_text.split(",")[0].strip().replace(" (sub)", "")
    pid = squad_ids().get((match_id, team, first)) or unique_ids().get(first)
    return name(pid) if pid else first


def how_out(kind, fielder_text="", match_id=None, fielding_team=None):
    """Dismissal wording: Bowled, LBW, Caught (fielder), Stumped (keeper), Run out, ..."""
    kind = (kind or "").strip()
    if kind == "caught":
        f = _fielder(fielder_text, match_id, fielding_team)
        return f"Caught ({f})" if f else "Caught"
    if kind == "stumped":
        f = _fielder(fielder_text, match_id, fielding_team)
        return f"Stumped ({f})" if f else "Stumped"
    return {"bowled": "Bowled", "lbw": "LBW", "run out": "Run out", "caught and bowled": "Caught and bowled",
            "hit wicket": "Hit wicket", "retired out": "Retired out", "retired hurt": "Retired hurt",
            "obstructing the field": "Obstructing the field", "": ""}.get(kind, kind.capitalize())


def over_labels(rows):
    """over.ball for the given balls (columns match_id, inning, over_no, delivery_no):
    the over number and the legal ball it was (or would have been, for a wide or no-ball)."""
    if rows.empty:
        return pd.Series(dtype=str)
    keys = rows[["match_id", "inning", "over_no"]].drop_duplicates()
    cond = " OR ".join(["(match_id = ? AND inning = ? AND over_no = ?)"] * len(keys))
    params = [v for r in keys.itertuples(index=False) for v in (r.match_id, int(r.inning), int(r.over_no))]
    allb = _read(f"SELECT match_id, inning, over_no, delivery_no, extras_type FROM deliveries WHERE {cond} "
                 "ORDER BY delivery_no", tuple(params))
    ext = allb["extras_type"].fillna("")
    allb["legal"] = ~ext.str.contains("wides") & ~ext.str.contains("noballs")
    allb["legal_before"] = allb.groupby(["match_id", "inning", "over_no"])["legal"].cumsum() - allb["legal"]
    lb = dict(zip(allb["delivery_no"], allb["legal_before"]))
    return rows.apply(lambda r: f"{int(r.over_no)}.{min(int(lb[r.delivery_no]) + 1, 6)}", axis=1)


# ---- teams: short codes, latest first, full name on hover
def code(team):
    return TEAM_CODES.get(team, team)


def teams_latest(df, team_col="team", season_col="season"):
    """Team names ordered by the last season played for them (latest first)."""
    if df.empty:
        return []
    last = df.groupby(team_col)[season_col].agg(["max", "min"]).sort_values(["max", "min"], ascending=False)
    return list(last.index)


def codes_latest(df, team_col="team", season_col="season"):
    return ", ".join(code(t) for t in teams_latest(df, team_col, season_col))


@st.cache_data(show_spinner=False)
def codes_by_player(table, lo, hi):
    """player_id -> team codes, latest first ('PZ, KK, IU'), from a value table in the chosen
    seasons. Vectorised and cached: the same order as teams_latest(), without a per-player loop."""
    v = in_seasons(value(table), lo, hi)
    g = v.groupby(["player_id", "team"])["season"].agg(["max", "min"]).reset_index()
    g = g.sort_values(["player_id", "max", "min"], ascending=[True, False, False], kind="mergesort")
    g["code"] = g["team"].map(code)
    return g.groupby("player_id", sort=False)["code"].agg(", ".join).to_dict()


def team_chips(teams):
    chips = "".join(f'<span class="dd-team" title="{html.escape(t)}">{html.escape(code(t))}</span>' for t in teams)
    return f'<span class="dd-teams">{chips}</span>' if chips else ""


# ------------------------------------------------------------------ data
def _con():
    return sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, check_same_thread=False)


@st.cache_data(show_spinner=False)
def query(sql, params=()):
    with _con() as c:
        return pd.read_sql_query(sql, c, params=params)


def insights_available():
    return SHOW_INSIGHTS and INSIGHTS_DB.exists()


@st.cache_data(show_spinner=False)
def insights(sql, params=()):
    """Read the private aggregate file read-only (same way as psl.sqlite)."""
    with sqlite3.connect(f"file:{INSIGHTS_DB.as_posix()}?mode=ro", uri=True, check_same_thread=False) as con:
        return pd.read_sql_query(sql, con, params=params)


@st.cache_data(show_spinner=False)
def export_info():
    return dict(query("SELECT key, value FROM export_info").values)


@st.cache_data(show_spinner=False)
def players():
    p = query("SELECT p.player_id, p.display_name, p.short_name, s.batting_hand, s.bowling_style, s.source_url, "
              "s.hand_source, s.style_source FROM players p LEFT JOIN public_style s USING (player_id)")
    return p.set_index("player_id")


@st.cache_data(show_spinner=False)
def player_teams():
    """One row per player, team and season (from the match squads)."""
    return query("SELECT DISTINCT x.player_id, x.team, m.season FROM match_players x JOIN matches m USING (match_id)")


def wiki_name(url):
    """'https://en.wikipedia.org/wiki/Mohammad_Umar_(Sindh_cricketer)' -> 'Mohammad Umar'."""
    if not isinstance(url, str) or "/wiki/" not in url:
        return None
    t = urllib.parse.unquote(url.split("/wiki/", 1)[1]).replace("_", " ")
    return re.sub(r"\s*\([^)]*\)\s*$", "", t).strip() or None


def _seasons_short(ss):
    lo, hi = min(ss), max(ss)
    return str(lo) if lo == hi else f"{lo}-{str(hi)[2:]}"


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


@st.cache_data(show_spinner=False)
def name_labels():
    """player_id -> the name shown everywhere: the Wikipedia title from public_style where there is
    one, else the Cricsheet name; never a '(2)' suffix. Players who would share a name are told
    apart by their teams (latest first) and seasons: 'Usman Khan, Multan Sultans and Hyderabad
    Kingsmen, 2023-26'."""
    p = players()
    base = {pid: wiki_name(r.source_url) or re.sub(r"\s*\(\d+\)$", "", str(r.short_name)) for pid, r in p.iterrows()}
    pt = player_teams()
    counts = pd.Series(list(base.values())).value_counts()
    out = {}
    for pid, n in base.items():
        if counts.get(n, 0) > 1:
            mine = pt[pt["player_id"] == pid]
            if len(mine):
                n = f"{n}, {_join(teams_latest(mine))}, {_seasons_short(mine['season'].tolist())}"
        out[pid] = n
    dup = pd.Series(list(out.values())).value_counts()
    return {pid: (f"{n} ({pid})" if dup[n] > 1 else n) for pid, n in out.items()}


@st.cache_data(show_spinner=False)
def unique_ids():
    """Cricsheet unique name -> player_id ('Mohammad Nawaz (3)' -> one player). Cricsheet writes
    substitute fielders this way ('Mohammad Nawaz (3) (sub)'); they are not in that match's squad."""
    return dict(query("SELECT display_name, player_id FROM players").values)


@st.cache_data(show_spinner=False)
def _squads():
    return query("SELECT match_id, team, player, player_id FROM match_players")


_SQUAD = {}


def squad_ids():
    """(match_id, team, Cricsheet name) -> player_id, for fielders and keepers."""
    if not _SQUAD:
        s = _squads()
        _SQUAD.update(zip(zip(s["match_id"], s["team"], s["player"]), s["player_id"]))
    return _SQUAD


BALL_SQL = """SELECT d.delivery_no, d.match_id, m.season, m.date, m.venue_name, d.inning,
                     d.batting_team, d.bowling_team, d.over_no, d.batter_id, d.non_striker_id,
                     d.bowler_id, d.player_dismissed_id, d.batsman_runs, d.extra_runs, d.total_runs,
                     d.extras_type, d.dismissal_kind, d.fielder
              FROM deliveries d JOIN matches m USING (match_id)
              WHERE d.inning IN (1, 2) {extra} ORDER BY d.delivery_no"""


def _read(sql, params=()):
    with _con() as con:
        return pd.read_sql_query(sql, con, params=params)


def derive(b):
    """Derived columns, following the CLAUDE.md rules (super overs already excluded by BALL_SQL)."""
    ext = b["extras_type"].fillna("")
    wide, nb, bye = ext.str.contains("wides"), ext.str.contains("noballs"), ext.str.contains("byes")
    b["faced"] = ~wide
    b["legal"] = ~wide & ~nb
    b["conceded"] = b["batsman_runs"] + np.where(wide, b["extra_runs"],
                                                 np.where(nb & bye, 1, np.where(nb, b["extra_runs"], 0)))
    kind = b["dismissal_kind"].fillna("")
    b["bowler_wkt"] = kind.isin(BOWLER_KINDS)
    b["out_any"] = b["player_dismissed_id"].notna() & (b["player_dismissed_id"] != "") & ~kind.isin(NOT_OUT_KINDS)
    b["batter_out"] = b["out_any"] & (b["player_dismissed_id"] == b["batter_id"])
    b["four"] = b["batsman_runs"] == 4
    b["six"] = b["batsman_runs"] == 6
    b["bat_dot"] = b["faced"] & (b["batsman_runs"] == 0)
    b["bowl_dot"] = b["legal"] & (b["conceded"] == 0)
    ph = phases()
    over = b["over_no"] + 1                                   # phase = over_no + 1
    b["phase_no"] = 0
    for _, r in ph.iterrows():
        b.loc[(over >= r.first_over) & (over <= r.last_over), "phase_no"] = r.phase_no
    p = players()
    b["bowl_style"] = b["bowler_id"].map(p["bowling_style"]).fillna(UNKNOWN)
    b["bowl_kind"] = np.where(b["bowl_style"].str.contains("Pace"), "Pace",
                              np.where(b["bowl_style"] == UNKNOWN, UNKNOWN, "Spin"))
    b["bat_hand"] = b["batter_id"].map(p["batting_hand"]).fillna(UNKNOWN)
    return b


@st.cache_data(show_spinner="Loading ball-by-ball data")
def balls():
    """Every ball of innings 1 and 2, in delivery_no order, with derived columns."""
    return derive(_read(BALL_SQL.format(extra="")))


@st.cache_data(show_spinner="Loading this player's balls", max_entries=200)
def balls_for(pid):
    """Only the balls one player took part in (indexed lookups): same rules as balls()."""
    return derive(_read(BALL_SQL.format(extra="AND (d.batter_id = ? OR d.non_striker_id = ? OR d.bowler_id = ? "
                                              "OR d.player_dismissed_id = ?)"), (pid,) * 4))


@st.cache_data(show_spinner=False)
def active_players():
    """Players who batted, were at the non-striker's end, or bowled in innings 1 and 2."""
    return set(_read("SELECT batter_id p FROM deliveries WHERE inning IN (1, 2) UNION "
                     "SELECT non_striker_id FROM deliveries WHERE inning IN (1, 2) UNION "
                     "SELECT bowler_id FROM deliveries WHERE inning IN (1, 2)")["p"])


@st.cache_data(show_spinner=False)
def phases():
    return query("SELECT phase_no, phase_name, first_over, last_over FROM this_phases ORDER BY phase_no")


def phase_names():
    return dict(phases()[["phase_no", "phase_name"]].values)


@st.cache_data(show_spinner=False)
def matches():
    return query("SELECT * FROM matches")


@st.cache_data(show_spinner=False)
def value(table):
    return query(f"SELECT * FROM {table}")


def in_seasons(df, lo, hi, col="season"):
    return df[(df[col] >= lo) & (df[col] <= hi)]


_NAMES = {}


def name(pid):
    """player_id -> the name shown everywhere (name_labels). A plain dict filled once per server
    process: the data file never changes while the app runs, and a dict lookup is fast."""
    if not _NAMES:
        _NAMES.update(name_labels())
    return _NAMES.get(pid, pid)


def player_options():
    """Player ids who batted or bowled, sorted by shown name."""
    return sorted(active_players(), key=name)


# ------------------------------------------------------------------ numbers
def div(a, b, scale=1.0):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, a * scale / np.where(b > 0, b, 1), np.nan)


def bat_stats(b, by):
    """Batting numbers from balls `b` grouped by `by` (outs are the batter's own dismissals on strike)."""
    g = b.groupby(by, dropna=False).agg(balls=("faced", "sum"), runs=("batsman_runs", "sum"),
                                        outs=("batter_out", "sum"), fours=("four", "sum"), sixes=("six", "sum"),
                                        dots=("bat_dot", "sum")).reset_index()
    g["sr"] = div(g["runs"], g["balls"], 100)
    g["avg"] = div(g["runs"], g["outs"])
    g["dot_pct"] = div(g["dots"], g["balls"], 100)
    g["bdry_pct"] = div(g["fours"] + g["sixes"], g["balls"], 100)
    return g


def bowl_stats(b, by):
    g = b.groupby(by, dropna=False).agg(balls=("legal", "sum"), runs=("conceded", "sum"),
                                        wkts=("bowler_wkt", "sum"), dots=("bowl_dot", "sum"),
                                        fours=("four", "sum"), sixes=("six", "sum")).reset_index()
    g["econ"] = div(g["runs"], g["balls"], 6)
    g["avg"] = div(g["runs"], g["wkts"])
    g["sr"] = div(g["balls"], g["wkts"])
    g["dot_pct"] = div(g["dots"], g["balls"], 100)
    return g


def overs(balls):
    balls = int(balls)
    return f"{balls // 6}.{balls % 6}" if balls % 6 else str(balls // 6)


def overs_num(balls):
    """Overs bowled as a number for tables (3 overs 2 balls -> 3.2), so it right-aligns."""
    balls = int(balls)
    return balls // 6 + (balls % 6) / 10


def fmt(v, nd=1, sign=False):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    try:
        if np.isnan(float(v)):
            return "-"
    except (TypeError, ValueError):
        return "-"
    return f"{float(v):+,.{nd}f}" if sign else f"{float(v):,.{nd}f}"


def pct(v):
    s = fmt(v, 1)
    return s if s == "-" else s + "%"


# ------------------------------------------------------------------ PSL records (Home)
_REC_BASE = """FROM deliveries d JOIN matches m USING (match_id)
               WHERE d.inning IN (1, 2) AND m.season BETWEEN ? AND ?"""
_CONCEDED = """d.batsman_runs + CASE WHEN d.extras_type LIKE '%wides%' THEN d.extra_runs
               WHEN d.extras_type LIKE '%noballs%' AND d.extras_type LIKE '%byes%' THEN 1
               WHEN d.extras_type LIKE '%noballs%' THEN d.extra_runs ELSE 0 END"""


@st.cache_data(show_spinner=False, max_entries=80)
def record_tables(lo, hi):
    """Records for a season range, read from the tables tools/build_records.py precomputed in the export
    (instant, also on a phone). Counted live by compute_record_tables() only if they are missing."""
    if not query("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'rec_info'").empty:
        info = query("SELECT unresolved FROM rec_info WHERE lo = ? AND hi = ?", (lo, hi))
        if len(info):
            out = []
            for name in ("rec_bat", "rec_bowl", "rec_catch"):
                df = query(f"SELECT * FROM {name} WHERE lo = ? AND hi = ?", (lo, hi))
                out.append(df.drop(columns=["lo", "hi"]).set_index("pid"))
            if "fours" not in out[0]:
                # an export made before 4s and 6s were precomputed: add them (one quick count, no data change)
                out[0] = _with_boundaries(out[0], lo, hi)
            if "ducks" not in out[0] or "maidens" not in out[1]:
                # an export made before these columns: add them (quick counts, no data change)
                out[0], out[1] = _with_extras(out[0], out[1], lo, hi)
            return (*out, int(info["unresolved"].iloc[0]))
    return compute_record_tables(lo, hi)


def _with_boundaries(bat, lo, hi):
    """Adds fours and sixes per batter: balls faced (wides excluded) with 4 or 6 runs off the bat,
    innings 1 and 2 only (no super overs), the chosen seasons."""
    b = query(f"""SELECT d.batter_id pid,
                         SUM(d.batsman_runs = 4 AND d.extras_type NOT LIKE '%wides%') fours,
                         SUM(d.batsman_runs = 6 AND d.extras_type NOT LIKE '%wides%') sixes
                  {_REC_BASE} GROUP BY 1""", (lo, hi)).set_index("pid")
    bat = bat.copy()
    for col in ("fours", "sixes"):
        bat[col] = bat.index.map(b[col]).fillna(0).astype(int)
    return bat


_NOT_OUT_SQL = "('retired hurt', 'retired not out')"


def _with_extras(bat, bowl, lo, hi):
    """Adds to the batting records: dots (balls faced with no run off the bat), ducks (out for 0) and
    30s (innings of 30 to 49); to the bowling records: maidens (an over of the bowler with 6 legal balls
    and no run conceded), 4W (innings of exactly 4 bowler wickets), 5W (5 or more), wides and no-balls
    (deliveries). Innings 1 and 2 only, the chosen seasons."""
    args = (lo, hi)
    xb = query(f"""WITH inn AS (SELECT match_id, inning, pid, SUM(r) runs FROM (
                       SELECT d.match_id, d.inning, d.batter_id pid, d.batsman_runs r {_REC_BASE}
                       UNION ALL SELECT d.match_id, d.inning, d.non_striker_id, 0 {_REC_BASE}) GROUP BY 1, 2, 3),
                   o AS (SELECT DISTINCT d.match_id, d.inning, d.player_dismissed_id pid {_REC_BASE}
                       AND COALESCE(d.player_dismissed_id, '') != '' AND d.dismissal_kind NOT IN {_NOT_OUT_SQL})
                   SELECT i.pid, SUM(i.runs = 0 AND o.pid IS NOT NULL) ducks,
                          SUM(i.runs BETWEEN 30 AND 49) thirties
                   FROM inn i LEFT JOIN o ON o.match_id = i.match_id AND o.inning = i.inning AND o.pid = i.pid
                   GROUP BY 1""", args * 3).set_index("pid")
    dots = query(f"""SELECT d.batter_id pid, SUM(d.batsman_runs = 0 AND COALESCE(d.extras_type, '') NOT LIKE '%wides%')
                     dots {_REC_BASE} GROUP BY 1""", args).set_index("pid")
    bat = bat.copy()
    bat["dots"] = bat.index.map(dots["dots"]).fillna(0).astype(int)
    bat["dot_pct"] = div(bat["dots"], bat["balls"], 100)
    for col in ("ducks", "thirties"):
        bat[col] = bat.index.map(xb[col]).fillna(0).astype(int)
    ov = query(f"""SELECT pid, SUM(legal >= 6 AND conceded = 0) maidens FROM (
                     SELECT d.match_id, d.inning, d.over_no, d.bowler_id pid,
                            SUM(COALESCE(d.extras_type, '') NOT LIKE '%wides%'
                                AND COALESCE(d.extras_type, '') NOT LIKE '%noballs%') legal,
                            SUM({_CONCEDED}) conceded {_REC_BASE} GROUP BY 1, 2, 3, 4) GROUP BY 1""",
               args).set_index("pid")
    wi = query(f"""SELECT pid, SUM(w = 4) four_w, SUM(w >= 5) five_w, SUM(wd) wides, SUM(nb) noballs FROM (
                     SELECT d.match_id, d.inning, d.bowler_id pid,
                            SUM(d.dismissal_kind IN ('bowled','caught','lbw','stumped','caught and bowled','hit wicket')) w,
                            SUM(COALESCE(d.extras_type, '') LIKE '%wides%') wd,
                            SUM(COALESCE(d.extras_type, '') LIKE '%noballs%') nb {_REC_BASE} GROUP BY 1, 2, 3)
                   GROUP BY 1""", args).set_index("pid")
    bowl = bowl.copy()
    bowl["maidens"] = bowl.index.map(ov["maidens"]).fillna(0).astype(int)
    for col in ("four_w", "five_w", "wides", "noballs"):
        bowl[col] = bowl.index.map(wi[col]).fillna(0).astype(int)
    return bat, bowl


def _fielder_lookup():
    """A function: fielder's Cricsheet name -> player_id, from the match squad, else a unique name, else that
    team's squad in the season, else across seasons (substitutes are not in the match squad); None if not
    found. The cached dicts are read once per call of this function, not once per name."""
    sq, uq, seasons_sq = squad_ids(), unique_ids(), _squad_by_team_season()

    def find(match_id, team, season, nm):
        nm = str(nm or "").strip().replace(" (sub)", "")
        return (sq.get((match_id, team, nm)) or uq.get(nm)
                or seasons_sq.get((team, season, nm)) or seasons_sq.get((team, None, nm)))
    return find


@st.cache_data(show_spinner=False, max_entries=80)
def fielding_table(lo, hi):
    """Per-player fielding in the chosen seasons: catches (as Most catches: wicketkeepers included, caught
    and bowled for the bowler), run outs (every fielder named in the run out is credited), stumpings and
    dismissals per match played. Returns (table indexed by player_id, fielder names not matched)."""
    d = query(f"""SELECT d.match_id, m.season, d.bowling_team team, d.dismissal_kind kind, d.fielder, d.bowler_id
                  {_REC_BASE} AND d.dismissal_kind IN ('caught', 'caught and bowled', 'run out', 'stumped')""",
              (lo, hi))
    rows, unresolved, find_fielder = [], 0, _fielder_lookup()
    for r in d.itertuples(index=False):
        if r.kind == "caught and bowled":
            rows.append((r.bowler_id, "ct"))
            continue
        names = str(r.fielder or "").split(",")
        for nm in (names if r.kind == "run out" else names[:1]):
            if not nm.strip():
                continue
            pid = find_fielder(r.match_id, r.team, r.season, nm)
            if pid is None:
                unresolved += 1
            else:
                rows.append((pid, {"caught": "ct", "run out": "ro", "stumped": "st"}[r.kind]))
    t = pd.DataFrame(rows, columns=["pid", "what"]).value_counts().unstack(fill_value=0)
    t = t.reindex(columns=["ct", "ro", "st"], fill_value=0)
    t["dis"] = t[["ct", "ro", "st"]].sum(axis=1)
    mat = query("""SELECT x.player_id pid, COUNT(DISTINCT x.match_id) mat FROM match_players x JOIN matches m
                   USING (match_id) WHERE m.season BETWEEN ? AND ? GROUP BY 1""", (lo, hi)).set_index("pid")["mat"]
    t["mat"] = t.index.map(mat).fillna(0).astype(int)
    t["per_match"] = div(t["dis"], t["mat"])
    return t, unresolved


def compute_record_tables(lo, hi):
    """Per-player batting, bowling and fielding totals for the chosen seasons, by the CLAUDE.md rules
    (innings 1 and 2 only; balls faced exclude wides; legal balls exclude wides and no-balls; runs
    conceded as in derive(); bowler wickets only). Returns (bat, bowl, catches, unresolved_catches)."""
    args = (lo, hi)
    mat = query(f"""SELECT x.player_id, COUNT(DISTINCT x.match_id) mat FROM match_players x JOIN matches m USING (match_id)
                    WHERE m.season BETWEEN ? AND ? GROUP BY 1""", args).set_index("player_id")["mat"]
    # batting: one row per innings batted (at the crease as striker or non-striker)
    inn = query(f"""SELECT match_id, inning, pid, SUM(runs) runs, SUM(faced) faced FROM (
                      SELECT d.match_id, d.inning, d.batter_id pid, d.batsman_runs runs,
                             (d.extras_type NOT LIKE '%wides%') faced {_REC_BASE}
                      UNION ALL
                      SELECT d.match_id, d.inning, d.non_striker_id, 0, 0 {_REC_BASE})
                    GROUP BY 1, 2, 3""", args + args)
    outs = query(f"""SELECT d.match_id, d.inning, d.player_dismissed_id pid {_REC_BASE}
                     AND d.player_dismissed_id IS NOT NULL AND d.player_dismissed_id != ''
                     AND d.dismissal_kind NOT IN ('retired hurt', 'retired not out')""", args)
    inn = inn.merge(outs.assign(out=1).drop_duplicates(["match_id", "inning", "pid"]), how="left",
                    on=["match_id", "inning", "pid"]).fillna({"out": 0})
    inn["hs_key"] = inn["runs"] * 2 + (1 - inn["out"])          # equal runs: not out ranks higher
    best = inn.sort_values("hs_key", ascending=False).drop_duplicates("pid").set_index("pid")
    bat = inn.groupby("pid").agg(inns=("inning", "size"), runs=("runs", "sum"), balls=("faced", "sum"),
                                 outs=("out", "sum"),
                                 fifties=("runs", lambda r: int(((r >= 50) & (r < 100)).sum())),
                                 hundreds=("runs", lambda r: int((r >= 100).sum())))
    bat["hs"] = [f"{int(best.at[x, 'runs'])}{'' if best.at[x, 'out'] else '*'}" for x in bat.index]
    bat["avg"] = div(bat["runs"], bat["outs"])
    bat["sr"] = div(bat["runs"], bat["balls"], 100)
    bat["mat"] = bat.index.map(mat).fillna(0).astype(int)
    bat = _with_boundaries(bat, lo, hi)
    # bowling: one row per bowler and innings
    bi = query(f"""SELECT d.match_id, d.inning, d.bowler_id pid,
                          SUM(d.extras_type NOT LIKE '%wides%' AND d.extras_type NOT LIKE '%noballs%') legal,
                          SUM({_CONCEDED}) conceded,
                          SUM(d.dismissal_kind IN ('bowled','caught','lbw','stumped','caught and bowled','hit wicket')) wkts
                   {_REC_BASE} GROUP BY 1, 2, 3""", args)
    bi["best_key"] = bi["wkts"] * 10000 - bi["conceded"]
    bb = bi.sort_values("best_key", ascending=False).drop_duplicates("pid").set_index("pid")
    bowl = bi.groupby("pid").agg(legal=("legal", "sum"), conceded=("conceded", "sum"), wkts=("wkts", "sum"))
    bowl["best"] = [f"{int(bb.at[x, 'wkts'])}/{int(bb.at[x, 'conceded'])}" for x in bowl.index]
    bowl["overs"] = bowl["legal"].map(overs_num)
    bowl["avg"] = div(bowl["conceded"], bowl["wkts"])
    bowl["econ"] = div(bowl["conceded"], bowl["legal"], 6)
    bowl["sr"] = div(bowl["legal"], bowl["wkts"])
    bowl["mat"] = bowl.index.map(mat).fillna(0).astype(int)
    bat, bowl = _with_extras(bat, bowl, lo, hi)
    # catches: caught (fielder, wicketkeepers included) and caught and bowled (the bowler)
    ct = query(f"""SELECT d.match_id, m.season, d.bowling_team team, d.dismissal_kind kind, d.fielder, d.bowler_id
                   {_REC_BASE} AND d.dismissal_kind IN ('caught', 'caught and bowled')""", args)
    catcher, unresolved, find_fielder = [], 0, _fielder_lookup()
    for r in ct.itertuples(index=False):
        if r.kind == "caught and bowled":
            catcher.append(r.bowler_id)
            continue
        pid = find_fielder(r.match_id, r.team, r.season, str(r.fielder or "").split(",")[0])
        if pid is None:
            unresolved += 1
        catcher.append(pid)
    ct["pid"] = catcher
    catches = ct.dropna(subset=["pid"]).groupby("pid").size().rename("ct").to_frame()
    catches["mat"] = catches.index.map(mat).fillna(0).astype(int)
    return bat, bowl, catches, unresolved


@st.cache_data(show_spinner=False)
def _squad_by_team_season():
    """(team, season, Cricsheet name) -> player_id when unique; (team, None, name) across seasons.
    Used for substitute fielders, who are not in that match's playing squad."""
    s = query("SELECT DISTINCT x.team, m.season, x.player, x.player_id FROM match_players x JOIN matches m USING (match_id)")
    out = {}
    g = s.groupby(["team", "season", "player"])["player_id"].agg(["nunique", "first"])
    out.update({k: v for k, v in g.loc[g["nunique"] == 1, "first"].items()})
    g = s.groupby(["team", "player"])["player_id"].agg(["nunique", "first"])
    out.update({(team, None, player): v for (team, player), v in g.loc[g["nunique"] == 1, "first"].items()})
    return out


def player_summary(pid, lo, hi):
    """The headline numbers of one player in the chosen seasons, computed once for the Player page,
    the share card and Compare (so all three always agree)."""
    b = in_seasons(balls_for(pid), lo, hi)
    bat, bowl = b[b["batter_id"] == pid], b[b["bowler_id"] == pid]
    dism = b[(b["player_dismissed_id"] == pid) & b["out_any"]]
    val = {t: in_seasons(value(t), lo, hi) for t in ("raa_bat", "raa_bowl", "wpa_bat", "wpa_bowl")}
    val = {t: v[v["player_id"] == pid] for t, v in val.items()}
    inns_bat = bat.groupby(["match_id", "inning"])["batsman_runs"].sum()
    appeared = pd.concat([b.loc[b["batter_id"] == pid, ["match_id", "inning"]],
                          b.loc[b["non_striker_id"] == pid, ["match_id", "inning"]]]).drop_duplicates()
    runs, balls_f, outs = int(bat["batsman_runs"].sum()), int(bat["faced"].sum()), len(dism)
    lb, rc, wk = int(bowl["legal"].sum()), int(bowl["conceded"].sum()), int(bowl["bowler_wkt"].sum())
    pt = in_seasons(player_teams(), lo, hi)
    pt = pt[pt["player_id"] == pid]
    return {
        "bat": balls_f > 0 or len(appeared) > 0, "bowl": len(bowl) > 0,
        "teams": teams_latest(pt), "seasons": sorted(pt["season"].unique().tolist()),
        "innings": len(appeared), "runs": runs, "balls": balls_f, "outs": outs,
        "avg": div(runs, outs).item(), "sr": div(runs, balls_f, 100).item(),
        "fifties": int((inns_bat >= 50).sum()), "hs": int(inns_bat.max()) if len(inns_bat) else 0,
        "bat_raa": val["raa_bat"]["raa"].sum(), "bat_wpa": val["wpa_bat"]["wpa"].sum(),
        "legal": lb, "conceded": rc, "wkts": wk, "bowl_matches": bowl["match_id"].nunique(),
        "econ": div(rc, lb, 6).item(), "bowl_avg": div(rc, wk).item(),
        "bowl_dot": div(bowl["bowl_dot"].sum(), lb, 100).item(),
        "bowl_raa": val["raa_bowl"]["raa"].sum(), "bowl_wpa": val["wpa_bowl"]["wpa"].sum(),
    }


# ------------------------------------------------------------------ teams (Teams page)
_FACED = "COALESCE(d.extras_type, '') NOT LIKE '%wides%'"
_LEGAL = _FACED + " AND COALESCE(d.extras_type, '') NOT LIKE '%noballs%'"
_OUT = f"(COALESCE(d.player_dismissed_id, '') != '' AND d.dismissal_kind NOT IN {_NOT_OUT_SQL})"


def _result_for(team, m):
    """W, L, T (tie: super overs are not in the data) or NR for `team` in matches `m`."""
    w = m["winner"].fillna("")
    return np.where(w == team, "W", np.where(w != "", "L", np.where(m["result"] == "tie", "T", "NR")))


@st.cache_data(show_spinner=False, max_entries=80)
def season_review(lo, hi):
    """One row per season: matches, champion (winner of the season's last match, the final), top run-scorer
    (runs off the bat; fewer balls wins a tie), top wicket-taker (bowler wickets; fewer runs conceded wins
    a tie), fours and sixes per match (balls faced with 4 or 6 off the bat)."""
    m = in_seasons(matches(), lo, hi)
    bt = query(f"""SELECT m.season, d.batter_id pid, SUM(d.batsman_runs) runs, SUM({_FACED}) balls,
                          SUM(d.batsman_runs = 4 AND {_FACED}) f4, SUM(d.batsman_runs = 6 AND {_FACED}) f6
                   {_REC_BASE} GROUP BY 1, 2""", (lo, hi))
    bw = query(f"""SELECT m.season, d.bowler_id pid, SUM({_CONCEDED}) conceded,
                          SUM(d.dismissal_kind IN ('bowled','caught','lbw','stumped','caught and bowled','hit wicket')) wkts
                   {_REC_BASE} GROUP BY 1, 2""", (lo, hi))
    rows = []
    for s, g in m.groupby("season"):
        fin = g.sort_values(["date", "match_id"]).iloc[-1]
        champ = fin["winner"] or "No result"
        opp = fin["team2"] if fin["team1"] == champ else fin["team1"]
        b = bt[bt["season"] == s].sort_values(["runs", "balls", "pid"], ascending=[False, True, True])
        w = bw[bw["season"] == s].sort_values(["wkts", "conceded", "pid"], ascending=[False, True, True])
        rows.append({"Season": s, "Matches": len(g), "Champion": champ, "Final v": code(opp) if fin["winner"] else "",
                     "Top run-scorer": name(b["pid"].iloc[0]), "Runs": int(b["runs"].iloc[0]),
                     "Top wicket-taker": name(w["pid"].iloc[0]), "Wkts": int(w["wkts"].iloc[0]),
                     "4s per match": b["f4"].sum() / len(g), "6s per match": b["f6"].sum() / len(g)})
    return pd.DataFrame(rows)


def team_results(team, lo, hi):
    """Every match of `team` in the chosen seasons, newest first: date, opponent, result and margin."""
    m = in_seasons(matches(), lo, hi)
    m = m[(m["team1"] == team) | (m["team2"] == team)].sort_values(["date", "match_id"], ascending=False)
    out = pd.DataFrame({"match_id": m["match_id"].values, "Date": m["date"].map(date_fmt).values,
                        "Season": m["season"].values,
                        "Opp": np.where(m["team1"] == team, m["team2"], m["team1"]), "Result": _result_for(team, m)})
    out["Opp"] = out["Opp"].map(code)
    out["Margin"] = [f"by {int(r)} runs" if pd.notna(r) and r else f"by {int(k)} wickets" if pd.notna(k) and k else ""
                     for r, k in zip(m["win_by_runs"], m["win_by_wickets"])]
    return out


def streaks(results):
    """(current streak, longest winning streak) from results newest first: ('W3', 5)."""
    cur = 0
    for r in results:
        if r != results[0]:
            break
        cur += 1
    best = run = 0
    for r in results:
        run = run + 1 if r == "W" else 0
        best = max(best, run)
    return (f"{results[0]}{cur}" if len(results) else "-"), best


@st.cache_data(show_spinner=False, max_entries=200)
def head_to_head(a, b, lo, hi):
    """Matches between franchises a and b: results, and each side's batting in every phase (runs including
    extras, run rate per legal over, wickets lost). Returns (summary dict, phase table)."""
    m = in_seasons(matches(), lo, hi)
    m = m[((m["team1"] == a) & (m["team2"] == b)) | ((m["team1"] == b) & (m["team2"] == a))]
    res = _result_for(a, m)
    summ = {"matches": len(m), "a_wins": int((res == "W").sum()), "b_wins": int((res == "L").sum()),
            "ties": int((res == "T").sum()), "nr": int((res == "NR").sum())}
    if m.empty:
        return summ, pd.DataFrame()
    ids = list(m["match_id"])
    d = query(f"""SELECT d.match_id, d.inning, d.batting_team team, d.over_no, d.total_runs runs,
                         ({_LEGAL}) legal, {_OUT} wkt
                  FROM deliveries d WHERE d.inning IN (1, 2) AND d.match_id IN ({','.join('?' * len(ids))})""",
              tuple(ids))
    ph = phases()
    d["phase_no"] = 0
    for r in ph.itertuples():
        d.loc[(d["over_no"] + 1).between(r.first_over, r.last_over), "phase_no"] = r.phase_no
    inns = d.groupby("team")[["match_id", "inning"]].apply(lambda x: len(x.drop_duplicates()))
    summ["a_runs"], summ["b_runs"] = (int(d.loc[d["team"] == t, "runs"].sum()) for t in (a, b))
    summ["a_inns"], summ["b_inns"] = int(inns.get(a, 0)), int(inns.get(b, 0))
    g = d.groupby(["phase_no", "team"]).agg(runs=("runs", "sum"), legal=("legal", "sum"), wkts=("wkt", "sum"))
    rows = []
    for n, label in phase_names().items():
        r = {"Phase": label}
        for t, k in ((a, "A"), (b, "B")):
            x = g.loc[(n, t)] if (n, t) in g.index else pd.Series({"runs": 0, "legal": 0, "wkts": 0})
            r[f"{k} RR"] = div(x["runs"], x["legal"], 6).item()
            r[f"{k} wkts"] = int(x["wkts"])
        rr_a, rr_b = r["A RR"], r["B RR"]
        r["Stronger"] = code(a) if rr_a > rr_b else code(b) if rr_b > rr_a else "Level"
        rows.append(r)
    return summ, pd.DataFrame(rows)


@st.cache_data(show_spinner=False, max_entries=80)
def team_style(lo, hi):
    """Per franchise: batting runs in 4s and 6s % (of runs off the bat) and dot % (balls faced with no run off
    the bat); bowling the same conceded, and dot % (legal balls with no run conceded)."""
    bat = query(f"""SELECT d.batting_team team, SUM(d.batsman_runs) runs,
                           SUM(CASE WHEN {_FACED} AND d.batsman_runs IN (4, 6) THEN d.batsman_runs ELSE 0 END) bruns,
                           SUM({_FACED}) faced, SUM({_FACED} AND d.batsman_runs = 0) dots {_REC_BASE} GROUP BY 1""",
                (lo, hi)).set_index("team")
    bowl = query(f"""SELECT d.bowling_team team, SUM(d.batsman_runs) runs,
                            SUM(CASE WHEN {_FACED} AND d.batsman_runs IN (4, 6) THEN d.batsman_runs ELSE 0 END) bruns,
                            SUM({_LEGAL}) legal, SUM(({_LEGAL}) AND ({_CONCEDED}) = 0) dots
                     {_REC_BASE} GROUP BY 1""", (lo, hi)).set_index("team")
    t = pd.DataFrame({"Team": bat.index})
    t["Bat: runs in 4s and 6s %"] = t["Team"].map(pd.Series(div(bat["bruns"], bat["runs"], 100), bat.index))
    t["Bat: dot %"] = t["Team"].map(pd.Series(div(bat["dots"], bat["faced"], 100), bat.index))
    t["Bowl: runs in 4s and 6s %"] = t["Team"].map(pd.Series(div(bowl["bruns"], bowl["runs"], 100), bowl.index))
    t["Bowl: dot %"] = t["Team"].map(pd.Series(div(bowl["dots"], bowl["legal"], 100), bowl.index))
    return t


@st.cache_data(show_spinner=False, max_entries=200)
def wicket_types(team, lo, hi):
    """How `team` lost wickets (batting) and took them (bowling and fielding), with the PSL share of each kind.
    Dismissals only: retired hurt and retired not out are left out."""
    d = query(f"""SELECT d.batting_team bat, d.bowling_team bowl, d.dismissal_kind kind {_REC_BASE}
                  AND {_OUT}""", (lo, hi))
    known = ["caught", "bowled", "lbw", "run out", "stumped", "caught and bowled", "hit wicket"]
    d["kind"] = d["kind"].where(d["kind"].isin(known), "other")
    order = known + ["other"]
    lost = d[d["bat"] == team]["kind"].value_counts().reindex(order, fill_value=0)
    took = d[d["bowl"] == team]["kind"].value_counts().reindex(order, fill_value=0)
    psl = d["kind"].value_counts().reindex(order, fill_value=0)
    t = pd.DataFrame({"How out": [k.upper() if k == "lbw" else k[0].upper() + k[1:] for k in order], "Lost": lost.values,
                      "Lost %": div(lost.values, lost.sum(), 100), "Taken": took.values,
                      "Taken %": div(took.values, took.sum(), 100), "PSL %": div(psl.values, psl.sum(), 100)})
    return t[(t["Lost"] > 0) | (t["Taken"] > 0)]


def player_movement(team, lo, hi):
    """Players of `team` in the chosen seasons who also played for another franchise in them: the
    franchise code for each season (squads), most matches for `team` first."""
    pt = in_seasons(player_teams(), lo, hi)
    mine = set(pt.loc[pt["team"] == team, "player_id"])
    moved = pt[pt["player_id"].isin(mine)].groupby("player_id")["team"].nunique()
    moved = moved[moved > 1].index
    g = pt[pt["player_id"].isin(moved)].copy()
    g["code"] = g["team"].map(code)
    grid = g.groupby(["player_id", "season"])["code"].agg(lambda x: "/".join(sorted(x))).unstack()
    mp = query("SELECT x.player_id, COUNT(*) n FROM match_players x JOIN matches m USING (match_id) "
               "WHERE x.team = ? AND m.season BETWEEN ? AND ? GROUP BY 1", (team, lo, hi)).set_index("player_id")["n"]
    grid = grid.reindex(columns=[s for s in SEASONS if lo <= s <= hi]).fillna("")
    grid.insert(0, "Matches for team", grid.index.map(mp).fillna(0).astype(int))
    grid.insert(0, "Player", grid.index.map(name))
    grid.columns = [str(x) for x in grid.columns]
    return grid.sort_values(["Matches for team", "Player"], ascending=[False, True]).reset_index(drop=True)


# ------------------------------------------------------------------ partnerships (Home, Player)
@st.cache_data(show_spinner=False, max_entries=80)
def partnership_stands(lo, hi):
    """One row per stand: the two batters at the crease together (batter and non_striker, either end) in an
    innings; runs include extras, balls exclude wides. Innings 1 and 2 only."""
    return query(f"""SELECT MIN(d.batter_id, d.non_striker_id) a, MAX(d.batter_id, d.non_striker_id) b,
                            d.match_id, d.inning, d.batting_team team, SUM(d.total_runs) runs, SUM({_FACED}) balls
                     {_REC_BASE} GROUP BY 1, 2, 3, 4, 5""", (lo, hi))


def _pairs(s):
    g = s.groupby(["a", "b"]).agg(inns=("runs", "size"), runs=("runs", "sum"), balls=("balls", "sum"),
                                  best=("runs", "max"), fifty=("runs", lambda r: int((r >= 50).sum()))).reset_index()
    g["rr"] = div(g["runs"], g["balls"], 6)
    g["avg"] = div(g["runs"], g["inns"])
    return g.sort_values(["runs", "balls"], ascending=[False, True]).reset_index(drop=True)


def top_partnerships(lo, hi, n=10):
    """The pairs with the most partnership runs together in the chosen seasons."""
    g = _pairs(partnership_stands(lo, hi)).head(n)
    g["Pair"] = [f"{name(a)} and {name(b)}" for a, b in zip(g["a"], g["b"])]
    return g


def player_partners(pid, lo, hi, n=10):
    """`pid`'s batting partners, most partnership runs first."""
    s = partnership_stands(lo, hi)
    s = s[(s["a"] == pid) | (s["b"] == pid)].copy()
    s["partner"] = np.where(s["a"] == pid, s["b"], s["a"])
    g = _pairs(s.assign(a=pid, b=s["partner"])).head(n)
    g["Partner"] = g["b"].map(name)
    return g


# ------------------------------------------------------------------ one match (Player > Matches)
def match_overs(match_id):
    """Runs (extras included) and wickets (dismissals, not retired hurt or not out) in every over of
    innings 1 and 2 of one match."""
    return query(f"""SELECT d.inning, d.batting_team team, d.over_no + 1 over, SUM(d.total_runs) runs, SUM({_OUT}) wkts
                     FROM deliveries d WHERE d.match_id = ? AND d.inning IN (1, 2) GROUP BY 1, 2, 3 ORDER BY 1, 3""",
                 (match_id,))


@st.cache_data(show_spinner=False)
def has_wp_ball():
    return not query("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'wp_ball'").empty


def match_wp(match_id):
    """Ball-by-ball win probability of the side batting first (wp_ball, from the export), in seq order;
    x is overs gone in the match (second innings after 20). None if this export has no wp_ball."""
    if not has_wp_ball():
        return None
    w = query("SELECT inning, seq, over_no, batting_team, wp_after FROM wp_ball WHERE match_id = ? "
              "AND inning IN (1, 2) ORDER BY inning, seq", (match_id,))
    if w.empty:
        return w
    w["k"] = w.groupby(["inning", "over_no"]).cumcount() + 1
    w["n"] = w.groupby(["inning", "over_no"])["seq"].transform("size")
    w["x"] = (w["inning"] - 1) * 20 + w["over_no"] + w["k"] / w["n"]
    w["wp_first"] = np.where(w["inning"] == 1, w["wp_after"], 1 - w["wp_after"]) * 100
    return w


def match_charts(overs, wp, team1, team2, key):
    """Win probability line (side batting first, %) and runs per over for both innings, wickets marked."""
    if wp is not None and len(wp):
        fig = go.Figure()
        fig.add_scatter(x=wp["x"], y=wp["wp_first"], mode="lines", name=f"{team1} win chance",
                        line=dict(color=BAT, width=2),
                        hovertemplate="Over %{x:.1f}: %{y:.0f}%<extra></extra>")
        fig.add_hline(y=50, line=dict(color=ZERO, width=1, dash="dot"))
        fig.add_vline(x=20, line=dict(color=ZERO, width=1))
        fig.update_yaxes(range=[0, 100])
        show(layout(fig, height=280, xtitle=f"Overs ({team1} bat 0 to 20, {team2} 20 to 40)",
                    ytitle=f"{code(team1)} win chance %"), key + "_wp")
    fig = go.Figure()
    for i, (inn, t) in enumerate(((1, team1), (2, team2))):
        o = overs[overs["inning"] == inn]
        fig.add_scatter(x=o["over"], y=o["runs"], mode="lines+markers", name=f"{code(t)} runs",
                        line=dict(color=SERIES[i], width=2), marker=dict(color=SERIES[i], size=5),
                        hovertemplate=f"{code(t)} over %{{x}}: %{{y}} runs<extra></extra>")
        wk = o[o["wkts"] > 0]
        fig.add_scatter(x=wk["over"], y=wk["runs"], mode="markers", name=f"{code(t)} wicket",
                        marker=dict(color=NEG, size=11, symbol="x-thin", line=dict(color=NEG, width=2)),
                        text=wk["wkts"], hovertemplate=f"{code(t)} over %{{x}}: %{{text}} wicket(s)<extra></extra>")
    show(layout(fig, height=300, xtitle="Over", ytitle="Runs in the over", legend=True), key + "_overs")


# ------------------------------------------------------------------ venues: chasing, defending, the toss
def venue_results(m, first_team):
    """Chasing against defending and the toss for matches `m` (indexed by match_id) with a winner;
    first_team: side batting first per match. Returns (chase table, toss table)."""
    m = m[m["winner"].fillna("") != ""].copy()
    m["first"] = m.index.map(first_team)
    m = m[m["first"].notna()]
    dfd = m[m["winner"] == m["first"]]
    chs = m[m["winner"] != m["first"]]
    n = len(m)
    chase = pd.DataFrame([
        {"Result": "Batting first won (defended)", "Matches": len(dfd), "Share %": div(len(dfd), n, 100).item(),
         "Average margin": f"{dfd['win_by_runs'].mean():.1f} runs" if len(dfd) and dfd["win_by_runs"].notna().any() else "-"},
        {"Result": "Batting second won (chased)", "Matches": len(chs), "Share %": div(len(chs), n, 100).item(),
         "Average margin": f"{chs['win_by_wickets'].mean():.1f} wickets" if len(chs) and chs["win_by_wickets"].notna().any() else "-"}])
    rows = []
    for dec, label in (("bat", "Chose to bat"), ("field", "Chose to field")):
        t = m[m["toss_decision"] == dec]
        won = int((t["winner"] == t["toss_winner"]).sum())
        rows.append({"Toss decision": label, "Matches": len(t), "Toss winner won": won,
                     "Toss winner won %": div(won, len(t), 100).item()})
    return chase, pd.DataFrame(rows)


POSITION_GROUPS = [("Top order (1 to 3)", 1, 3), ("Middle order (4 to 6)", 4, 6), ("Lower order (7 to 11)", 7, 11)]


def position_stats(pid, lo, hi):
    """Batting by position in the order (first appearance at the crease, batting_positions): innings,
    runs, balls faced, strike rate and average (every dismissal, as the career average)."""
    b = in_seasons(balls_for(pid), lo, hi)
    pos = query("SELECT match_id, inning, position FROM batting_positions WHERE player_id = ?", (pid,))
    bat = b[b["batter_id"] == pid].groupby(["match_id", "inning"]).agg(runs=("batsman_runs", "sum"),
                                                                       balls=("faced", "sum")).reset_index()
    outs = b[(b["player_dismissed_id"] == pid) & b["out_any"]][["match_id", "inning"]].drop_duplicates().assign(out=1)
    inn = (b.loc[(b["batter_id"] == pid) | (b["non_striker_id"] == pid), ["match_id", "inning"]].drop_duplicates()
           .merge(pos, on=["match_id", "inning"], how="left").merge(bat, on=["match_id", "inning"], how="left")
           .merge(outs, on=["match_id", "inning"], how="left").fillna({"runs": 0, "balls": 0, "out": 0}))
    rows = []
    for label, a, z in POSITION_GROUPS:
        g = inn[inn["position"].between(a, z)]
        if len(g):
            rows.append({"Position": label, "Inns": len(g), "Runs": int(g["runs"].sum()),
                         "Balls": int(g["balls"].sum()), "Outs": int(g["out"].sum())})
    t = pd.DataFrame(rows, columns=["Position", "Inns", "Runs", "Balls", "Outs"])
    t["SR"] = div(t["Runs"], t["Balls"], 100)
    t["Avg"] = div(t["Runs"], t["Outs"])
    return t


def boundary_stats(runs, balls, fours, sixes):
    """Balls per four, balls per six, boundary ball % (fours and sixes per ball faced) and % of runs in
    boundaries (4 x fours + 6 x sixes over runs off the bat)."""
    return {"balls_per_4": div(balls, fours).item(), "balls_per_6": div(balls, sixes).item(),
            "bdry_pct": div(fours + sixes, balls, 100).item(),
            "bdry_runs_pct": div(4 * fours + 6 * sixes, runs, 100).item()}


# ------------------------------------------------------------------ strengths and weaknesses (Player)
MIN_SPLIT_BALLS = 30      # a situation needs at least this many balls to be considered
SHRINK_BALLS = 60         # shrinkage: each rate is pulled to the PSL average by this many balls' worth
MIN_EFFECT = 0.05         # listed only if at least 5% better or worse than the PSL average after shrinkage

# role -> situations (column, how a sentence starts)
SITUATIONS = {"bat": {"bowl_style": "Against {v}", "phase_no": "In the {v}", "venue": "At {v}"},
              "bowl": {"bat_hand": "To {v}", "phase_no": "In the {v}", "venue": "At {v}"}}
# role -> metric: (rate numerator column, higher rate is better, label, formatter of the shown value)
METRICS = {
    "bat": {"sr": ("runs", True, "strike rate"), "bpd": ("outs", False, "balls per dismissal"),
            "dot": ("dots", False, "dot balls"), "bdry": ("bd", True, "boundary balls")},
    "bowl": {"econ": ("runs", False, "economy"), "bpw": ("outs", True, "balls per wicket"),
             "dot": ("dots", True, "dot balls"), "bdry": ("bd", False, "boundaries conceded")},
}


def _split_totals(b, role, col):
    """Balls, runs, dismissals, dots and boundary balls per situation (CLAUDE.md rules)."""
    if role == "bat":
        b = b.assign(n=b["faced"], r=b["batsman_runs"], o=b["batter_out"], d=b["bat_dot"],
                     x=b["faced"] & (b["four"] | b["six"]))
    else:
        b = b.assign(n=b["legal"], r=b["conceded"], o=b["bowler_wkt"], d=b["bowl_dot"],
                     x=b["legal"] & (b["four"] | b["six"]))
    if col == "venue":
        b = b.assign(venue=b["venue_name"].map(ground))
    g = b.groupby(col).agg(balls=("n", "sum"), runs=("r", "sum"), outs=("o", "sum"), dots=("d", "sum"),
                           bd=("x", "sum"))
    return g.drop(index=[UNKNOWN, 0], errors="ignore")


@st.cache_data(show_spinner="Working out the PSL averages", max_entries=40)
def league_splits(role, col, lo, hi):
    """PSL totals per situation in the chosen seasons (the comparison for every player)."""
    return _split_totals(in_seasons(balls(), lo, hi), role, col)


def _show(metric, num, balls):
    """The shown value of a metric from totals."""
    if metric in ("sr",):
        return div(num, balls, 100).item()
    if metric == "econ":
        return div(num, balls, 6).item()
    if metric in ("bpd", "bpw"):
        return div(balls, num).item()
    return div(num, balls, 100).item()          # dot and boundary percentages


def _fmt_metric(metric, v):
    if v is None or pd.isna(v):
        return "-"
    if metric == "econ":
        return f"{v:.2f}"
    if metric in ("dot", "bdry"):
        return f"{v:.1f}%"
    return f"{v:.1f}"


def strengths(pid, lo, hi, role, min_balls=MIN_SPLIT_BALLS, k=SHRINK_BALLS):
    """Every (situation, metric) with at least min_balls, compared with the PSL average for the same
    situation. The player's rate is shrunk to the PSL rate: (x + k * league_rate) / (n + k); the effect
    is the shrunk rate's relative difference from the PSL rate, signed so that positive is good.
    Returns one row per situation and metric, best effect first."""
    mine_b = in_seasons(balls_for(pid), lo, hi)
    mine_b = mine_b[mine_b["batter_id" if role == "bat" else "bowler_id"] == pid]
    rows = []
    pn = phase_names()
    for col, start in SITUATIONS[role].items():
        mine, lg = _split_totals(mine_b, role, col), league_splits(role, col, lo, hi)
        for v, r in mine.iterrows():
            if r["balls"] < min_balls or v not in lg.index:
                continue
            L = lg.loc[v]
            label = pn.get(v, v) if col == "phase_no" else (f"{v}-hand batters" if col == "bat_hand" else v)
            for m, (numcol, higher_good, mname) in METRICS[role].items():
                lrate = L[numcol] / L["balls"]
                if lrate <= 0:
                    continue
                shrunk = (r[numcol] + k * lrate) / (r["balls"] + k)
                effect = (shrunk / lrate - 1) * (1 if higher_good else -1)
                rows.append({"situation": start.format(v=label), "col": col, "value": v, "metric": m,
                             "metric_name": mname, "balls": int(r["balls"]),
                             "player": _show(m, r[numcol], r["balls"]), "psl": _show(m, L[numcol], L["balls"]),
                             "shrunk": _show(m, shrunk * r["balls"], r["balls"]), "effect": effect})
    out = pd.DataFrame(rows)
    return out.sort_values("effect", ascending=False).reset_index(drop=True) if len(out) else out


def top_strengths(pid, lo, hi, role, n=3, min_balls=MIN_SPLIT_BALLS):
    """Top n strengths and weaknesses: the best (or worst) metric per situation, one sentence each."""
    s = strengths(pid, lo, hi, role, min_balls)
    if s.empty:
        return s, s
    best = s[s["effect"] >= MIN_EFFECT].sort_values("effect", ascending=False).drop_duplicates("situation").head(n)
    worst = s[(s["effect"] <= -MIN_EFFECT) & ~s["situation"].isin(best["situation"])]   # one or the other
    worst = worst.sort_values("effect").drop_duplicates("situation").head(n)
    return best, worst


def strength_sentence(r):
    return (f"{r['situation']}: {r['metric_name']} {_fmt_metric(r['metric'], r['player'])} "
            f"v PSL {_fmt_metric(r['metric'], r['psl'])} ({r['balls']:,} balls).")


def effect_bars(rows, key, height=300):
    """Strengths (green, right) and weaknesses (red, left) as one horizontal diverging chart."""
    rows = rows.sort_values("effect")
    labels = [f"{r.situation}: {r.metric_name}" for r in rows.itertuples()]
    vals = (rows["effect"] * 100).round(1)
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation="h", marker_color=[POS if v >= 0 else NEG for v in vals],
                           marker_line=dict(color=CHART_BG, width=2),
                           hovertext=[strength_sentence(r._asdict()) + f" Shrunk: {r.effect * 100:+.1f}% v PSL."
                                      for r in rows.itertuples()], hoverinfo="text"))
    lay = layout(fig, height=height, xtitle="Better or worse than the PSL average (%, after shrinkage)")
    lay.update_yaxes(showgrid=False, automargin=True)
    lay.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor=ZERO)
    show(lay, key)


# ------------------------------------------------------------------ match by match (Player)
def match_rows(pid, lo, hi):
    """One row per match played: batting, bowling, WPA for that match and the result."""
    b = in_seasons(balls_for(pid), lo, hi)
    mp = in_seasons(query("SELECT x.match_id, x.team, x.player_id, m.season, m.date, m.team1, m.team2, "
                          "m.venue_name, m.winner FROM match_players x JOIN matches m USING (match_id)"), lo, hi)
    mine = mp[mp["player_id"] == pid].sort_values("date", ascending=False).copy()
    bat, bowl = b[b["batter_id"] == pid], b[b["bowler_id"] == pid]
    at_crease = set(b.loc[(b["batter_id"] == pid) | (b["non_striker_id"] == pid), "match_id"])
    gb = bat.groupby("match_id").agg(runs=("batsman_runs", "sum"), balls=("faced", "sum"))
    gw = bowl.groupby("match_id").agg(legal=("legal", "sum"), conceded=("conceded", "sum"), wkts=("bowler_wkt", "sum"))
    dism = b[(b["player_dismissed_id"] == pid) & b["out_any"]].drop_duplicates("match_id").set_index("match_id")
    w = query("SELECT match_id, total_wpa FROM wpa_match WHERE player_id = ?", (pid,)).set_index("match_id")["total_wpa"]
    out = pd.DataFrame({"match_id": mine["match_id"].values, "Date": mine["date"].map(date_fmt).values,
                        "Opp": np.where(mine["team1"] == mine["team"], mine["team2"], mine["team1"])})
    out["Opp"] = out["Opp"].map(code)
    mids = out["match_id"]
    out["Runs"] = [gb["runs"].get(m) if m in at_crease else np.nan for m in mids]
    out["Balls"] = [gb["balls"].get(m, 0) if m in at_crease else np.nan for m in mids]
    out["Runs"] = [(0 if m in at_crease and pd.isna(r) else r) for m, r in zip(mids, out["Runs"])]
    out["SR"] = div(out["Runs"], out["Balls"], 100)
    out["How out"] = [how_out(dism.at[m, "dismissal_kind"], dism.at[m, "fielder"], m, dism.at[m, "bowling_team"])
                      if m in dism.index else ("not out" if m in at_crease else "") for m in mids]
    out["Overs"] = [overs_num(gw["legal"].get(m)) if m in gw.index else np.nan for m in mids]
    out["Wkts"] = [gw["wkts"].get(m) if m in gw.index else np.nan for m in mids]
    out["Conceded"] = [gw["conceded"].get(m) if m in gw.index else np.nan for m in mids]
    out["Econ"] = [div(gw["conceded"].get(m), gw["legal"].get(m), 6).item() if m in gw.index else np.nan for m in mids]
    out["WPA"] = [w.get(m, np.nan) for m in mids]
    out["Result"] = np.where(mine["winner"].values == mine["team"].values, "Won",
                             np.where(mine["winner"].fillna("").values == "", "No result or tie", "Lost"))
    return out


def progression(pid, match_id):
    """Ball by ball for one match: the player's batting (cumulative runs by ball faced) and bowling
    (cumulative runs conceded by legal ball), in delivery_no order."""
    b = balls_for(pid)
    b = b[b["match_id"] == match_id].sort_values("delivery_no")
    bat = b[(b["batter_id"] == pid) & b["faced"]].copy()
    bat["n"] = range(1, len(bat) + 1)
    bat["cum"] = bat["batsman_runs"].cumsum()
    out_ball = b[(b["player_dismissed_id"] == pid) & b["out_any"]]
    bowl = b[b["bowler_id"] == pid].copy()
    bowl["n"] = bowl["legal"].cumsum()
    bowl["cum"] = bowl["conceded"].cumsum()
    return bat, out_ball, bowl


def progression_chart(bat, out_ball, bowl, key):
    """Cumulative runs (batting blue line) with fours and sixes (orange) and the dismissal (red); and, for
    a bowler, cumulative runs conceded with wickets (red)."""
    fig = go.Figure()
    if len(bat):
        fig.add_scatter(x=bat["n"], y=bat["cum"], mode="lines", name="Runs scored", line=dict(color=BAT, width=2),
                        hovertemplate="Ball %{x}: %{y} runs<extra></extra>")
        bd = bat[bat["four"] | bat["six"]]
        fig.add_scatter(x=bd["n"], y=bd["cum"], mode="markers", name="Four or six",
                        marker=dict(color=SERIES[1], size=8, line=dict(color=CHART_BG, width=2)),
                        hovertemplate="Ball %{x}: boundary, %{y} runs<extra></extra>")
        if len(out_ball):
            fig.add_scatter(x=[bat["n"].max()], y=[bat["cum"].max()], mode="markers", name="Out",
                            marker=dict(color=NEG, size=11, symbol="x", line=dict(color=CHART_BG, width=1)),
                            hovertemplate="Out after %{x} balls, %{y} runs<extra></extra>")
    if len(bowl):
        fig.add_scatter(x=bowl["n"], y=bowl["cum"], mode="lines", name="Runs conceded (bowling)",
                        line=dict(color=SERIES[2], width=2, dash="dot"),
                        hovertemplate="Legal ball %{x}: %{y} runs conceded<extra></extra>")
        wk = bowl[bowl["bowler_wkt"]]
        fig.add_scatter(x=wk["n"], y=wk["cum"], mode="markers", name="Wicket",
                        marker=dict(color=NEG, size=10, symbol="diamond", line=dict(color=CHART_BG, width=1)),
                        hovertemplate="Wicket at legal ball %{x}<extra></extra>")
    show(layout(fig, height=320, xtitle="Ball", ytitle="Runs", legend=True), key)


# ------------------------------------------------------------------ owner mode: HD image exports
# Only for the owner: the page must be opened with ?owner=<key> where <key> equals OWNER_KEY in Streamlit
# secrets (never in the code or the repo). A visitor sees exactly the normal page: every owner step is behind
# one `if is_owner()`. The key is read once, compared in constant time, remembered for the session and removed
# from the address bar (so a copied link never carries it). A wrong key turns owner mode off.
def owner_check(show_seasons=True):
    """Once per run, from Home.py before the page: owner mode on or off, and per-run export state."""
    ss = st.session_state
    given = st.query_params.get("owner")
    if given is not None:
        try:
            want = str(st.secrets.get("OWNER_KEY", ""))
        except Exception:                      # no secrets file at all (local runs without one)
            want = ""
        ss["_owner"] = bool(want) and hmac.compare_digest(str(given).encode(), want.encode())
        st.query_params.pop("owner", None)
    if ss.get("_owner"):
        ss["_x_n"], ss["_x_section"], ss["_x_subject"], ss["_x_credit"] = 0, "", "", ""
        ss["_x_seasons"] = show_seasons


def is_owner():
    return bool(st.session_state.get("_owner"))


def export_subject(text):
    """The player, team or ground a page is about: printed under the title of its image exports."""
    if is_owner():
        st.session_state["_x_subject"] = str(text or "")


def export_credit(text):
    """An extra data credit for this page's image exports (Insights: ESPNcricinfo)."""
    if is_owner():
        st.session_state["_x_credit"] = str(text or "")


def _export_context(title):
    ss = st.session_state
    title = title or ss.get("_x_section") or "Dugout Data"
    bits = [ss.get("_x_subject", "")]
    if ss.get("_x_seasons", True) and "season_range" in ss:
        bits.append(season_label(*ss["season_range"]))
    bits = [b for b in bits if b]
    credits = ([ss["_x_credit"]] if ss.get("_x_credit") else []) + ["Data: Cricsheet.org | Analysis by Hammad"]
    ss["_x_n"] = ss.get("_x_n", 0) + 1
    name = slug(" ".join([title] + bits)) or "dugout-data"
    return title, " | ".join(bits), credits, f"dd_png_{ss['_x_n']}", f"dugout-data-{name}.png"


def _save_button(make_png, key, file_name):
    """Owner only: 'Save as image'. The PNG is made only when the button is pressed (no cost before)."""
    st.download_button("Save as image", data=make_png, file_name=file_name, mime="image/png", key=key,
                       on_click="ignore", type="tertiary", icon=":material/download:")


def _canvas(width_px, height_px):
    """A matplotlib figure laid out in pixels (y down), white page. Figure, not pyplot: thread safe."""
    from matplotlib.figure import Figure
    fig = Figure(figsize=(width_px / 100, height_px / 100), dpi=100, facecolor=PAGE_BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, width_px)
    ax.set_ylim(height_px, 0)
    return fig, ax


def _pt(px):
    return px * 0.72                          # matplotlib font size in points for a size in pixels at 100 dpi


def _frame(ax, width, height, title, subtitle, credits):
    """Top band, title and subtitle; at the bottom the credit lines and the site name."""
    import matplotlib.patches as mp
    ax.add_patch(mp.Rectangle((0, 0), width, 6, color=HEADER_BG))
    ax.text(32, 44, title, color=INK, fontsize=_pt(24), fontweight="bold", va="center")
    if subtitle:
        ax.text(32, 76, subtitle, color=MUTED, fontsize=_pt(15), va="center")
    y = height - 22
    ax.text(width - 32, y, SITE, color=ACCENT, fontsize=_pt(14), fontweight="bold", va="center", ha="right")
    for line in reversed(credits):
        ax.text(32, y, line, color=MUTED, fontsize=_pt(13), va="center")
        y -= 20


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, facecolor=PAGE_BG)      # 3x the 100 dpi layout: HD
    return buf.getvalue()


def table_png(title, subtitle, credits, heads, rows, numeric):
    """A clean HD PNG of a table: title on top, light theme, header band, zebra rows, numbers right-aligned,
    long text wrapped; credit and site name at the bottom."""
    import textwrap

    import matplotlib.patches as mp
    char, pad, line_h = 7.6, 12, 21                         # 14 px type
    wrapped = [[textwrap.wrap(str(v), 46) or [""] for v in r] for r in rows]
    hwrap = [textwrap.wrap(str(h), 18) or [""] for h in heads]
    widths = []
    for i, h in enumerate(hwrap):
        longest = max([len(x) for x in h] + [len(x) for r in wrapped for x in r[i]])
        widths.append(longest * char + 2 * pad)
    tw = sum(widths)
    width = max(800, int(tw + 64))          # 800: the credit and the site name never meet
    head_h = line_h * max(len(h) for h in hwrap) + 14
    row_hs = [line_h * max(len(c) for c in r) + 12 for r in wrapped]
    top = 104 if subtitle else 80
    height = int(top + head_h + sum(row_hs) + 34 + 20 * len(credits) + 20)
    fig, ax = _canvas(width, height)
    _frame(ax, width, height, title, subtitle, credits)
    x0 = 32

    def cell(x, w, y, lines, num, colour, bold=False):
        for j, ln in enumerate(lines):
            ax.text(x + w - pad if num else x + pad, y + 7 + line_h * (j + 0.5), ln, color=colour,
                    fontsize=_pt(14), fontweight="bold" if bold else "normal", va="center",
                    ha="right" if num else "left")

    ax.add_patch(mp.Rectangle((x0, top), tw, head_h, facecolor=SURFACE_2, lw=0))
    x = x0
    for h, w, num in zip(hwrap, widths, numeric):
        cell(x, w, top, h, num, MUTED, bold=True)
        x += w
    y = top + head_h
    for k, (r, rh) in enumerate(zip(wrapped, row_hs)):
        if k % 2:
            ax.add_patch(mp.Rectangle((x0, y), tw, rh, facecolor=SURFACE, lw=0))
        ax.plot([x0, x0 + tw], [y, y], color=BORDER, lw=0.8)
        x = x0
        for lines, w, num in zip(r, widths, numeric):
            cell(x, w, y, lines, num, INK)
            x += w
        y += rh
    ax.add_patch(mp.Rectangle((x0, top), tw, y - top, facecolor="none", edgecolor=BORDER, lw=1))
    return _png(fig)


_NUMBER = re.compile(r"[+\-]?[\d,]*\.?\d*%?|-")


def cards_png(title, subtitle, credits, items):
    """HD PNG of stats cards (label, value, short note), four per row, the site's card look."""
    import matplotlib.patches as mp
    per, cw, ch, gap = min(4, max(1, len(items))), 250, 128, 16
    rows_n = -(-len(items) // per)
    width = max(800, 64 + per * cw + (per - 1) * gap)
    top = 104 if subtitle else 80
    height = int(top + rows_n * (ch + gap) + 30 + 20 * len(credits) + 20)
    fig, ax = _canvas(width, height)
    _frame(ax, width, height, title, subtitle, credits)
    for i, (label, value, note_) in enumerate(items):
        x, y = 32 + (i % per) * (cw + gap), top + (i // per) * (ch + gap)
        ax.add_patch(mp.FancyBboxPatch((x, y), cw, ch, boxstyle="round,pad=0,rounding_size=10",
                                       facecolor=SURFACE, edgecolor=BORDER, lw=1))
        ax.add_patch(mp.Rectangle((x + 8, y), cw - 16, 3, color=ACCENT))
        ax.text(x + 16, y + 26, str(label).upper(), color=MUTED, fontsize=_pt(12), fontweight="bold", va="center")
        v = str(value)
        size = 30 if len(v) <= 12 else max(15, int(30 * 12 / len(v)))
        ax.text(x + 16, y + 66, v, color=INK, fontsize=_pt(size), fontweight="bold", va="center")
        if note_:
            n = str(note_) if len(str(note_)) <= 32 else str(note_)[:31] + "..."
            ax.text(x + 16, y + 104, n, color=MUTED if _NUMBER.fullmatch(v.strip()) else ACCENT,
                    fontsize=_pt(13), va="center")
    return _png(fig)


def export_table(df, cfg, fmts, title=None, index=False):
    """Owner only: the 'Save as image' button under a table."""
    if index:
        df = df.reset_index()
    cols = list(df.columns)
    heads = [str((cfg.get(c) or {}).get("label") or c) if isinstance(cfg.get(c), dict) else str(c) for c in cols]
    rows = [[_cell_text(v, fmts.get(c), cfg.get(c)) for c, v in zip(cols, r)] for r in df.itertuples(index=False)]
    numeric = [pd.api.types.is_numeric_dtype(df[c]) or (isinstance(cfg.get(c), dict) and
               (cfg[c].get("alignment") == "right" or cfg[c].get("type_config", {}).get("type") == "number"))
               for c in cols]
    t, sub, credits, key, fname = _export_context(title)
    _save_button(lambda: table_png(t, sub, credits, heads, rows, numeric), key, fname)


def export_chart_config(fig, key):
    """Owner only: the site name under the chart, and Plotly's own camera button saving a PNG at 3x (made in
    the browser, so no kaleido)."""
    fig.update_layout(title=dict(text=SITE, x=0.99, xanchor="right", y=0, yanchor="bottom", yref="container", pad=dict(b=8),
                                 font=dict(size=11, color=ACCENT)))
    fig.update_layout(margin_b=(fig.layout.margin.b or 0) + 30)
    return {"displayModeBar": True, "displaylogo": False, "modeBarButtons": [["toImage"]],
            "toImageButtonOptions": {"format": "png", "scale": 3, "filename": f"dugout-data-{slug(key)}"}}


# ------------------------------------------------------------------ share card (the only download)
@st.cache_data(show_spinner="Making the share card", max_entries=100)
def share_card_png(pid, lo, hi):
    """1080 x 1350 PNG (light: white, blue rules): name, teams, seasons, key numbers, 'Dugout Data' and
    'Data: Cricsheet.org'."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = player_summary(pid, lo, hi)
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=PAGE_BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1080)
    ax.set_ylim(1350, 0)
    ax.add_patch(plt.Rectangle((0, 0), 1080, 14, color=HEADER_BG))
    ax.text(72, 110, "Dugout Data", color=INK, fontsize=30, fontweight="bold", va="center")
    ax.text(72, 160, TAGLINE, color=MUTED, fontsize=17, va="center")
    nm = name(pid)
    size = 52 if len(nm) <= 22 else max(30, int(52 * 22 / len(nm)))
    ax.text(72, 300, nm, color=INK, fontsize=size, fontweight="bold", va="center")
    sub = " | ".join(code(t) for t in s["teams"])
    seas = (f"{s['seasons'][0]}" if len(s["seasons"]) == 1 else f"{s['seasons'][0]}-{s['seasons'][-1]}") if s["seasons"] else ""
    ax.text(72, 375, f"{sub}    PSL {seas}", color=MUTED, fontsize=20, va="center")
    items = []
    if s["bat"]:
        items += [("Batting RAA", raa_fmt(s["bat_raa"])), ("Runs", num_fmt(s["runs"])),
                  ("Strike rate", fmt(s["sr"])), ("Average", fmt(s["avg"]))]
    if s["bowl"]:
        items += [("Bowling RAA", raa_fmt(s["bowl_raa"])), ("Wickets", num_fmt(s["wkts"])),
                  ("Economy", fmt(s["econ"], 2)), ("Bowling average", fmt(s["bowl_avg"]))]
    items = items[:8]
    for i, (label, val) in enumerate(items):
        col, row = i % 2, i // 2
        x, y = 72 + col * 480, 470 + row * 190
        ax.add_patch(plt.Rectangle((x, y), 450, 165, facecolor=SURFACE, edgecolor=BORDER, linewidth=2))
        ax.add_patch(plt.Rectangle((x, y), 450, 6, color=ACCENT))
        ax.text(x + 28, y + 50, label.upper(), color=MUTED, fontsize=15, fontweight="bold", va="center")
        ax.text(x + 28, y + 112, val, color=INK, fontsize=40, fontweight="bold", va="center")
    ax.text(72, 1255, "RAA: runs above an average men's T20 player in the same season and phase.",
            color=FAINT, fontsize=14, va="center")
    ax.text(72, 1300, "Data: Cricsheet.org | Analysis by Hammad", color=MUTED, fontsize=16, va="center")
    ax.text(1008, 1300, "Dugout Data", color=ACCENT, fontsize=16, fontweight="bold", va="center", ha="right")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=PAGE_BG)
    plt.close(fig)
    return buf.getvalue()


# ------------------------------------------------------------------ charts
def layout(fig, height=320, xtitle=None, ytitle=None, legend=False, credit=None):
    """Common chart look (light: white ground, dark text), with the Dugout Data watermark (and an optional data credit)."""
    fig.add_annotation(text="Dugout Data", xref="paper", yref="paper", x=1, y=1, xanchor="right", yanchor="top",
                       showarrow=False, font=dict(size=11, color=MARK))
    if credit:
        fig.add_annotation(text=credit, xref="paper", yref="paper", x=0, y=-0.02, xanchor="left", yanchor="top",
                           yshift=-28, showarrow=False, font=dict(size=10, color=MUTED))
    fig.update_layout(template="plotly_white", height=height,
                      margin=dict(l=8, r=8, t=30 if legend else 22, b=52 if credit else 8),
                      font=dict(family="Source Sans Pro, Source Sans 3, Arial, sans-serif", size=13, color=INK),
                      paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG, barcornerradius=4, bargap=0.25,
                      bargroupgap=0.08, showlegend=legend,
                      hoverlabel=dict(bgcolor=CHART_BG, bordercolor=BORDER, font_color=INK),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=MUTED)))
    fig.update_xaxes(title=xtitle, showgrid=False, linecolor=BORDER, tickfont=dict(color=MUTED), automargin=True)
    fig.update_yaxes(title=ytitle, title_font=dict(color=MUTED, size=12), gridcolor=GRID, showgrid=True,
                     zeroline=True, zerolinecolor=ZERO, linecolor=BORDER, tickfont=dict(color=MUTED),
                     automargin=True)
    return fig


def show(fig, key):
    # No zoom or pan by touch or mouse: on a phone a finger dragging over a chart drew a zoom box and
    # zoomed in far (tester video, 2026-11-04). Hover and tap labels still work.
    fig.update_layout(dragmode=False)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    config = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "showAxisDragHandles": False}
    if is_owner():
        config.update(export_chart_config(fig, key))
    st.plotly_chart(fig, config=config, key=key, width="stretch", theme=None)


def polarity_bars(x, y, hover, ytitle, key, height=300, credit=None):
    """One measure where the sign matters (RAA, WPA): green above average, red below."""
    y = np.asarray(y, dtype=float)
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=[POS if v >= 0 else NEG for v in y],
                           marker_line=dict(color=CHART_BG, width=2), hovertext=hover, hoverinfo="text"))
    show(layout(fig, height=height, ytitle=ytitle, credit=credit), key)


def grouped_bars(x, series, ytitle, key, height=320, credit=None):
    """series: list of (label, values). Up to 3 series, fixed colour order, legend shown."""
    fig = go.Figure()
    for i, (label, vals) in enumerate(series):
        fig.add_bar(name=label, x=x, y=vals, marker_color=SERIES[i], marker_line=dict(color=CHART_BG, width=2),
                    hovertemplate=f"%{{x}}<br>{label}: %{{y:,.2f}}<extra></extra>")
    fig.update_layout(barmode="group")
    show(layout(fig, height=height, ytitle=ytitle, legend=len(series) > 1, credit=credit), key)


# ------------------------------------------------------------------ scoring zones (Insights only)
# Zones from the batter's view (left-handers mirrored when the private aggregates are built), drawn
# from behind the batter: straight hits at the top, off side on the right, fine on the bottom.
ZONES = {5: "Long-off", 6: "Cover", 7: "Point", 8: "Third man", 1: "Fine leg", 2: "Square leg",
         3: "Midwicket", 4: "Long-on"}
ZONE_ANGLE = {5: 22.5, 6: 67.5, 7: 112.5, 8: 157.5, 1: 202.5, 2: 247.5, 3: 292.5, 4: 337.5}
ZONE_MEASURES = {"runs": "Runs", "fours": "Fours", "sixes": "Sixes"}
SEQ = [[0, "#EEF4FC"], [1, "#7FAEE9"]]                          # pale to mid blue (dark text AA on both)
DIV = [[0, "#EE9A9A"], [0.5, SURFACE], [1, "#7FAEE9"]]          # below average, level, above average


def zone_shares(z):
    """Totals per zone 1 to 8 from zone aggregate rows, with each measure's share (%) of the
    total that has a zone. Zone 0 (no location) and NULL are left out of the shares."""
    g = z[z["zone"].between(1, 8)].groupby("zone")[["balls", "runs", "fours", "sixes", "caught"]].sum()
    g = g.reindex(list(ZONES), fill_value=0).astype(int)
    for m in ZONE_MEASURES:
        g[f"{m}_share"] = div(g[m], g[m].sum(), 100)
    g["name"] = [ZONES[k] for k in g.index]
    return g


def field_chart(values, labels, hover, key, diverging=False, scale_max=None, credit=None, height=400):
    """8-sector field chart. values: per zone (ZONES order); labels: text in each sector."""
    vals = np.asarray(values, dtype=float)
    top = scale_max or (np.nanmax(np.abs(vals)) if np.isfinite(vals).any() and np.nanmax(np.abs(vals)) > 0 else 1)
    fig = go.Figure(go.Barpolar(
        theta=[ZONE_ANGLE[k] for k in ZONES], r=[0.86] * 8, base=0.14, width=[44] * 8,
        marker=dict(color=np.nan_to_num(vals), colorscale=DIV if diverging else SEQ,
                    cmin=-top if diverging else 0, cmax=top, line=dict(color=CHART_BG, width=2)),
        hovertext=hover, hoverinfo="text"))
    fig.add_scatterpolar(theta=[ZONE_ANGLE[k] for k in ZONES], r=[0.62] * 8, mode="text", text=labels,
                         textfont=dict(color=INK, size=12), hoverinfo="skip")
    lay = layout(fig, height=height, credit=credit)
    lay.update_layout(polar=dict(bgcolor=CHART_BG, hole=0,
                                 angularaxis=dict(rotation=90, direction="clockwise", showticklabels=False,
                                                  showgrid=False, linecolor=BORDER, ticks=""),
                                 radialaxis=dict(visible=False, range=[0, 1])),
                      margin=dict(l=24, r=24, t=42, b=60 if credit else 24))
    for text, x in (("Leg side", 0.0), ("Off side", 1.0)):        # bottom corners, clear of the circle
        lay.add_annotation(text=text, xref="paper", yref="paper", x=x, y=0.0, showarrow=False, yanchor="bottom",
                           xanchor="left" if x < 0.5 else "right", font=dict(size=11, color=MUTED))
    lay.add_annotation(text="Straight", xref="paper", yref="paper", x=0.5, y=1.0, yanchor="bottom",
                       showarrow=False, font=dict(size=11, color=MUTED))
    show(lay, key)


def compare_table(rows, a_label, b_label, better=None):
    """HTML comparison table (no download toolbar). rows: (metric, a_text, b_text, a_num, b_num, higher_is_better)."""
    head = f"<tr><th></th><th>{html.escape(a_label)}</th><th>{html.escape(b_label)}</th></tr>"
    body = []
    for metric, at, bt, an, bn, hib in rows:
        ca = cb = ""
        if hib is not None and an is not None and bn is not None and not (pd.isna(an) or pd.isna(bn)) and an != bn:
            a_wins = (an > bn) if hib else (an < bn)
            ca, cb = (' class="best"', "") if a_wins else ("", ' class="best"')
        body.append(f"<tr><td>{html.escape(metric)}</td><td{ca}>{html.escape(at)}</td><td{cb}>{html.escape(bt)}</td></tr>")
    st.markdown(f'<table class="dd-compare">{head}{"".join(body)}</table>', unsafe_allow_html=True)
    if is_owner():                     # owner mode only: "Save as image" (title: the section above)
        cells = [[m, a, b] for m, a, b, *_ in rows]
        t, sub, credits, key, fname = _export_context(f"{a_label} v {b_label}: "
                                                      + (st.session_state.get("_x_section") or "Compare"))
        _save_button(lambda: table_png(t, sub, credits, ["", a_label, b_label], cells, [False, True, True]),
                     key, fname)
