"""
Soccer Player Picker v4
- Content gap now counts SUBSTANTIAL competitors (5+ min, 50k+ views) — actual rivals
  for an animated bio, not 30-second clips
- Combined YouTube call halves API quota cost
- Modern UI with custom CSS, polished winner card, category badges
- Suggest mode samples players from curated pools
- Manual mode accepts player names
"""

import random
import re
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ============================================================
# THRESHOLDS — what counts as a "real competitor"
# ============================================================

MIN_COMPETITOR_DURATION_SEC = 300    # 5 minutes
MIN_COMPETITOR_VIEWS = 50_000        # 50k views


# ============================================================
# PLAYER POOLS
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

CATEGORY_STYLES = {
    "Iconic retired": ("#FEF3C7", "#92400E"),
    "Rising star":    ("#D1FAE5", "#065F46"),
    "Active star":    ("#DBEAFE", "#1E40AF"),
    "Custom":         ("#F1F5F9", "#475569"),
}


def get_category(name):
    return CATEGORY_MAP.get(name, "Custom")


def category_badge_html(category):
    bg, fg = CATEGORY_STYLES.get(category, CATEGORY_STYLES["Custom"])
    return (
        f'<span style="display:inline-block;padding:4px 12px;border-radius:9999px;'
        f'font-size:12px;font-weight:600;background:{bg};color:{fg};">{category}</span>'
    )


def suggest_players(num_icons, num_rising, num_active, exclude):
    icons = [p for p in ICONIC_PLAYERS if p not in exclude]
    rising = [p for p in RISING_STARS if p not in exclude]
    active = [p for p in ACTIVE_STARS if p not in exclude]
    selection = []
    selection += random.sample(icons, min(num_icons, len(icons)))
    selection += random.sample(rising, min(num_rising, len(rising)))
    selection += random.sample(active, min(num_active, len(active)))
    return selection


def format_count(n):
    if n < 1000: return f"{n:,}"
    if n < 1_000_000: return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n / 1_000_000:.1f}M".replace(".0M", "M")


def parse_iso_duration(iso_str):
    """Convert YouTube's ISO 8601 duration (e.g. 'PT5M30S') to seconds."""
    if not iso_str or not iso_str.startswith('PT'):
        return 0
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_str)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mn * 60 + s


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Soccer Player Picker",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed",
)

WEIGHTS = {
    "contentGap": 0.35, "googleTrends": 0.30, "ytSearchDemand": 0.15,
    "storyRichness": 0.10, "skillTeachable": 0.10,
}

LABELS = {
    "contentGap": "Content gap", "googleTrends": "Google Trends",
    "ytSearchDemand": "YT demand", "storyRichness": "Story richness",
    "skillTeachable": "Teachable skill",
}


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  html, body, [class*="css"], [class*="st-"] {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
  }

  .block-container {
      padding-top: 2.5rem !important;
      padding-bottom: 5rem !important;
      max-width: 880px !important;
  }

  #MainMenu, footer, header[data-testid="stHeader"] { display: none !important; }

  h1 { font-weight: 700 !important; letter-spacing: -0.025em !important; font-size: 2.25rem !important; }
  h2 { font-weight: 600 !important; letter-spacing: -0.02em !important; }
  h3 { font-weight: 600 !important; letter-spacing: -0.015em !important; }

  .stButton > button {
      border-radius: 10px !important;
      font-weight: 600 !important;
      padding: 0.65rem 1.5rem !important;
      border: 1px solid #E2E8F0 !important;
      transition: all 0.15s ease !important;
      box-shadow: none !important;
  }
  .stButton > button:hover { border-color: #CBD5E1 !important; background: #F8FAFC !important; }
  .stButton > button[kind="primary"] {
      background: #10B981 !important; color: white !important;
      border: 1px solid #10B981 !important;
      padding: 0.8rem 1.5rem !important; font-size: 1rem !important;
  }
  .stButton > button[kind="primary"]:hover {
      background: #059669 !important; border-color: #059669 !important;
      transform: translateY(-1px);
      box-shadow: 0 6px 16px rgba(16, 185, 129, 0.3) !important;
  }

  div[data-testid="stExpander"] {
      background: white !important; border: 1px solid #E2E8F0 !important;
      border-radius: 12px !important; margin-bottom: 0.5rem !important;
      box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
  }
  div[data-testid="stExpander"] summary { font-weight: 500 !important; padding: 0.85rem 1.1rem !important; }
  div[data-testid="stExpander"] summary:hover { background: #F8FAFC !important; }

  div[data-testid="stMetric"] {
      background: #F8FAFC !important; padding: 0.85rem 1rem !important;
      border-radius: 10px !important; border: 1px solid #E2E8F0 !important;
  }
  div[data-testid="stMetricLabel"] {
      font-size: 0.7rem !important; text-transform: uppercase;
      letter-spacing: 0.05em; font-weight: 600 !important; color: #64748B !important;
  }
  div[data-testid="stMetricValue"] {
      font-size: 1.5rem !important; font-weight: 700 !important; color: #0F172A !important;
  }

  input, textarea { border-radius: 8px !important; border: 1px solid #E2E8F0 !important; }
  input:focus, textarea:focus {
      border-color: #10B981 !important;
      box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1) !important;
  }

  hr { border-color: #E2E8F0 !important; margin: 1.5rem 0 !important; }

  div[data-testid="stAlert"] { border-radius: 10px !important; border: 1px solid #E2E8F0 !important; }

  .winner-card {
      background: linear-gradient(135deg, #ECFDF5 0%, #F0FDF4 100%);
      border: 1px solid #A7F3D0; border-left: 4px solid #10B981;
      border-radius: 16px; padding: 1.75rem 2rem; margin: 1.5rem 0;
  }
  .winner-label {
      font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em;
      font-weight: 700; color: #059669; margin-bottom: 0.5rem;
  }
  .winner-name {
      font-size: 2.25rem; font-weight: 700; color: #064E3B;
      line-height: 1.1; margin: 0 0 0.5rem 0; letter-spacing: -0.02em;
  }
  .winner-score-row {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 1rem; flex-wrap: wrap; gap: 8px;
  }
  .winner-score { font-size: 1.5rem; font-weight: 700; color: #047857; }
  .winner-reason { font-size: 0.95rem; line-height: 1.6; color: #064E3B; margin-top: 0.75rem; }

  .hero-tagline { font-size: 1.05rem; color: #64748B; margin-top: -0.5rem; margin-bottom: 2rem; }
  .section-label {
      font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em;
      font-weight: 700; color: #64748B; margin-bottom: 0.4rem;
  }

  .video-item {
      font-size: 0.85rem; color: #334155;
      padding: 6px 0; border-bottom: 1px solid #F1F5F9;
      line-height: 1.4;
  }
  .video-meta { color: #94A3B8; font-size: 0.75rem; font-weight: 500; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# YOUTUBE — combined gap + demand in one search
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_youtube_signals(player_name, api_key):
    """
    Single YouTube search → derives both Content Gap and YT Demand.

    Content Gap = inverse of substantial-competitor count
        (videos that are 5+ minutes AND have 50k+ views)
    YT Demand = bucketed sum of view counts for top 10 most-viewed videos

    Returns dict with: gap_score, comp_count, top_competitors,
                       demand_score, total_views_top10
    """
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        query = f'"{player_name}"'  # quoted phrase for stricter matching
        search = youtube.search().list(
            q=query, part="snippet", maxResults=50,
            type="video", order="viewCount",
        ).execute()

        items = search.get("items", [])
        video_ids = []
        for item in items:
            id_obj = item.get("id", {})
            if isinstance(id_obj, dict) and id_obj.get("videoId"):
                video_ids.append(id_obj["videoId"])

        if not video_ids:
            return {
                "gap_score": 10, "comp_count": 0, "top_competitors": [],
                "demand_score": 1, "total_views_top10": 0,
            }

        stats_resp = youtube.videos().list(
            id=",".join(video_ids),
            part="statistics,contentDetails,snippet",
        ).execute()

        enriched = []
        for v in stats_resp.get("items", []):
            duration_sec = parse_iso_duration(
                v.get("contentDetails", {}).get("duration", "PT0S")
            )
            views = int(v.get("statistics", {}).get("viewCount", 0))
            title = v.get("snippet", {}).get("title", "")
            enriched.append({
                "title": title,
                "views": views,
                "duration_sec": duration_sec,
                "duration_min": duration_sec // 60,
            })

        enriched.sort(key=lambda x: -x["views"])

        # === Content gap from substantial competitors ===
        substantial = [
            v for v in enriched
            if v["duration_sec"] >= MIN_COMPETITOR_DURATION_SEC
            and v["views"] >= MIN_COMPETITOR_VIEWS
        ]
        comp_count = len(substantial)

        if comp_count == 0: gap_score = 10
        elif comp_count == 1: gap_score = 9
        elif comp_count == 2: gap_score = 8
        elif comp_count <= 4: gap_score = 7
        elif comp_count <= 7: gap_score = 6
        elif comp_count <= 10: gap_score = 5
        elif comp_count <= 15: gap_score = 4
        elif comp_count <= 25: gap_score = 3
        elif comp_count <= 40: gap_score = 2
        else: gap_score = 1

        # === Demand from top-10 view sum ===
        total_views_top10 = sum(v["views"] for v in enriched[:10])
        if total_views_top10 < 10_000: demand_score = 1
        elif total_views_top10 < 100_000: demand_score = 3
        elif total_views_top10 < 1_000_000: demand_score = 5
        elif total_views_top10 < 10_000_000: demand_score = 7
        elif total_views_top10 < 100_000_000: demand_score = 9
        else: demand_score = 10

        return {
            "gap_score": gap_score,
            "comp_count": comp_count,
            "top_competitors": substantial[:5],
            "demand_score": demand_score,
            "total_views_top10": total_views_top10,
        }
    except HttpError as e:
        st.error(f"YouTube API error for {player_name}: {e}")
        return {
            "gap_score": 5, "comp_count": -1, "top_competitors": [],
            "demand_score": 5, "total_views_top10": -1,
        }
    except Exception as e:
        st.warning(f"Could not fetch YouTube data for {player_name}: {e}")
        return {
            "gap_score": 5, "comp_count": -1, "top_competitors": [],
            "demand_score": 5, "total_views_top10": -1,
        }


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_google_trends(player_name, serpapi_key):
    if not serpapi_key:
        return 5, 0.0
    try:
        url = "https://serpapi.com/search"
        params = {
            "engine": "google_trends", "q": player_name,
            "data_type": "TIMESERIES", "date": "today 1-m",
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
        if first <= 0: first = 1
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
        st.warning(f"Google Trends fetch failed for {player_name}: {type(e).__name__}. Defaulting to 5.")
        return 5, 0.0


def calc_weighted_score(scores):
    return sum(scores.get(k, 0) * WEIGHTS[k] for k in WEIGHTS)


def generate_reason(name, scores, category=None, runner_up=None):
    items = [
        ("a major content gap", scores["contentGap"], scores["contentGap"] * WEIGHTS["contentGap"]),
        ("surging Google search trends", scores["googleTrends"], scores["googleTrends"] * WEIGHTS["googleTrends"]),
        ("strong YouTube search demand", scores["ytSearchDemand"], scores["ytSearchDemand"] * WEIGHTS["ytSearchDemand"]),
        ("a rich underdog backstory", scores["storyRichness"], scores["storyRichness"] * WEIGHTS["storyRichness"]),
        ("a very teachable signature skill", scores["skillTeachable"], scores["skillTeachable"] * WEIGHTS["skillTeachable"]),
    ]
    items.sort(key=lambda x: -x[2])
    reason = f"Wins on {items[0][0]} ({items[0][1]}/10) and {items[1][0]} ({items[1][1]}/10)."

    if category == "Iconic retired" and scores["googleTrends"] >= 7:
        reason += " Retired icon with rising interest — likely World Cup or anniversary tailwind."
    elif category == "Rising star" and scores["contentGap"] >= 7:
        reason += " Rising star with few real competitors — perfect window to be first."
    elif category == "Active star" and scores["contentGap"] >= 7 and scores["googleTrends"] >= 7:
        reason += " Active star that's still under-covered with proper bios — uncommon and valuable combo."

    if scores["contentGap"] >= 8 and scores["googleTrends"] >= 8:
        reason += " High demand, low real competition — a rare combo."
    elif scores["contentGap"] >= 8:
        reason += " The open lane means easier ranking against existing content."
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

st.markdown("# ⚽ Soccer Player Picker")
st.markdown(
    '<p class="hero-tagline">Find under-served, surging players for your animated YouTube channel.</p>',
    unsafe_allow_html=True
)

try:
    api_key = st.secrets["YOUTUBE_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("YouTube API key missing. Add `YOUTUBE_API_KEY` under Settings → Secrets.")
    st.stop()

try:
    serpapi_key = st.secrets["SERPAPI_KEY"]
except (KeyError, FileNotFoundError):
    serpapi_key = None
    st.warning("SerpAPI key not set. Google Trends will default to 5. Sign up free at serpapi.com.")

if "covered" not in st.session_state:
    st.session_state["covered"] = set()

st.markdown('<div class="section-label">Scoring weights</div>', unsafe_allow_html=True)
cols = st.columns(5)
for i, (k, w) in enumerate(WEIGHTS.items()):
    with cols[i]:
        st.metric(LABELS[k], f"{int(w * 100)}%")

with st.expander("How this finds gaps — quick version"):
    st.markdown(
        """
The picker targets a **demand-supply mismatch** — players people are actively searching for but who don't have enough quality content yet.

- **Content gap** counts only *substantial competitors* on YouTube — videos that are 5+ minutes long AND have 50k+ views. A 30-second highlight clip doesn't compete with an animated bio; a 10-minute documentary does. Fewer real competitors = bigger gap.
- **Google Trends** pulls the last 30 days of search interest and detects rising momentum — FC Mobile drops, transfers, tournament moments, breaking news.
- **YT demand** confirms there's actual viewing happening for the player.
- **Story** and **skill** are your judgment calls.

The combined 65% weight on gap + trends means the top picks will always be players with rising interest AND open lanes — exactly what YouTube Studio's Research tool surfaces, just outside the platform. Full methodology with brackets at the bottom of the page.
        """
    )

st.markdown("<br>", unsafe_allow_html=True)

mode = st.radio(
    "Mode",
    ["🎲 Suggest players for me", "📝 Analyze my list"],
    horizontal=True,
    label_visibility="collapsed",
)

players_to_analyze = []
analyze_clicked = False

if mode == "🎲 Suggest players for me":
    st.markdown('<div class="section-label" style="margin-top:1rem;">Player mix</div>', unsafe_allow_html=True)
    st.caption("Icons benefit from World Cup tailwind. Rising stars ride FC Mobile / news spikes with low competition.")

    c1, c2, c3 = st.columns(3)
    with c1: num_icons = st.number_input("Iconic retired", 0, 10, 2)
    with c2: num_rising = st.number_input("Rising stars", 0, 10, 3)
    with c3: num_active = st.number_input("Active stars", 0, 10, 2)

    total = num_icons + num_rising + num_active

    if st.checkbox("Show candidate pools"):
        tab1, tab2, tab3 = st.tabs(["Iconic retired", "Rising stars", "Active stars"])
        with tab1: st.write(", ".join(ICONIC_PLAYERS))
        with tab2: st.write(", ".join(RISING_STARS))
        with tab3: st.write(", ".join(ACTIVE_STARS))

    st.markdown("<br>", unsafe_allow_html=True)
    analyze_clicked = st.button(
        f"🎲 Analyze {total} players" if total > 0 else "🎲 Analyze",
        type="primary", use_container_width=True, disabled=(total == 0),
    )
    if analyze_clicked:
        players_to_analyze = suggest_players(
            num_icons, num_rising, num_active,
            exclude=st.session_state["covered"],
        )

else:
    st.markdown('<div class="section-label" style="margin-top:1rem;">Players to analyze</div>', unsafe_allow_html=True)
    default_players = "Lamine Yamal\nFlorian Wirtz\nTrinity Rodman\nJay-Jay Okocha\nVitor Roque"
    players_input = st.text_area("Names", value=default_players, height=140, label_visibility="collapsed")
    st.markdown("<br>", unsafe_allow_html=True)
    analyze_clicked = st.button("🔍 Analyze players", type="primary", use_container_width=True)
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
        yt = fetch_youtube_signals(name, api_key)
        gt_score, gt_pct = fetch_google_trends(name, serpapi_key)
        time.sleep(0.3)

        scores = {
            "contentGap": yt["gap_score"],
            "googleTrends": gt_score,
            "ytSearchDemand": yt["demand_score"],
            "storyRichness": 7, "skillTeachable": 7,
        }
        results.append({
            "name": name, "category": get_category(name),
            "scores": scores,
            "raw": {
                "comp_count": yt["comp_count"],
                "top_competitors": yt["top_competitors"],
                "trend_pct": gt_pct,
                "total_views_top10": yt["total_views_top10"],
            },
        })

    progress.progress(1.0, text="Done")
    time.sleep(0.3)
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

    badge = category_badge_html(winner["category"])
    reason_text = generate_reason(winner["name"], winner["scores"], winner["category"], runner_up)
    st.markdown(f"""
    <div class="winner-card">
        <div class="winner-label">🏆 This week's pick</div>
        <div class="winner-name">{winner['name']}</div>
        <div class="winner-score-row">
            <div>{badge}</div>
            <div class="winner-score">{winner['total']:.1f} <span style="font-size:0.85rem;font-weight:500;opacity:0.75;">/ 10</span></div>
        </div>
        <div class="winner-reason">{reason_text}</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns([2, 1])
    with c1:
        st.caption(f"Analyzed at {st.session_state.get('analyzed_at', 'unknown')}")
    with c2:
        if st.button("✓ Mark as covered", use_container_width=True):
            st.session_state["covered"].add(winner["name"])
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">All candidates</div>', unsafe_allow_html=True)

    for i, r in enumerate(ranked):
        badge = category_badge_html(r["category"])
        header_text = f"#{i + 1}  ·  {r['name']}  ·  {r['total']:.1f}/10"
        with st.expander(header_text):
            st.markdown(badge, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Auto-scored**")
                if r["raw"]["comp_count"] >= 0:
                    gap_detail = f"{r['raw']['comp_count']} substantial competitors"
                else:
                    gap_detail = "(fetch failed)"
                st.markdown(f"Content gap: **{r['scores']['contentGap']}/10**  \n_{gap_detail}_")
                st.markdown(
                    f"Google Trends: **{r['scores']['googleTrends']}/10**  \n"
                    f"_{r['raw']['trend_pct']:+.0f}% over 30d_"
                )
                if r["raw"]["total_views_top10"] >= 0:
                    views_detail = f"{format_count(r['raw']['total_views_top10'])} views across top 10"
                else:
                    views_detail = "(fetch failed)"
                st.markdown(f"YT demand: **{r['scores']['ytSearchDemand']}/10**  \n_{views_detail}_")
            with col2:
                st.markdown("**Your judgment**")
                original_idx = results.index(r)
                st.slider("Story richness", 1, 10, r["scores"]["storyRichness"], key=f"story_{original_idx}")
                st.slider("Teachable skill", 1, 10, r["scores"]["skillTeachable"], key=f"skill_{original_idx}")

            if r["raw"].get("top_competitors"):
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(f"**Real competitors found ({len(r['raw']['top_competitors'])} shown):**")
                for c in r["raw"]["top_competitors"]:
                    st.markdown(
                        f'<div class="video-item">{c["title"]}<br>'
                        f'<span class="video-meta">{c["duration_min"]} min · {format_count(c["views"])} views</span></div>',
                        unsafe_allow_html=True
                    )
            elif r["raw"]["comp_count"] == 0:
                st.success("✨ No substantial competitors found — wide-open lane.")

    if st.session_state["covered"]:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander(f"Covered players  ·  {len(st.session_state['covered'])} excluded from suggestions"):
            st.write(", ".join(sorted(st.session_state["covered"])))
            if st.button("Clear covered list"):
                st.session_state["covered"] = set()
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Full rankings</div>', unsafe_allow_html=True)
    df = pd.DataFrame([
        {
            "Rank": i + 1, "Player": r["name"], "Category": r["category"],
            "Total": round(r["total"], 1),
            "Content gap": r["scores"]["contentGap"],
            "Google Trends": r["scores"]["googleTrends"],
            "YT demand": r["scores"]["ytSearchDemand"],
            "Story": r["scores"]["storyRichness"],
            "Skill": r["scores"]["skillTeachable"],
            "Real competitors": r["raw"]["comp_count"],
            "Trend %": round(r["raw"]["trend_pct"], 1),
            "Top-10 YT views": r["raw"]["total_views_top10"],
        }
        for i, r in enumerate(ranked)
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False)
    st.download_button(
        "Download as CSV", csv,
        f"player_rankings_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        "text/csv", use_container_width=True,
    )

st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("---")
st.markdown('<div class="section-label">How the scoring works</div>', unsafe_allow_html=True)
st.markdown(
    """
**Content gap — 35% weight — auto-scored from YouTube**
Searches YouTube for the player's exact name (using a quoted phrase for stricter matching) and counts only **substantial competitors** — videos that are at least 5 minutes long AND have at least 50,000 views. A 30-second highlight clip doesn't compete with an animated bio for search ranking. A 10-minute documentary with 200k views does. Fewer real competitors means a real demand-supply gap your video can fill.
*Brackets: 0 competitors = 10/10, 1-2 = 8-9/10, 3-7 = 6-7/10, 8-15 = 4-5/10, 16+ = 1-3/10.*

**Google Trends — 30% weight — auto-scored from SerpAPI**
Pulls the player's Google search interest over the **last 30 days**. Compares the most recent third of that window to the earliest third to detect rising or falling momentum. The short window captures fresh signals — FC Mobile releases, recent transfers, tournament moments, breaking news — instead of slower long-term trends.
*Scale: +100% rise = 10/10. Flat = 5/10. -50% drop = 3/10.*

**YT demand — 15% weight — auto-scored from YouTube**
Sums the view counts of the top 10 most-viewed videos for this player's name. High total means heavy attention is flowing to content about them — confirms an audience exists.
*Scale: 100M+ combined views = 9/10. 1M = 5/10. Under 10K = 1/10.*

**Story richness — 10% weight — manual slider**
Your judgment on how compelling the player's life story is — childhood, struggles, breakthrough moment, signature personality.

**Teachable skill — 10% weight — manual slider**
How clearly you can break down the player's signature move into an animated lesson.

---

**The demand-supply gap, explained.** The reason this works for finding gaps: a player with surging Google Trends (people searching) AND few substantial YouTube competitors (no good videos answering them) is a textbook demand-supply mismatch — exactly what YouTube Studio's Research tab surfaces. The 65% combined weight on Content Gap + Trends targets that mismatch directly. A player with 500k total videos but only 3 substantial bios is more open than this metric would have suggested before.

**What gets shown in each candidate's card:** the actual competing videos (title, length, view count) so you can spot-check whether they're really competitors or just highlight reels sneaking past the filter. If the list looks wrong, the thresholds (5 min, 50k views) are easy to tune in the code.

**Caching:** API results cached for 1 hour. The cache clears on each app redeploy, so your first analysis after a code change always returns fresh numbers.
"""
)
