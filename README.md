# Dugout Data

Pakistan Super League analytics from every ball since 2016: records and leaderboards, player
value (RAA, Wicket Value and Total against the average men's T20 player in the same match
situation, and win probability added), player pages with strengths and
weaknesses and match-by-match logs, matchups, team and venue pages.

Analysis by Hammad.

## Data and credits

- **Ball-by-ball data: [Cricsheet.org](https://cricsheet.org)**, shared under the Open Data
  Commons Attribution License (ODC-BY). Innings 1 and 2 only; super overs are left out.
- **Player profiles (age, country, batting hand, bowling style): Source: ESPNcricinfo**, plus
  Wikipedia, DBpedia and Wikidata (CC BY-SA) and developer verified values, grouped into Dugout
  Data's own categories, with the source shown on each player page. Ages and birth years only.
- **Insights page only: ESPNcricinfo ball-by-ball records.** The Insights line, length, zone and
  shot fields come from ESPNcricinfo ball-by-ball records; Dugout Data only adds them up per player
  and season. The full text is on the app's Method tab.

The data files are not part of this repository; the app loads them when it starts.

## Run it

```
pip install -r requirements.txt
streamlit run app/Home.py
```

Start Streamlit from the repository root so `.streamlit/config.toml` (the dark theme) is read.
