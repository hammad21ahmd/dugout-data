# Dugout Data

Pakistan Super League analytics from every ball since 2016: records and leaderboards, player
value (RAA, Wicket Value and Total against the average men's T20 player in the same match
situation, and win probability added), player pages with strengths and
weaknesses and match-by-match logs, matchups, team and venue pages.

Analysis by Hammad.

## Data and credits

- **Ball-by-ball data: [Cricsheet.org](https://cricsheet.org)**, shared under the Open Data
  Commons Attribution License (ODC-BY). Innings 1 and 2 only; super overs are left out.
- **Batting and bowling styles: Wikipedia, DBpedia and Wikidata** (CC BY-SA), or developer
  verified (checked by hand), with the source shown on each player page.
- **Insights page only: Data: ESPNcricinfo ball-by-ball.** Line, length and scoring-zone
  figures on that page are totals per player and season from ESPNcricinfo ball-by-ball records.
  They are not Dugout Data's own data and appear nowhere else in the app.

The data files are not part of this repository; the app loads them when it starts.

## Run it

```
pip install -r requirements.txt
streamlit run app/Home.py
```

Start Streamlit from the repository root so `.streamlit/config.toml` (the dark theme) is read.
