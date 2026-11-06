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
c.table(pd.DataFrame([("RAA", c.HELP["RAA"]), ("WPA", c.HELP["WPA"]), ("Wins", c.HELP["Wins"]),
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

c.section("RAA: runs above average")
st.markdown("""
For each season and phase (Powerplay, Middle, Death), the average men's T20 player sets the
standard: runs per ball and outs per ball across all men's T20 matches in Cricsheet that season.

- **Batting RAA** = (runs scored minus the runs an average batter scores from the same balls)
  plus (outs an average batter would lose from those balls minus actual outs) times that season's
  runs per wicket. A batter who scores at the average rate and gets out at the average rate has
  RAA 0.
- **Bowling RAA** = (runs an average bowler concedes from the same legal balls minus runs
  conceded) plus (wickets minus the wickets an average bowler takes) times that season's runs
  per wicket.
- **Wins** = RAA divided by ten times that season's runs per wicket (about 240 to 270 runs per
  win).
- RAA bowling runs count every bye on a no-ball against the bowler, so in 7 seasons they are 2 to
  11 runs higher in total than the runs conceded shown elsewhere on this site.
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

c.section("Limits")
st.markdown("""
- RAA and WPA say how much value a player added, not why. They do not adjust for the ground,
  the opposition, or the batting position yet (planned for Phase 2).
- Batting RAA values each out avoided at a full season's runs per wicket (about 24 runs). In
  T20 a wicket usually costs less than that, so this version of RAA rewards batters who rarely
  get out more than fast scorers. Phase 2 replaces it with a run-expectancy model that prices a
  wicket by the runs it actually costs at that point of the innings.
- Cricsheet has 23 of the 24 matches of PSL 2016 (one match is missing), so totals that include
  2016 (runs, wickets, catches and the records on Home) can be slightly below official PSL records.
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
st.markdown("Data: Cricsheet.org. Styles: Wikipedia, DBpedia, Wikidata and developer verified. Analysis by Hammad. "
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
