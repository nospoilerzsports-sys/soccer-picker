"""
Soccer Player Picker v2.1
- Suggest mode: auto-samples players from curated pools (icons, rising stars, active stars)
- Manual mode: analyze players you type in
- Scores via YouTube Data API and SerpAPI Google Trends
- Heavy weight on content gap + Trends for finding under-served, surging players
- Footer explains exactly what each score measures
"""

import random
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ============================================================
# CURATED PLAYER POOLS
# Edit these lists anytime to change suggestions.
# ============================================================

ICONIC_PLAYERS = [
    "Zinedine Zidane", "Ronaldinho", "Ronaldo Nazario", "Roberto Carlos",
    "Cafu", "Roberto Baggio", "Andrea Pirlo", "Paolo Maldini", "Franco Baresi",
    "Gianluigi Buffon", "Fabio Cannavaro", "Alessandro Del Piero",
    "Thierry Henry", "Dennis Bergkamp", "Patrick Vieira", "Eric Cantona",
    "Ryan Giggs", "Paul Scholes", "Frank Lampard", "Steven Gerrard",
    "John Terry", "Rio Ferdinand", "Ashley Cole",
    "Didier Drogba", "Samuel Eto'o", "Yaya Toure", "Michael Essien",
    "Jay-Jay Okocha", "George Weah", "Nwankwo Kanu",
    "Hristo Stoichkov", "Gheorghe Hagi",
    "Carlos Valderrama", "Rene Higuita", "Faustino Asprilla",
    "Gabriel Batistuta", "Hernan Crespo", "Juan Sebastian Veron", "Juan Roman Riquelme",
    "Rivaldo", "Romario", "Bebeto",
    "Hidetoshi Nakata", "Park Ji-sung",
    "Xavi Hernandez", "Andres Iniesta", "Carles Puyol", "Iker Casillas",
    "Wesley Sneijder", "Arjen Robben", "Robin van Persie",
    "Miroslav Klose", "Philipp Lahm", "Bastian Schweinsteiger",
    "Marta", "Mia Hamm", "Abby Wambach", "Homare Sawa",
]

RISING_STARS = [
    "Lamine Yamal", "Pau Cubarsi", "Arda Guler", "Kenan Yildiz",
    "Endrick", "Estevao Willian", "Vitor Roque",
    "Desire Doue", "Bradley Barcola", "Warren Zaire-Emery",
    "Joao Neves", "Antonio Silva", "Goncalo Inacio",
    "Wilson Odobert", "Mathys Tel",
    "Kobbie Mainoo", "Cole Palmer", "Adam Wharton",
    "Alejandro Garnacho", "Rasmus Hojlund",
    "Karim Adeyemi", "Florian Wirtz", "Jamal Musiala",
    "Eduardo Camavinga", "Aurelien Tchouameni",
    "Ansu Fati", "Pedri", "Gavi", "Nico Williams",
    "Trinity Rodman", "Sophia Smith", "Salma Paralluelo",
    "Linda Caicedo", "Lena Oberdorf", "Catarina Macario", "Naomi Girma",
]

ACTIVE_STARS = [
    "Erling Haaland", "Vinicius Junior", "Rodrygo", "Raphinha",
    "Bukayo Saka", "Martin Odegaard", "Declan Rice", "Phil Foden",
    "Jude Bellingham",
    "Lautaro Martinez", "Julian Alvarez", "Lucas Paqueta",
    "Christian Pulisic", "Weston McKennie", "Tyler Adams", "Tim Weah",
    "Alphonso Davies", "Jonathan David", "Stephen Eustaquio",
    "Hirving Lozano", "Edson Alvarez", "Santiago Gimenez", "Raul Jimenez",
    "Mohamed Salah", "Sadio Mane",
    "Victor Osimhen", "Khvicha Kvaratskhelia", "Rafael Leao",
    "Heung-min Son", "Takefusa Kubo",
    "Federico Valverde", "Darwin Nunez",
    "Antoine Griezmann", "Robert Lewandowski",
    "Aitana Bonmati", "Alexia Putellas", "Sam Kerr",
    "Mary Earps", "Lucy Bronze", "Lauren James", "Asisat Oshoala",
]

CATEGORY_MAP = {p: "Iconic retired" for p in ICONIC_PLAYERS}
CATEGORY_MAP.update({p: "Rising star" for p in RISING_STARS})
CATEGORY_MAP.update({p: "Active star" for p in ACTIVE_STARS})


def get_category(name: str) -> str:
    return CATEGORY_MAP.get(name, "Custom")


def suggest_players(num_icons: int, num_rising: int, num_active: int, exclude: set):
    icons = [p for p in ICONIC_PLAYERS if p not in exclude]
    rising = [p for p in RISING_STARS if p not in exclude]
    active = [p for p in ACTIVE_STARS if p not in exclude]

    selection = []
    selection += random.sample(icons, min(num_icons, len(icons)))
    selection += random.sample(rising, min(num_rising, len(rising)))
    selection += random.sample(active, min(num_active, len(active)))
    return selection


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Soccer Player Picker",
    page_icon="⚽",
    layout="wide",
)

WEIGHTS = {
    "contentGap": 0.35,
    "googleTrends": 0.30,
    "ytSearchDemand": 0.15,
    "storyRichness": 0.10,
    "skillTeachable": 0.10,
}

LABELS = {
    "contentGap": "Content gap",
    "googleTrends": "Google Trends",
    "ytSearchDemand": "YT demand",
    "storyRichness": "Story richness",
    "skillTeachable": "Teachable skill",
}


# ============================================================
# SCORING FUNCTIONS
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_content_gap(player_name: str, api_key: str):
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        query = f"animated {player_name} biography story"
        response = youtube.search().list(
            q=query, part="snippet", maxResults=25, type="video"
        ).execute()
        count = len(response.get("items", []))
        if count <= 0:
            score = 10
        elif count >= 9:
            score = 1
        else:
            score = 10 - count
        return score, count
    except HttpError as e:
        st.error(f"YouTube API error (content gap, {player_name}): {e}")
        return 5, -1
    except Exception as e:
        st.warning(f"Could not fetch content gap for {player_name}: {e}")
        return 5, -1


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_youtube_demand(player_name: str, api_key: str):
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        search = youtube.search().list(
            q=player_name, part="snippet", maxResults=10,
            type="video", order="relevance",
        ).execute()

        video_ids = []
        for item in search.get("items", []):
            id_obj = item.get("id", {})
            if isinstance(id_obj, dict) and id_obj.get("videoId"):
                video_ids.append(id_obj["videoId"])

        if not video_ids:
            return 1, 0

        stats = youtube.videos().list(
            id=",".join(video_ids), part="statistics"
        ).execute()
        total_views = sum(
            int(v.get("statistics", {}).get("viewCount", 0))
            for v in stats.get("items", [])
        )

        if total_views < 10_000: score = 1
        elif total_views < 100_000: score = 3
        elif total_views < 1_000_000: score = 5
        elif total_views < 10_000_000: score = 7
        elif total_views < 100_000_000: score = 9
        else: score = 10

        return score, total_views
    except HttpError as e:
        st.error(f"YouTube API error (demand, {player_name}): {e}")
        return 5, -1
    except Exception as e:
        st.warning(f"Could not fetch YT demand for {player_name}: {e}")
        return 5, -1


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_google_trends(player_name: str, serpapi_key: str):
    if not serpapi_key:
        return 5, 0.0

    try:
        url = "https://serpapi.com/search"
        params = {
            "engine": "google_trends",
            "q": player_name,
            "data_type": "TIMESERIES",
            "date": "today 3-m",
            "api_key": serpapi_key,
        }
        response = requests.get(url, params=params, timeout=25)
        response.raise_for_status()
        data = response.json()

        timeline = data.get("interest_over_time", {}).get("timeline_data", [])
        if not timeline:
            return 5, 0.0

        values = []
        for point in timeline:
            vals = point.get("values", [])
            if vals and isinstance(vals, list):
                v = vals[0].get("extracted_value")
                if v is not None:
                    values.append(v)

        if len(values) < 4:
            return 5, 0.0

        third = max(1, len(values) // 3)
        first = sum(values[:third]) / third
        last = sum(values[-third:]) / third
        if first <= 0:
            first = 1
        pct_change = (last - first) / first * 100

        if pct_change >= 100: score = 10
        elif pct_change >= 50: score = 9
        elif pct_change >= 25: score = 8
        elif pct_change >= 10: score = 7
        elif pct_change >= 0: score = 6
        elif pct_change >= -10: score = 5
        elif pct_change >= -25: score = 4
        elif pct_change >= -50: score = 3
        else: score = 1

        return score, pct_change
    except Exception as e:
        st.warning(
            f"Google Trends fetch failed for {player_name}: {type(e).__name__}. Defaulting to 5."
        )
        return 5, 0.0


# ============================================================
# WEIGHTED SCORING + REASONING
# ============================================================

def calc_weighted_score(scores: dict) -> float:
    return sum(scores.get(k, 0) * WEIGHTS[k] for k in WEIGHTS)


def generate_reason(name, scores, category=None, runner_up=None) -> str:
    items = [
        ("a major content gap", scores["contentGap"], scores["contentGap"] * WEIGHTS["contentGap"]),
        ("surging Google search trends", scores["googleTrends"], scores["googleTrends"] * WEIGHTS["googleTrends"]),
        ("strong YouTube search demand", scores["ytSearchDemand"], scores["ytSearchDemand"] * WEIGHTS["ytSearchDemand"]),
        ("a rich underdog backstory", scores["storyRichness"], scores["storyRichness"] * WEIGHTS["storyRichness"]),
        ("a very teachable signature skill", scores["skillTeachable"], scores["skillTeachable"] * WEIGHTS["skillTeachable"]),
    ]
    items.sort(key=lambda x: -x[2])

    cat_label = f" _({category})_" if category and category != "Custom" else ""
    reason = (
        f"**{name}**{cat_label} wins on {items[0][0]} ({items[0][1]}/10) "
        f"and {items[1][0]} ({items[1][1]}/10)."
    )

    if category == "Iconic retired" and scores["googleTrends"] >= 7:
        reason += " Retired icon with rising interest — likely World Cup or anniversary tailwind."
    elif category == "Rising star" and scores["contentGap"] >= 7:
        reason += " Rising star with an open lane — great shot at being first if FC Mobile or news boosts them."
    elif category == "Active star" and scores["contentGap"] >= 7 and scores["googleTrends"] >= 7:
        reason += " Active star that's still under-covered — uncommon and valuable combo."

    if scores["contentGap"] >= 8 and scores["googleTrends"] >= 8:
        reason += " Low competition plus hot timing — a rare combo."
    elif scores["contentGap"] >= 8:
        reason += " The open lane means easier ranking."
    elif scores["googleTrends"] >= 8:
        reason += " Ride the wave while interest is peaking."

    if runner_up:
        margin = calc_weighted_score(scores) - calc_weighted_score(runner_up["scores"])
        if margin > 0:
            reason += f" Edges {runner_up['name']} by {margin:.1f} points."

    return reason


# ============================================================
# UI
# ============================================================

st.title("⚽ Soccer Player Picker")
st.caption(
    "Auto-ranks soccer players for your YouTube channel. "
    "Heavy weight on content gap and Google Trends — surfaces under-served players with surging interest."
)

try:
    api_key = st.secrets["YOUTUBE_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("⚠️ YouTube API key missing. Add `YOUTUBE_API_KEY` under Settings → Secrets.")
    st.stop()

try:
    serpapi_key = st.secrets["SERPAPI_KEY"]
except (KeyError, FileNotFoundError):
    serpapi_key = None
    st.warning("⚠️ SerpAPI key not set. Google Trends will default to 5. Sign up free at serpapi.com.")

if "covered" not in st.session_state:
    st.session_state["covered"] = set()

with st.expander("How scoring works"):
    st.write(
        "Each player gets 5 sub-scores (1–10), multiplied by the weights below and added. "
        "Content gap and Google Trends carry the most weight."
    )
    cols = st.columns(5)
    for i, (k, w) in enumerate(WEIGHTS.items()):
        with cols[i]:
            st.metric(LABELS[k], f"{int(w * 100)}%")

st.divider()
mode = st.radio(
    "Mode",
    ["🎲 Suggest players for me", "📝 Analyze my list"],
    horizontal=True,
)

players_to_analyze = []

if mode == "🎲 Suggest players for me":
    st.subheader("How many of each type?")
    st.caption("Mix and match. Icons benefit from World Cup tailwind. Rising stars have less competition and ride FC Mobile / news spikes.")

    c1, c2, c3 = st.columns(3)
    with c1:
        num_icons = st.number_input("Iconic retired", 0, 10, 2)
    with c2:
        num_rising = st.number_input("Rising stars", 0, 10, 3)
    with c3:
        num_active = st.number_input("Active stars", 0, 10, 2)

    total = num_icons + num_rising + num_active
    if total == 0:
        st.warning("Pick at least 1 player from any category.")
    else:
        st.caption(f"Will analyze **{total}** players, excluding any you've marked as covered ({len(st.session_state['covered'])}).")

    show_pools = st.checkbox("Show full candidate pools")
    if show_pools:
        with st.expander("View candidate pools"):
            tab1, tab2, tab3 = st.tabs(["Iconic retired", "Rising stars", "Active stars"])
            with tab1:
                st.write(", ".join(ICONIC_PLAYERS))
            with tab2:
                st.write(", ".join(RISING_STARS))
            with tab3:
                st.write(", ".join(ACTIVE_STARS))

    analyze_clicked = st.button(
        f"🎲 Suggest and analyze {total} players" if total > 0 else "🎲 Suggest and analyze",
        type="primary",
        use_container_width=True,
        disabled=(total == 0),
    )

    if analyze_clicked:
        players_to_analyze = suggest_players(
            num_icons, num_rising, num_active,
            exclude=st.session_state["covered"],
        )

else:
    st.subheader("Players to analyze")
    default_players = "Lamine Yamal\nFlorian Wirtz\nTrinity Rodman\nJay-Jay Okocha\nVitor Roque"
    players_input = st.text_area("One name per line", value=default_players, height=140)

    analyze_clicked = st.button(
        "🔍 Analyze players", type="primary", use_container_width=True
    )
    if analyze_clicked:
        players_to_analyze = [p.strip() for p in players_input.split("\n") if p.strip()]


if analyze_clicked and players_to_analyze:
    if len(players_to_analyze) > 15:
        st.warning("Capped at 15 players per run.")
        players_to_analyze = players_to_analyze[:15]

    results = []
    progress = st.progress(0, text="Starting analysis...")

    for i, name in enumerate(players_to_analyze):
        progress.progress(i / len(players_to_analyze), text=f"Analyzing {name}...")

        cg_score, cg_count = fetch_content_gap(name, api_key)
        gt_score, gt_pct = fetch_google_trends(name, serpapi_key)
        yd_score, yd_views = fetch_youtube_demand(name, api_key)
        time.sleep(0.3)

        scores = {
            "contentGap": cg_score,
            "googleTrends": gt_score,
            "ytSearchDemand": yd_score,
            "storyRichness": 7,
            "skillTeachable": 7,
        }
        results.append({
            "name": name,
            "category": get_category(name),
            "scores": scores,
            "raw": {
                "gap_count": cg_count,
                "trend_pct": gt_pct,
                "demand_views": yd_views,
            },
        })

    progress.progress(1.0, text="Done!")
    time.sleep(0.4)
    progress.empty()

    st.session_state["results"] = results
    st.session_state["analyzed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

if "results" in st.session_state:
    results = st.session_state["results"]

    for i, r in enumerate(results):
        for slider_key, score_key in [(f"story_{i}", "storyRichness"), (f"skill_{i}", "skillTeachable")]:
            if slider_key in st.session_state:
                r["scores"][score_key] = st.session_state[slider_key]
        r["total"] = calc_weighted_score(r["scores"])

    ranked = sorted(results, key=lambda x: -x["total"])
    winner = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    st.divider()
    st.markdown("### 🏆 This week's pick")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"## {winner['name']}")
        st.caption(f"Category: {winner['category']}")
    with col2:
        st.metric("Total", f"{winner['total']:.1f} / 10")

    st.info(generate_reason(winner["name"], winner["scores"], winner["category"], runner_up))
    st.caption(f"Analyzed at {st.session_state.get('analyzed_at', 'unknown time')}")

    if st.button(f"✅ Mark {winner['name']} as covered (exclude from future suggestions)"):
        st.session_state["covered"].add(winner["name"])
        st.success(f"Added {winner['name']} to covered list.")

    st.divider()
    st.subheader("Fine-tune story & skill scores")
    st.caption("Auto-scored (APIs): content gap, Google Trends, YT demand. Editable: story and skill.")

    for i, r in enumerate(ranked):
        with st.expander(f"#{i + 1}  {r['name']}  ({r['category']})  —  {r['total']:.1f}/10"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Auto-scored**")
                gap_detail = (
                    f"_{r['raw']['gap_count']} existing animated videos_"
                    if r["raw"]["gap_count"] >= 0 else "_(fetch failed)_"
                )
                st.write(f"Content gap: **{r['scores']['contentGap']}/10**  {gap_detail}")
                st.write(
                    f"Google Trends: **{r['scores']['googleTrends']}/10**  "
                    f"_({r['raw']['trend_pct']:+.0f}% over 90d)_"
                )
                views_detail = (
                    f"_{r['raw']['demand_views']:,} total views_"
                    if r["raw"]["demand_views"] >= 0 else "_(fetch failed)_"
                )
                st.write(f"YT demand: **{r['scores']['ytSearchDemand']}/10**  {views_detail}")
            with col2:
                st.markdown("**Manual scores**")
                original_idx = results.index(r)
                st.slider("Story richness", 1, 10, r["scores"]["storyRichness"], key=f"story_{original_idx}")
                st.slider("Teachable skill", 1, 10, r["scores"]["skillTeachable"], key=f"skill_{original_idx}")

    if st.session_state["covered"]:
        st.divider()
        with st.expander(f"Covered players ({len(st.session_state['covered'])}) — excluded from suggestions"):
            st.write(", ".join(sorted(st.session_state["covered"])))
            if st.button("Clear covered list"):
                st.session_state["covered"] = set()
                st.rerun()

    st.divider()
    st.subheader("Full rankings")
    df = pd.DataFrame([
        {
            "Rank": i + 1,
            "Player": r["name"],
            "Category": r["category"],
            "Total": round(r["total"], 1),
            "Content gap": r["scores"]["contentGap"],
            "Google Trends": r["scores"]["googleTrends"],
            "YT demand": r["scores"]["ytSearchDemand"],
            "Story": r["scores"]["storyRichness"],
            "Skill": r["scores"]["skillTeachable"],
            "Existing bio videos": r["raw"]["gap_count"],
            "Trend %": round(r["raw"]["trend_pct"], 1),
            "Total YT views": r["raw"]["demand_views"],
        }
        for i, r in enumerate(ranked)
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False)
    st.download_button(
        "📥 Download as CSV",
        csv,
        f"player_rankings_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        "text/csv",
        use_container_width=True,
    )

# ============================================================
# FOOTER — What each score means
# ============================================================

st.divider()
st.markdown("### ℹ️ What each score actually measures")
st.markdown(
    """
**Content gap — 35% weight — auto-scored from YouTube**
Searches YouTube for `"animated [player name] biography story"` and counts how many results come back. Fewer existing videos means a bigger gap and a better chance for your video to rank.
*Scale: 0 results = 10/10. 5 results = 5/10. 9+ results = 1/10.*

**Google Trends — 30% weight — auto-scored from SerpAPI**
Pulls the player's Google search interest over the last 90 days. Compares the most recent third of the window to the earliest third. Rising interest means the player is gaining momentum — often from FC Mobile releases, transfers, tournaments, or news cycles.
*Scale: +100% rise = 10/10. Flat = 5/10. -50% drop = 3/10.*

**YT demand — 15% weight — auto-scored from YouTube**
Searches YouTube for the player's name (top 10 results), then sums the total view counts. More views means more people are actively searching for them — confirms there's an audience.
*Scale: 100M+ views = 9/10. 1M = 5/10. Under 10K = 1/10.*

**Story richness — 10% weight — manual slider**
Your judgment on how compelling the player's life story is — childhood, struggles, breakthrough moment, signature personality. A player with a rich underdog narrative scores higher than one with a straightforward path.

**Teachable skill — 10% weight — manual slider**
How clearly you can break down the player's signature move into an animated lesson. A clean step-over or trademark free-kick technique scores high; vague qualities like "great vision" score lower.

---

**Why these weights?** Content gap is the biggest factor because being first matters most — if 10 animated bios already exist, ranking your video is hard regardless of how good it is. Trends catches FC Mobile spikes, World Cup tailwinds, and news cycles that signal *now* is the right moment. Demand confirms people are actually searching at all. Story and skill combined (20%) are the content-quality factors only you can judge.

**Caching:** API results are cached for 1 hour. Re-running the same player within an hour won't hit the API again, saving your free-tier quota.
"""
)
