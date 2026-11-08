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
  name are kept apart. Where two records were one person, or an ID was wrong, they were corrected
  against ESPNcricinfo scorecards and profiles. Identity and style corrections are logged.
- **Names:** a player's own name only. When two different people share a name, the birth year is
  added, for example "Mohammad Irfan (b. 1982)".
- **Overseas** players are those whose country is not Pakistan. Ages are on match day.
- **Grounds:** different spellings of a ground are joined into one name.
""")

c.section("Data sources", "Every source used on Dugout Data. Pages do not repeat these credits; the "
                          f'"{c.METHOD_LINK}" link at the bottom of every page leads here.')
st.markdown(f"""
- **Cricsheet.org** (ODC-BY licence): every ball, match, team, player ID and result, for PSL and for the
  men's T20 baseline. All runs, wickets, RAA, Wicket Value, Total and WPA come from it.
- **ESPNcricinfo player profiles:** age, birth year, country, batting hand and bowling style, shown only as
  Dugout's own categories (below), never ESPNcricinfo's wording.
- **Wikipedia, Wikidata and DBpedia** (CC BY-SA): batting hand and bowling style where ESPNcricinfo has none or
  disagrees, and players' names. The Player page links the Wikipedia article a value came from.
- **Developer verified:** values checked by hand by the developer, labelled "Developer verified" on the Player page.
- **Manual:** values entered by hand from a named Wikipedia article.
- **Inferred:** where no source has a value, the style or hand the player used most in his own PSL balls.

**Source order.** Each field takes the first source that has a value: developer verified, manual,
ESPNcricinfo profile, DBpedia/Wikidata, inferred from his PSL balls, else Unknown. When sources disagree on
a style, the style he bowled most in PSL decides; if his balls cannot settle it, the current value stays;
if he bowled no PSL balls, the source order decides. Both cases get confidence low and are checked by hand.

**Confidence** of each value:
- *verified*: checked by the developer.
- *high*: entered by hand, or two sources agree.
- *medium*: one source only, or a disagreement settled by his PSL balls.
- *low*: a disagreement his PSL balls cannot settle (checked by hand).
- *inferred*: from his PSL balls only.

**Dugout categories.** Bowling style has three levels: the group (Pace or Spin), the family
(Pace; Finger Spin: off-spin and left-arm orthodox; Wrist Spin: leg-spin and left-arm wrist-spin) and the
type (Right-arm Pace, Left-arm Pace, Right-arm Off-spin, Left-arm Orthodox, Right-arm Leg-spin, Left-arm Wrist-spin). Batting
hand is Right or Left. Players with no known style or hand show as Unknown.

**Birth dates.** Pages show a player's age and birth year only. An exact date of birth is never shown or
offered for download.

**Corrections log.** Every identity, name, style and country correction (merged records, fixed IDs,
changed styles) is kept in Dugout Data's corrections log with its evidence and date.
""")
if c.SHOW_INSIGHTS:
    # The Insights page has no credit of its own (owner's decision 2026-11-09): its source is listed here in
    # full. The seasons are read from the data (common.ll_seasons_text), never typed in.
    ll_cover = c.ll_seasons_text(detail=True)
    st.markdown("**ESPNcricinfo ball-by-ball records** (Insights page only). The Insights line, length, zone and "
                "shot fields (and the control flag and each match's day or night label) come from ESPNcricinfo "
                "ball-by-ball records; Dugout Data only adds them up per player and season."
                + (f" They cover {ll_cover}." if ll_cover else "")
                + " Only balls whose runs and wickets agree with Cricsheet are counted.")

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
- Matchups depend on styles and hands; a bowler with no known style (or a batter with no known hand) is
  left out of those tables.
""")

if c.SHOW_INSIGHTS:
    c.section("Insights")
    st.markdown("Line and length numbers on the Insights page are added up from ESPNcricinfo "
                "ball-by-ball records, joined to Cricsheet ball by ball (only balls whose runs and "
                "wickets agree are used). That data is not Dugout Data's own; its source is listed under "
                "Data sources above.")
    c.section("Insights views", "What each tab means and the seasons it covers.")
    st.markdown(f"""
- **Seasons covered:** line, length, shot and control: {c.ll_seasons_text(detail=True) or "none in this version"}. Scoring zones and day or night labels exist for every season, but the
  Insights page uses the same seasons for every tab. Each view says which seasons it shows.
- **Pitch map:** for a bowler or a batter, every length (yorker to short) against every line (wide outside off
  to wide down leg). Bowlers: legal balls (no wides or no-balls), economy from runs conceded by the counting
  rules above, wicket %, dot % (legal balls with nothing conceded), boundary %. Batters: balls faced (no wides),
  strike rate, dismissal %, dot %, boundary %. Control % is the share of balls the data marks the batter as in
  control of. The view shows how many balls have a line and length (coverage %).
- **Bowler zones:** where batters score off a bowler: runs off the bat in eight sectors seen from behind the
  batter (left-handers mirrored), against the PSL share in the same zone.
- **Shots:** the shot played, as recorded in the data: balls, strike rate, dismissal % (dismissals per 100
  balls), boundary % and control %, against all PSL batters.
- **Where to bowl:** for a batter with at least 150 balls faced with a line and length: his tightest length,
  line and spot (lowest strike rate), the spot where he gets out most often (at least 2 dismissals), where he
  scores most and where he is caught most. Each pick needs at least {c.MIN_BALLS} balls.
- **Day and night:** each match's day, day/night or night label: matches, batting first win %, toss winner
  win %, toss winners choosing to field, average first and second innings, and each franchise's win %.
- **Small samples:** every number shows the balls (or matches) behind it. A rate is blank under {c.MIN_BALLS}
  balls ("not enough balls") and marked {c.SMALL_MARK} under {c.SMALL_BALLS} balls (small sample). Win % on
  Day and night is blank under {c.SMALL_MATCHES} matches with a winner.
""")

c.section("Toss and bowling type v batting hand")
st.markdown(f"""
- **Teams > Toss** (Cricsheet, every season): tosses won, how often the toss winner chose to field, and win %
  after winning or losing the toss and batting first or chasing. Win % counts only matches with a winner (a tie
  is settled by a super over, which is not in the data, so it has no winner here). Batting first follows the
  toss winner's choice. Rows under {c.SMALL_MATCHES} matches are marked as small samples.
- **Matchups > Left and right, bowling type v batting hand:** strike rate, average, dot % or boundary % of
  right- and left-hand batters against each Dugout bowling type, from Cricsheet balls and the player profiles.
  Blank under {c.MIN_BALLS} balls; {c.SMALL_MARK} under {c.SMALL_BALLS} balls.
- **Team average age and the PSL age curve** are on Teams > Squad: ages in whole years on match day, never a
  date of birth.
""")

c.section("Partnerships, discipline, fielding, entry and dismissals")
st.markdown(f"""
All from Cricsheet balls, innings 1 and 2 only. A wicket is any dismissal except retired hurt and retired not
out (run outs and retired out count).
- **Teams > Partnerships:** the stand for each wicket runs from the fall of one wicket to the next: team runs,
  extras included, and balls faced (wides not counted). The last stand of an innings is unbroken unless ten
  wickets fell. Average: runs per stand that ended. **Collapse:** {c.COLLAPSE_WKTS} wickets for {c.COLLAPSE_RUNS}
  runs or fewer, counted from the score at the wicket before (80/2 to 100/5 is 3 for 20). The collapse index is
  the share of innings batted with at least one collapse; collapses caused, the share of opponents' innings.
  Rates are blank under {c.MIN_INNS} innings or stands and marked small under {c.SMALL_INNS}.
- **Teams > Discipline:** extras given away when bowling: wides and no-balls (balls and runs), byes, leg byes
  and penalty runs. The no-ball run follows the counting rules: a no-ball with byes or leg byes is 1 run, the
  rest are byes or leg byes. Per match: per innings bowled in the chosen seasons.
- **Teams > Fielding:** catches (wicketkeepers included; caught and bowled to the bowler), run outs (every fielder
  named in a run out is credited) and stumpings, for one franchise and as PSL leaders. Fielders are named in
  the data by name and matched to the player by that match's squad, so merged records count once.
  Wicketkeeper and substitute catches are not told apart.
- **Player > Phases, When he comes in:** the score, wickets and overs when he first came to the crease (before
  his first ball at either end), and his runs, balls, strike rate and average by wickets down and by phase. His
  usual position is the band of batting positions he batted in most often (Opener 1 or 2, Number 3, Numbers 4
  and 5, 6 and 7, 8 to 11), or Mixed when no band has half his innings.
- **Player > Phases, How he gets out:** each type's share of his dismissals (at either end) against all PSL
  dismissals in the same seasons; at least {c.MIN_INNS} dismissals, small under {c.SMALL_INNS}.
""")

c.section("Credit")
st.markdown("Data: Cricsheet.org (ball by ball for PSL and for the men's T20 baseline). Player profiles: see "
            "Data sources above. Analysis by Hammad. "
            "No team logos or player photos are used.")
st.markdown(c.IDEA_CREDIT)

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
