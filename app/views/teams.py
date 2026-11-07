"""
teams.py - each franchise: value by phase (Total), strongest and weakest roles, top contributors;
form and streaks; head to head; batting and bowling style and wicket types; player movement; season
review. READ-ONLY.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app/ folder, for common.py

import common as c  # noqa: E402

c.page("Teams", "Where each franchise gains and loses runs, its form, rivals and seasons.")
lo, hi = c.season_filter()
pn = c.phase_names()

rb = c.in_seasons(c.value("value_bat"), lo, hi)
rw = c.in_seasons(c.value("value_bowl"), lo, hi)


def by_team_phase(t):
    g = t.groupby(["team", "phase_no"]).agg(total=("total", "sum"), balls=("balls", "sum")).reset_index()
    g["per100"] = c.div(g["total"], g["balls"], 100)
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
c.export_subject(team)
labels = [pn[n] for n in sorted(pn)]
tb = bat[bat["team"] == team].set_index("phase_no").reindex(sorted(pn))
tw = bowl[bowl["team"] == team].set_index("phase_no").reindex(sorted(pn))

t_val, t_form, t_h2h, t_style, t_move, t_seas = st.tabs(
    ["Value", "Form", "Head to head", "Style", "Players", "Seasons"])
with t_val:
    roles = pd.DataFrame([{"Role": f"{k} in the {pn[n].split(' (')[0]}", "per100": t.loc[n, "per100"], "total": t.loc[n, "total"]}
                          for k, t in (("Batting", tb), ("Bowling", tw)) for n in sorted(pn) if pd.notna(t.loc[n, "per100"])])
    if len(roles):
        best, worst = roles.loc[roles["per100"].idxmax()], roles.loc[roles["per100"].idxmin()]
        c.cards(export="Strongest and weakest role", items=[("Strongest role", best["Role"], f"{c.raa_fmt(best['total'])} Total, {best['per100']:+.2f} per 100 balls"),
                 ("Weakest role", worst["Role"], f"{c.raa_fmt(worst['total'])} Total, {worst['per100']:+.2f} per 100 balls")],
                lead=True)

    c.section(f"{team} by phase", "Total per 100 balls: above zero means better than the average men's T20 side "
                                  "in the same situations.")
    c.grouped_bars(labels, [("Batting", tb["per100"].values), ("Bowling", tw["per100"].values)],
                   "Total per 100 balls", key="team_phase")

    c.section("Top contributors", "Total (batting plus bowling) for this franchise in the chosen seasons.")
    pb = rb[rb["team"] == team].groupby("player_id").agg(bat=("total", "sum"), bat_balls=("balls", "sum"))
    pw = rw[rw["team"] == team].groupby("player_id").agg(bowl=("total", "sum"), bowl_balls=("balls", "sum"))
    top = pb.join(pw, how="outer").fillna(0)
    top["Total"] = top["bat"] + top["bowl"]
    top = top.sort_values("Total", ascending=False).reset_index()
    top["Player"] = top["player_id"].map(c.name)
    c.table(top[["Player", "bat_balls", "bat", "bowl_balls", "bowl", "Total"]]
            .rename(columns={"bat_balls": "Balls faced", "bat": "Bat Total", "bowl_balls": "Balls bowled",
                             "bowl": "Bowl Total"}),
            column_config={"Player": c.col_text(), "Balls faced": c.col_int(), "Balls bowled": c.col_int(),
                           "Bat Total": c.col_raa(help=c.HELP["Total"]), "Bowl Total": c.col_raa(help=c.HELP["Total"]),
                           "Total": c.col_raa(help="Batting Total plus bowling Total, in runs")})

    # ------------------------------------------------------------------ league table
    c.section("All franchises", "Phase columns are Total per 100 balls; totals are in runs.")
    grid = pd.DataFrame({"Team": teams})
    for kind, g in (("Bat", bat), ("Bowl", bowl)):
        for n, label in pn.items():
            s = g[g["phase_no"] == n].set_index("team")["per100"]
            grid[f"{kind} {label.split(' ')[0]}"] = grid["Team"].map(s)
        tot = g.groupby("team").agg(total=("total", "sum"), balls=("balls", "sum"))
        grid[f"{kind} Total"] = grid["Team"].map(tot["total"])
    grid["Total"] = grid["Bat Total"] + grid["Bowl Total"]
    grid = grid.sort_values("Total", ascending=False)
    c.table(grid, column_config={"Team": c.col_text(), **{
        k: (c.col_raa(help="Total in runs") if "total" in k.lower() else c.col_wpa(help=c.HELP["per 100 balls"]))
        for k in grid.columns if k != "Team"}})
    c.note(c.VALUE_NOTE)

# ------------------------------------------------------------------ form
with t_form:
    res = c.team_results(team, lo, hi)
    last = res.head(10)
    cur, best = c.streaks(res["Result"].tolist())
    c.cards(export="Form", items=[("Last 10", f"{(last['Result'] == 'W').sum()}-{(last['Result'] == 'L').sum()}", "won-lost"),
             ("Current streak", cur, "W won, L lost, T tie, NR no result"),
             ("Longest winning run", str(best), "in the chosen seasons"),
             ("Matches", f"{len(res):,}", f"{(res['Result'] == 'W').sum()} won")], lead=True)
    c.section("Last 10 matches", "Newest first. Ties: the super over is not in the data, so no winner is shown.")
    c.table(last[["Date", "Opp", "Result", "Margin"]],
            column_config={"Date": c.col_text(width="small"), "Opp": c.col_teams("Opp"),
                           "Result": c.col_text(width="small"), "Margin": c.col_text()})

# ------------------------------------------------------------------ head to head
with t_h2h:
    others = [x for x in codes if x != c.code(team)]
    c.link_default("h2h_pick", "opp", others, others[0])
    opp = teams[codes.index(st.selectbox("Opponent", others, key="h2h_pick",
                                          format_func=lambda k: f"{teams[codes.index(k)]} ({k})"))]
    c.link_set(opp=c.code(opp))
    hs, hp = c.head_to_head(team, opp, lo, hi)
    if not hs["matches"]:
        c.empty(f"{team} and {opp} did not meet in {c.season_label(lo, hi)}.", " Choose a wider season range.")
    else:
        c.cards(export=f"Head to head v {opp}", items=[("Matches", str(hs["matches"]), ""),
                 (f"{c.code(team)} won", str(hs["a_wins"]), ""), (f"{c.code(opp)} won", str(hs["b_wins"]), ""),
                 ("Tied or no result", str(hs["ties"] + hs["nr"]), f"{hs['ties']} tied, {hs['nr']} no result"),
                 (f"{c.code(team)} runs per innings", c.fmt(c.div(hs["a_runs"], hs["a_inns"]).item()),
                  f"{hs['a_runs']:,} in {hs['a_inns']} innings"),
                 (f"{c.code(opp)} runs per innings", c.fmt(c.div(hs["b_runs"], hs["b_inns"]).item()),
                  f"{hs['b_runs']:,} in {hs['b_inns']} innings")], lead=True)
        c.section("Phase by phase", "Each side's batting against the other: runs per over (extras included, legal "
                                    "balls) and wickets lost. Stronger: the higher run rate.")
        a_, b_ = c.code(team), c.code(opp)
        c.table(hp.rename(columns={"A RR": f"{a_} RR", "A wkts": f"{a_} wkts", "B RR": f"{b_} RR",
                                   "B wkts": f"{b_} wkts"}),
                column_config={"Phase": c.col_text(), f"{a_} RR": c.col_2(help="Runs per over"),
                               f"{b_} RR": c.col_2(help="Runs per over"), f"{a_} wkts": c.col_int(help="Wickets lost"),
                               f"{b_} wkts": c.col_int(help="Wickets lost"), "Stronger": c.col_text(width="small")})

# ------------------------------------------------------------------ style and wicket types
with t_style:
    c.section("Boundaries and dot balls", "Runs in 4s and 6s as a share of runs off the bat. Batting dot: a ball "
                                          "faced with no run off the bat; bowling dot: a legal ball with no run "
                                          "conceded.")
    ts = c.team_style(lo, hi)
    ts["Team"] = ts["Team"].map(lambda x: f"{x} ({c.code(x)})")
    c.table(ts.sort_values("Bat: runs in 4s and 6s %", ascending=False),
            column_config={"Team": c.col_text(), **{k: c.col_pct() for k in ts.columns if k != "Team"}})
    c.section(f"How {team} lose and take wickets", "Dismissals only (retired hurt and retired not out left out). "
                                                     "Taken includes run outs; PSL % is all franchises.")
    wt = c.wicket_types(team, lo, hi)
    c.table(wt, column_config={"How out": c.col_text(), "Lost": c.col_int(help="Batting: wickets lost this way"),
                               "Lost %": c.col_pct(), "Taken": c.col_int(help="Bowling and fielding"),
                               "Taken %": c.col_pct(), "PSL %": c.col_pct(help="All PSL dismissals")})

# ------------------------------------------------------------------ player movement
with t_move:
    c.section("Player movement", f"Players of {team} who also played for another franchise in the chosen "
                                 "seasons: the franchise in each season (from the match squads).")
    mv = c.player_movement(team, lo, hi)
    if mv.empty:
        c.empty(f"No {team} player played for another franchise in {c.season_label(lo, hi)}.")
    else:
        c.table(mv, column_config={"Player": c.col_text(), "Matches for team": c.col_int(help=f"Matches for {team}"),
                                   **{k: c.col_text(width="small") for k in mv.columns[2:]}})
        c.note(c.TEAM_LEGEND)

# ------------------------------------------------------------------ season review
with t_seas:
    c.section("Season review", "Champion: winner of the season's last match, the final. Runs off the bat and "
                               "bowler wickets; 4s and 6s per match over all matches of the season.")
    sr = c.season_review(lo, hi)
    sr["Champion"] = sr["Champion"].map(lambda x: c.code(x) if x in c.TEAM_CODES else x)
    c.table(sr, column_config={"Season": st.column_config.NumberColumn(format="%d", width="small"),
                               "Matches": c.col_int(), "Champion": c.col_teams("Champion"),
                               "Final v": c.col_teams("Final v"), "Top run-scorer": c.col_text(), "Runs": c.col_int(),
                               "Top wicket-taker": c.col_text(), "Wkts": c.col_int(),
                               "4s per match": c.col_1(help="Fours per match"),
                               "6s per match": c.col_1(help="Sixes per match")})
    c.note("Cricsheet has 23 of the 24 matches of PSL 2016. " + c.TEAM_LEGEND)

c.footer()
