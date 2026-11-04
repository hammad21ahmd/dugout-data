"""
insights.py - Insights: line and length, scoring zones and bowler variations for PSL 2018
and 2020 to 2026.
READ-ONLY. Reads only the private aggregate file (tools/build_insights.py): totals per
player, season, role, line or length. No ball-level rows exist in it or on this page.
Shown only when common.SHOW_INSIGHTS is True. Every chart and the page carry the credit.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app/ folder, for common.py

import common as c  # noqa: E402

c.page("Insights", "Where bowlers pitch it, where batters score, and how each length goes.")
st.markdown(f'<span class="dd-chip"><b>{c.INSIGHTS_CREDIT}</b></span>', unsafe_allow_html=True)
c.note("The line, length and shot data on this page come from ESPNcricinfo ball-by-ball records. "
       "They are not Dugout Data's own data; Dugout Data only adds them up per player and season.")
if not c.insights_available():
    c.empty("Insights are not available in this version of the site.", " The rest of Dugout Data works as usual.")
    c.footer(extra=c.INSIGHTS_CREDIT)
    st.stop()

LENGTHS = {"YORKER": "Yorker", "FULL_TOSS": "Full toss", "FULL": "Full", "GOOD_LENGTH": "Good length",
           "SHORT_OF_A_GOOD_LENGTH": "Short of a length", "SHORT": "Short"}
LINES = {"WIDE_OUTSIDE_OFFSTUMP": "Wide outside off", "OUTSIDE_OFFSTUMP": "Outside off",
         "ON_THE_STUMPS": "On the stumps", "DOWN_LEG": "Down leg", "WIDE_DOWN_LEG": "Wide down leg"}
LABELS = {"length": LENGTHS, "line": LINES}
AVAILABLE = [2018, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

lo, hi = c.season_filter()
seasons = [s for s in AVAILABLE if lo <= s <= hi]
c.note("Covers PSL 2018 and 2020 to 2026 (2016 and 2017 have no line and length data; 2019 has too "
       "little). Only balls whose runs and wickets agree with Cricsheet are counted. "
       + (f"Showing {', '.join(map(str, seasons))}." if seasons else ""))
if not seasons:
    c.empty("No line and length data for these seasons.", " Choose a range that includes 2018 or 2020 to 2026.")
    c.footer(extra=c.INSIGHTS_CREDIT)
    st.stop()

agg = c.insights("SELECT * FROM agg")
agg = agg[agg["season"].isin(seasons)]
league = agg[agg["player_id"] == "ALL"]
players = agg[agg["player_id"] != "ALL"]


def summary(df, role, dim):
    """Totals per category with share of balls and the role's rate."""
    g = df[(df["role"] == role) & (df["dim"] == dim)].groupby("category").agg(
        balls=("balls", "sum"), runs=("runs", "sum"), outs=("outs", "sum")).reindex(list(LABELS[dim])).fillna(0)
    g["share"] = c.div(g["balls"], g["balls"].sum(), 100)
    if role == "bat":
        g["rate"] = c.div(g["runs"], g["balls"], 100)          # strike rate
    else:
        g["rate"] = c.div(g["runs"], g["balls"], 6)            # runs per over (all deliveries)
    g["balls_per_out"] = c.div(g["balls"], g["outs"])
    g["label"] = [LABELS[dim][k] for k in g.index]
    return g


tab_league, tab_bat, tab_bowl, tab_zone, tab_var = st.tabs(
    ["League", "Batter", "Bowler", "Scoring zones", "Bowler variations"])

with tab_league:
    s = summary(league, "bat", "length")
    c.section("Strike rate by length", "All PSL batters, balls faced. " + c.HELP["SR"])
    c.grouped_bars(list(s["label"]), [("Strike rate", s["rate"].values)], "Strike rate", key="lg_sr",
                   credit=c.INSIGHTS_CREDIT)
    w = summary(league, "bowl", "length")
    lt = pd.DataFrame({"Length": s["label"], "Share of balls %": w["share"].values, "Strike rate": s["rate"].values,
                       "Dismissals": s["outs"].astype(int).values, "Balls per dismissal": s["balls_per_out"].values})
    c.table(lt, column_config={"Length": c.col_text(), "Share of balls %": c.col_pct(),
                               "Strike rate": c.col_1(help=c.HELP["SR"]), "Dismissals": c.col_int(),
                               "Balls per dismissal": c.col_1(help=c.HELP["Balls per dismissal"])})
    c.section("Share of balls by length, by season")
    sh = league[(league["role"] == "bowl") & (league["dim"] == "length")].pivot_table(
        index="season", columns="category", values="balls", aggfunc="sum").reindex(columns=list(LENGTHS)).fillna(0)
    sh = sh.div(sh.sum(axis=1), axis=0) * 100
    sh.columns = [LENGTHS[k] for k in sh.columns]
    c.table(sh.reset_index().rename(columns={"season": "Season"}),
            column_config={"Season": st.column_config.NumberColumn(format="%d", width="small"),
                           **{k: c.col_pct() for k in LENGTHS.values()}})
    c.note("Share of balls counts every delivery, including wides and no-balls. Strike rate and dismissals use "
           "balls faced (no wides); dismissals are batters out on strike.")


def player_tab(role, key):
    noun = "balls faced" if role == "bat" else "deliveries"
    a, m = st.columns([3, 1])
    min_balls = m.number_input("Minimum balls", 0, 3000, 150, 30, key=f"min_{key}")
    tot = players[(players["role"] == role) & (players["dim"] == "length")].groupby("player_id")["balls"].sum()
    ids = tot[tot >= min_balls].index
    if not len(ids):
        c.empty("No player has that many balls in these seasons.", " Lower the minimum or widen the seasons.")
        return
    names = pd.Series({p: c.name(p) for p in ids}).sort_values()
    default = "Babar Azam" if role == "bat" else "Shaheen Shah Afridi"
    idx = list(names.values).index(default) if default in names.values else 0
    pid = a.selectbox("Player", names.index, index=idx, format_func=lambda p: names[p], key=f"pl_{key}")
    me = players[players["player_id"] == pid]
    for dim in ("length", "line"):
        mine, lg = summary(me, role, dim), summary(league, role, dim)
        c.section(f"Share of {noun} by {dim}", "Compared with all PSL players.")
        c.grouped_bars(list(mine["label"]), [(names[pid], mine["share"].values), ("All PSL", lg["share"].values)],
                       f"% of {noun}", key=f"{key}_{dim}", credit=c.INSIGHTS_CREDIT)
    mine = summary(me, role, "length")
    rate = "Strike rate" if role == "bat" else "Runs per over"
    outs = "Dismissals" if role == "bat" else "Wickets"
    t = pd.DataFrame({"Length": mine["label"], "Balls": mine["balls"].astype(int).values,
                      "Share %": mine["share"].values, rate: mine["rate"].values,
                      outs: mine["outs"].astype(int).values, f"Balls per {outs.lower()[:-1]}": mine["balls_per_out"].values})
    c.section("By length")
    c.table(t, column_config={"Length": c.col_text(), "Balls": c.col_int(), "Share %": c.col_pct(),
                              rate: c.col_1(help=c.HELP["SR"]) if role == "bat" else c.col_2(help=c.HELP["Econ"]),
                              outs: c.col_int(), f"Balls per {outs.lower()[:-1]}": c.col_1(help=c.HELP["Balls per dismissal"])})
    c.section("By season: share by length")
    ps = me[(me["role"] == role) & (me["dim"] == "length")].pivot_table(
        index="season", columns="category", values="balls", aggfunc="sum").reindex(columns=list(LENGTHS)).fillna(0)
    n = ps.sum(axis=1)
    ps = ps.div(n.replace(0, np.nan), axis=0) * 100
    ps.columns = [LENGTHS[k] for k in ps.columns]
    ps.insert(0, "Balls", n.astype(int))
    c.table(ps.reset_index().rename(columns={"season": "Season"}),
            column_config={"Season": st.column_config.NumberColumn(format="%d", width="small"), "Balls": c.col_int(),
                           **{k: c.col_pct() for k in LENGTHS.values()}})


with tab_bat:
    player_tab("bat", "bat")
    c.note("Balls faced exclude wides. Dismissals are outs on strike.")
with tab_bowl:
    player_tab("bowl", "bowl")
    c.note("Every delivery counts, including wides and no-balls. Runs per over uses runs conceded by the "
           "Cricsheet rules; wickets are bowler wickets.")

# ------------------------------------------------------------------ scoring zones
KINDS = {"all": "Pace and spin", "pace": "Pace", "spin": "Spin"}
PHASES = {0: "All overs", 1: "Powerplay", 2: "Middle", 3: "Death"}
SHOWS = {"share": "Share of balls", "econ": "Economy", "wkts": "Wickets"}
MIN_ZONE_BALLS = 200          # a batter needs this many balls (after the filters) to be listed
MIN_CELL_BALLS = 30           # a line and length cell (or row) needs this many balls for economy


def pick(label, options, key, default):
    v = st.segmented_control(label, list(options), format_func=options.get, key=key, default=default)
    return default if v is None else v


def filtered(df, kind, phase):
    if kind != "all":
        df = df[df["kind"] == kind]
    if phase:
        df = df[df["phase"] == phase]
    return df


zone_all = c.insights("SELECT * FROM zone")
zone_all = zone_all[zone_all["season"].isin(seasons)]

with tab_zone:
    st.markdown('<p class="dd-meta">Where the runs go, in eight sectors of the field, seen from behind the '
                'batter: straight at the top, off side on the right. Left-handers are mirrored, so the off side '
                'is always on the right.</p>', unsafe_allow_html=True)
    f1, f2, f3 = st.columns([1.2, 1.4, 1])
    with f1:
        kind = pick("Bowling", KINDS, "zn_kind", "all")
    with f2:
        phase = pick("Phase", PHASES, "zn_phase", 0)
    with f3:
        measure = pick("Share of", c.ZONE_MEASURES, "zn_measure", "runs")
    bat_rows = filtered(zone_all[zone_all["role"] == "bat"], kind, phase)
    lg_rows = bat_rows[bat_rows["player_id"] == "ALL"]
    me_rows = bat_rows[bat_rows["player_id"] != "ALL"]
    a, m = st.columns([3, 1])
    min_z = m.number_input("Minimum balls", 50, 3000, MIN_ZONE_BALLS, 50, key="zn_min",
                           help="Balls faced with the chosen bowling and phase. Batters with fewer are not listed.")
    tot = me_rows.groupby("player_id")["balls"].sum()
    ids = list(tot[tot >= min_z].index)
    names = pd.Series({p: c.name(p) for p in ids}, dtype=object).sort_values()
    options = ["ALL"] + list(names.index)
    zpid = a.selectbox("Batter", options, key="zn_player",
                       format_func=lambda p: "All PSL batters" if p == "ALL" else names[p],
                       index=options.index("8a75e999") if "8a75e999" in options else 0)
    lg = c.zone_shares(lg_rows)
    who = "All PSL batters" if zpid == "ALL" else names[zpid]
    mine = lg if zpid == "ALL" else c.zone_shares(me_rows[me_rows["player_id"] == zpid])
    mname = c.ZONE_MEASURES[measure].lower()
    filt = f"{KINDS[kind]}, {PHASES[phase].lower()}"
    covered = c.div(lg_rows.loc[lg_rows["zone"].between(1, 8), "runs"].sum(), lg_rows["runs"].sum(), 100).item()

    if mine[measure].sum() == 0:
        c.empty(f"No {mname} with a zone for {who} in this selection.", " Try other filters or seasons.")
    else:
        sh = mine[f"{measure}_share"]
        c.section(f"Share of {mname} by zone: {who}", f"{filt}. Share of all {mname} that have a zone.")
        c.field_chart(sh.values, [f"{n}<br>{v:.1f}%" for n, v in zip(mine["name"], sh)],
                      [f"{n}: {v:.1f}% of {mname} ({int(x):,} {mname}, {int(b):,} balls)"
                       for n, v, x, b in zip(mine["name"], sh, mine[measure], mine["balls"])],
                      key="zn_share", credit=c.INSIGHTS_CREDIT)

    if zpid != "ALL" and mine[measure].sum() > 0:
        diff = mine[f"{measure}_share"] - lg[f"{measure}_share"]
        c.section(f"Relative zones: {who} v the PSL average",
                  f"Share of {mname} in each zone minus the PSL share in the same selection, in percentage points.")
        c.field_chart(diff.values, [f"{n}<br>{v:+.1f} pp" for n, v in zip(mine["name"], diff)],
                      [f"{n}: {x:.1f}% v PSL {y:.1f}% ({d:+.1f} pp)" for n, x, y, d in
                       zip(mine["name"], mine[f"{measure}_share"], lg[f"{measure}_share"], diff)],
                      key="zn_rel", diverging=True, credit=c.INSIGHTS_CREDIT)

    caught = mine["caught"]
    c.section(f"Caught by zone: {who}", "Batters caught (including caught and bowled), counted per zone.")
    if caught.sum() == 0:
        c.empty("No caught dismissals with a zone in this selection.")
    else:
        c.field_chart(caught.values, [f"{n}<br>{v:,}" for n, v in zip(mine["name"], caught)],
                      [f"{n}: {v:,} caught ({v * 100 / caught.sum():.1f}%)" for n, v in zip(mine["name"], caught)],
                      key="zn_caught", credit=c.INSIGHTS_CREDIT)
    zt = pd.DataFrame({"Zone": mine["name"].values, "Balls": mine["balls"].values, "Runs": mine["runs"].values,
                       "Runs %": mine["runs_share"].values, "Fours %": mine["fours_share"].values,
                       "Sixes %": mine["sixes_share"].values, "PSL runs %": lg["runs_share"].values,
                       "Caught": mine["caught"].values})
    c.table(zt, column_config={"Zone": c.col_text(), "Balls": c.col_int(), "Runs": c.col_int(),
                               "Runs %": c.col_pct(), "Fours %": c.col_pct(), "Sixes %": c.col_pct(),
                               "PSL runs %": c.col_pct(), "Caught": c.col_int()})
    c.note(f"Balls faced (no wides) with a scoring zone; {covered:.1f}% of PSL runs in this selection have one. "
           "The eight sectors are equal on the chart; real zones follow the ground. Pace or spin is the "
           "bowler's type in the data.")

# ------------------------------------------------------------------ bowler variations
ll_all = c.insights("SELECT * FROM ll")
ll_all = ll_all[ll_all["season"].isin(seasons)]
LL_LEN, LL_LINE = list(LENGTHS), list(LINES)
# Short axis labels for the heatmap (full names in the hover text and the tables).
AXIS_LEN = {**LENGTHS, "SHORT_OF_A_GOOD_LENGTH": "Short of length"}
AXIS_LINE = {"WIDE_OUTSIDE_OFFSTUMP": "Wide off", "OUTSIDE_OFFSTUMP": "Off", "ON_THE_STUMPS": "Stumps",
             "DOWN_LEG": "Leg", "WIDE_DOWN_LEG": "Wide leg"}


def ll_cells(df):
    """Balls, runs and wickets per length (rows) and line (columns), only balls with both known."""
    d = df.dropna(subset=["line", "length"])
    return {col: d.pivot_table(index="length", columns="line", values=col, aggfunc="sum")
            .reindex(index=LL_LEN, columns=LL_LINE).fillna(0) for col in ("balls", "runs", "wkts")}


def ll_by(df, dim):
    lab = LENGTHS if dim == "length" else LINES
    g = df.dropna(subset=[dim]).groupby(dim)[["balls", "runs", "wkts"]].sum().reindex(list(lab)).fillna(0)
    g["share"] = c.div(g["balls"], g["balls"].sum(), 100)
    g["econ"] = np.where(g["balls"] >= MIN_CELL_BALLS, c.div(g["runs"], g["balls"], 6), np.nan)
    g["label"] = [lab[k] for k in g.index]
    return g


with tab_var:
    st.markdown('<p class="dd-meta">Where a bowler pitches it and what happens: share of deliveries, economy and '
                'wickets by length and line. The data has no ball type (slower ball, googly and so on), so '
                'variations are shown by line and length only.</p>', unsafe_allow_html=True)
    v1, v2 = st.columns([1.2, 1.4])
    with v1:
        vkind = pick("Bowling", KINDS, "vr_kind", "all")
    with v2:
        vphase = pick("Phase", PHASES, "vr_phase", 0)
    rows = filtered(ll_all, vkind, vphase)
    lgv, mev = rows[rows["player_id"] == "ALL"], rows[rows["player_id"] != "ALL"]
    a, m = st.columns([3, 1])
    min_v = m.number_input("Minimum balls", 30, 3000, 120, 30, key="vr_min",
                           help="Deliveries with the chosen bowling and phase. Bowlers with fewer are not listed.")
    tot = mev.groupby("player_id")["balls"].sum()
    vids = list(tot[tot >= min_v].index)
    vnames = pd.Series({p: c.name(p) for p in vids}, dtype=object).sort_values()
    vopts = ["ALL"] + list(vnames.index)
    vpid = a.selectbox("Bowler", vopts, key="vr_player",
                       format_func=lambda p: "All PSL bowlers" if p == "ALL" else vnames[p],
                       index=vopts.index("45a7e761") if "45a7e761" in vopts else 0)
    vwho = "All PSL bowlers" if vpid == "ALL" else vnames[vpid]
    sel = lgv if vpid == "ALL" else mev[mev["player_id"] == vpid]
    cells = ll_cells(sel)
    if cells["balls"].values.sum() == 0:
        c.empty(f"No line and length data for {vwho} in this selection.", " Try other filters or seasons.")
    else:
        what = pick("Show", SHOWS, "vr_show", "share")
        n = cells["balls"].values.sum()
        if what == "share":
            z = cells["balls"] / n * 100
            text = z.map(lambda v: f"{v:.1f}%")
        elif what == "econ":
            z = (cells["runs"] / cells["balls"].replace(0, np.nan) * 6).where(cells["balls"] >= MIN_CELL_BALLS)
            text = z.map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
        else:
            z = cells["wkts"]
            text = z.map(lambda v: f"{int(v):,}")
        extra = f" Economy shown only where a cell has at least {MIN_CELL_BALLS} balls." if what == "econ" else ""
        c.section(f"{SHOWS[what]} by length and line: {vwho}", f"{KINDS[vkind]}, {PHASES[vphase].lower()}." + extra)
        hover = [[f"{LENGTHS[r]}, {LINES[ln]}: {int(cells['balls'].at[r, ln]):,} balls, "
                  f"{int(cells['runs'].at[r, ln]):,} runs, {int(cells['wkts'].at[r, ln]):,} wickets"
                  for ln in LL_LINE] for r in LL_LEN]
        fig = c.go.Figure(c.go.Heatmap(
            z=z.values, x=[AXIS_LINE[ln] for ln in LL_LINE], y=[AXIS_LEN[r] for r in LL_LEN], text=text.values,
            texttemplate="%{text}", textfont=dict(color=c.INK, size=11), hovertext=hover, hoverinfo="text",
            colorscale=c.SEQ, showscale=False, xgap=2, ygap=2))
        lay = c.layout(fig, height=380, credit=c.INSIGHTS_CREDIT)
        lay.update_yaxes(autorange="reversed", showgrid=False, zeroline=False, automargin=True, ticksuffix="  ")
        lay.update_xaxes(showgrid=False, automargin=True)
        lay.update_layout(margin=dict(l=128, r=28, t=34))
        lay.layout.annotations[0].update(yanchor="bottom")      # watermark above the grid, not on it
        c.show(lay, "vr_heat")
        for dim in ("length", "line"):
            g, lgg = ll_by(sel, dim), ll_by(lgv, dim)
            c.section(f"By {dim}")
            t2 = pd.DataFrame({dim.capitalize(): g["label"].values, "Balls": g["balls"].astype(int).values,
                               "Share %": g["share"].values, "PSL share %": lgg["share"].values,
                               "Economy": g["econ"].values, "PSL economy": lgg["econ"].values,
                               "Wickets": g["wkts"].astype(int).values})
            c.table(t2, column_config={dim.capitalize(): c.col_text(), "Balls": c.col_int(), "Share %": c.col_pct(),
                                       "PSL share %": c.col_pct(), "Economy": c.col_2(help=c.HELP["Econ"]),
                                       "PSL economy": c.col_2(help=c.HELP["Econ"]), "Wickets": c.col_int()})
    c.note(f"Every delivery counts, including wides and no-balls. Economy uses runs conceded by the Cricsheet "
           f"rules and is blank under {MIN_CELL_BALLS} balls; wickets are bowler wickets. PSL columns use the same "
           "bowling and phase filters.")

c.footer(extra=c.INSIGHTS_CREDIT)
