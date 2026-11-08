"""
matchups.py - head to head (batter v bowler), batters against bowling types, and bowlers
against right- and left-hand batters; left- and right-hand batters against pace and spin, and
left-right partnerships. READ-ONLY. Styles and hands from player_profile (Dugout's own categories).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app/ folder, for common.py

import common as c  # noqa: E402

c.page("Matchups", "How a batter fared against one bowler, against each type of bowling, how bowlers did "
                   "against right- and left-hand batters, and how left and right compare.")
lo, hi = c.season_filter()
with st.spinner("Loading ball-by-ball data"):
    b = c.in_seasons(c.balls(), lo, hi)

VIEWS = {"h2h": "Head to head", "type": "Batters v bowling type", "hand": "Bowlers v batting hand",
         "lr": "Left and right"}
c.link_default("mu_view", "view", list(VIEWS), "h2h")
view = st.segmented_control("View", list(VIEWS), format_func=VIEWS.get, key="mu_view", label_visibility="collapsed")     or "h2h"

# ------------------------------------------------------------------ head to head
if view == "h2h":
    pairs = b.groupby(["batter_id", "bowler_id"])["faced"].sum().reset_index()
    if pairs.empty:
        c.empty("No balls in these seasons.", "Choose a wider season range at the top of the page.")
    else:
        batters = sorted(pairs["batter_id"].unique(), key=c.name)
        default = next((x for x in batters if c.name(x) == "Babar Azam"), batters[0])
        a, d = st.columns(2)
        c.link_default("mu_batter", "batter", batters, default)
        bat_id = a.selectbox("Batter", batters, key="mu_batter", format_func=c.name, placeholder="Type a name")
        opts = pairs[pairs["batter_id"] == bat_id].sort_values("faced", ascending=False)["bowler_id"].tolist()
        c.link_default("mu_bowler", "bowler", opts, next((x for x in opts if c.name(x) == "Shadab Khan"), opts[0]))
        bowl_id = d.selectbox("Bowler (most balls first)", opts, key="mu_bowler", format_func=c.name)
        c.link_set(view="h2h", batter=bat_id, bowler=bowl_id, type=None, hand=None)
        h = b[(b["batter_id"] == bat_id) & (b["bowler_id"] == bowl_id)]
        s = c.bat_stats(h.assign(all=1), "all").iloc[0]
        out = h[h["bowler_wkt"] & (h["player_dismissed_id"] == bat_id)]
        n_out = len(out)
        met = h["match_id"].nunique()
        first, last = h["date"].min(), h["date"].max()

        st.markdown(f'<p class="dd-lede"><b>{c.name(bat_id)} v {c.name(bowl_id)}, {c.season_label(lo, hi)}</b></p>'
                    f'<p class="dd-meta">They met in {met} {"match" if met == 1 else "matches"}'
                    + (f", on {c.date_fmt(first)}" if first == last else
                       f", from {c.date_fmt(first)} to {c.date_fmt(last)}")
                    + f". {c.name(bat_id)} faced {int(s['balls'])} balls from {c.name(bowl_id)}.</p>",
                    unsafe_allow_html=True)
        c.cards([("Balls", f"{int(s['balls']):,}", f"{met} {'match' if met == 1 else 'matches'}"),
                 ("Runs", f"{int(s['runs']):,}", f"{int(s['fours'])} fours, {int(s['sixes'])} sixes"),
                 ("Strike rate", c.fmt(s["sr"]), ""),
                 ("Dismissals", str(n_out), ""),
                 ("Average", c.fmt(c.div(s["runs"], n_out).item()), ""),
                 ("Balls per dismissal", c.fmt(c.div(s["balls"], n_out).item()), ""),
                 ("Dot ball %", c.pct(s["dot_pct"]), ""),
                 ("Boundary %", c.pct(s["bdry_pct"]), "")], lead=True, detail=True)

        def breakdown(by, label):
            g = c.bat_stats(h, by)
            dis = out.groupby(by).size()
            g["Dismissals"] = g[by].map(dis).fillna(0).astype(int)
            g["SR"] = g["sr"]
            g = g.rename(columns={"balls": "Balls", "runs": "Runs", "dot_pct": "Dot %", "bdry_pct": "Boundary %"})
            return g[[by, "Balls", "Runs", "SR", "Dismissals", "Dot %", "Boundary %"]].rename(columns={by: label})

        cfg = {"Balls": c.col_int(), "Runs": c.col_int(), "SR": c.col_1(help=c.HELP["SR"]),
               "Dismissals": c.col_int(), "Dot %": c.col_pct(help=c.HELP["Dot %"]),
               "Boundary %": c.col_pct(help=c.HELP["Boundary %"])}
        c.section("By phase", "Powerplay overs 1 to 6, Middle 7 to 15, Death 16 to 20.")
        ph = breakdown("phase_no", "Phase")
        ph["Phase"] = ph["Phase"].map(c.phase_names())
        c.table(ph, column_config={"Phase": c.col_text(width="medium"), **cfg})
        c.section("By season")
        c.table(breakdown("season", "Season"),
                column_config={"Season": st.column_config.NumberColumn(format="%d", width="small"), **cfg})

        c.section("Dismissals")
        if n_out:
            m = c.matches().set_index("match_id")
            dt = out.sort_values("delivery_no")
            dt = pd.DataFrame({
                "Date": dt["date"].map(c.date_fmt),
                "Match": [c.match_title(m.at[x, "team1"], m.at[x, "team2"]) for x in dt["match_id"]],
                "Venue": dt["venue_name"].map(c.ground),
                "Over": c.over_labels(dt).values,
                "How out": [c.how_out(k, f, mid, t) for k, f, mid, t in
                            zip(dt["dismissal_kind"], dt["fielder"], dt["match_id"], dt["bowling_team"])]})
            c.table(dt, column_config={"Date": c.col_text(width="small"), "Match": c.col_text(width="large"),
                                       "Venue": c.col_text(width="medium"),
                                       "Over": c.col_text(width="small", help="over.ball, e.g. 10.4 = 4th ball of the 11th over"),
                                       "How out": c.col_text(width="medium")})
        else:
            c.empty(f"{c.name(bowl_id)} has not dismissed {c.name(bat_id)} in {c.season_label(lo, hi)}.",
                    " Run-outs are not credited to the bowler.")

# ------------------------------------------------------------------ batters v bowling type
if view == "type":
    groups = ["Pace", "Spin", "Finger Spin", "Wrist Spin"] + c.STYLE_ORDER[:-1]
    a, m_ = st.columns([2, 1])
    old = st.query_params.get("type")
    if old in c.OLD_TYPE_NAMES and "mu_type" not in st.session_state:
        st.query_params["type"] = c.OLD_TYPE_NAMES[old]         # old shared links keep working
    c.link_default("mu_type", "type", groups, "Pace")
    choice = a.selectbox("Bowling type", groups, key="mu_type",
                         help="Pace and Spin are the groups; Finger Spin (off-spin, left-arm orthodox) and Wrist Spin "
                              "(leg-spin, left-arm wrist-spin) are the spin families; then each type.")
    c.link_set(view="type", type=choice, batter=None, bowler=None, hand=None)
    min_balls = m_.number_input("Minimum balls", 0, 2000, 60, 10, key="mb1")
    sub = (b[b["bowl_kind"] == choice] if choice in ("Pace", "Spin")
           else b[b["bowl_family"] == choice] if choice in ("Finger Spin", "Wrist Spin") else b[b["bowl_style"] == choice])
    t = c.bat_stats(sub, "batter_id")
    t = t[t["balls"] >= min_balls]
    t["Batter"] = t["batter_id"].map(c.name)
    sort = st.radio("Sort by", ["Runs", "SR", "Avg"], horizontal=True, key="s1")
    t = t.sort_values({"Runs": "runs", "SR": "sr", "Avg": "avg"}[sort], ascending=False)
    if t.empty:
        c.empty("No batter has that many balls against this type.", " Lower the minimum or widen the seasons.")
    else:
        c.table(t[["Batter", "balls", "runs", "outs", "sr", "avg", "dot_pct", "bdry_pct"]]
                .rename(columns={"balls": "Balls", "runs": "Runs", "outs": "Outs", "sr": "SR", "avg": "Avg",
                                 "dot_pct": "Dot %", "bdry_pct": "Boundary %"}),
                column_config={"Batter": c.col_text(), "Balls": c.col_int(), "Runs": c.col_int(),
                               "Outs": c.col_int(help="Dismissals on strike"), "SR": c.col_1(help=c.HELP["SR"]),
                               "Avg": c.col_1(help=c.HELP["Avg"]), "Dot %": c.col_pct(help=c.HELP["Dot %"]),
                               "Boundary %": c.col_pct(help=c.HELP["Boundary %"])})
    all_bat = c.bat_stats(sub.assign(all=1), "all")
    if len(all_bat):
        c.note(f"All batters against {choice}: strike rate {c.fmt(all_bat['sr'].iloc[0])}, average "
               f"{c.fmt(all_bat['avg'].iloc[0])}, {int(all_bat['balls'].iloc[0]):,} balls. Outs are dismissals on strike. "
               "Bowling types are Dugout's own categories.")

# ------------------------------------------------------------------ bowlers v batting hand
if view == "hand":
    a, m_ = st.columns([2, 1])
    c.link_default("mu_hand", "hand", ["Right", "Left"], "Right")
    hand = a.selectbox("Batting hand", ["Right", "Left"], key="mu_hand", format_func=lambda x: f"{x}-hand batters")
    c.link_set(view="hand", hand=hand, batter=None, bowler=None, type=None)
    min_balls2 = m_.number_input("Minimum balls", 0, 2000, 60, 10, key="mb2")
    t = c.bowl_stats(b[b["bat_hand"] == hand], "bowler_id")
    t = t[t["balls"] >= min_balls2]
    t["Bowler"] = t["bowler_id"].map(c.name)
    t["Style"] = t["bowler_id"].map(c.players()["bowling_style"]).fillna(c.UNKNOWN)
    t["Overs"] = t["balls"].map(c.overs_num)
    sort = st.radio("Sort by", ["Wkts", "Econ", "Dot %"], horizontal=True, key="s2")
    t = t.sort_values({"Wkts": "wkts", "Econ": "econ", "Dot %": "dot_pct"}[sort], ascending=(sort == "Econ"))
    if t.empty:
        c.empty("No bowler has that many balls against these batters.", " Lower the minimum or widen the seasons.")
    else:
        c.table(t[["Bowler", "Style", "Overs", "runs", "wkts", "econ", "avg", "sr", "dot_pct"]]
                .rename(columns={"runs": "Runs", "wkts": "Wkts", "econ": "Econ", "avg": "Avg",
                                 "sr": "Balls per wkt", "dot_pct": "Dot %"}),
                column_config={"Bowler": c.col_text(), "Style": c.col_text(), "Overs": c.col_1(help="Overs bowled (3.2 = 3 overs 2 balls)"),
                               "Runs": c.col_int(), "Wkts": c.col_int(), "Econ": c.col_2(help=c.HELP["Econ"]),
                               "Avg": c.col_1(help=c.HELP["Avg"]), "Balls per wkt": c.col_1(help=c.HELP["Balls per dismissal"]),
                               "Dot %": c.col_pct(help=c.HELP["Dot %"])})
    c.note("Batting hand and bowling type: Dugout's own categories. Balls to batters with no known hand are left out.")

# ------------------------------------------------------------------ left and right
if view == "lr":
    SPLITS = {"Group": ("bowl_kind", ["Pace", "Spin"]), "Family": ("bowl_family", c.FAMILY_ORDER),
              "Type": ("bowl_style", c.STYLE_ORDER[:-1])}
    c.link_default("mu_split", "split", list(SPLITS), "Group")
    split = st.radio("Bowling split by", list(SPLITS), horizontal=True, key="mu_split")
    c.link_set(view="lr", split=split, batter=None, bowler=None, type=None, hand=None)
    col, order = SPLITS[split]
    t = c.hand_v_bowling(b, col)
    c.section("Left- and right-hand batters against each kind of bowling",
              "Strike rate, average, dot and boundary balls for every PSL batter, by batting hand.")
    if t.empty:
        c.empty("No balls in these seasons.", " Choose a wider season range at the top of the page.")
    else:
        t["o"] = t[col].map({s: i for i, s in enumerate(order)})
        t = t.sort_values(["o", "bat_hand"], ascending=[True, False])
        sr = t.pivot(index=col, columns="bat_hand", values="sr").reindex([x for x in order if x in set(t[col])])
        c.grouped_bars(list(sr.index), [(f"{h}-hand batters", sr[h].values) for h in ("Right", "Left") if h in sr],
                       "Strike rate", key="lr_bars")
        t["Batters"] = t["bat_hand"] + "-hand"
        c.table(t[[col, "Batters", "balls", "runs", "outs", "sr", "avg", "dot_pct", "bdry_pct"]]
                .rename(columns={col: "Bowling", "balls": "Balls", "runs": "Runs", "outs": "Outs", "sr": "SR",
                                 "avg": "Avg", "dot_pct": "Dot %", "bdry_pct": "Boundary %"}),
                column_config={"Bowling": c.col_text(), "Batters": c.col_text(width="small"), "Balls": c.col_int(),
                               "Runs": c.col_int(), "Outs": c.col_int(help="Dismissals on strike"),
                               "SR": c.col_1(help=c.HELP["SR"]), "Avg": c.col_1(help=c.HELP["Avg"]),
                               "Dot %": c.col_pct(help=c.HELP["Dot %"]), "Boundary %": c.col_pct(help=c.HELP["Boundary %"])})
    c.section("Left-right partnerships", "Stands with one left- and one right-hand batter against stands where "
                                        "both bat the same way.")
    g, lr = c.hand_partnerships(lo, hi)
    if g.empty:
        c.empty("No partnerships in these seasons.")
    else:
        c.table(g[["pair", "stands", "runs", "per_stand", "rr", "fifty_pct"]]
                .rename(columns={"pair": "Batters", "stands": "Stands", "runs": "Runs", "per_stand": "Runs per stand",
                                 "rr": "Run rate", "fifty_pct": "50+ %"}),
                column_config={"Batters": c.col_text(), "Stands": c.col_int(), "Runs": c.col_int(help="Extras included"),
                               "Runs per stand": c.col_1(), "Run rate": c.col_2(help="Runs per 6 balls faced"),
                               "50+ %": c.col_pct(help="Share of stands worth 50 or more")})
        if len(lr):
            c.table(title="Left-right pairs with the most runs",
                    df=lr[["Pair", "inns", "runs", "rr", "best"]].rename(
                        columns={"inns": "Inns", "runs": "Runs", "rr": "Run rate", "best": "Best"}),
                    column_config={"Pair": c.col_text(width="large"), "Inns": c.col_int(help="Stands together"),
                                   "Runs": c.col_int(help="Partnership runs, extras included"),
                                   "Run rate": c.col_2(help="Runs per 6 balls faced"), "Best": c.col_int(help="Highest stand")})
    c.note("Batting hands and bowling types are Dugout's own categories. A stand is two batters at the crease together in an innings, whichever end; runs include extras.")

    # Phase B (2026-11-08): every bowling type against each batting hand in one heatmap.
    HM = {"sr": "Strike rate", "avg": "Average", "dot_pct": "Dot %", "bdry_pct": "Boundary %"}
    c.section("Bowling type v batting hand",
              f"Every Dugout bowling type against right- and left-hand batters. Blank under {c.MIN_BALLS} balls; "
              f"{c.SMALL_MARK} marks a small sample (under {c.SMALL_BALLS} balls).")
    hm_what = st.segmented_control("Show", list(HM), format_func=HM.get, key="mu_hm_show", default="sr") or "sr"
    ht = c.hand_v_bowling(b, "bowl_style")
    types = [x for x in c.STYLE_ORDER if x != c.UNKNOWN]
    if ht.empty:
        c.empty("No balls in these seasons.", " Choose a wider season range at the top of the page.")
    else:
        hands = ["Right", "Left"]
        cell = ht.set_index(["bowl_style", "bat_hand"])
        get = lambda s, h, col: cell.at[(s, h), col] if (s, h) in cell.index else (0 if col == "balls" else np.nan)
        nb = np.array([[get(s, h, "balls") for h in hands] for s in types], dtype=float)
        val = np.array([[get(s, h, hm_what) for h in hands] for s in types], dtype=float)
        z = np.where(nb >= c.MIN_BALLS, val, np.nan)
        text = [[c.sample_rate(val[i][j], nb[i][j]) for j in range(2)] for i in range(len(types))]
        hover = [[f"{s} v {h}-hand batters: {int(nb[i][j]):,} balls" + (
                  f", {HM[hm_what]} {val[i][j]:.1f}" if nb[i][j] >= c.MIN_BALLS and val[i][j] == val[i][j] else ", not enough balls")
                  for j, h in enumerate(hands)] for i, s in enumerate(types)]
        fig = c.go.Figure(c.go.Heatmap(z=z, x=[f"{h}-hand batters" for h in hands], y=types, text=text,
                                       texttemplate="%{text}", textfont=dict(color=c.INK, size=12), hovertext=hover,
                                       hoverinfo="text", colorscale=c.SEQ, showscale=False, xgap=2, ygap=2))
        lay = c.layout(fig, height=360)
        lay.update_yaxes(autorange="reversed", showgrid=False, zeroline=False, automargin=True, ticksuffix="  ")
        lay.update_xaxes(showgrid=False, automargin=True, side="top")
        c.show(lay, "mu_hand_heat")
        c.table(pd.DataFrame({"Bowling type": np.repeat(types, 2), "Batters": [f"{h}-hand" for _ in types for h in hands],
                              "Balls": nb.ravel().astype(int), HM[hm_what]: c.masked(val.ravel(), nb.ravel()),
                              "Sample": c.sample_label(nb.ravel())}),
                column_config={"Bowling type": c.col_text(), "Batters": c.col_text(width="small"),
                               "Balls": c.col_int(help="Balls faced"),
                               HM[hm_what]: c.col_1(help=c.HELP.get({"sr": "SR", "avg": "Avg", "dot_pct": "Dot %",
                                                                     "bdry_pct": "Boundary %"}[hm_what])),
                               "Sample": c.col_text(width="small")})

c.footer()
