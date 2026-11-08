"""
teams.py - each franchise: value by phase (Total), strongest and weakest roles, top contributors;
form and streaks; head to head; results and totals at each venue; batting and bowling style and wicket types; player movement;
squad (ages, overseas and local players, the PSL age curve); season review; toss; partnerships by wicket and
the collapse index, discipline (extras) and fielding (Phase C, 2026-11-09). READ-ONLY. Ages and countries come
from player_profile (sources listed on the Method tab); ages are shown in years, never a birth date.
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

# Phase C tabs (2026-11-09) come last and run only when opened (on_change="rerun" gives each tab an .open
# flag); the first nine tabs render exactly as before.
t_val, t_form, t_h2h, t_ven, t_style, t_move, t_squad, t_seas, t_toss, t_part, t_disc, t_field = st.tabs(
    ["Value", "Form", "Head to head", "Venues", "Style", "Players", "Squad", "Seasons", "Toss", "Partnerships",
     "Discipline", "Fielding"], key="team_tab", on_change="rerun")
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

# ------------------------------------------------------------------ venues
with t_ven:
    c.section(f"{team} at each venue", "Results and team totals at every PSL ground in the chosen seasons. "
                                       "Totals are runs including extras.")
    tv_all = st.toggle("Show all", key="tv_all",
                       help=f"Show every venue, including those with fewer than {c.TV_MIN_MATCHES} matches.")
    tv = c.team_venues(team, lo, hi)
    keep = tv if tv_all else tv[tv["Matches"] >= c.TV_MIN_MATCHES]
    if tv.empty:
        c.empty(f"{team} played no matches in {c.season_label(lo, hi)}.", " Choose a wider season range.")
    elif keep.empty:
        c.empty(f"No venue with at least {c.TV_MIN_MATCHES} {team} matches in {c.season_label(lo, hi)}.",
                " Switch on Show all to see every venue.")
    else:
        c.table(keep, column_config={
            "Venue": c.col_text(), "Matches": c.col_int(), "Won": c.col_int(), "Lost": c.col_int(),
            "Win %": c.col_pct(help="Won out of matches with a winner (ties and no results left out)"),
            "Avg 1st inns": c.col_1(help="Average total when batting first (matches with a result)"),
            "Avg 2nd inns": c.col_1(help="Average total when batting second (matches with a result)"),
            "Highest": c.col_int(help="Highest innings total (matches with a result)"),
            "Lowest": c.col_int(help="Lowest innings total (matches with a result, shortened innings included)")})
    left = len(tv) - len(keep)
    c.note(f"Minimum: {c.TV_MIN_MATCHES} matches at a venue. Showing {len(keep)} of {len(tv)} venues"
           + (f"; {left} with fewer matches left out (switch on Show all to see them)." if left else ".")
           + " Win %: won out of matches with a winner; a tie has no winner in the data and counts in Matches"
           " only. Totals and averages leave out no-result matches; rain-shortened"
           " innings are included. Avg 1st inns and Avg 2nd inns: batting first and batting second.")

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

# ------------------------------------------------------------------ squad: ages, overseas and local players
with t_squad:
    ages = c.team_ages(lo, hi)
    ov = c.overseas_value(lo, hi)
    me = ages[ages["team"] == team]
    mo = ov[ov["team"] == team]
    young, old, debuts = c.age_extremes(lo, hi, team)
    if me.empty:
        c.empty(f"{team} played no matches in {c.season_label(lo, hi)}.", " Choose a wider season range.")
    else:
        r, o = me.iloc[0], (mo.iloc[0] if len(mo) else None)
        c.cards(export="Squad", items=[
            ("Average age", c.fmt(r["avg_age"]), "Average age on match day, every appearance counted once"),
            ("Overseas share", c.pct(r["os_pct"]), f"{int(r['os_players'])} overseas players of {int(r['players'])}"),
            ("Youngest", c.name(young.iloc[0]["player_id"]) if len(young) else "-",
             f"{c.fmt(young.iloc[0]['age'])} years" if len(young) else ""),
            ("Oldest", c.name(old.iloc[0]["player_id"]) if len(old) else "-",
             f"{c.fmt(old.iloc[0]['age'])} years" if len(old) else ""),
            ("Overseas Total", c.raa_fmt(o["os_total"]) if o is not None else "-",
             "Batting plus bowling Total by overseas players, in runs"),
            ("Local Total", c.raa_fmt(o["local_total"]) if o is not None else "-",
             "Batting plus bowling Total by Pakistan players, in runs")], lead=True)
        c.section(f"{team} by season", "Ages on match day in years. Overseas: a player whose country is not Pakistan.")
        ts = c.team_season_ages(team, lo, hi)
        c.table(ts[["season", "avg_age", "youngest", "oldest", "players", "os_players", "os_pct"]].rename(columns={
                    "season": "Season", "avg_age": "Avg age", "youngest": "Youngest", "oldest": "Oldest",
                    "players": "Players", "os_players": "Overseas players", "os_pct": "Overseas %"}),
                column_config={"Season": st.column_config.NumberColumn(format="%d", width="small"),
                               "Avg age": c.col_1(help="Average age on match day, every appearance counted once"),
                               "Youngest": c.col_1(help="Youngest player's age on match day"),
                               "Oldest": c.col_1(help="Oldest player's age on match day"),
                               "Players": c.col_int(), "Overseas players": c.col_int(),
                               "Overseas %": c.col_pct(help="Overseas share of appearances")})
        c.section("Youngest and oldest", f"Each {team} player once, at his youngest or oldest match in the chosen seasons.")
        for title, t in (("Youngest", young), ("Oldest", old)):
            if len(t):
                c.table(title=f"{title} {team} players", df=pd.DataFrame({
                    "Player": t["player_id"].map(c.name).values, "Age": t["age"].values, "Season": t["season"].values}),
                    column_config={"Player": c.col_text(), "Age": c.col_1(help="Age on match day, in years"),
                                   "Season": st.column_config.NumberColumn(format="%d", width="small")})
        if len(debuts):
            c.section("PSL debuts", f"Players whose first PSL match was for {team} in the chosen seasons, youngest first.")
            c.table(pd.DataFrame({"Player": debuts["player_id"].map(c.name).values, "Debut age": debuts["age"].values,
                                  "Season": debuts["season"].values,
                                  "Overseas": debuts["overseas"].map({1: "Yes", 0: "No"}).fillna("-").values}).head(c.MAX_ROWS),
                    column_config={"Player": c.col_text(), "Debut age": c.col_1(help="Age at the first PSL match, in years"),
                                   "Season": st.column_config.NumberColumn(format="%d", width="small"),
                                   "Overseas": c.col_text(width="small")})

    c.section("All franchises", "Average age, overseas players and what overseas and local players added "
                                "(Total, and Total per 100 balls faced plus bowled).")
    allt = ages.merge(ov, on="team", how="left")
    allt["Team"] = allt["team"].map(lambda x: f"{x} ({c.code(x)})")
    c.table(allt.sort_values("avg_age")[["Team", "avg_age", "players", "os_players", "os_pct", "os_ball_pct",
                                         "os_total", "local_total", "os_per100", "local_per100"]].rename(columns={
                "avg_age": "Avg age", "players": "Players", "os_players": "Overseas players",
                "os_pct": "Overseas % of appearances", "os_ball_pct": "Overseas % of balls",
                "os_total": "Overseas Total", "local_total": "Local Total",
                "os_per100": "Overseas per 100 balls", "local_per100": "Local per 100 balls"}),
            column_config={"Team": c.col_text(), "Avg age": c.col_1(help="Average age on match day"),
                           "Players": c.col_int(), "Overseas players": c.col_int(),
                           "Overseas % of appearances": c.col_pct(),
                           "Overseas % of balls": c.col_pct(help="Overseas share of balls faced plus legal balls bowled"),
                           "Overseas Total": c.col_raa(help=c.HELP["Total"]), "Local Total": c.col_raa(help=c.HELP["Total"]),
                           "Overseas per 100 balls": c.col_wpa(help=c.HELP["per 100 balls"]),
                           "Local per 100 balls": c.col_wpa(help=c.HELP["per 100 balls"])})

    c.section("PSL age curve", "All PSL players by age on match day: Total per 100 balls (above zero is better than "
                               "the average men's T20 player).")
    ac = c.age_curve(lo, hi)
    bands = [lab for _, _, lab in c.AGE_BANDS]
    bat_c = ac[ac["role"] == "bat"].set_index("band").reindex(bands)
    bowl_c = ac[ac["role"] == "bowl"].set_index("band").reindex(bands)
    c.grouped_bars(bands, [("Batting", bat_c["per100"].values), ("Bowling", bowl_c["per100"].values)],
                   "Total per 100 balls", key="age_curve")
    curve = pd.DataFrame({"Age": bands, "Bat players": bat_c["players"].values, "Balls faced": bat_c["balls"].values,
                          "SR": bat_c["rate"].values, "Bat per 100": bat_c["per100"].values,
                          "Bowl players": bowl_c["players"].values, "Balls bowled": bowl_c["balls"].values,
                          "Econ": bowl_c["rate"].values, "Bowl per 100": bowl_c["per100"].values})
    c.table(curve.dropna(how="all", subset=["Balls faced", "Balls bowled"]),
            column_config={"Age": c.col_text(width="small"), "Bat players": c.col_int(), "Balls faced": c.col_int(),
                           "SR": c.col_1(help=c.HELP["SR"]), "Bat per 100": c.col_wpa(help=c.HELP["per 100 balls"]),
                           "Bowl players": c.col_int(), "Balls bowled": c.col_int(help="Legal balls"),
                           "Econ": c.col_2(help=c.HELP["Econ"]), "Bowl per 100": c.col_wpa(help=c.HELP["per 100 balls"])})
    c.note("Ages are in years on match day; players with no known birth "
           "date or country are left out. Overseas means a country other than Pakistan.")

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

# ------------------------------------------------------------------ toss (Phase B, 2026-11-08; Cricsheet)
with t_toss:
    tt = c.toss_teams(lo, hi)
    me = tt[tt["team"] == team]
    if me.empty:
        c.empty(f"{team} played no matches in {c.season_label(lo, hi)}.", " Choose a wider season range.")
    else:
        r = me.iloc[0]

        def rate(v, n, unit="matches"):
            return ("-" if n == 0 or v != v else c.pct(v)), f"{int(n)} {unit}" + (" (small sample)" if 0 < n < c.SMALL_MATCHES else "")

        # Teams cards show label and value only (STYLE.md); the counts are the hover note, and any small
        # sample is named in a line under the cards so phones see it too.
        items = [("Tosses won", c.pct(r["toss_pct"]), f"{int(r['tosses'])} of {int(r['matches'])} matches"),
                 ("Chose to field", *rate(r["field_pct"], r["tosses"], "tosses won")),
                 ("Win % after winning the toss", *rate(r["win_tw"], r["dec_tw"])),
                 ("Win % after losing the toss", *rate(r["win_tl"], r["dec_tl"])),
                 ("Win % batting first", *rate(r["win_bf"], r["dec_bf"])),
                 ("Win % chasing", *rate(r["win_ch"], r["dec_ch"]))]
        c.cards(export="Toss", lead=True, items=items)
        small = [lab for lab, _, n in items if "(small sample)" in n]
        c.note(f"{team}: {int(r['matches'])} matches, {int(r['tosses'])} tosses won. "
               + (f"Small samples (under {c.SMALL_MATCHES} matches): {', '.join(small)}." if small else ""))
    c.section("All franchises", f"Win % out of matches with a winner (ties and no results left out); blank under "
                                f"{c.SMALL_MATCHES} matches.")
    at_ = tt.sort_values("matches", ascending=False)
    c.table(pd.DataFrame({
        "Team": at_["team"].map(lambda x: f"{x} ({c.code(x)})").values, "Matches": at_["matches"].values,
        "Tosses won %": at_["toss_pct"].values, "Chose to field %": at_["field_pct"].values,
        "Win % won toss": c.masked(at_["win_tw"], at_["dec_tw"], c.SMALL_MATCHES),
        "Win % lost toss": c.masked(at_["win_tl"], at_["dec_tl"], c.SMALL_MATCHES),
        "Win % batting first": c.masked(at_["win_bf"], at_["dec_bf"], c.SMALL_MATCHES),
        "Win % chasing": c.masked(at_["win_ch"], at_["dec_ch"], c.SMALL_MATCHES)}),
        column_config={"Team": c.col_text(), "Matches": c.col_int(), "Tosses won %": c.col_pct(),
                       "Chose to field %": c.col_pct(help="Share of tosses won where the team chose to field"),
                       "Win % won toss": c.col_pct(), "Win % lost toss": c.col_pct(),
                       "Win % batting first": c.col_pct(), "Win % chasing": c.col_pct()})
    tl = c.toss_league(lo, hi)
    c.section("PSL by season", "Toss winners' choices and results, all matches.")
    c.table(pd.DataFrame({"Season": tl["season"].values, "Matches": tl["matches"].values,
                          "With a winner": tl["decided"].values, "Toss winner won %": tl["toss_won_pct"].values,
                          "Chose to field %": tl["field_pct"].values, "Batting first won %": tl["bf_pct"].values}),
            column_config={"Season": st.column_config.NumberColumn(format="%d", width="small"), "Matches": c.col_int(),
                           "With a winner": c.col_int(), "Toss winner won %": c.col_pct(),
                           "Chose to field %": c.col_pct(), "Batting first won %": c.col_pct()})
    c.note("Toss and results from Cricsheet, every season. Batting first follows the toss winner's choice. "
           "Ties are decided by a super over, which is not in the data, so a tie has no winner here.")

# ------------------------------------------------------------------ Phase C (2026-11-09): run only when opened
with t_part:
    if t_part.open:
        st_all = c.in_seasons(c.stands_by_wicket(), lo, hi)
        mine_st, ci = st_all[st_all["team"] == team], c.collapse_index(lo, hi)
        if mine_st.empty:
            c.empty(f"{team} batted in no innings in {c.season_label(lo, hi)}.", " Choose a wider season range.")
        else:
            me = ci.loc[team] if team in ci.index else None
            tb_, lg_ = c.stand_table(mine_st), c.stand_table(st_all)

            def inns_rate(v, n):
                return ("-" if n < c.MIN_INNS else c.pct(v)), f"{int(n)} innings" + (
                    " (small sample)" if c.MIN_INNS <= n < c.SMALL_INNS else (" (not enough innings)" if n < c.MIN_INNS else ""))

            items = [("Innings with a collapse", *inns_rate(me["coll_pct"], me["inns"])),
                     ("Collapses caused", *inns_rate(me["caused_pct"], me["inns_b"])),
                     ("Average opening stand", c.fmt(tb_.at[1, "avg"]), f"{int(tb_.at[1, 'stands'])} stands"),
                     ("50+ stands", f"{int(tb_['fifty'].sum()):,}", f"{len(mine_st):,} stands")]
            c.cards(export="Partnerships", lead=True, items=items)
            small = [lab for lab, _, n in items if "(small sample)" in n or "(not enough innings)" in n]
            c.note(f"A collapse: {c.COLLAPSE_WKTS} wickets for {c.COLLAPSE_RUNS} runs or fewer, counted from the score "
                   f"at the wicket before (80/2 to 100/5 is 3 for 20). Collapses caused: opponents' innings with one. "
                   + (f"Small samples: {', '.join(small)}." if small else ""))
            c.section(f"{team} stands by wicket", "Runs from the fall of one wicket to the next (extras included); balls "
                                                  "faced, wides not counted. Average: runs per stand that ended.")
            c.table(pd.DataFrame({
                "Wicket": [c.wicket_label(w) for w in tb_.index], "Stands": tb_["stands"].values,
                "Runs": tb_["runs"].values, "Average": c.masked(tb_["avg"], tb_["ended"], c.MIN_INNS),
                "Run rate": c.masked(tb_["rr"], tb_["stands"], c.MIN_INNS), "Best": tb_["best"].values,
                "50+": tb_["fifty"].values, "PSL average": lg_["avg"].values,
                "Sample": c.count_label(tb_["stands"], unit="stands")}),
                column_config={"Wicket": c.col_text(width="small"), "Stands": c.col_int(), "Runs": c.col_int(),
                               "Average": c.col_1(help=f"Blank under {c.MIN_INNS} stands that ended"),
                               "Run rate": c.col_2(help="Runs per 6 balls faced"), "Best": c.col_int(),
                               "50+": c.col_int(help="Stands of 50 or more"),
                               "PSL average": c.col_1(help="All franchises, same seasons"),
                               "Sample": c.col_text(width="small")})
            c.section("All franchises", f"Collapse rates are blank under {c.MIN_INNS} innings.")
            op = c.in_seasons(c.stands_by_wicket(), lo, hi)
            op = op[op["wicket"] == 1].groupby("team").agg(n=("runs", "size"), ended=("ended", "sum"), runs=("runs", "sum"))
            at_ = ci.sort_values("inns", ascending=False)
            c.table(pd.DataFrame({
                "Team": [f"{x} ({c.code(x)})" for x in at_.index], "Innings": at_["inns"].values,
                "With a collapse %": c.masked(at_["coll_pct"], at_["inns"], c.MIN_INNS),
                "Collapses caused %": c.masked(at_["caused_pct"], at_["inns_b"], c.MIN_INNS),
                "Average opening stand": pd.Series(c.div(op["runs"], op["ended"]), index=op.index).reindex(at_.index).values}),
                column_config={"Team": c.col_text(), "Innings": c.col_int(help="Innings batted"),
                               "With a collapse %": c.col_pct(help="Share of innings batted with a collapse"),
                               "Collapses caused %": c.col_pct(help="Share of opponents' innings with a collapse"),
                               "Average opening stand": c.col_1(help="Runs per 1st-wicket stand that ended")})
        c.note("Innings 1 and 2 only. A wicket is any dismissal except retired hurt and retired not out. The last "
               "stand of an innings is unbroken unless ten wickets fell.")

EXT_CFG = {"Matches": c.col_int(help="Innings bowled"), "Wides": c.col_int(help="Wide balls"),
           "Wide runs": c.col_int(help="Runs from wides, boundaries off wides included"),
           "No-balls": c.col_int(), "No-ball runs": c.col_int(
               help="The no-ball extra (a no-ball with byes or leg byes: 1 run, the rest are byes)"),
           "Byes": c.col_int(), "Leg byes": c.col_int(),
           "Wides per 100 balls": c.col_2(help="Wides per 100 legal balls"),
           "Extras per match": c.col_1(help="All extras, penalty runs included")}


def ext_frame(g, first, labels):
    g = c.extras_rates(g)
    return pd.DataFrame({first: labels, "Matches": g["matches"].values, "Wides": g["wides"].values,
                         "Wide runs": g["wide_runs"].values, "No-balls": g["noballs"].values,
                         "No-ball runs": g["nb_runs"].values, "Byes": g["byes"].values,
                         "Leg byes": g["legbyes"].values, "Wides per 100 balls": g["wides_100"].values,
                         "Extras per match": g["extras_pm"].values})


with t_disc:
    if t_disc.open:
        ex = c.team_extras(lo, hi)
        mine_ex = ex[ex["team"] == team]
        if mine_ex.empty:
            c.empty(f"{team} bowled in no innings in {c.season_label(lo, hi)}.", " Choose a wider season range.")
        else:
            r = c.extras_rates(mine_ex.drop(columns=["team", "season"]).sum().to_frame().T).iloc[0]
            m_ = int(r["matches"])
            sm = " (small sample)" if m_ < c.SMALL_MATCHES else ""
            c.cards(export="Discipline", lead=True, items=[
                ("Wides per match", c.fmt(r["wides_pm"], 2), f"{int(r['wides']):,} wides in {m_} matches{sm}"),
                ("No-balls per match", c.fmt(r["noballs_pm"], 2), f"{int(r['noballs']):,} no-balls in {m_} matches{sm}"),
                ("Extras per match", c.fmt(r["extras_pm"], 1), f"{int(r['extras']):,} extras in {m_} matches{sm}"),
                ("Byes and leg byes per match", c.fmt(r["byes_pm"], 2),
                 f"{int(r['byes'] + r['legbyes']):,} runs in {m_} matches{sm}")])
            c.note(f"{team}: {m_} matches bowled in, {int(r['legal']):,} legal balls."
                   + (f" Small sample: under {c.SMALL_MATCHES} matches." if sm else ""))
            c.section(f"{team} by season", "Extras given away when bowling.")
            ms = mine_ex.sort_values("season")
            c.table(ext_frame(ms, "Season", ms["season"].values),
                    column_config={"Season": st.column_config.NumberColumn(format="%d", width="small"), **EXT_CFG})
            c.section("All franchises", "Extras given away when bowling, the chosen seasons together.")
            al = ex.drop(columns="season").groupby("team").sum().sort_values("matches", ascending=False)
            c.table(ext_frame(al, "Team", [f"{x} ({c.code(x)})" for x in al.index]),
                    column_config={"Team": c.col_text(), **EXT_CFG})
        c.note("Innings 1 and 2 only (super overs left out). Runs conceded by the bowler include wides and the "
               "no-ball extra, not byes or leg byes.")

with t_field:
    if t_field.open:
        tf = c.team_fielding(lo, hi, team)
        if tf.empty:
            c.empty(f"No catches, run outs or stumpings for {team} in {c.season_label(lo, hi)}.",
                    " Choose a wider season range.")
        else:
            c.section(f"{team} fielders", f"Dismissals made for {team}. Per match is blank under {c.SMALL_MATCHES} "
                                          f"matches for {team}.")
            tf = tf.head(c.MAX_ROWS)
            c.table(pd.DataFrame({"Player": [c.name(x) for x in tf.index], "Mat": tf["mat"].values,
                                  "Dis": tf["dis"].values, "Ct": tf["ct"].values, "RO": tf["ro"].values,
                                  "St": tf["st"].values, "Per match": tf["per_match"].values}),
                    column_config={"Player": c.col_text(), "Mat": c.col_int(help=f"Matches for {team}"),
                                   "Dis": c.col_int(help="Catches, run outs and stumpings"),
                                   "Ct": c.col_int(help="Catches (wicketkeepers included; caught and bowled to the bowler)"),
                                   "RO": c.col_int(help="Run outs: every fielder named in one is credited"),
                                   "St": c.col_int(help="Stumpings"), "Per match": c.col_2()})
        fd, f_unres = c.fielding_table(lo, hi)
        c.section("PSL leaders", "All franchises, the chosen seasons. Top 10 each.")
        cols = st.columns(3)
        for col, (k, title, head) in zip(cols, (("ct", "Most catches", "Catches"), ("ro", "Most run outs", "Run outs"),
                                                ("st", "Most stumpings", "Stumpings"))):
            with col:
                top = fd[fd[k] > 0].sort_values([k, "mat"], ascending=[False, True]).head(10)
                if top.empty:
                    c.empty(f"No {head.lower()} in these seasons.")
                else:
                    c.table(pd.DataFrame({"Player": [c.name(x) for x in top.index], "Mat": top["mat"].values,
                                          head: top[k].values}),
                            column_config={"Player": c.col_text(), "Mat": c.col_int()}, title=title)
        c.note("Fielders from Cricsheet, matched to the player by that match's squad (substitutes by name). "
               + (f"{f_unres} fielder name{'s' if f_unres != 1 else ''} could not be matched." if f_unres else ""))

c.footer()
