"""
teams.py - each franchise by phase: batting and bowling value (RAA), strongest and weakest
roles, top contributors. READ-ONLY.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app/ folder, for common.py

import common as c  # noqa: E402

c.page("Teams", "Where each franchise gains and loses runs, phase by phase.")
lo, hi = c.season_filter()
pn = c.phase_names()

rb = c.in_seasons(c.value("raa_bat"), lo, hi)
rw = c.in_seasons(c.value("raa_bowl"), lo, hi)


def by_team_phase(t):
    g = t.groupby(["team", "phase_no"]).agg(raa=("raa", "sum"), balls=("balls", "sum")).reset_index()
    g["per100"] = c.div(g["raa"], g["balls"], 100)
    return g


bat, bowl = by_team_phase(rb), by_team_phase(rw)
teams = sorted(set(bat["team"]) | set(bowl["team"]))
if not teams:
    c.empty("No matches in these seasons.", " Choose a wider season range at the top of the page.")
    c.footer()
    st.stop()

# ------------------------------------------------------------------ one team
codes = [c.code(x) for x in teams]
c.link_default("team_pick", "team", codes, codes[0])
team = teams[codes.index(st.selectbox("Franchise", codes, key="team_pick",
                                        format_func=lambda k: f"{teams[codes.index(k)]} ({k})"))]
c.link_set(team=c.code(team))
labels = [pn[n] for n in sorted(pn)]
tb = bat[bat["team"] == team].set_index("phase_no").reindex(sorted(pn))
tw = bowl[bowl["team"] == team].set_index("phase_no").reindex(sorted(pn))

roles = pd.DataFrame([{"Role": f"{k} in the {pn[n].split(' (')[0]}", "per100": t.loc[n, "per100"], "raa": t.loc[n, "raa"]}
                      for k, t in (("Batting", tb), ("Bowling", tw)) for n in sorted(pn) if pd.notna(t.loc[n, "per100"])])
if len(roles):
    best, worst = roles.loc[roles["per100"].idxmax()], roles.loc[roles["per100"].idxmin()]
    c.cards([("Strongest role", best["Role"], f"{c.raa_fmt(best['raa'])} RAA, {best['per100']:+.2f} per 100 balls"),
             ("Weakest role", worst["Role"], f"{c.raa_fmt(worst['raa'])} RAA, {worst['per100']:+.2f} per 100 balls")],
            lead=True)

c.section(f"{team} by phase", "RAA per 100 balls: above zero means better than an average men's T20 side that season.")
c.grouped_bars(labels, [("Batting", tb["per100"].values), ("Bowling", tw["per100"].values)],
               "RAA per 100 balls", key="team_phase")

c.section("Top contributors", "Total RAA for this franchise in the chosen seasons.")
pb = rb[rb["team"] == team].groupby("player_id").agg(bat=("raa", "sum"), bat_balls=("balls", "sum"))
pw = rw[rw["team"] == team].groupby("player_id").agg(bowl=("raa", "sum"), bowl_balls=("balls", "sum"))
top = pb.join(pw, how="outer").fillna(0)
top["Total"] = top["bat"] + top["bowl"]
top = top.sort_values("Total", ascending=False).reset_index()
top["Player"] = top["player_id"].map(c.name)
c.table(top[["Player", "bat_balls", "bat", "bowl_balls", "bowl", "Total"]]
        .rename(columns={"bat_balls": "Balls faced", "bat": "Bat RAA", "bowl_balls": "Balls bowled",
                         "bowl": "Bowl RAA", "Total": "Total RAA"}),
        column_config={"Player": c.col_text(), "Balls faced": c.col_int(), "Balls bowled": c.col_int(),
                       "Bat RAA": c.col_raa(), "Bowl RAA": c.col_raa(), "Total RAA": c.col_raa()})

# ------------------------------------------------------------------ league table
c.section("All franchises", "Phase columns are RAA per 100 balls; totals are in runs.")
grid = pd.DataFrame({"Team": teams})
for kind, g in (("Bat", bat), ("Bowl", bowl)):
    for n, label in pn.items():
        s = g[g["phase_no"] == n].set_index("team")["per100"]
        grid[f"{kind} {label.split(' ')[0]}"] = grid["Team"].map(s)
    tot = g.groupby("team").agg(raa=("raa", "sum"), balls=("balls", "sum"))
    grid[f"{kind} total RAA"] = grid["Team"].map(tot["raa"])
grid["Total RAA"] = grid["Bat total RAA"] + grid["Bowl total RAA"]
grid = grid.sort_values("Total RAA", ascending=False)
c.table(grid, column_config={"Team": c.col_text(), **{
    k: (c.col_raa(help="Total RAA in runs") if "total" in k.lower() else c.col_wpa(help=c.HELP["per 100 balls"]))
    for k in grid.columns if k != "Team"}})
c.note(c.HELP["RAA"])

c.footer()
