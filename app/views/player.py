"""
player.py - one player's PSL record: overview, seasons, phases, against each bowling type
and batting hand (public styles only), venues and teams, game log. READ-ONLY.
"""

import html
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app/ folder, for common.py

import common as c  # noqa: E402

c.page("Player", "One player's PSL record: value, seasons, phases, matchups and every game.")
lo, hi = c.season_filter()

p = c.players()
options = c.player_options()
default = next((x for x in options if c.name(x) == "Babar Azam"), options[0])
c.link_default("player_pick", "player", options, default)
pid = st.selectbox("Player", options, key="player_pick", format_func=c.name, placeholder="Type a name")
c.link_set(player=pid)
c.export_subject(c.name(pid))

b = c.in_seasons(c.balls_for(pid), lo, hi)      # only this player's balls (indexed)
mp = c.in_seasons(c.query("SELECT x.match_id, x.team, x.player_id, m.season, m.date, m.team1, m.team2, "
                          "m.venue_name, m.winner FROM match_players x JOIN matches m USING (match_id)"), lo, hi)
mine = mp[mp["player_id"] == pid]
bat = b[b["batter_id"] == pid]
bowl = b[b["bowler_id"] == pid]
dism = b[(b["player_dismissed_id"] == pid) & b["out_any"]]

# ------------------------------------------------------------------ player header
hand, style, fam, src, hs, ss, country = p.loc[pid, ["batting_hand", "bowling_style", "style_family", "source_url",
                                                     "hand_source", "style_source", "country"]]
age_now, born, debut_age, _ = c.player_ages(pid)
# Profile line: age and birth year only (never the birth date), country, batting hand, Dugout style.
bio_bits = [f"Age {age_now} (born {born})" if age_now is not None else None,
            country if isinstance(country, str) else None,
            f"{hand}-hand bat" if isinstance(hand, str) else None,
            (f"{style} ({fam})" if isinstance(fam, str) and fam != "Pace" else style) if isinstance(style, str) else None,
            f"PSL debut at {debut_age}" if debut_age is not None else None]
style_txt = " | ".join(x for x in bio_bits if x)
# Header sources: only the Wikipedia link (CC BY-SA attribution) and "Developer verified". Every other
# source is listed once on the Method tab ("Data sources and method" link in the footer).
used = {s for v, s in ((hand, hs), (style, ss)) if isinstance(v, str) and isinstance(s, str)}
labels = []
for s in ("dbpedia", "manual", "developer"):
    if s in used:
        lab = c.SOURCE_LABEL[s]
        if lab == "Wikipedia":
            lab = f'<a href="{html.escape(src)}" target="_blank">Wikipedia</a>' if isinstance(src, str) else None
        if lab and lab not in labels:
            labels.append(lab)
src_txt = f" Source: {', '.join(labels)}." if labels and style_txt else ""
teams = c.teams_latest(mine)
seasons = sorted(mine["season"].unique())
st.markdown(f'<p class="dd-lede"><b>{html.escape(c.name(pid))}</b></p>'
            + (f'<p class="dd-meta">{mine["match_id"].nunique()} matches, '
               f'{seasons[0] if len(seasons) == 1 else f"{seasons[0]} to {seasons[-1]}"}. '
               f'{html.escape(style_txt) + "." if style_txt else "Style: no source yet."}{src_txt}</p>' if seasons else "")
            + c.team_chips(teams), unsafe_allow_html=True)
if mine.empty:
    c.empty(f"{c.name(pid)} played no PSL matches in {c.season_label(lo, hi)}.",
            " Choose a wider season range at the top of the page.")
    c.footer()
    st.stop()

raa_b = c.in_seasons(c.value("value_bat"), lo, hi)
raa_w = c.in_seasons(c.value("value_bowl"), lo, hi)
wpa_b = c.in_seasons(c.value("wpa_bat"), lo, hi)
wpa_w = c.in_seasons(c.value("wpa_bowl"), lo, hi)
my = {k: t[t["player_id"] == pid] for k, t in
      {"raa_b": raa_b, "raa_w": raa_w, "wpa_b": wpa_b, "wpa_w": wpa_w}.items()}

inns_bat = bat.groupby(["match_id", "inning"]).agg(runs=("batsman_runs", "sum")).reset_index() \
    if not bat.empty else pd.DataFrame(columns=["match_id", "inning", "runs"])
appeared = pd.concat([b.loc[b["batter_id"] == pid, ["match_id", "inning"]],
                      b.loc[b["non_striker_id"] == pid, ["match_id", "inning"]]]).drop_duplicates()
outs_all = len(dism)
runs, balls_f = int(bat["batsman_runs"].sum()), int(bat["faced"].sum())
pn = c.phase_names()

with st.container(key="dd_player_tabs"):    # key: on a phone the seven tabs wrap into two rows (common.CSS)
    t_over, t_str, t_seas, t_phase, t_match, t_vt, t_log = st.tabs(
        ["Overview", "Strengths", "Seasons", "Phases", "Matchups", "Venues & Teams", "Matches"])

# ------------------------------------------------------------------ overview
S = c.player_summary(pid, lo, hi)
with t_over:
    if S["bat"]:
        c.section("Batting")
        c.cards(export="Batting", items=[("Batting Total", c.raa_fmt(S["bat_total"]),
                                          f"RAA {c.raa_fmt(S['bat_raa'])}, Wicket Value {c.raa_fmt(S['bat_wv'])}"),
                 ("Batting WPA", c.fmt(S["bat_wpa"], 2, True), ""),
                 ("Runs", c.num_fmt(S["runs"]), f"{S['balls']:,} balls"),
                 ("Innings", c.num_fmt(S["innings"]), ""),
                 ("Average", c.fmt(S["avg"]), f"{S['outs']:,} outs"),
                 ("Strike rate", c.fmt(S["sr"]), ""),
                 ("50s", c.num_fmt(S["fifties"]), f"HS {S['hs']}")], lead=True, detail=True)
        f4, f6 = int(bat["four"].sum()), int(bat["six"].sum())
        bs = c.boundary_stats(runs, balls_f, f4, f6)
        c.section("Boundaries", "Balls faced exclude wides.")
        c.cards(export="Boundaries", items=[("Balls per four", c.fmt(bs["balls_per_4"]), f"{f4:,} fours"),
                 ("Balls per six", c.fmt(bs["balls_per_6"]), f"{f6:,} sixes"),
                 ("Boundary balls", c.pct(bs["bdry_pct"]), "fours and sixes per ball"),
                 ("Runs in 4s and 6s", c.pct(bs["bdry_runs_pct"]), "of runs off the bat")], detail=True)
    fd = c.fielding_table(lo, hi)[0]
    if pid in fd.index:
        f = fd.loc[pid]
        st.markdown(f'<p class="dd-meta"><b>Fielding:</b> {int(f["ct"])} catches, {int(f["ro"])} run outs, '
                    f'{int(f["st"])} stumpings; {c.fmt(f["per_match"], 2)} dismissals per match '
                    f'({int(f["mat"])} matches).</p>', unsafe_allow_html=True)
    if S["bowl"]:
        c.section("Bowling")
        c.cards(export="Bowling", items=[("Bowling Total", c.raa_fmt(S["bowl_total"]),
                                          f"RAA {c.raa_fmt(S['bowl_raa'])}, Wicket Value {c.raa_fmt(S['bowl_wv'])}"),
                 ("Bowling WPA", c.fmt(S["bowl_wpa"], 2, True), ""),
                 ("Wickets", c.num_fmt(S["wkts"]), f"{S['conceded']:,} runs conceded"),
                 ("Overs", c.overs(S["legal"]), f"{S['bowl_matches']} matches"),
                 ("Economy", c.fmt(S["econ"], 2), ""),
                 ("Average", c.fmt(S["bowl_avg"]), ""),
                 ("Dot ball %", c.pct(S["bowl_dot"]), "")], lead=True, detail=True)
    c.note(c.VALUE_NOTE + " " + c.HELP["WPA"])

    # The only download on the site: a branded image with "Dugout Data" and "Data: Cricsheet.org".
    c.section("Share", "A 1080 x 1350 image of these numbers, for social posts.")
    if st.button("Make share card", key=f"share_{pid}_{lo}_{hi}"):
        st.session_state["share_for"] = (pid, lo, hi)
    if st.session_state.get("share_for") == (pid, lo, hi):
        png = c.share_card_png(pid, lo, hi)
        st.image(png, width=360)
        st.download_button("Download share card (PNG)", png, file_name=f"dugout-data-{c.slug(c.name(pid))}-{lo}-{hi}.png",
                           mime="image/png", key="share_download")

# ------------------------------------------------------------------ seasons
sb = c.bat_stats(bat, "season").set_index("season") if not bat.empty else pd.DataFrame()
sw = c.bowl_stats(bowl, "season").set_index("season") if not bowl.empty else pd.DataFrame()
rows = []
for s in seasons:
    rows.append({
        "Season": s, "Team": ", ".join(c.code(x) for x in sorted(mine.loc[mine["season"] == s, "team"].unique())),
        "Matches": mine.loc[mine["season"] == s, "match_id"].nunique(),
        "Runs": sb["runs"].get(s, 0) if len(sb) else 0, "SR": sb["sr"].get(s, np.nan) if len(sb) else np.nan,
        "Bat Total": my["raa_b"].loc[my["raa_b"]["season"] == s, "total"].sum(),
        "Bat WPA": my["wpa_b"].loc[my["wpa_b"]["season"] == s, "wpa"].sum(),
        "Wkts": sw["wkts"].get(s, 0) if len(sw) else 0, "Econ": sw["econ"].get(s, np.nan) if len(sw) else np.nan,
        "Bowl Total": my["raa_w"].loc[my["raa_w"]["season"] == s, "total"].sum(),
        "Bowl WPA": my["wpa_w"].loc[my["wpa_w"]["season"] == s, "wpa"].sum()})
seas = pd.DataFrame(rows)
seas["Total"] = seas["Bat Total"] + seas["Bowl Total"]
with t_over:
    c.section("Value by season", "Total (batting plus bowling). Blue: above the average men's T20 player in the "
                                 "same situations; red: below.")
    c.polarity_bars([str(s) for s in seas["Season"]], seas["Total"],
                    [f"{s}: {v:+.1f} runs (bat {a:+.1f}, bowl {w:+.1f})" for s, v, a, w in
                     zip(seas["Season"], seas["Total"], seas["Bat Total"], seas["Bowl Total"])],
                    "Total (runs)", key="seasons_chart", height=260)
with t_seas:
    c.section("Season by season")
    c.table(seas, column_config={
        "Season": st.column_config.NumberColumn(format="%d", width="small"), "Team": c.col_teams(),
        "Matches": c.col_int(), "Runs": c.col_int(), "SR": c.col_1(help=c.HELP["SR"]),
        "Wkts": c.col_int(), "Econ": c.col_2(help=c.HELP["Econ"]),
        "Bat Total": c.col_raa(help=c.HELP["Total"]), "Bowl Total": c.col_raa(help=c.HELP["Total"]),
        "Total": c.col_raa(help="Batting Total plus bowling Total, in runs"),
        "Bat WPA": c.col_wpa(), "Bowl WPA": c.col_wpa()})
    c.note(c.VALUE_NOTE + " " + c.HELP["WPA"])

# ------------------------------------------------------------------ phases
with t_phase:
    c.section("Batting by phase", "Powerplay overs 1 to 6, Middle 7 to 15, Death 16 to 20.")
    if bat.empty:
        c.empty("Did not bat in these seasons.")
    else:
        t = c.bat_stats(bat, "phase_no")
        r = my["raa_b"].groupby("phase_no")[["raa", "wv", "total"]].sum()
        t["RAA"] = t["phase_no"].map(r["raa"]).fillna(0)
        t["Wicket Value"] = t["phase_no"].map(r["wv"]).fillna(0)
        t["Total"] = t["phase_no"].map(r["total"]).fillna(0)
        t["Phase"] = t["phase_no"].map(pn)
        c.table(t[["Phase", "balls", "runs", "outs", "sr", "dot_pct", "bdry_pct", "RAA", "Wicket Value", "Total"]]
                .rename(columns={"balls": "Balls", "runs": "Runs", "outs": "Outs", "sr": "SR",
                                 "dot_pct": "Dot %", "bdry_pct": "Boundary %"}),
                column_config={"Phase": c.col_text(), "Balls": c.col_int(), "Runs": c.col_int(),
                               "Outs": c.col_int(help="Dismissals on strike"), "SR": c.col_1(help=c.HELP["SR"]),
                               "Dot %": c.col_pct(help=c.HELP["Dot %"]), "Boundary %": c.col_pct(help=c.HELP["Boundary %"]),
                               "RAA": c.col_raa(help=c.HELP["RAA"]), "Wicket Value": c.col_raa(help=c.HELP["Wicket Value"]),
                               "Total": c.col_raa(help=c.HELP["Total"])})
    c.section("Batting by position", "Position in the batting order: the order in which batters first came to "
                                     "the crease in that innings.")
    pt = c.position_stats(pid, lo, hi)
    if pt.empty:
        c.empty("Did not bat in these seasons.")
    else:
        c.table(pt[["Position", "Inns", "Runs", "Balls", "SR", "Avg"]],
                column_config={"Position": c.col_text(), "Inns": c.col_int(), "Runs": c.col_int(),
                               "Balls": c.col_int(help="Balls faced, wides not counted"),
                               "SR": c.col_1(help=c.HELP["SR"]), "Avg": c.col_1(help=c.HELP["Avg"])})
    c.section("Bowling by phase")
    if bowl.empty:
        c.empty("Did not bowl in these seasons.")
    else:
        t = c.bowl_stats(bowl, "phase_no")
        r = my["raa_w"].groupby("phase_no")[["raa", "wv", "total"]].sum()
        t["RAA"] = t["phase_no"].map(r["raa"]).fillna(0)
        t["Wicket Value"] = t["phase_no"].map(r["wv"]).fillna(0)
        t["Total"] = t["phase_no"].map(r["total"]).fillna(0)
        t["Phase"] = t["phase_no"].map(pn)
        t["Overs"] = t["balls"].map(c.overs_num)
        c.table(t[["Phase", "Overs", "runs", "wkts", "econ", "dot_pct", "RAA", "Wicket Value", "Total"]]
                .rename(columns={"runs": "Runs", "wkts": "Wkts", "econ": "Econ", "dot_pct": "Dot %"}),
                column_config={"Phase": c.col_text(), "Overs": c.col_1(help="Overs bowled (3.2 = 3 overs 2 balls)"),
                               "Runs": c.col_int(), "Wkts": c.col_int(), "Econ": c.col_2(help=c.HELP["Econ"]),
                               "Dot %": c.col_pct(help=c.HELP["Dot %"]), "RAA": c.col_raa(help=c.HELP["RAA"]),
                               "Wicket Value": c.col_raa(help=c.HELP["Wicket Value"]),
                               "Total": c.col_raa(help=c.HELP["Total"])})
    c.note(c.VALUE_NOTE + " Batting outs here count dismissals on strike; the career average also counts "
           "run-outs at the non-striker's end.")

    # Phase C (2026-11-09): entry situation and dismissal profile, after everything above.
    c.section("When he comes in", "The score, wickets and overs when he first came to the crease (before his first "
                                  "ball at either end), and how he batted from there.")
    ent, by_wkts, by_phase, (role, n_role, n_inns) = c.entry_summary(pid, lo, hi)
    if ent.empty:
        c.empty("Did not bat in these seasons.")
    else:
        few = n_inns < c.SMALL_INNS
        c.cards(detail=True, items=[
            ("Usual position", role if n_inns >= c.MIN_INNS else "Not enough innings",
             f"{n_role} of {n_inns} innings" + (" (small sample)" if few else "")),
            ("Average score when in", f"{ent['score_in'].mean():.0f}/{ent['wkts_in'].mean():.1f}",
             f"runs/wickets, {n_inns} innings"),
            ("Average over when in", c.fmt(ent["legal_in"].mean() / 6, 1), f"{n_inns} innings")])
        ecfg = {"Inns": c.col_int(), "Runs": c.col_int(), "Balls": c.col_int(help="Balls faced, wides not counted"),
                "SR": c.col_1(help=c.HELP["SR"]), "Avg": c.col_1(help=c.HELP["Avg"] + f" Blank under {c.MIN_INNS} innings."),
                "Score when in": c.col_1(help="Average team score when he came in"),
                "Sample": c.col_text(width="small")}
        for g, first in ((by_wkts, "Came in at"), (by_phase, "Came in during")):
            c.table(pd.DataFrame({first: g.index, "Inns": g["inns"].values, "Runs": g["runs"].values,
                                  "Balls": g["balls"].values, "SR": c.masked(g["sr"], g["balls"]),
                                  "Avg": c.masked(g["avg"], g["inns"], c.MIN_INNS),
                                  "Score when in": g["score"].values, "Sample": c.count_label(g["inns"])}),
                    column_config={first: c.col_text(), **ecfg})
        c.note(f"Usual position: the band of batting positions he batted in most often (Mixed when no band has half "
               f"his innings). SR is blank under {c.MIN_BALLS} balls. Phase when in: legal balls bowled before he came "
               "in (Powerplay overs 1 to 6, Middle 7 to 15, Death 16 to 20).")
    c.section("How he gets out", "Every dismissal (as striker or non-striker), retired hurt and retired not out left "
                                 "out, against all PSL dismissals in the same seasons.")
    dp = c.dismissal_profile(pid, lo, hi)
    n_out = int(dp["n"].sum())
    if n_out < c.MIN_INNS:
        c.empty(f"Not enough dismissals for {c.name(pid)} in {c.season_label(lo, hi)} ({n_out}).",
                f" A profile needs at least {c.MIN_INNS}. Widen the seasons.")
    else:
        dp = dp[(dp["n"] > 0) | (dp["psl"] >= 1)]
        c.table(pd.DataFrame({"How out": dp.index, "Dismissals": dp["n"].values, "Share %": dp["share"].values,
                              "PSL share %": dp["psl"].values}),
                column_config={"How out": c.col_text(), "Dismissals": c.col_int(), "Share %": c.col_pct(),
                               "PSL share %": c.col_pct(help="All PSL dismissals, same seasons")})
        c.note(f"{n_out} dismissals." + (f" Small sample (under {c.SMALL_INNS})." if n_out < c.SMALL_INNS else "")
               + " Other: hit wicket, obstructing the field, retired out.")

# ------------------------------------------------------------------ against types and hands
with t_match:
    c.section("Batting against each bowling type")
    if bat.empty:
        c.empty("Did not bat in these seasons.")
    else:
        t = c.bat_stats(bat, "bowl_style")
        t["order"] = t["bowl_style"].map({s: i for i, s in enumerate(c.STYLE_ORDER)})
        t = t.sort_values("order")
        c.table(t[["bowl_style", "balls", "runs", "outs", "sr", "avg", "dot_pct", "bdry_pct"]]
                .rename(columns={"bowl_style": "Bowling type", "balls": "Balls", "runs": "Runs", "outs": "Outs",
                                 "sr": "SR", "avg": "Avg", "dot_pct": "Dot %", "bdry_pct": "Boundary %"}),
                column_config={"Bowling type": c.col_text(), "Balls": c.col_int(), "Runs": c.col_int(),
                               "Outs": c.col_int(help="Dismissals on strike"), "SR": c.col_1(help=c.HELP["SR"]),
                               "Avg": c.col_1(help=c.HELP["Avg"]), "Dot %": c.col_pct(help=c.HELP["Dot %"]),
                               "Boundary %": c.col_pct(help=c.HELP["Boundary %"])})
    c.section("Bowling against each batting hand")
    if bowl.empty:
        c.empty("Did not bowl in these seasons.")
    else:
        t = c.bowl_stats(bowl, "bat_hand")
        t["Overs"] = t["balls"].map(c.overs_num)
        t["bat_hand"] = t["bat_hand"].replace({"Right": "Right-hand batters", "Left": "Left-hand batters"})
        c.table(t[["bat_hand", "Overs", "runs", "wkts", "econ", "avg", "sr", "dot_pct"]]
                .rename(columns={"bat_hand": "Batters", "runs": "Runs", "wkts": "Wkts", "econ": "Econ",
                                 "avg": "Avg", "sr": "Balls per wkt", "dot_pct": "Dot %"}),
                column_config={"Batters": c.col_text(), "Overs": c.col_1(help="Overs bowled (3.2 = 3 overs 2 balls)"),
                               "Runs": c.col_int(), "Wkts": c.col_int(), "Econ": c.col_2(help=c.HELP["Econ"]),
                               "Avg": c.col_1(help=c.HELP["Avg"]),
                               "Balls per wkt": c.col_1(help=c.HELP["Balls per dismissal"]),
                               "Dot %": c.col_pct(help=c.HELP["Dot %"])})
    c.note("Styles come from Wikipedia, DBpedia and Wikidata, or are developer verified. "
           "Unknown means no source for that player yet.")
    c.section("Best batting partners", "Partnership runs together (extras included), balls faced (no wides).")
    pp = c.player_partners(pid, lo, hi)
    if pp.empty:
        c.empty("Did not bat in these seasons.")
    else:
        c.table(pp[["Partner", "inns", "runs", "balls", "rr", "best", "fifty"]]
                .rename(columns={"inns": "Inns", "runs": "Runs", "balls": "Balls", "rr": "Run rate", "best": "Best",
                                 "fifty": "50+"}),
                column_config={"Partner": c.col_text(), "Inns": c.col_int(help="Stands together"), "Runs": c.col_int(),
                               "Balls": c.col_int(), "Run rate": c.col_2(help="Runs per 6 balls faced"),
                               "Best": c.col_int(help="Highest stand"), "50+": c.col_int(help="Stands of 50 or more")})

# ------------------------------------------------------------------ strengths and weaknesses
with t_str:
    st.markdown('<p class="dd-meta">Each situation is compared with the PSL average for the same situation in the '
                'chosen seasons. Small samples are pulled towards the average before ranking, so a few lucky '
                'balls do not top the list.</p>', unsafe_allow_html=True)
    min_b = st.number_input("Minimum balls in a situation", 10, 500, c.MIN_SPLIT_BALLS, 10, key="str_min",
                            help=f"Situations with fewer balls are left out. Shrinkage: {c.SHRINK_BALLS} balls "
                                 "at the PSL rate are added to each situation before ranking, and only "
                                 f"differences of at least {c.MIN_EFFECT:.0%} after that are listed.")
    shown = 0
    for role, title, did in (("bat", "Batting", S["bat"]), ("bowl", "Bowling", S["bowl"])):
        if not did:
            continue
        best, worst = c.top_strengths(pid, lo, hi, role, min_balls=min_b)
        if best.empty and worst.empty:
            continue
        shown += 1
        c.section(title, "Against bowling types, by phase and at each ground." if role == "bat" else
                  "Against right- and left-hand batters, by phase and at each ground.")
        left, right = st.columns(2)
        with left:
            st.markdown("**Strengths**")
            st.markdown("\n".join(f"- {c.strength_sentence(r)}" for r in best.to_dict("records"))
                        or "No situation clearly above the PSL average.")
        with right:
            st.markdown("**Weaknesses**")
            st.markdown("\n".join(f"- {c.strength_sentence(r)}" for r in worst.to_dict("records"))
                        or "No situation clearly below the PSL average.")
        c.effect_bars(pd.concat([best, worst]), key=f"str_{role}", height=90 + 38 * (len(best) + len(worst)))
    if not shown:
        c.empty(f"Not enough balls for {c.name(pid)} in {c.season_label(lo, hi)}.",
                " Lower the minimum or widen the seasons.")
    c.note("Strike rate and dot balls use balls faced (bowling: legal balls). Dismissals for batting are outs on "
           "strike; for bowling, bowler wickets. Styles and batting hands come from Wikipedia, DBpedia and Wikidata, or are "
           "developer verified.")

# ------------------------------------------------------------------ venues and teams
VT_BAT_CFG = {"Venue": c.col_text(), "Opposition": c.col_text(), "Mat": c.col_int(help="Matches played"),
              "Inns": c.col_int(help="Innings at the crease"), "Runs": c.col_int(),
              "Balls": c.col_int(help="Balls faced, wides not counted"), "SR": c.col_1(help=c.HELP["SR"]),
              "Avg": c.col_1(help=c.HELP["Avg"]), "Boundary %": c.col_pct(help=c.HELP["Boundary %"]),
              "RAA": c.col_raa(help=c.HELP["RAA"]), "Wicket Value": c.col_raa(help=c.HELP["Wicket Value"]),
              "Total": c.col_raa(help=c.HELP["Total"])}
VT_BOWL_CFG = {"Venue": c.col_text(), "Opposition": c.col_text(), "Mat": c.col_int(help="Matches in which the player bowled"),
               "Overs": c.col_1(help="Overs bowled (3.2 = 3 overs 2 balls)"), "Wkts": c.col_int(),
               "Runs": c.col_int(help="Runs conceded"), "Econ": c.col_2(help=c.HELP["Econ"]),
               "Avg": c.col_1(help=c.HELP["Avg"]), "Balls per wkt": c.col_1(help=c.HELP["Balls per dismissal"]),
               "Dot %": c.col_pct(help=c.HELP["Dot %"]), "RAA": c.col_raa(help=c.HELP["RAA"]),
               "Wicket Value": c.col_raa(help=c.HELP["Wicket Value"]), "Total": c.col_raa(help=c.HELP["Total"])}
VT_BAT_COLS = ["Mat", "Inns", "Runs", "Balls", "SR", "Avg", "Boundary %", "RAA", "Wicket Value", "Total"]
VT_BOWL_COLS = ["Mat", "Overs", "Wkts", "Runs", "Econ", "Avg", "Balls per wkt", "Dot %", "RAA", "Wicket Value", "Total"]

with t_vt:
    st.markdown('<p class="dd-meta">Batting and bowling at each PSL ground and against each team, in the chosen '
                f'seasons. Rows need at least {c.VT_MIN_BAT} balls faced (batting) or {c.VT_MIN_BOWL} legal balls '
                '(bowling); small samples swing a lot.</p>', unsafe_allow_html=True)
    show_all = st.toggle("Show all", key="vt_all",
                         help="Show every venue and team, including those below the minimum balls.")
    V = c.venue_team_splits(pid, lo, hi)
    for role, did, nothing in (("bat", S["bat"], "Did not bat in these seasons."),
                               ("bowl", S["bowl"], "Did not bowl in these seasons.")):
        for key, label, title in (("venue", "Venue", "at each venue"), ("team", "Opposition", "against each team")):
            plural = "venues" if key == "venue" else "teams"
            c.section(("Batting " if role == "bat" else "Bowling ") + title)
            t = V[f"{role}_{key}"]
            if not did or t.empty:
                c.empty(nothing)
                continue
            n_col, minimum, unit = (("Balls", c.VT_MIN_BAT, "balls faced") if role == "bat"
                                    else ("Legal balls", c.VT_MIN_BOWL, "legal balls"))
            keep = t if show_all else t[t[n_col] >= minimum]
            if keep.empty:
                c.empty(f"No {key} with at least {minimum} {unit}.", " Switch on Show all to see every row.")
            else:
                cols = [label] + (VT_BAT_COLS if role == "bat" else VT_BOWL_COLS)
                c.table(keep[cols], column_config={k: v for k, v in (VT_BAT_CFG if role == "bat" else VT_BOWL_CFG).items()
                                                   if k in cols})
            left = len(t) - len(keep)
            c.note(f"Sample: {len(keep)} of {len(t)} {plural}, {int(keep[n_col].sum()):,} of {int(t[n_col].sum()):,} "
                   f"{unit}." + (f" {left} {plural if left != 1 else plural[:-1]} under {minimum} {unit} left out; "
                                 "switch on Show all to see them." if left else
                                 (f" Rows under {minimum} {unit} are small samples." if show_all else "")))
    c.note("Batting Avg counts every dismissal, like the career average; Wicket Value counts outs on strike, like "
           "the rest of the site. Runs conceded leave out byes and leg-byes; run outs are not bowler wickets. "
           + c.VALUE_NOTE)

# ------------------------------------------------------------------ match by match
with t_log:
    mr = c.match_rows(pid, lo, hi)
    c.section("Every match", "Newest first. WPA is the change in the team's chance of winning from this player's "
                             "batting and bowling in that match.")
    show_cols = ["Date", "Opp", "Runs", "Balls", "SR", "How out", "Overs", "Wkts", "Conceded", "Econ", "WPA", "Result"]
    if not S["bowl"]:
        show_cols = [x for x in show_cols if x not in ("Overs", "Wkts", "Conceded", "Econ")]
    c.table(mr[show_cols], column_config={
        "Date": c.col_text(width="small"), "Opp": c.col_teams("Opp"), "Runs": c.col_int(), "Balls": c.col_int(),
        "SR": c.col_1(help=c.HELP["SR"]), "How out": c.col_text(),
        "Overs": c.col_1(help="Overs bowled (3.2 = 3 overs 2 balls)"), "Wkts": c.col_int(),
        "Conceded": c.col_int(help="Runs conceded"), "Econ": c.col_2(help=c.HELP["Econ"]),
        "WPA": c.col_wpa(help=c.HELP["WPA"] + " Blank: no WPA for that match."), "Result": c.col_text(width="small")})

    c.section("Ball by ball", "Runs scored by ball faced, with fours and sixes; for a bowler, runs conceded by "
                              "legal ball, with wickets.")
    ids = list(mr["match_id"])
    if ids:
        labels = dict(zip(mr["match_id"], [f"{d} v {o}" for d, o in zip(mr["Date"], mr["Opp"])]))
        c.link_default("match_pick", "match", ids, ids[0])
        mid = st.selectbox("Match", ids, key="match_pick", format_func=labels.get)
        c.link_set(match=mid)
        bat_b, out_b, bowl_b = c.progression(pid, mid)
        if len(bat_b) or len(bowl_b):
            c.progression_chart(bat_b, out_b, bowl_b, key="progression")
        else:
            c.empty("Did not bat or bowl in this match.")

        ov = c.match_overs(mid)
        t1 = ov.loc[ov["inning"] == 1, "team"].iloc[0] if (ov["inning"] == 1).any() else ""
        t2 = ov.loc[ov["inning"] == 2, "team"].iloc[0] if (ov["inning"] == 2).any() else ""
        wp = c.match_wp(mid)
        c.section("The match", f"Win chance of {t1} (batting first) after every ball, and runs and wickets in "
                               "every over of both innings.")
        if wp is None:
            c.note("Win probability needs a newer data file (wp_ball). Over by over is shown below.")
        elif wp.empty:
            c.note("No win probability for this match (see Method).")
        if len(ov):
            c.match_charts(ov, wp, t1, t2, key="match")
            grid = ov.pivot_table(index="over", columns="inning", values=["runs", "wkts"], aggfunc="sum")
            tab = pd.DataFrame({"Over": grid.index})
            for inn, t in ((1, t1), (2, t2)):
                if ("runs", inn) in grid.columns:
                    tab[f"{c.code(t)} runs"] = grid[("runs", inn)].values
                    tab[f"{c.code(t)} wkts"] = grid[("wkts", inn)].values
            c.table(tab, column_config={k: c.col_int() for k in tab.columns})

c.footer()
