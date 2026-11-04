"""
common.py - shared code for the Dugout Data app (design system: docs/STYLE.md).

READ-ONLY: opens psl.sqlite (and, for Insights, the aggregate file) in read-only mode; where
they are found or downloaded is decided by data_files.py. No MySQL, no writes.
Protection: no download buttons except the branded share card (a PNG with "Dugout Data"
and "Data: Cricsheet.org"), dataframe toolbar hidden, at most 50 rows per table,
"Dugout Data" watermark on every chart.
Data rules (CLAUDE.md): innings 1 and 2 only; phase = over_no + 1 mapped to this_phases;
balls in delivery_no order; ball faced excludes wides; legal ball excludes wides and
no-balls; runs conceded include wides and no-ball extras, not byes or leg-byes (no-ball
with byes: 1 run to the bowler); bowler wickets are bowled, caught, lbw, stumped,
caught and bowled, hit wicket. Styles come only from public_style (Wikipedia/DBpedia).
"""

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
BOWLER_KINDS = ["bowled", "caught", "lbw", "stumped", "caught and bowled", "hit wicket"]
NOT_OUT_KINDS = ["retired hurt", "retired not out"]
STYLE_ORDER = ["Right-arm Pace", "Left-arm Pace", "Right-arm Off-spin", "Right-arm Leg-spin",
               "Left-arm Orthodox", "Left-arm Chinaman", "Unknown"]
UNKNOWN = "Unknown"
TEAM_CODES = {"Karachi Kings": "KK", "Lahore Qalandars": "LQ", "Islamabad United": "IU", "Peshawar Zalmi": "PZ",
              "Quetta Gladiators": "QG", "Multan Sultans": "MS", "Hyderabad Kingsmen": "HK", "Rawalpindiz": "RP"}
TEAM_LEGEND = ", ".join(f"{v} {k}" for k, v in TEAM_CODES.items())

# ---- Colours (docs/STYLE.md): dark by default. UI: one accent. Charts: validated dark data palette.
ACCENT = "#4f94e5"            # the one accent: UI, sliders, tabs, card rules, chart highlight
PAGE_BG, SURFACE, SURFACE_2, BORDER = "#111212", "#1a1a19", "#222220", "#2f2f2c"
INK, MUTED, FAINT = "#f0efec", "#c3c2b7", "#9a998f"
GRID = "#2c2c29"
SERIES = [ACCENT, "#d95926", "#199e70"]             # accent blue, orange, aqua (fixed order, dark steps)
POS, NEG = ACCENT, "#e66767"                        # diverging poles: above / below average

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
[data-testid="stHeader"] {{ background: {PAGE_BG}; border-bottom: 1px solid {BORDER}; }}
.block-container {{ max-width: 1120px; padding: 4.25rem 1.5rem 3rem 1.5rem !important; }}
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
a {{ color: {ACCENT}; }}

/* ---- top navigation: light text, subtle hover, clear active page (works even without config.toml) ---- */
[data-testid="stTopNav"] {{ gap: .15rem; }}
[data-testid="stTopNavLink"], [data-testid="stSidebarNavLink"] {{ color: {INK} !important; background: transparent !important;
    border-radius: 8px; border-bottom: 2px solid transparent; }}
[data-testid="stTopNavLink"] *, [data-testid="stSidebarNavLink"] * {{ color: {INK} !important; }}
[data-testid="stTopNavLink"]:hover, [data-testid="stSidebarNavLink"]:hover {{ background: {SURFACE_2} !important; }}
[data-testid="stTopNavLink"][aria-current="page"], [data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: {SURFACE_2} !important; border-bottom-color: {ACCENT}; }}
[data-testid="stTopNavLink"][aria-current="page"] *, [data-testid="stSidebarNavLink"][aria-current="page"] * {{
    color: {ACCENT} !important; font-weight: 700; }}

/* ---- widget labels and tabs: readable on dark (WCAG AA) ---- */
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
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.dd-card-value {{ color: {INK}; font-size: 1.65rem; font-weight: 700; line-height: 1.2; margin-top: .15rem;
                  font-variant-numeric: tabular-nums; white-space: nowrap; }}
/* A name or phrase in a card never wraps: one line, smaller type, ellipsis as a last resort. */
.dd-card-value.text {{ font-size: 1.12rem; line-height: 1.55; overflow: hidden; text-overflow: ellipsis; }}
.dd-card-help {{ color: {FAINT}; font-size: .78rem; line-height: 1.35; margin-top: .2rem; }}
.dd-card-detail {{ color: {MUTED}; font-size: .8rem; margin-top: .15rem; white-space: nowrap; overflow: hidden;
                   text-overflow: ellipsis; font-variant-numeric: tabular-nums; }}
.dd-card-sub {{ color: {ACCENT}; font-size: .9rem; font-weight: 700; margin-top: .1rem; white-space: nowrap;
                font-variant-numeric: tabular-nums; }}

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
[data-testid="stPlotlyChart"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: .4rem; }}

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
  .dd-card-value.text {{ font-size: .98rem; line-height: 1.75; }}
  .dd-section {{ margin-top: 1.6rem; }}
  .dd-compare th, .dd-compare td {{ padding: .45rem .5rem; font-size: .85rem; }}
  /* season bar: one full-width row from the left edge, range label beside the buttons */
  .st-key-dd_season_bar {{ justify-content: flex-start !important; flex-wrap: nowrap !important;
                           gap: .3rem !important; width: 100% !important; }}
  .st-key-dd_season_bar > div:first-child {{ flex: 1 1 auto !important; min-width: 0; }}
  .st-key-dd_season_bar [data-testid="stButtonGroup"] > div {{ width: 100%; flex-wrap: nowrap !important; }}
  .st-key-dd_season_bar [data-testid="stButtonGroup"] button {{ flex: 1 1 auto; padding: .25rem .45rem;
                                                                min-height: 2.1rem; }}
  .st-key-dd_season_bar button p {{ font-size: .8rem !important; white-space: nowrap; }}
  .st-key-dd_season_bar [data-testid="stPopover"] button {{ padding: .25rem .3rem; min-height: 2.1rem; }}
  .dd-seasons {{ font-size: .74rem; padding: .1rem .35rem; }}
  /* three presets, then one compact button showing the range that opens the Custom slider */
  .st-key-dd_season_bar > div:has([data-testid="stPopover"]):not(.st-key-dd_season_phone),
  .st-key-dd_season_bar > div:has(.dd-seasons) {{ display: none !important; }}
  .st-key-dd_season_bar > .st-key-dd_season_phone {{ display: block !important; flex: 0 0 auto !important; }}
  /* tabs: all fit on one line */
  .stTabs [role="tablist"] {{ gap: 0; }}
  .stTabs [role="tab"] {{ padding: .4rem .3rem; }}
  .stTabs [role="tab"] p {{ font-size: .84rem; }}
}}
@media (max-width: 380px) {{
  .stTabs [role="tab"] {{ padding: .4rem .2rem; }}
  .stTabs [role="tab"] p {{ font-size: .78rem; }}
  .st-key-dd_season_bar button p {{ font-size: .74rem !important; }}
  .st-key-dd_season_bar [data-testid="stButtonGroup"] button {{ padding: .25rem .3rem; }}
}}
/* ---- phone navigation: page chips, always visible (hidden on desktop, where the top menu shows) ---- */
/* Streamlit wraps the chip row in a layout box: hidden too, or the empty box adds a 16 px gap on desktop */
.st-key-dd_mobile_nav, .st-key-dd_season_phone,
[data-testid="stLayoutWrapper"]:has(> .st-key-dd_mobile_nav) {{ display: none !important; }}
@media (max-width: 768px) {{
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
def header():
    """Same header on every page: brand, tagline, season filter. Drawn once by Home.py.
    The season range is in the URL as ?seasons=2016-2026."""
    # The link wins on the first run, and when a ?seasons= link that differs from what this session last
    # wrote is opened inside a running session. An empty link (page switches clear it) changes nothing.
    st.session_state.setdefault("_slider_gen", 0)
    url = st.query_params.get("seasons", "")
    if "season_range" not in st.session_state or (url and url != st.session_state.get("_seasons_url")):
        rng = (SEASONS[0], SEASONS[-1])
        m = re.fullmatch(r"(\d{4})-(\d{4})", url)
        if m and int(m.group(1)) in SEASONS and int(m.group(2)) in SEASONS and int(m.group(1)) <= int(m.group(2)):
            rng = (int(m.group(1)), int(m.group(2)))
        st.session_state.season_range = rng
        st.session_state._slider_gen += 1

    def keep(key):
        st.session_state.season_range = tuple(st.session_state[key])

    def pick():
        choice = st.session_state._season_preset
        if choice in SEASON_PRESETS:
            st.session_state.season_range = SEASON_PRESETS[choice]
            st.session_state._slider_gen += 1

    # The highlighted preset follows the range (from a link, the slider or a preset). The Custom slider
    # gets a new key whenever the range changes outside it (preset or link), so it always opens on the
    # range shown. Before, a slider opened once kept its old range: after a preset, choosing that old
    # range again was no change at all, so the page stayed on the preset (bug report 2026-11-03).
    st.session_state._season_preset = preset_for(st.session_state.season_range)
    slider_key = f"_season_widget_{st.session_state._slider_gen}"
    left, right = st.columns([2, 3], vertical_alignment="center")
    left.markdown('<div class="dd-brand"><b>Dugout<span> </span>Data</b></div>', unsafe_allow_html=True)
    with right.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small",
                         key="dd_season_bar"):
        st.segmented_control("Seasons", list(SEASON_PRESETS), key="_season_preset", on_change=pick,
                             label_visibility="collapsed", help="Every page shows the PSL seasons chosen here.")
        with st.popover("Custom", type="tertiary" if preset_for(st.session_state.season_range) else "primary"):
            st.select_slider("Seasons", options=SEASONS, value=tuple(st.session_state.season_range),
                             key=slider_key, on_change=keep, args=(slider_key,),
                             help="Choose the first and last season.")
        lo, hi = st.session_state.season_range
        rng_txt = str(lo) if lo == hi else f"{lo}-{hi}"
        st.markdown(f'<span class="dd-seasons">{rng_txt}</span>', unsafe_allow_html=True)
        # Phone only (CSS): Custom and the range label become one compact button that shows the range and
        # opens the same slider. Hidden on desktop, where Custom and the label above show as before.
        phone_key = f"_season_widget_m_{st.session_state._slider_gen}"
        with st.popover(rng_txt, type="tertiary" if preset_for(st.session_state.season_range) else "primary",
                        key="dd_season_phone"):
            st.select_slider("Seasons", options=SEASONS, value=tuple(st.session_state.season_range),
                             key=phone_key, on_change=keep, args=(phone_key,),
                             help="Choose the first and last season.")
    st.markdown('<hr class="dd-rule">', unsafe_allow_html=True)
    want = f"{lo}-{hi}" if (lo, hi) != (SEASONS[0], SEASONS[-1]) else ""
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



SEASON_PRESETS = {"All seasons": (SEASONS[0], SEASONS[-1]), "Last 3": (SEASONS[-3], SEASONS[-1]),
                  str(SEASONS[-1]): (SEASONS[-1], SEASONS[-1])}


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
    st.session_state.setdefault("season_range", (SEASONS[0], SEASONS[-1]))
    return st.session_state.season_range


season_widget = header   # older name


def section(title, help_text=""):
    st.markdown(f'<p class="dd-section">{html.escape(title)}</p>'
                + (f'<p class="dd-section-help">{html.escape(help_text)}</p>' if help_text else ""),
                unsafe_allow_html=True)


def footer(copyright=False, extra=""):
    info = export_info()
    # Credit line, then the details on their own lines (separate blocks, so they never run together).
    lines = ([html.escape(extra)] if extra else []) + ([html.escape(COPYRIGHT)] if copyright else []) + [
        f'Data export {html.escape(date_fmt(info.get("exported_at_utc", "")[:10]))}. Cricsheet data is shared '
        f'under the ODC-BY licence; batting and bowling styles come from Wikipedia and DBpedia (CC BY-SA).']
    st.markdown(f'<div class="dd-footer"><div class="dd-footer-credit">{FOOTER}</div>'
                + "".join(f'<div class="dd-footer-small">{x}</div>' for x in lines) + '</div>',
                unsafe_allow_html=True)


def cards(items, lead=False, detail=False):
    """items: (label, value, note). By default a card shows its label and value only; the note
    becomes the card's hover tooltip. A value that is not a number (a name, a role) is shown on
    one line in smaller type, with the note as one short figure below it (e.g. '+2,033 RAA').
    detail=True (Player, Matchups) shows the note as a short second line under the number too,
    because phones cannot show hover tooltips ('3,377 balls', 'HS 115', '10 fours, 5 sixes').
    lead=True adds the accent rule (headline cards)."""
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


tiles = cards   # older name


def note(text):
    st.markdown(f'<p class="dd-note">{html.escape(text)}</p>', unsafe_allow_html=True)


def empty(title, hint=""):
    """Friendly empty state."""
    st.markdown(f'<div class="dd-empty"><b>{html.escape(title)}</b>{html.escape(hint)}</div>', unsafe_allow_html=True)


# ---- tables: printf formats in column_config become Python formats with thousands separators
_PY_FMT = {"%d": "{:,.0f}", "%.1f": "{:,.1f}", "%.2f": "{:,.2f}", "%.1f%%": "{:,.1f}%", "%+.2f": "{:+,.2f}"}


def table(df, column_config=None, **kwargs):
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
    if n > MAX_ROWS:
        note(f"Showing the first {MAX_ROWS} of {n} rows. Narrow the seasons or raise the minimum to see others.")


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
    p = query("SELECT p.player_id, p.display_name, p.short_name, s.batting_hand, s.bowling_style, s.source_url "
              "FROM players p LEFT JOIN public_style s USING (player_id)")
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
    # catches: caught (fielder, wicketkeepers included) and caught and bowled (the bowler)
    ct = query(f"""SELECT d.match_id, m.season, d.bowling_team team, d.dismissal_kind kind, d.fielder, d.bowler_id
                   {_REC_BASE} AND d.dismissal_kind IN ('caught', 'caught and bowled')""", args)
    sq = squad_ids()
    seasons_sq = _squad_by_team_season()
    catcher, unresolved = [], 0
    for r in ct.itertuples(index=False):
        if r.kind == "caught and bowled":
            catcher.append(r.bowler_id)
            continue
        nm = str(r.fielder or "").split(",")[0].strip().replace(" (sub)", "")
        pid = (sq.get((r.match_id, r.team, nm)) or unique_ids().get(nm)
               or seasons_sq.get((r.team, r.season, nm)) or seasons_sq.get((r.team, None, nm)))
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
    """Strengths (accent, right) and weaknesses (red, left) as one horizontal diverging chart."""
    rows = rows.sort_values("effect")
    labels = [f"{r.situation}: {r.metric_name}" for r in rows.itertuples()]
    vals = (rows["effect"] * 100).round(1)
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation="h", marker_color=[POS if v >= 0 else NEG for v in vals],
                           marker_line=dict(color=SURFACE, width=2),
                           hovertext=[strength_sentence(r._asdict()) + f" Shrunk: {r.effect * 100:+.1f}% v PSL."
                                      for r in rows.itertuples()], hoverinfo="text"))
    lay = layout(fig, height=height, xtitle="Better or worse than the PSL average (%, after shrinkage)")
    lay.update_yaxes(showgrid=False, automargin=True)
    lay.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor="#5f5e58")
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
    """Cumulative runs (accent line) with fours and sixes (orange) and the dismissal (red); and, for
    a bowler, cumulative runs conceded with wickets (red)."""
    fig = go.Figure()
    if len(bat):
        fig.add_scatter(x=bat["n"], y=bat["cum"], mode="lines", name="Runs scored", line=dict(color=ACCENT, width=2),
                        hovertemplate="Ball %{x}: %{y} runs<extra></extra>")
        bd = bat[bat["four"] | bat["six"]]
        fig.add_scatter(x=bd["n"], y=bd["cum"], mode="markers", name="Four or six",
                        marker=dict(color=SERIES[1], size=8, line=dict(color=SURFACE, width=2)),
                        hovertemplate="Ball %{x}: boundary, %{y} runs<extra></extra>")
        if len(out_ball):
            fig.add_scatter(x=[bat["n"].max()], y=[bat["cum"].max()], mode="markers", name="Out",
                            marker=dict(color=NEG, size=11, symbol="x", line=dict(color=SURFACE, width=1)),
                            hovertemplate="Out after %{x} balls, %{y} runs<extra></extra>")
    if len(bowl):
        fig.add_scatter(x=bowl["n"], y=bowl["cum"], mode="lines", name="Runs conceded (bowling)",
                        line=dict(color=SERIES[2], width=2, dash="dot"),
                        hovertemplate="Legal ball %{x}: %{y} runs conceded<extra></extra>")
        wk = bowl[bowl["bowler_wkt"]]
        fig.add_scatter(x=wk["n"], y=wk["cum"], mode="markers", name="Wicket",
                        marker=dict(color=NEG, size=10, symbol="diamond", line=dict(color=SURFACE, width=1)),
                        hovertemplate="Wicket at legal ball %{x}<extra></extra>")
    show(layout(fig, height=320, xtitle="Ball", ytitle="Runs", legend=True), key)


# ------------------------------------------------------------------ share card (the only download)
@st.cache_data(show_spinner="Making the share card", max_entries=100)
def share_card_png(pid, lo, hi):
    """1080 x 1350 PNG: name, teams, seasons, key numbers, 'Dugout Data' and 'Data: Cricsheet.org'."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = player_summary(pid, lo, hi)
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=PAGE_BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1080)
    ax.set_ylim(1350, 0)
    ax.add_patch(plt.Rectangle((0, 0), 1080, 14, color=ACCENT))
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
    """Common chart look (dark), with the Dugout Data watermark (and an optional data credit)."""
    fig.add_annotation(text="Dugout Data", xref="paper", yref="paper", x=1, y=1, xanchor="right", yanchor="top",
                       showarrow=False, font=dict(size=11, color="#6f6e67"))
    if credit:
        fig.add_annotation(text=credit, xref="paper", yref="paper", x=0, y=-0.02, xanchor="left", yanchor="top",
                           yshift=-28, showarrow=False, font=dict(size=10, color=MUTED))
    fig.update_layout(template="plotly_dark", height=height,
                      margin=dict(l=8, r=8, t=30 if legend else 22, b=52 if credit else 8),
                      font=dict(family="Source Sans Pro, Source Sans 3, Arial, sans-serif", size=13, color=INK),
                      paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, barcornerradius=4, bargap=0.25,
                      bargroupgap=0.08, showlegend=legend,
                      hoverlabel=dict(bgcolor=SURFACE_2, bordercolor=BORDER, font_color=INK),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=MUTED)))
    fig.update_xaxes(title=xtitle, showgrid=False, linecolor=BORDER, tickfont=dict(color=MUTED))
    fig.update_yaxes(title=ytitle, title_font=dict(color=MUTED, size=12), gridcolor=GRID, showgrid=True,
                     zeroline=True, zerolinecolor="#5f5e58", linecolor=BORDER, tickfont=dict(color=MUTED))
    return fig


def show(fig, key):
    # No zoom or pan by touch or mouse: on a phone a finger dragging over a chart drew a zoom box and
    # zoomed in far (tester video, 2026-11-04). Hover and tap labels still work.
    fig.update_layout(dragmode=False)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False,
                                 "showAxisDragHandles": False}, key=key, width="stretch", theme=None)


def polarity_bars(x, y, hover, ytitle, key, height=300, credit=None):
    """One measure where the sign matters (RAA, WPA): blue above average, red below."""
    y = np.asarray(y, dtype=float)
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=[POS if v >= 0 else NEG for v in y],
                           marker_line=dict(color=SURFACE, width=2), hovertext=hover, hoverinfo="text"))
    show(layout(fig, height=height, ytitle=ytitle, credit=credit), key)


def grouped_bars(x, series, ytitle, key, height=320, credit=None):
    """series: list of (label, values). Up to 3 series, fixed colour order, legend shown."""
    fig = go.Figure()
    for i, (label, vals) in enumerate(series):
        fig.add_bar(name=label, x=x, y=vals, marker_color=SERIES[i], marker_line=dict(color=SURFACE, width=2),
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
SEQ = [[0, "#1d2733"], [1, "#2e6bb8"]]                          # dark to deep accent (white text AA)
DIV = [[0, "#b84a4a"], [0.5, SURFACE_2], [1, "#2e6bb8"]]        # below average, level, above average


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
                    cmin=-top if diverging else 0, cmax=top, line=dict(color=SURFACE, width=2)),
        hovertext=hover, hoverinfo="text"))
    fig.add_scatterpolar(theta=[ZONE_ANGLE[k] for k in ZONES], r=[0.62] * 8, mode="text", text=labels,
                         textfont=dict(color=INK, size=12), hoverinfo="skip")
    lay = layout(fig, height=height, credit=credit)
    lay.update_layout(polar=dict(bgcolor=SURFACE, hole=0,
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
