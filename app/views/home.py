"""
home.py - Dugout Data home: PSL records (most runs, wickets, catches, best economy and strike
rate) and the RAA and WPA leaderboards as tabs in one row; biggest movers; links.
READ-ONLY: reads data/psl.sqlite only.
"""

import pandas as pd
import streamlit as st

import common as c

lo, hi = c.season_filter()
c.page("PSL at a Glance", f"Records, leaderboards and player value, {c.season_label(lo, hi)}. "
                          "For every season since 2016, choose All seasons at the top.")
# Default minimums from common.record_minimums (one season, or a range). The slider key carries the kind of
# range, so switching between one season and several starts from the matching default.
MIN_OVERS, MIN_BALLS = c.record_minimums(lo, hi)
KIND = "one" if lo == hi else "many"

# ------------------------------------------------------------------ at a glance
m = c.in_seasons(c.matches(), lo, hi)
rb, rw = c.in_seasons(c.value("raa_bat"), lo, hi), c.in_seasons(c.value("raa_bowl"), lo, hi)
tot_raa = pd.concat([rb[["player_id", "raa"]], rw[["player_id", "raa"]]]).groupby("player_id")["raa"].sum()
top = tot_raa.idxmax() if len(tot_raa) else None
c.cards([("Matches", f"{len(m):,}", ""),
         ("Players", f"{len(set(rb['player_id']) | set(rw['player_id'])):,}", ""),
         ("Balls", f"{int(rb['balls'].sum()):,}", ""),
         ("Top value", c.name(top) if top else "-", f"{c.raa_fmt(tot_raa.max())} RAA" if top else "")], lead=True)

# ------------------------------------------------------------------ records and leaderboards (one row of tabs)
bat, bowl, catches, unresolved = c.record_tables(lo, hi)
NUM = {"Mat": c.col_int(help="Matches played"), "Inns": c.col_int(help="Innings batted (at the crease)"),
       "Runs": c.col_int(), "Balls": c.col_int(help="Balls faced, wides not counted"),
       "HS": st.column_config.TextColumn("HS", help="Highest score; * = not out", width="small", alignment="right"),
       "Avg": c.col_1(help=c.HELP["Avg"]), "SR": c.col_1(help=c.HELP["SR"]), "50s": c.col_int(), "100s": c.col_int(),
       "4s": c.col_int(help="Fours"), "6s": c.col_int(help="Sixes"),
       "Overs": c.col_1(help="Overs bowled (3.2 = 3 overs 2 balls)"), "Wkts": c.col_int(help="Bowler wickets"),
       "BBI": st.column_config.TextColumn("BBI", help="Best bowling in an innings: wickets/runs", width="small",
                                           alignment="right"),
       "Econ": c.col_2(help=c.HELP["Econ"]), "Bowl SR": c.col_1("SR", help="Balls bowled per wicket"),
       "Bowl avg": c.col_1("Avg", help="Runs conceded per wicket"), "Conceded": c.col_int("Runs", help="Runs conceded"),
       "Ct": c.col_int(help="Catches, wicketkeepers included; caught and bowled counts for the bowler"),
       "Dots %": c.col_pct(help=c.HELP["Dot %"]), "Ducks": c.col_int(help="Out for 0"),
       "30s": c.col_int(help="Innings of 30 to 49"), "Maidens": c.col_int(help="Overs of 6 legal balls, no run conceded"),
       "4W": c.col_int(help="Innings with exactly 4 wickets"), "5W": c.col_int(help="Innings with 5 or more wickets"),
       "Wides": c.col_int(help="Wides bowled (deliveries)"), "NB": c.col_int(help="No-balls bowled (deliveries)"),
       "RO": c.col_int(help="Run outs: every fielder named in the run out is credited"),
       "St": c.col_int(help="Stumpings"), "Dis": c.col_int(help="Catches plus run outs plus stumpings"),
       "Per match": c.col_2(help="Fielding dismissals per match played"),
       "Balls per 4": c.col_1(help="Balls faced per four"),
       "Balls per 6": c.col_1(help="Balls faced per six"),
       "Boundary %": c.col_pct(help="Fours and sixes per ball faced"),
       "Runs in 4s and 6s %": c.col_pct(help="Share of runs off the bat that came in fours and sixes"),
       "Player": c.col_text(), "#": st.column_config.NumberColumn(format="%d", width=40)}


def ranked(df, n):
    df = df.head(n).reset_index()
    df.insert(0, "#", range(1, len(df) + 1))
    df["Player"] = df["pid"].map(c.name)
    return df


def leaderboard(table, metric, min_balls):
    v = c.in_seasons(c.value(table), lo, hi)
    agg = {"balls": ("balls", "sum"), "runs": ("runs", "sum"), metric: (metric, "sum")}
    if table == "raa_bat":
        agg["outs"] = ("outs", "sum")
    if table == "raa_bowl":
        agg["wkts"] = ("wkts", "sum")
    if table.startswith("raa"):
        agg["wins"] = ("wins", "sum")
    g = v.groupby("player_id").agg(**agg).reset_index()
    g["teams"] = g["player_id"].map(c.codes_by_player(table, lo, hi))
    g = g[g["balls"] >= min_balls]
    g["Player"] = g["player_id"].map(c.name)
    g["per 100 balls"] = c.div(g[metric], g["balls"], 100)
    if "bowl" in table:
        g["Econ"] = c.div(g["runs"], g["balls"], 6)
    else:
        g["SR"] = c.div(g["runs"], g["balls"], 100)
    g = g.sort_values(metric, ascending=False).head(15).reset_index(drop=True)
    g.insert(0, "#", g.index + 1)
    cols = ["#", "Player", "teams", "balls", "runs"] + (["wkts"] if "wkts" in g else []) + \
           (["Econ"] if "Econ" in g else ["SR"]) + [metric, "per 100 balls"] + (["wins"] if "wins" in g else [])
    return g[cols].rename(columns={"teams": "Team", "balls": "Balls", "runs": "Runs", "wkts": "Wkts",
                                   metric: metric.upper(), "wins": "Wins"})


VALUE_TABS = {"Batting RAA": ("raa_bat", "raa"), "Bowling RAA": ("raa_bowl", "raa"),
              "Batting WPA": ("wpa_bat", "wpa"), "Bowling WPA": ("wpa_bowl", "wpa")}
c.section("Records and leaderboards")
tabs = st.tabs(["Most runs", "Most wickets", "Most catches", "Best economy", "Best strike rate"] + list(VALUE_TABS)
               + ["Boundaries", "Fielding", "Partnerships"])

with tabs[0]:
    t = ranked(bat.sort_values(["runs", "balls"], ascending=[False, True]), 10)
    t = t.rename(columns={"mat": "Mat", "inns": "Inns", "runs": "Runs", "hs": "HS", "avg": "Avg", "sr": "SR",
                          "fifties": "50s", "hundreds": "100s", "fours": "4s", "sixes": "6s",
                          "balls": "Balls", "dot_pct": "Dots %", "ducks": "Ducks", "thirties": "30s"})
    c.table(t[["#", "Player", "Mat", "Inns", "Runs", "HS", "Avg", "SR", "Balls", "Dots %", "30s", "50s", "100s",
               "Ducks", "4s", "6s"]], column_config=NUM, title="Most runs")
    c.note("Average counts every dismissal, including run-outs at the non-striker's end.")
with tabs[1]:
    t = ranked(bowl.sort_values(["wkts", "conceded"], ascending=[False, True]), 10)
    t = t.rename(columns={"mat": "Mat", "overs": "Overs", "wkts": "Wkts", "best": "BBI", "avg": "Bowl avg",
                          "econ": "Econ", "sr": "Bowl SR", "maidens": "Maidens", "four_w": "4W",
                          "five_w": "5W", "wides": "Wides", "noballs": "NB"})
    c.table(t[["#", "Player", "Mat", "Overs", "Wkts", "BBI", "Bowl avg", "Econ", "Bowl SR", "Maidens", "4W", "5W",
               "Wides", "NB"]], column_config=NUM, title="Most wickets")
    c.note("Wickets credited to the bowler (not run-outs). Runs conceded include wides and no-balls, not byes "
           "or leg-byes.")
with tabs[2]:
    t = ranked(catches.sort_values("ct", ascending=False), 5).rename(columns={"mat": "Mat", "ct": "Ct"})
    c.table(t[["#", "Player", "Mat", "Ct"]], column_config=NUM, title="Most catches")
    c.note("Includes catches by wicketkeepers; a caught and bowled counts for the bowler. Substitute fielders are "
           "credited by name" + (f"; {unresolved} catch{'es' if unresolved != 1 else ''} by substitutes could not "
                                 "be matched to a player and are left out." if unresolved else "."))
with tabs[3]:
    min_overs = st.slider("Minimum overs", 0, 200, MIN_OVERS, 5, key=f"rec_min_overs_{KIND}",
                          help="Players with at least this many overs bowled in the chosen seasons.")
    t = bowl[bowl["legal"] >= min_overs * 6].sort_values(["econ", "legal"], ascending=[True, False])
    if t.empty:
        c.empty("No bowler has that many overs in these seasons.", " Lower the minimum or widen the seasons.")
    else:
        t = ranked(t, 10).rename(columns={"mat": "Mat", "overs": "Overs", "conceded": "Conceded", "wkts": "Wkts",
                                          "econ": "Econ"})
        c.table(t[["#", "Player", "Mat", "Overs", "Conceded", "Wkts", "Econ"]], column_config=NUM, title="Best economy")
with tabs[4]:
    min_sr_balls = st.slider("Minimum balls faced", 0, 1500, MIN_BALLS, 10, key=f"rec_min_balls_{KIND}",
                             help="Players with at least this many balls faced in the chosen seasons.")
    t = bat[bat["balls"] >= min_sr_balls].sort_values(["sr", "balls"], ascending=[False, False])
    if t.empty:
        c.empty("No batter has faced that many balls in these seasons.", " Lower the minimum or widen the seasons.")
    else:
        t = ranked(t, 10).rename(columns={"mat": "Mat", "inns": "Inns", "runs": "Runs", "balls": "Balls",
                                          "sr": "SR", "avg": "Avg"})
        c.table(t[["#", "Player", "Mat", "Inns", "Runs", "Balls", "SR", "Avg"]], column_config=NUM, title="Best strike rate")

for tab, (label, (table, metric)) in zip(tabs[5:9], VALUE_TABS.items()):
    with tab:
        mb = st.slider("Minimum balls", 0, 600, 120, 30, key=f"min_{table}",
                       help="Balls faced for batting, balls bowled for bowling, in the chosen seasons.")
        t = leaderboard(table, metric, mb)
        if t.empty:
            c.empty("No player has that many balls in these seasons.", " Lower the minimum or widen the seasons.")
            continue
        c.table(t, title=label, column_config={
            "#": st.column_config.NumberColumn(format="%d", width=40), "Player": c.col_text(),
            "Team": c.col_teams(), "Balls": c.col_int(), "Runs": c.col_int(), "Wkts": c.col_int(),
            "SR": c.col_1(help=c.HELP["SR"]), "Econ": c.col_2(help=c.HELP["Econ"]),
            "RAA": c.col_raa(), "WPA": c.col_wpa(),
            "per 100 balls": c.col_raa(help=c.HELP["per 100 balls"]) if metric == "raa" else
            c.col_wpa(help=c.HELP["per 100 balls"]),
            "Wins": c.col_wpa(help=c.HELP["Wins"])})
        c.note(c.HELP["RAA"] if metric == "raa" else c.HELP["WPA"] + " WPA is missing for 18 matches (see Method).")

with tabs[9]:
    min_bd = st.slider("Minimum balls faced", 0, 1500, MIN_BALLS, 10, key=f"rec_min_bdry_{KIND}",
                       help="Players with at least this many balls faced in the chosen seasons.")
    t = bat[bat["balls"] >= max(min_bd, 1)].copy()
    if t.empty:
        c.empty("No batter has faced that many balls in these seasons.", " Lower the minimum or widen the seasons.")
    else:
        t["Balls per 4"], t["Balls per 6"] = c.div(t["balls"], t["fours"]), c.div(t["balls"], t["sixes"])
        t["Boundary %"] = c.div(t["fours"] + t["sixes"], t["balls"], 100)
        t["Runs in 4s and 6s %"] = c.div(4 * t["fours"] + 6 * t["sixes"], t["runs"], 100)
        t = ranked(t.sort_values(["Boundary %", "balls"], ascending=[False, False]), 10).rename(
            columns={"balls": "Balls", "runs": "Runs", "fours": "4s", "sixes": "6s"})
        c.table(t[["#", "Player", "Balls", "Runs", "4s", "6s", "Boundary %", "Balls per 4", "Balls per 6",
                   "Runs in 4s and 6s %"]], column_config=NUM, title="Boundaries")
        c.note("Balls faced exclude wides. Ranked by boundary %: fours and sixes per ball faced.")
with tabs[10]:
    fd, f_unres = c.fielding_table(lo, hi)
    t = ranked(fd.sort_values(["dis", "mat"], ascending=[False, True]), 10).rename(
        columns={"mat": "Mat", "ct": "Ct", "ro": "RO", "st": "St", "dis": "Dis", "per_match": "Per match"})
    c.table(t[["#", "Player", "Mat", "Dis", "Ct", "RO", "St", "Per match"]], column_config=NUM, title="Fielding")
    c.note("Catches as in Most catches. A run out credits every fielder named in it. "
           + (f"{f_unres} fielder name{'s' if f_unres != 1 else ''} (substitutes) could not be matched to a player."
              if f_unres else ""))
with tabs[11]:
    t = c.top_partnerships(lo, hi)
    t.insert(0, "#", range(1, len(t) + 1))
    c.table(title="Partnerships", df=t[["#", "Pair", "inns", "runs", "balls", "rr", "best", "fifty"]]
            .rename(columns={"inns": "Inns", "runs": "Runs", "balls": "Balls", "rr": "Run rate", "best": "Best",
                             "fifty": "50+"}),
            column_config={"#": NUM["#"], "Pair": c.col_text(width="large"), "Inns": c.col_int(help="Stands together"),
                           "Runs": c.col_int(help="Partnership runs, extras included"),
                           "Balls": c.col_int(help="Balls faced, wides not counted"),
                           "Run rate": c.col_2(help="Runs per 6 balls faced"), "Best": c.col_int(help="Highest stand"),
                           "50+": c.col_int(help="Stands of 50 or more")})
    c.note("A stand is two batters at the crease together in an innings, whichever end.")

c.note("Cricsheet has 23 of the 24 matches of PSL 2016, so totals that include 2016 can be slightly below "
       "official PSL records. See Method.")

# ------------------------------------------------------------------ biggest movers
prev = hi - 1
c.section("Biggest movers", f"Total RAA (batting plus bowling) in {hi} against {prev}. Players need 60 balls "
                            "(faced plus bowled) in both seasons." if prev >= 2016 else "")
if prev < 2016:
    c.empty("Movers compare a season with the one before.", " Choose a range ending in 2017 or later.")
else:
    tot = pd.concat([c.value("raa_bat")[["season", "player_id", "raa", "balls"]],
                     c.value("raa_bowl")[["season", "player_id", "raa", "balls"]]])
    s = tot[tot["season"].isin([prev, hi])].groupby(["player_id", "season"]).agg(raa=("raa", "sum"), balls=("balls", "sum")).unstack()
    s = s.dropna()
    s = s[(s[("balls", prev)] >= 60) & (s[("balls", hi)] >= 60)]
    move = pd.DataFrame({"Player": s.index.map(c.name), f"RAA {prev}": s[("raa", prev)].values,
                         f"RAA {hi}": s[("raa", hi)].values})
    move["Change"] = move[f"RAA {hi}"] - move[f"RAA {prev}"]
    cfg = {"Player": c.col_text(), **{k: c.col_raa() for k in move.columns if k != "Player"}}
    a, b = st.tabs(["Up most", "Down most"])
    with a:
        c.table(move.sort_values("Change", ascending=False).head(8), column_config=cfg, title="Biggest movers up")
    with b:
        c.table(move.sort_values("Change").head(8), column_config=cfg, title="Biggest movers down")
    c.note(c.HELP["RAA"] + " Change = RAA " + str(hi) + " minus RAA " + str(prev) + ".")

# ------------------------------------------------------------------ explore
c.section("Explore")
links = [("views/player.py", "Player", "Any player's value, seasons, phases and game log."),
         ("views/matchups.py", "Matchups", "Batter v bowler, and against each type of bowling."),
         ("views/compare.py", "Compare", "Two players side by side."),
         ("views/teams.py", "Teams", "Value, form, head to head and every season."),
         ("views/venues.py", "Venues", "Par scores, chasing, pace v spin, the toss."),
         ("views/method.py", "Method", "How every number is made, and its limits.")]
cols = st.columns(len(links))
for col, (path, label, desc) in zip(cols, links):
    with col:
        st.page_link(path, label=label)
        st.caption(desc)

c.footer()
