"""
insights.py - Insights: line and length, scoring zones and bowler variations for PSL 2018
and 2020 to 2026.
READ-ONLY. Reads only the private aggregate file (tools/build_insights.py): totals per
player, season, role, line or length. No ball-level rows exist in it or on this page.
Shown only when common.SHOW_INSIGHTS is True. No credit on the page or its charts (owner's decision
2026-11-09): one line at the end names the seasons, built from the data; the Method tab lists the source.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app/ folder, for common.py

import common as c  # noqa: E402

c.page("Insights", "Where bowlers pitch it, where batters score, and how each length goes.")
if not c.insights_available():
    c.empty("Insights are not available in this version of the site.", " The rest of Dugout Data works as usual.")
    c.footer()
    st.stop()

LENGTHS = {"YORKER": "Yorker", "FULL_TOSS": "Full toss", "FULL": "Full", "GOOD_LENGTH": "Good length",
           "SHORT_OF_A_GOOD_LENGTH": "Short of a length", "SHORT": "Short"}
LINES = {"WIDE_OUTSIDE_OFFSTUMP": "Wide outside off", "OUTSIDE_OFFSTUMP": "Outside off",
         "ON_THE_STUMPS": "On the stumps", "DOWN_LEG": "Down leg", "WIDE_DOWN_LEG": "Wide down leg"}
LABELS = {"length": LENGTHS, "line": LINES}
AVAILABLE = list(c.ll_coverage()["covered"])      # seasons with line and length data, read from the file

lo, hi = c.season_filter()
seasons = [s for s in AVAILABLE if lo <= s <= hi]
if not seasons:
    c.empty("No line and length data for these seasons.",
            f" Choose a range that includes {c.season_runs(AVAILABLE).replace(' and ', ' or ', 1)}.")
    c.footer()
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


# Phase B tabs (2026-11-08) come after the original five and run only when opened (on_change="rerun"
# gives each tab an .open flag), so the page stays as fast as before for every visitor.
(tab_league, tab_bat, tab_bowl, tab_zone, tab_var,
 tab_pm, tab_bz, tab_shot, tab_wtb, tab_dn) = st.tabs(
    ["League", "Batter", "Bowler", "Scoring zones", "Bowler variations",
     "Pitch map", "Bowler zones", "Shots", "Where to bowl", "Day and night"], key="ins_tab", on_change="rerun")

with tab_league:
    s = summary(league, "bat", "length")
    c.section("Strike rate by length", "All PSL batters, balls faced. " + c.HELP["SR"])
    c.grouped_bars(list(s["label"]), [("Strike rate", s["rate"].values)], "Strike rate", key="lg_sr")
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
                       f"% of {noun}", key=f"{key}_{dim}")
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
                      key="zn_share")

    if zpid != "ALL" and mine[measure].sum() > 0:
        diff = mine[f"{measure}_share"] - lg[f"{measure}_share"]
        c.section(f"Relative zones: {who} v the PSL average",
                  f"Share of {mname} in each zone minus the PSL share in the same selection, in percentage points.")
        c.field_chart(diff.values, [f"{n}<br>{v:+.1f} pp" for n, v in zip(mine["name"], diff)],
                      [f"{n}: {x:.1f}% v PSL {y:.1f}% ({d:+.1f} pp)" for n, x, y, d in
                       zip(mine["name"], mine[f"{measure}_share"], lg[f"{measure}_share"], diff)],
                      key="zn_rel", diverging=True)

    caught = mine["caught"]
    c.section(f"Caught by zone: {who}", "Batters caught (including caught and bowled), counted per zone.")
    if caught.sum() == 0:
        c.empty("No caught dismissals with a zone in this selection.")
    else:
        c.field_chart(caught.values, [f"{n}<br>{v:,}" for n, v in zip(mine["name"], caught)],
                      [f"{n}: {v:,} caught ({v * 100 / caught.sum():.1f}%)" for n, v in zip(mine["name"], caught)],
                      key="zn_caught")
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
        lay = c.layout(fig, height=380)
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

# ================================================================== Phase B tabs (2026-11-08)
# Every rate shows the balls behind it; under c.MIN_BALLS a rate is left blank ("not enough balls"),
# under c.SMALL_BALLS it carries c.SMALL_MARK (small sample).
B_READY = c.insights_has(*c.B_TABLES)
SMALL_NOTE = (f"Rates need at least {c.MIN_BALLS} balls; {c.SMALL_MARK} marks a small sample "
              f"({c.MIN_BALLS} to {c.SMALL_BALLS - 1} balls).")
PM_SHOW = {"bat": {"rate": "Strike rate", "out_pct": "Dismissal %", "dot_pct": "Dot %", "bdry_pct": "Boundary %",
                   "ctl_pct": "Control %", "share": "Share of balls"},
           "bowl": {"rate": "Economy", "out_pct": "Wicket %", "dot_pct": "Dot %", "bdry_pct": "Boundary %",
                    "ctl_pct": "Batter control %", "share": "Share of balls"}}


def not_ready():
    c.empty("This view is not available in this version of the site.", " The other Insights tabs work as usual.")


def b_player_pick(rows, key, label, default_pid, min_default=120):
    """Player picker over b_ rows (already filtered): 'All PSL' plus players with the minimum balls."""
    a, m = st.columns([3, 1])
    min_b = m.number_input("Minimum balls", 30, 3000, min_default, 30, key=f"{key}_min",
                           help="Balls with the chosen filters. Players with fewer are not listed.")
    tot = rows[rows["player_id"] != "ALL"].groupby("player_id")["balls"].sum()
    ids = list(tot[tot >= min_b].index)
    names = pd.Series({p: c.name(p) for p in ids}, dtype=object).sort_values()
    opts = ["ALL"] + list(names.index)
    pid = a.selectbox(label, opts, key=f"{key}_player",
                      format_func=lambda p: "All PSL" if p == "ALL" else names[p],
                      index=opts.index(default_pid) if default_pid in opts else 0)
    return pid, ("All PSL" if pid == "ALL" else names[pid])


def seasons_note(extra=""):
    c.note(f"Seasons with this data: {c.ll_seasons_text()}. Showing {', '.join(map(str, seasons))}. " + extra)


def heat(z, text, hover, key, height=380):
    fig = c.go.Figure(c.go.Heatmap(
        z=z, x=[AXIS_LINE[ln] for ln in LL_LINE], y=[AXIS_LEN[r] for r in LL_LEN], text=text,
        texttemplate="%{text}", textfont=dict(color=c.INK, size=11), hovertext=hover, hoverinfo="text",
        colorscale=c.SEQ, showscale=False, xgap=2, ygap=2))
    lay = c.layout(fig, height=height)
    lay.update_yaxes(autorange="reversed", showgrid=False, zeroline=False, automargin=True, ticksuffix="  ")
    lay.update_xaxes(showgrid=False, automargin=True)
    lay.update_layout(margin=dict(l=128, r=28, t=34))
    lay.layout.annotations[0].update(yanchor="bottom")
    c.show(lay, key)


# ------------------------------------------------------------------ pitch map
with tab_pm:
    if not tab_pm.open:
        pass
    elif not B_READY:
        not_ready()
    else:
        st.markdown('<p class="dd-meta">Where the ball pitched (length) and its line, and what happened: for a bowler '
                    'or for a batter. Every cell shows its ball count when you hover or tap it.</p>',
                    unsafe_allow_html=True)
        p1, p2, p3 = st.columns([1, 1.2, 1.4])
        with p1:
            role = pick("For", {"bowl": "Bowlers", "bat": "Batters"}, "pm_role", "bowl")
        with p2:
            pkind = pick("Bowling", KINDS, "pm_kind", "all")
        with p3:
            pphase = pick("Phase", PHASES, "pm_phase", 0)
        rows = c.b_filter(c.b_table("b_pm", role), pkind, pphase, seasons)
        pid, who = b_player_pick(rows, "pm", "Bowler" if role == "bowl" else "Batter",
                                 "45a7e761" if role == "bowl" else "8a75e999")
        sel = rows[rows["player_id"] == pid]
        lg_sel = rows[rows["player_id"] == "ALL"]
        cov, known, total = c.pm_coverage(sel)
        noun = "legal balls" if role == "bowl" else "balls faced"
        if known < c.MIN_BALLS:
            c.empty(f"Not enough balls with a line and length for {who} in this selection ({known:,}).",
                    " Widen the seasons, or choose All overs or Pace and spin.")
        else:
            shows = PM_SHOW[role]
            what = pick("Show", shows, "pm_show", "rate")
            cells = c.pm_cells(sel, role)
            n = cells["balls"].sum()
            vals = cells["balls"] * 100 / n if what == "share" else cells[what]
            nd = 2 if (what == "rate" and role == "bowl") else 1
            text = [c.sample_rate(v, b, nd) if what != "share" else (f"{v:.1f}%" if b else "")
                    for v, b in zip(vals, cells["balls"])]
            z = [v if (what == "share" or b >= c.MIN_BALLS) else np.nan for v, b in zip(vals, cells["balls"])]
            rate_name = "SR" if role == "bat" else "Econ"
            hover = [f"{c.LENGTH_LABELS[ln]}, {c.LINE_LABELS[li]}: {int(r['balls']):,} {noun}, {int(r['runs']):,} runs, "
                     f"{int(r['outs']):,} {'dismissals' if role == 'bat' else 'wickets'}"
                     + (f", {rate_name} {r['rate']:.{nd}f}" if r["balls"] >= c.MIN_BALLS else ", not enough balls")
                     for (ln, li), r in cells.iterrows()]
            shape = (len(LL_LEN), len(LL_LINE))
            c.section(f"{shows[what]} by length and line: {who}",
                      f"{KINDS[pkind]}, {PHASES[pphase].lower()}. {known:,} {noun} with a line and length "
                      f"({cov:.1f}% of {total:,}).")
            heat(np.array(z, dtype=float).reshape(shape), np.array(text, dtype=object).reshape(shape),
                 np.array(hover, dtype=object).reshape(shape), "pm_heat")
            for dim in ("length", "line"):
                g, lgg = c.pm_by(sel, role, dim), c.pm_by(lg_sel, role, dim)
                rate = "SR" if role == "bat" else "Econ"
                t = pd.DataFrame({dim.capitalize(): g["label"].values, "Balls": g["balls"].astype(int).values,
                                  "Runs": g["runs"].astype(int).values,
                                  ("Outs" if role == "bat" else "Wkts"): g["outs"].astype(int).values,
                                  rate: c.masked(g["rate"], g["balls"]), "Dot %": c.masked(g["dot_pct"], g["balls"]),
                                  "Boundary %": c.masked(g["bdry_pct"], g["balls"]),
                                  "Control %": c.masked(g["ctl_pct"], g["ctl_n"]),
                                  f"PSL {rate}": lgg["rate"].values, "Sample": c.sample_label(g["balls"])})
                c.section(f"By {dim}")
                c.table(t, column_config={
                    dim.capitalize(): c.col_text(), "Balls": c.col_int(help=f"{noun.capitalize()} with this {dim}"),
                    "Runs": c.col_int(), "Outs": c.col_int(help="Dismissals on strike"), "Wkts": c.col_int(help="Bowler wickets"),
                    rate: c.col_1(help=c.HELP["SR"]) if role == "bat" else c.col_2(help=c.HELP["Econ"]),
                    "Dot %": c.col_pct(help=c.HELP["Dot %"]), "Boundary %": c.col_pct(help=c.HELP["Boundary %"]),
                    "Control %": c.col_pct(help="Share of balls (with a control value) the batter was in control of"),
                    f"PSL {rate}": c.col_1() if role == "bat" else c.col_2(), "Sample": c.col_text(width="small")})
        seasons_note(("Bowlers: legal balls (no wides or no-balls); runs conceded by the Cricsheet rules, so wides "
                      "and no-balls add runs but not balls; wickets are bowler wickets. " if role == "bowl" else
                      "Batters: balls faced (no wides); dismissals on strike. ")
                     + "Control is the data's own in-control or not-in-control mark. " + SMALL_NOTE)

# ------------------------------------------------------------------ bowler zones (where a bowler leaks runs)
with tab_bz:
    if not tab_bz.open:
        pass
    elif not B_READY:
        not_ready()
    else:
        st.markdown('<p class="dd-meta">Where batters score off a bowler: runs off the bat in eight sectors, seen '
                    'from behind the batter (left-handers mirrored, so the off side is always on the right).</p>',
                    unsafe_allow_html=True)
        b1, b2, b3 = st.columns([1.2, 1.4, 1])
        with b1:
            zkind = pick("Bowling", KINDS, "bz_kind", "all")
        with b2:
            zphase = pick("Phase", PHASES, "bz_phase", 0)
        with b3:
            zmeasure = pick("Share of", c.ZONE_MEASURES, "bz_measure", "runs")
        zb = c.b_filter(c.b_table("b_zone"), zkind, zphase, seasons)
        bowl_rows, lg_rows = zb[zb["role"] == "bowl"], zb[(zb["role"] == "bat") & (zb["player_id"] == "ALL")]
        zpid, zwho = b_player_pick(bowl_rows, "bz", "Bowler", "45a7e761", 120)
        if zpid == "ALL":
            zpid, zwho = None, "All PSL bowlers"
        mine_rows = lg_rows if zpid is None else bowl_rows[bowl_rows["player_id"] == zpid]
        mine, lg = c.zone_shares(mine_rows), c.zone_shares(lg_rows)
        mname = c.ZONE_MEASURES[zmeasure].lower()
        if mine["balls"].sum() < c.MIN_BALLS or mine[zmeasure].sum() == 0:
            c.empty(f"Not enough balls with a zone for {zwho} in this selection.", " Try other filters or seasons.")
        else:
            sh = mine[f"{zmeasure}_share"]
            c.section(f"Share of {mname} conceded by zone: {zwho}",
                      f"{KINDS[zkind]}, {PHASES[zphase].lower()}. {int(mine['balls'].sum()):,} balls faced off "
                      f"him with a zone.")
            c.field_chart(sh.values, [f"{n}<br>{v:.1f}%" for n, v in zip(mine["name"], sh)],
                          [f"{n}: {v:.1f}% of {mname} ({int(x):,} {mname}, {int(b):,} balls)"
                           for n, v, x, b in zip(mine["name"], sh, mine[zmeasure], mine["balls"])],
                          key="bz_share")
            if zpid is not None:
                diff = mine[f"{zmeasure}_share"] - lg[f"{zmeasure}_share"]
                c.section(f"Relative zones: {zwho} v the PSL average",
                          f"Share of {mname} conceded in each zone minus the PSL share, in percentage points.")
                c.field_chart(diff.values, [f"{n}<br>{v:+.1f} pp" for n, v in zip(mine["name"], diff)],
                              [f"{n}: {x:.1f}% v PSL {y:.1f}% ({d:+.1f} pp)" for n, x, y, d in
                               zip(mine["name"], mine[f"{zmeasure}_share"], lg[f"{zmeasure}_share"], diff)],
                              key="bz_rel", diverging=True)
            zt = pd.DataFrame({"Zone": mine["name"].values, "Balls": mine["balls"].values, "Runs": mine["runs"].values,
                               "Runs per ball": c.masked(c.div(mine["runs"], mine["balls"]), mine["balls"]),
                               "Runs %": mine["runs_share"].values, "Fours": mine["fours"].values,
                               "Sixes": mine["sixes"].values, "PSL runs %": lg["runs_share"].values,
                               "Sample": c.sample_label(mine["balls"])})
            c.table(zt, column_config={"Zone": c.col_text(), "Balls": c.col_int(help="Balls faced that went to this zone"),
                                       "Runs": c.col_int(help="Runs off the bat"), "Runs per ball": c.col_2(),
                                       "Runs %": c.col_pct(), "Fours": c.col_int(), "Sixes": c.col_int(),
                                       "PSL runs %": c.col_pct(), "Sample": c.col_text(width="small")})
        seasons_note("Balls faced off the bowler (no wides) whose landing zone is recorded; runs are off the bat, "
                     "so extras are not in any zone. " + SMALL_NOTE)

# ------------------------------------------------------------------ shots
with tab_shot:
    if not tab_shot.open:
        pass
    elif not B_READY:
        not_ready()
    else:
        st.markdown('<p class="dd-meta">The shot the batter played, as recorded in the data: how often, how fast he '
                    'scored with it and how often it got him out.</p>', unsafe_allow_html=True)
        s1, s2 = st.columns([1.2, 1.4])
        with s1:
            skind = pick("Bowling", KINDS, "sh_kind", "all")
        with s2:
            sphase = pick("Phase", PHASES, "sh_phase", 0)
        srows = c.b_filter(c.b_table("b_shot"), skind, sphase, seasons)
        spid, swho = b_player_pick(srows, "sh", "Batter", "8a75e999", 150)
        mine = c.shot_table(srows[srows["player_id"] == spid])
        lg = c.shot_table(srows[srows["player_id"] == "ALL"])
        known = int(mine["balls"].sum())
        alln = int(srows[srows["player_id"] == spid]["balls"].sum())
        if known < c.MIN_BALLS:
            c.empty(f"Not enough balls with a recorded shot for {swho} in this selection ({known:,}).",
                    " Widen the seasons or the filters.")
        else:
            lg = lg.reindex(mine.index)
            ok = mine[mine["balls"] >= c.MIN_BALLS].head(12)
            c.section(f"Strike rate by shot: {swho}",
                      f"{KINDS[skind]}, {PHASES[sphase].lower()}. Shots with at least {c.MIN_BALLS} balls; "
                      f"{known:,} of {alln:,} balls faced have a shot ({known * 100 / alln:.1f}%).")
            if len(ok):
                series = [(swho, ok["rate"].values)] + ([("All PSL", lg.loc[ok.index, "rate"].values)] if spid != "ALL" else [])
                c.grouped_bars(list(ok["label"]), series, "Strike rate", key="sh_sr")
            else:
                c.empty("No shot has enough balls for a strike rate.", " Widen the seasons or the filters.")
            st_ = pd.DataFrame({"Shot": mine["label"].values, "Balls": mine["balls"].astype(int).values,
                                "Share %": mine["share"].values, "Runs": mine["runs"].astype(int).values,
                                "SR": c.masked(mine["rate"], mine["balls"]), "Outs": mine["outs"].astype(int).values,
                                "Dismissal %": c.masked(mine["out_pct"], mine["balls"]),
                                "Boundary %": c.masked(mine["bdry_pct"], mine["balls"]),
                                "Control %": c.masked(mine["ctl_pct"], mine["ctl_n"]),
                                "PSL SR": lg["rate"].values, "PSL dismissal %": lg["out_pct"].values,
                                "Sample": c.sample_label(mine["balls"])}).head(c.MAX_ROWS)
            c.table(st_, column_config={"Shot": c.col_text(), "Balls": c.col_int(), "Share %": c.col_pct(),
                                        "Runs": c.col_int(), "SR": c.col_1(help=c.HELP["SR"]),
                                        "Outs": c.col_int(help="Dismissals on strike playing this shot"),
                                        "Dismissal %": c.col_pct(help="Dismissals per 100 balls"),
                                        "Boundary %": c.col_pct(help=c.HELP["Boundary %"]),
                                        "Control %": c.col_pct(help="Share of balls the batter was in control of"),
                                        "PSL SR": c.col_1(), "PSL dismissal %": c.col_pct(),
                                        "Sample": c.col_text(width="small")})
        seasons_note("Balls faced (no wides); dismissals on strike. " + SMALL_NOTE)

# ------------------------------------------------------------------ where to bowl (batter weakness card)
MIN_WTB = 150            # a batter needs this many balls faced with a line and length (after the filters)
with tab_wtb:
    if not tab_wtb.open:
        pass
    elif not B_READY:
        not_ready()
    else:
        st.markdown('<p class="dd-meta">Where to bowl to a batter: his tightest length, line and spot, where he '
                    'gets out most, and where he scores, against the PSL average with the same filters.</p>',
                    unsafe_allow_html=True)
        w1, w2 = st.columns([1.2, 1.4])
        with w1:
            wkind = pick("Bowling", KINDS, "wtb_kind", "all")
        with w2:
            wphase = pick("Phase", PHASES, "wtb_phase", 0)
        pm_all = c.b_filter(c.b_table("b_pm", "bat"), wkind, wphase, seasons)
        known = pm_all.dropna(subset=["line", "length"])
        tot = known[known["player_id"] != "ALL"].groupby("player_id")["balls"].sum()
        ids = list(tot[tot >= MIN_WTB].index)
        names = pd.Series({p: c.name(p) for p in ids}, dtype=object).sort_values()
        if not len(names):
            c.empty(f"No batter has {MIN_WTB} balls with a line and length in this selection.",
                    " Widen the seasons or the filters.")
        else:
            opts = list(names.index)
            wpid = st.selectbox("Batter", opts, key="wtb_player", format_func=lambda p: names[p],
                                index=opts.index("8a75e999") if "8a75e999" in opts else 0)
            zb = c.b_filter(c.b_table("b_zone", "bat"), wkind, wphase, seasons)
            cards, cand = c.where_to_bowl(pm_all[pm_all["player_id"] == wpid], pm_all[pm_all["player_id"] == "ALL"],
                                          zb[zb["player_id"] == wpid], zb[zb["player_id"] == "ALL"])
            c.section(f"Where to bowl to {names[wpid]}",
                      f"{KINDS[wkind]}, {PHASES[wphase].lower()}. {int(tot[wpid]):,} balls faced with a line and length.")
            if cards:
                c.cards([(lab, where, f"{detail}; {balls:,} balls" + (" (small sample)" if balls < c.SMALL_BALLS else ""))
                         for lab, where, detail, balls in cards], detail=True)
            else:
                c.empty("No length, line or spot has enough balls for this batter.", " Widen the seasons or the filters.")
            cand = cand[cand["balls"] > 0].copy()
            cand["sample"] = c.sample_label(cand["balls"])
            cand = cand.sort_values(["what", "balls"], ascending=[True, False])
            c.section("Every length, line and spot", "Sorted by balls. Rates are blank under the minimum.")
            c.table(pd.DataFrame({"Type": cand["what"].values, "Where": cand["where"].values,
                                  "Balls": cand["balls"].astype(int).values,
                                  "SR": c.masked(cand["sr"], cand["balls"]), "PSL SR": cand["psl_sr"].values,
                                  "Outs": cand["outs"].astype(int).values,
                                  "Balls per out": c.masked(cand["per_out"], cand["balls"]),
                                  "PSL balls per out": cand["psl_per_out"].values,
                                  "Sample": cand["sample"]}).head(c.MAX_ROWS),
                    column_config={"Type": c.col_text(width="small"), "Where": c.col_text(), "Balls": c.col_int(),
                                   "SR": c.col_1(help=c.HELP["SR"]), "PSL SR": c.col_1(), "Outs": c.col_int(),
                                   "Balls per out": c.col_1(help=c.HELP["Balls per dismissal"]),
                                   "PSL balls per out": c.col_1(), "Sample": c.col_text(width="small")})
        seasons_note(f"A batter is listed with at least {MIN_WTB} balls faced with a line and length. A length, line "
                     f"or spot is picked only with at least {c.MIN_BALLS} balls; 'most dismissals' needs at least 2. "
                     "Zones: balls with a recorded landing zone. " + SMALL_NOTE)

# ------------------------------------------------------------------ day and night
with tab_dn:
    if not tab_dn.open:
        pass
    elif not B_READY:
        not_ready()
    else:
        st.markdown('<p class="dd-meta">Day, day/night and night matches: who wins, what the toss is worth and how '
                    'many runs the first and second innings make.</p>', unsafe_allow_html=True)
        g = c.daynight_summary(tuple(seasons))
        if g.empty:
            c.empty("No matches with a day or night label in these seasons.")
        else:
            c.section("By start time", "Win % out of matches with a winner (ties and no results left out). "
                                       "Average innings totals from those matches.")
            dt = pd.DataFrame({"Start": g.index, "Matches": g["matches"].astype(int).values,
                               "With a winner": g["decided"].astype(int).values,
                               "Batting first won %": g["bat_first_pct"].values, "Toss winner won %": g["toss_won_pct"].values,
                               "Chose to field %": g["field_pct"].values, "Avg 1st inns": g["avg1"].values,
                               "Avg 2nd inns": g["avg2"].values,
                               "Sample": np.where(g["matches"] < c.SMALL_MATCHES, "Small", "")})
            c.table(dt, column_config={"Start": c.col_text(width="small"), "Matches": c.col_int(),
                                       "With a winner": c.col_int(), "Batting first won %": c.col_pct(),
                                       "Toss winner won %": c.col_pct(), "Chose to field %": c.col_pct(help="Toss winners who chose to field"),
                                       "Avg 1st inns": c.col_1(help="Runs, extras included"),
                                       "Avg 2nd inns": c.col_1(help="Runs, extras included"),
                                       "Sample": c.col_text(width="small")})
            c.grouped_bars(list(g.index), [("Batting first won %", g["bat_first_pct"].values),
                                           ("Toss winner won %", g["toss_won_pct"].values)],
                           "Win %", key="dn_bars")
            tm = c.daynight_teams(tuple(seasons))
            wide = pd.DataFrame({"Team": sorted(tm["team"].unique())})
            cfg = {"Team": c.col_teams("Team")}
            for d in [x for x in c.DAYNIGHT if x in set(tm["daynight"])]:
                s = tm[tm["daynight"] == d].set_index("team")
                wide[f"{d} matches"] = wide["Team"].map(s["matches"]).fillna(0).astype(int).values
                wide[f"{d} win %"] = c.masked(wide["Team"].map(s["win_pct"]).values,
                                              wide["Team"].map(s["decided"]).fillna(0).values, c.SMALL_MATCHES)
                cfg[f"{d} matches"] = c.col_int()
                cfg[f"{d} win %"] = c.col_pct(help=f"Blank under {c.SMALL_MATCHES} matches with a winner")
            wide["Team"] = wide["Team"].map(c.code)
            c.section("Each franchise", f"Matches and win % by start time; win % is blank under {c.SMALL_MATCHES} "
                                        "matches with a winner.")
            c.table(wide, column_config=cfg)
            c.note(c.TEAM_LEGEND)
        c.note(f"Start times are the data's day, day/night or night label for each match. Showing "
               f"{', '.join(map(str, seasons))}.")

c.note(f"Line, length and shot data: {c.ll_seasons_text()}.")
c.footer()
