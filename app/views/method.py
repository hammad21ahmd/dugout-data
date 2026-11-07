"""
method.py - how every number is made, its limits, and the data credit. READ-ONLY.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app/ folder, for common.py

import common as c  # noqa: E402

c.page("Method", "How every number on Dugout Data is made, and what it cannot tell you.")
info = c.export_info()
missing = [m for m in info.get("wpa_matches_missing", "").split(",") if m]

c.section("Metrics", "The short version. Every card and column on the site uses these definitions.")
c.table(pd.DataFrame([("RAA", c.HELP["RAA"]), ("Wicket Value", c.HELP["Wicket Value"]), ("Total", c.HELP["Total"]),
                      ("WPA", c.HELP["WPA"]),
                      ("Strike rate", c.HELP["SR"].split(": ", 1)[1].capitalize()), ("Economy", c.HELP["Econ"].split(": ", 1)[1].capitalize()),
                      ("Average", c.HELP["Avg"].split(": ", 1)[1].capitalize()), ("Dot ball %", c.HELP["Dot %"].split(": ", 1)[1].capitalize()),
                      ("Boundary %", c.HELP["Boundary %"]), ("Balls per dismissal", c.HELP["Balls per dismissal"]),
                      ("Per 100 balls", c.HELP["per 100 balls"])], columns=["Metric", "Meaning"]),
        column_config={"Metric": c.col_text(width="small"), "Meaning": c.col_text(width="large")})

c.section("Data")
st.markdown(f"""
- **Ball by ball:** Cricsheet.org (open data, ODC-BY licence). Every men's Pakistan Super League
  match from 2016 to 2026: {info.get('matches', '357')} matches, {int(info.get('deliveries', 0)):,} balls.
  Data export {c.date_fmt(info.get('exported_at_utc', '')[:10])}.
- **Players** are matched by Cricsheet player ID, never by name, so two players with the same
  name are kept apart.
- **Batting and bowling styles** come from Wikipedia, DBpedia and Wikidata (CC BY-SA), each with
  its source page, or are developer verified (checked by hand by the developer, shown as
  "Developer verified" on the player page). They cover about 98% of balls faced and 98% of
  legal balls; players with no known source show as Unknown.
- **Grounds:** different spellings of a ground are joined into one name.
""")

c.section("Counting rules")
st.markdown("""
- Only innings 1 and 2 count. Super overs are left out.
- Phases: Powerplay overs 1 to 6, Middle overs 7 to 15, Death overs 16 to 20.
- A ball faced excludes wides. A legal ball for a bowler excludes wides and no-balls.
- Runs conceded include wides and no-ball extras, but not byes or leg-byes. On a no-ball with
  byes, only the no-ball run counts against the bowler.
- Bowler wickets: bowled, caught, lbw, stumped, caught and bowled, hit wicket.
- Batting average uses every dismissal (including run-outs at the non-striker's end). Matchup
  and phase tables count dismissals on strike.
- Overs are written over.ball: 10.4 is the 4th legal ball of the 11th over.
""")

c.section("RAA, Wicket Value and Total")
v_matches, v_balls = int(info.get("value_baseline_matches", 0)), int(info.get("value_baseline_balls", 0))
st.markdown(f"""
The standard is the average men's T20 player worldwide from 2016 to 2026: every men's T20 match in
Cricsheet in those seasons ({v_matches:,} matches, {v_balls:,} balls, international and league), innings 1
and 2. Every ball is put in its **match situation**: the over (1 to 20) and the wickets the batting side has
lost (0 to 9). That makes 200 situations, and for each one the baseline gives:

- the runs off the bat per ball faced, and the chance the striker is out (batting);
- the runs conceded per legal ball, and the chance of a bowler wicket (bowling);
- the runs the batting side still scores from that point to the end of the innings, on average.

**Batting**
- **RAA** = runs scored minus the runs an average batter scores from the same balls in the same situations.
- **Wicket Value** = (outs an average batter would lose from those balls minus actual outs) times the value of a
  wicket in each situation. A wicket's value is the drop in the runs still to come: the average for that over and
  wickets down, minus the average with one more wicket down. Early in an innings, with wickets in hand, a
  wicket costs a few runs; with the tail in, it can cost many more.

**Bowling**
- **RAA** = the runs an average bowler concedes from the same legal balls in the same situations, minus runs
  conceded. Fewer runs conceded gives a higher RAA.
- **Wicket Value** = (wickets taken minus the wickets an average bowler takes from those balls) times the value
  of a wicket in each situation.

**Total** = RAA + Wicket Value, both in runs. A player at the average rate in every situation has Total 0.
Across all {v_balls:,} baseline balls each part adds up to about 0.

Small samples: a situation with fewer than 200 balls (for example the first over with four wickets down) is
joined with the nearest wicket counts of the same over, then the nearest overs. The runs still to come in such a
situation come from a ball-by-ball chain built from the same data (runs and wicket chance per ball, six balls an
over, to the end of the innings). A wicket never adds expected runs: the runs still to come never rise with one
more wicket down.
""")

c.section("WPA: win probability added")
st.markdown(f"""
A win probability model, built from men's T20 matches, gives the batting side's chance of
winning before and after every ball. WPA adds up those changes for each batter and bowler.
+1.00 is one whole win added.
- WPA is not available for {len(missing)} of {info.get('matches', '357')} matches (including the 3
  no results), so season WPA totals cover slightly fewer balls than RAA.
""")

c.section("Player: strengths and weaknesses")
st.markdown(f"""
- Each situation (bowling type, phase and ground for batting; batting hand, phase and ground for bowling)
  is compared with the PSL average for the same situation in the chosen seasons.
- Batting: strike rate, balls per dismissal (outs on strike), dot balls and boundary balls, per ball faced.
  Bowling: economy (all runs conceded per legal ball), balls per wicket, dot balls and boundaries conceded.
- A situation needs at least {c.MIN_SPLIT_BALLS} balls (adjustable). Before ranking, {c.SHRINK_BALLS} balls at
  the PSL rate are added to the player's numbers, so a small sample is pulled towards the average; only
  differences of at least {c.MIN_EFFECT:.0%} after that are listed. The sentences show the actual numbers.
""")

c.section("Player: match by match")
st.markdown("""
- One row per match played. WPA for a match is the change in the team's chance of winning from that
  player's batting and bowling in that match; it adds up to the season WPA. It is blank for the 18
  matches without WPA.
- The ball-by-ball chart shows runs scored by ball faced (fours and sixes marked) and, for a bowler,
  runs conceded by legal ball (wickets marked), in the order the balls were bowled.
""")

c.section("Player: venues and teams")
st.markdown(f"""
- Batting and bowling at each ground (spellings of a ground joined) and against each opposing team, in the
  chosen seasons, with the same counting rules as above.
- A row needs at least {c.VT_MIN_BAT} balls faced (batting) or {c.VT_MIN_BOWL} legal balls (bowling); "Show all"
  lists every row. The note under each table gives the sample: rows and balls shown out of the total.
- Batting average counts every dismissal, like the career average. RAA, Wicket Value and Total are the same as
  elsewhere, added up over the balls at that ground or against that team, so the rows add up to the player's
  totals.
""")

c.section("Teams: venues")
st.markdown(f"""
- For the chosen franchise, each ground (spellings joined) in the chosen seasons: matches, won, lost, win % (won out
  of matches with a winner; ties have no winner in the data), average total batting first and batting second,
  highest and lowest total (runs including extras, innings 1 and 2 only, no-result matches left out). A ground
  needs at least {c.TV_MIN_MATCHES} matches; "Show all" lists every one.
""")

c.section("Limits")
st.markdown("""
- RAA, Wicket Value, Total and WPA say how much value a player added, not why. They do not adjust for the
  ground, the opposition or the batting position.
- The value of a wicket comes from first innings only: a chase stops once the target is reached, so second
  innings would understate the runs still to come.
- Super overs are left out. Innings shortened by rain are not separated, so they pull the runs still to come
  (and the value of a wicket) slightly down.
- The baseline is the same for every season. PSL scoring rose after 2023 (about 1.42 runs per ball faced from
  2023 to 2026 against 1.22 from 2016 to 2018), so batters of recent seasons get higher RAA and bowlers of
  recent seasons lower. To compare players fairly, compare them within one season with the season control at
  the top of every page.
- The baseline is every men's T20 match, so PSL players together are above or below zero (PSL batters
  score faster than the average men's T20 batter).
- Cricsheet has 23 of the 24 matches of PSL 2016 (one match is missing), so totals that include
  2016 (runs, wickets, catches and the records on Home) can be slightly below official PSL records.
- Cricsheet lists two PSL matches as not available: Peshawar Zalmi vs Karachi Kings (11 Feb 2016)
  and Multan Sultans vs Karachi Kings (2 Mar 2018). They are not included in this app.
- Small samples swing a lot: use the minimum-balls filters.
- Matchups depend on public styles; a bowler with no public style is left out of type tables.
""")

if c.SHOW_INSIGHTS:
    c.section("Insights")
    st.markdown("Line and length numbers on the Insights page are added up from ESPNcricinfo "
                "ball-by-ball records, joined to Cricsheet ball by ball (only balls whose runs and "
                "wickets agree are used). That data is not Dugout Data's own. "
                f"Credit: {c.INSIGHTS_CREDIT}.")

c.section("Credit")
st.markdown("Data: Cricsheet.org (ball by ball for PSL and for the men's T20 baseline). Styles: Wikipedia, DBpedia, "
            "Wikidata and developer verified. Analysis by Hammad. "
            "No team logos or player photos are used.")

with st.expander(f"Matches without WPA ({len(missing)})"):
    mm = c.matches().set_index("match_id")
    rows = [(c.date_fmt(mm.at[x, "date"]), c.match_title(mm.at[x, "team1"], mm.at[x, "team2"]),
             mm.at[x, "result"] if mm.at[x, "result"] != "normal" else "") for x in missing if x in mm.index]
    if rows:
        c.table(pd.DataFrame(rows, columns=["Date", "Match", "Note"]),
                column_config={"Date": c.col_text(width="small"), "Match": c.col_text(width="large"),
                               "Note": c.col_text(width="small")})
    else:
        st.write("None")

c.footer(copyright=True)
