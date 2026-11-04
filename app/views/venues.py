"""
venues.py - par score, chasing record, pace v spin economy and toss effect for each PSL
ground. READ-ONLY.
"""

import sys
from pathlib import Path

import numpy as np
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app/ folder, for common.py

import common as c  # noqa: E402

c.page("Venues", "How each ground plays: par score, chasing, pace against spin, and the toss.")
lo, hi = c.season_filter()

m = c.in_seasons(c.matches(), lo, hi)
with st.spinner("Loading ball-by-ball data"):
    b = c.in_seasons(c.balls(), lo, hi)
if m.empty:
    c.empty("No matches in these seasons.", " Choose a wider season range at the top of the page.")
    c.footer()
    st.stop()

inn = b.groupby(["match_id", "inning"]).agg(total=("total_runs", "sum"), team=("batting_team", "first")).reset_index()
first = inn[inn["inning"] == 1].set_index("match_id")
second = inn[inn["inning"] == 2].set_index("match_id")
m = m.set_index("match_id")
m["first_total"] = first["total"]
m["chaser"] = second["team"]
m["chase_won"] = np.where(m["winner"].fillna("") == "", np.nan, (m["winner"] == m["chaser"]).astype(float))
m["toss_won"] = np.where(m["winner"].fillna("") == "", np.nan, (m["winner"] == m["toss_winner"]).astype(float))
m["chose_field"] = (m["toss_decision"] == "field").astype(float)

kinds = b[b["bowl_kind"].isin(["Pace", "Spin"])]
econ = kinds.groupby(["venue_name", "bowl_kind"]).agg(r=("conceded", "sum"), lb=("legal", "sum")).reset_index()
econ["econ"] = c.div(econ["r"], econ["lb"], 6)
econ = econ.pivot(index="venue_name", columns="bowl_kind", values="econ")
spin_share = kinds.groupby("venue_name").apply(lambda x: x.loc[x["bowl_kind"] == "Spin", "legal"].sum() / x["legal"].sum(),
                                               include_groups=False)

g = m.reset_index().groupby("venue_name").agg(
    Matches=("match_id", "count"), Results=("chase_won", "count"), par=("first_total", "median"),
    avg_first=("first_total", "mean"), chase=("chase_won", "mean"), toss=("toss_won", "mean"),
    field=("chose_field", "mean"), seasons=("season", lambda s: f"{s.min()} to {s.max()}" if s.min() != s.max() else str(s.min())))
g["Pace econ"] = econ.get("Pace")
g["Spin econ"] = econ.get("Spin")
g["Spin share"] = spin_share * 100
g = g.sort_values("Matches", ascending=False).reset_index()
for col in ["chase", "toss", "field"]:
    g[col] = g[col] * 100

# ------------------------------------------------------------------ one ground
slugs = [c.slug(c.ground(v)) for v in g["venue_name"]]
c.link_default("ground_pick", "ground", slugs, slugs[0])
venue = g["venue_name"].iloc[slugs.index(st.selectbox("Ground", slugs, key="ground_pick",
                                                    format_func=lambda s: g["venue_name"].iloc[slugs.index(s)]))]
c.link_set(ground=c.slug(c.ground(venue)))
r = g[g["venue_name"] == venue].iloc[0]
st.markdown(f'<p class="dd-meta">{int(r["Matches"])} matches, {r["seasons"]}; {int(r["Results"])} with a winner.</p>',
            unsafe_allow_html=True)
c.cards([("Par score", c.fmt(r["par"]), "median first-innings total"),
         ("Average 1st innings", c.fmt(r["avg_first"]), "mean first-innings total"),
         ("Chasing side won", c.pct(r["chase"]), "of matches with a winner"),
         ("Toss winner won", c.pct(r["toss"]), "of matches with a winner"),
         ("Chose to field", c.pct(r["field"]), "of tosses"),
         ("Pace economy", c.fmt(r["Pace econ"], 2), "runs per over by pace bowlers"),
         ("Spin economy", c.fmt(r["Spin econ"], 2), "runs per over by spinners"),
         ("Spin share", c.pct(r["Spin share"]), "of legal balls bowled by spinners")], lead=True)

c.section("By season")
v = m[m["venue_name"] == venue].reset_index()
vs = v.groupby("season").agg(Matches=("match_id", "count"), Par=("first_total", "median"),
                             chase=("chase_won", "mean"), Results=("chase_won", "count")).reset_index()
vs["Chasing side won %"] = vs["chase"] * 100
c.table(vs[["season", "Matches", "Results", "Par", "Chasing side won %"]].rename(columns={"season": "Season"}),
        column_config={"Season": st.column_config.NumberColumn(format="%d", width="small"), "Matches": c.col_int(),
                       "Results": c.col_int(help="Matches with a winner"),
                       "Par": c.col_1(help="Median first-innings total"),
                       "Chasing side won %": c.col_pct(help="Share of matches with a winner won by the side batting second")})

# ------------------------------------------------------------------ all grounds
c.section("All grounds")
show = g.assign(Ground=g["venue_name"].map(c.ground), City=g["venue_name"].str.split(", ").str[-1]).rename(columns={
    "seasons": "Seasons", "par": "Par", "avg_first": "Average 1st inns", "chase": "Chasing side won %",
    "toss": "Toss winner won %", "field": "Chose to field %"})
c.table(show[["Ground", "City", "Seasons", "Matches", "Results", "Par", "Average 1st inns", "Chasing side won %",
              "Toss winner won %", "Chose to field %", "Pace econ", "Spin econ", "Spin share"]],
        column_config={"Ground": c.col_text(width="medium"), "City": c.col_text(width="small"),
                       "Seasons": c.col_text(width="small"), "Matches": c.col_int(),
                       "Results": c.col_int(help="Matches with a winner"),
                       "Par": c.col_1(help="Median first-innings total"), "Average 1st inns": c.col_1(),
                       "Chasing side won %": c.col_pct(), "Toss winner won %": c.col_pct(),
                       "Chose to field %": c.col_pct(), "Pace econ": c.col_2(help=c.HELP["Econ"]),
                       "Spin econ": c.col_2(help=c.HELP["Econ"]),
                       "Spin share": c.col_pct(help="Share of legal balls bowled by spinners")})
c.note("Win percentages leave out ties and no results. Par includes rain-shortened games. Pace and spin use "
       "public styles; bowlers with no public style are left out.")

c.section("Pace against spin", "Economy by ground: lower is better for the bowlers.")
c.grouped_bars(list(g["venue_name"].map(c.ground)), [("Pace", g["Pace econ"].values), ("Spin", g["Spin econ"].values)],
               "Economy (runs per over)", key="venue_econ")

c.footer()
