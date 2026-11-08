"""
compare.py - two players side by side: career, value, phases and matchups by bowling type.
READ-ONLY. Numbers come from the same functions as the Player page (common.player_summary,
bat_stats, bowl_stats), so they always agree. Shareable: ?a=<player_id>&b=<player_id>.
"""

import html
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app/ folder, for common.py

import common as c  # noqa: E402

c.page("Compare", "Two players side by side: value, career, phases and how they fare against each type of bowling.")
lo, hi = c.season_filter()

options = c.player_options()
def_a = next((x for x in options if c.name(x) == "Babar Azam"), options[0])
def_b = next((x for x in options if c.name(x) == "Mohammad Rizwan"), options[1])
left, right = st.columns(2)
c.link_default("cmp_a", "a", options, def_a)
c.link_default("cmp_b", "b", options, def_b)
a = left.selectbox("Player A", options, key="cmp_a", format_func=c.name, placeholder="Type a name")
b = right.selectbox("Player B", options, key="cmp_b", format_func=c.name, placeholder="Type a name")
c.link_set(a=a, b=b)

SA, SB = c.player_summary(a, lo, hi), c.player_summary(b, lo, hi)
na, nb = c.name(a), c.name(b)
for col, pid, S in ((left, a, SA), (right, b, SB)):
    seas = S["seasons"]
    col.markdown(f'<p class="dd-lede"><b>{html.escape(c.name(pid))}</b></p>'
                 + (f'<p class="dd-meta">PSL {seas[0]}' + ("" if len(seas) == 1 else f"-{seas[-1]}") + "</p>"
                    if seas else '<p class="dd-meta">No PSL matches in these seasons.</p>')
                 + c.team_chips(S["teams"]), unsafe_allow_html=True)
if a == b:
    c.note("Both sides show the same player. Pick another player for A or B.")


def row(metric, key, text, higher=True):
    va, vb = SA[key], SB[key]
    return (metric, text(va), text(vb), va, vb, higher)


c.section("Value", c.VALUE_NOTE)
c.compare_table([row("Batting Total", "bat_total", c.raa_fmt), row("Batting RAA", "bat_raa", c.raa_fmt),
                 row("Batting Wicket Value", "bat_wv", c.raa_fmt),
                 row("Batting WPA", "bat_wpa", lambda v: c.fmt(v, 2, True)),
                 row("Bowling Total", "bowl_total", c.raa_fmt), row("Bowling RAA", "bowl_raa", c.raa_fmt),
                 row("Bowling Wicket Value", "bowl_wv", c.raa_fmt),
                 row("Bowling WPA", "bowl_wpa", lambda v: c.fmt(v, 2, True))],
                na, nb)

c.section("Career")
c.compare_table([row("Innings", "innings", c.num_fmt, None), row("Runs", "runs", c.num_fmt),
                 row("Balls faced", "balls", c.num_fmt, None), row("Average", "avg", c.fmt),
                 row("Strike rate", "sr", c.fmt), row("50s", "fifties", c.num_fmt),
                 row("Wickets", "wkts", c.num_fmt), row("Overs", "legal", c.overs, None),
                 row("Economy", "econ", lambda v: c.fmt(v, 2), False), row("Bowling average", "bowl_avg", c.fmt, False),
                 row("Dot ball % (bowling)", "bowl_dot", c.pct)], na, nb)
c.note("Highlighted: the better of the two where more (or, for economy and bowling average, less) is better.")

# ------------------------------------------------------------------ value by season
pt = c.in_seasons(c.player_teams(), lo, hi)
seasons = sorted(set(pt.loc[pt["player_id"].isin([a, b]), "season"]))
if seasons:
    def season_total(pid):
        tot = pd.concat([c.in_seasons(c.value(t), lo, hi) for t in ("value_bat", "value_bowl")])
        return tot[tot["player_id"] == pid].groupby("season")["total"].sum().reindex(seasons).fillna(0).values

    c.section("Value by season", "Total (batting plus bowling) per season.")
    c.grouped_bars([str(s) for s in seasons], [(na, season_total(a)), (nb, season_total(b))], "Total (runs)",
                   key="cmp_seasons", height=300)

# ------------------------------------------------------------------ phases
pn = c.phase_names()
ba = c.in_seasons(c.balls_for(a), lo, hi)
bb = c.in_seasons(c.balls_for(b), lo, hi)
bat_a, bat_b = ba[ba["batter_id"] == a], bb[bb["batter_id"] == b]
bowl_a, bowl_b = ba[ba["bowler_id"] == a], bb[bb["bowler_id"] == b]

c.section("Batting by phase", "Strike rate; balls faced in brackets.")
pa, pb = c.bat_stats(bat_a, "phase_no").set_index("phase_no"), c.bat_stats(bat_b, "phase_no").set_index("phase_no")
c.compare_table([(pn[n], f"{c.fmt(pa['sr'].get(n, np.nan))} ({int(pa['balls'].get(n, 0)):,})",
                  f"{c.fmt(pb['sr'].get(n, np.nan))} ({int(pb['balls'].get(n, 0)):,})",
                  pa["sr"].get(n, np.nan), pb["sr"].get(n, np.nan), True) for n in sorted(pn)], na, nb)
if len(bowl_a) or len(bowl_b):
    c.section("Bowling by phase", "Economy; overs in brackets.")
    wa, wb = c.bowl_stats(bowl_a, "phase_no").set_index("phase_no"), c.bowl_stats(bowl_b, "phase_no").set_index("phase_no")
    c.compare_table([(pn[n], f"{c.fmt(wa['econ'].get(n, np.nan), 2)} ({c.overs(wa['balls'].get(n, 0))})",
                      f"{c.fmt(wb['econ'].get(n, np.nan), 2)} ({c.overs(wb['balls'].get(n, 0))})",
                      wa["econ"].get(n, np.nan), wb["econ"].get(n, np.nan), False) for n in sorted(pn)], na, nb)

# ------------------------------------------------------------------ matchups by bowling type
c.section("Batting against each bowling type", "Strike rate; balls faced in brackets. Bowling types are Dugout's own categories.")
ta, tb = c.bat_stats(bat_a, "bowl_style").set_index("bowl_style"), c.bat_stats(bat_b, "bowl_style").set_index("bowl_style")
types = [s for s in c.STYLE_ORDER if s in ta.index or s in tb.index]
if types:
    c.compare_table([(s, f"{c.fmt(ta['sr'].get(s, np.nan))} ({int(ta['balls'].get(s, 0)):,})",
                      f"{c.fmt(tb['sr'].get(s, np.nan))} ({int(tb['balls'].get(s, 0)):,})",
                      ta["sr"].get(s, np.nan), tb["sr"].get(s, np.nan), True) for s in types], na, nb)
else:
    c.empty("Neither player batted in these seasons.")

c.footer()
