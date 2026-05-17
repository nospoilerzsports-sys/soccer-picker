"""
Soccer Player Picker
A weighted scoring tool that auto-ranks soccer players for YouTube content
based on YouTube content gap, Google Trends momentum, and YouTube search demand.

Manual overrides available for story richness and teachable skill.
"""

import math
import time
from datetime import datetime

import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pytrends.request import TrendReq

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
# SCORING FUNCTIONS (auto-fetch from APIs)
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_content_gap(player_name: str, api_key: str):
    """
    Count animated biography videos already on YouTube for this player.
    Fewer existing videos = bigger content gap = higher score.
    """
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        query = f"animated {player_name} biography story"
        response = youtube.search().list(
            q=query, part="snippet", maxResults=25, type="video"
        ).execute()
        count = len(response.get("items", []))

        # 0 results = 10, 9+ = 1
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
    """
    Total view counts of the top 10 results when searching for the player's name.
    More views = stronger search demand.
    """
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        search = youtube.search().list(
            q=player_name,
            part="snippet",
            maxResults=10,
            type="video",
            order="relevance",
        ).execute()

        video_ids = [item["id"]["videoId"] for item in search.get("items", [])]
        if not video_ids:
            return 1, 0

        stats = youtube.videos().list(
            id=",".join(video_ids), part="statistics"
        ).execute()
        total_views = sum(
            int(v.get("statistics", {}).get("viewCount", 0))
            for v in stats.get("items", [])
        )

        # Log-scale bucketing
        if total_views < 10_000:
            score = 1
        elif total_views < 100_000:
            score = 3
        elif total_views < 1_000_000:
            score = 5
        elif total_views < 10_000_000:
            score = 7
        elif total_views < 100_000_000:
            score = 9
        else:
            score = 10

        return score, total_views
    except HttpError as e:
        st.error(f"YouTube API error (demand, {player_name}): {e}")
        return 5, -1
    except Exception as e:
        st.warning(f"Could not fetch YT demand for {player_name}: {e}")
        return 5, -1


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_google_trends(player_name: str):
    """
    Compare last third vs first third of 90 days of Google search interest.
    Rising slope = higher score.
    """
    try:
        pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25), retries=2, backoff_factor=0.5)
        pytrends.build_payload(
            kw_list=[player_name],
            cat=0,
            timeframe="today 3-m",
            geo="",
            gprop="",
        )
        df = pytrends.interest_over_time()
        if df.empty or player_name not in df.columns:
            return 5, 0.0

        values = df[player_name].values
        if len(values) < 4:
            return 5, 0.0

        third = max(1, len(values) // 3)
        first = values[:third].mean()
        last = values[-third:].mean()

        if first <= 0:
            first = 1

        pct_change = (last - first) / first * 100

        # Bucketed score
        if pct_change >= 100:
            score = 10
        elif pct_change >= 50:
            score = 9
        elif pct_change >= 25:
            score = 8
        elif pct_change >= 10:
            score = 7
        elif pct_change >= 0:
            score = 6
        elif pct_change >= -10:
            score = 5
        elif pct_change >= -25:
            score = 4
        elif pct_change >= -50:
            score = 3
        else:
            score = 1

        return score, pct_change
    except Exception as e:
        st.warning(
            f"Google Trends unavailable for {player_name} (rate-limited or blocked). "
            f"Defaulting to score 5. Error: {type(e).__name__}"
        )
        return 5, 0.0


# ============================================================
# WEIGHTED SCORING + REASONING
# ============================================================

def calc_weighted_score(scores: dict) -> float:
    return sum(scores.get(k, 0) * WEIGHTS[k] for k in WEIGHTS)


def generate_reason(player_name: str, scores: dict, runner_up=None) -> str:
    items = [
        ("a major content gap", scores["contentGap"], scores["contentGap"] * WEIGHTS["contentGap"]),
        ("surging Google search trends", scores["googleTrends"], scores["googleTrends"] * WEIGHTS["googleTrends"]),
        ("strong YouTube search demand", scores["ytSearchDemand"], scores["ytSearchDemand"] * WEIGHTS["ytSearchDemand"]),
        ("a rich underdog backstory", scores["storyRichness"], scores["storyRichness"] * WEIGHTS["storyRichness"]),
        ("a very teachable signature skill", scores["skillTeachable"], scores["skillTeachable"] * WEIGHTS["skillTeachable"]),
    ]
    items.sort(key=lambda x: -x[2])

    reason = (
        f"**{player_name}** wins on {items[0][0]} ({items[0][1]}/10) "
        f"and {items[1][0]} ({items[1][1]}/10)."
    )

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
    "Auto-ranks soccer players for your YouTube content based on YouTube content gap, "
    "Google Trends momentum, and search demand. Story and skill scores are manual."
)

# --- API key check ---
try:
    api_key = st.secrets["YOUTUBE_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "⚠️ YouTube API key not configured. "
        "Add `YOUTUBE_API_KEY` under Settings → Secrets in Streamlit Cloud."
    )
    st.stop()

# --- Weight display ---
with st.expander("How scoring works"):
    st.write(
        "Each player gets 5 sub-scores (1–10). They're multiplied by these weights "
        "and added up. Content gap and Google Trends get the most weight — exactly "
        "the bias you want for finding under-served, trending players."
    )
    cols = st.columns(5)
    for i, (k, w) in enumerate(WEIGHTS.items()):
        with cols[i]:
            st.metric(LABELS[k], f"{int(w * 100)}%")

# --- Player input ---
st.subheader("Players to analyze")
default_players = (
    "Lamine Yamal\nAitana Bonmati\nTrinity Rodman\nFlorian Wirtz\nJude Bellingham"
)
players_input = st.text_area(
    "One name per line",
    value=default_players,
    height=140,
    help="Tip: include the player's most common Google search spelling.",
)

analyze = st.button("🔍 Analyze players", type="primary", use_container_width=True)

# --- Run analysis ---
if analyze:
    players = [p.strip() for p in players_input.split("\n") if p.strip()]

    if not players:
        st.warning("Add at least one player.")
        st.stop()

    if len(players) > 15:
        st.warning("Limit is 15 players per run (to stay within free API quota).")
        players = players[:15]

    results = []
    progress = st.progress(0, text="Starting analysis...")

    for i, name in enumerate(players):
        progress.progress(i / len(players), text=f"Analyzing {name}...")

        cg_score, cg_count = fetch_content_gap(name, api_key)
        gt_score, gt_pct = fetch_google_trends(name)
        yd_score, yd_views = fetch_youtube_demand(name, api_key)

        time.sleep(0.3)  # be polite to APIs

        scores = {
            "contentGap": cg_score,
            "googleTrends": gt_score,
            "ytSearchDemand": yd_score,
            "storyRichness": 7,  # default — user can override
            "skillTeachable": 7,
        }
        results.append({
            "name": name,
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

# --- Display results ---
if "results" in st.session_state:
    results = st.session_state["results"]

    # Apply any slider overrides from session state, then compute totals
    for i, r in enumerate(results):
        story_key = f"story_{i}"
        skill_key = f"skill_{i}"
        if story_key in st.session_state:
            r["scores"]["storyRichness"] = st.session_state[story_key]
        if skill_key in st.session_state:
            r["scores"]["skillTeachable"] = st.session_state[skill_key]
        r["total"] = calc_weighted_score(r["scores"])

    ranked = sorted(results, key=lambda x: -x["total"])
    winner = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    # Winner card
    st.divider()
    st.markdown("### 🏆 This week's pick")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"## {winner['name']}")
    with col2:
        st.metric("Total", f"{winner['total']:.1f} / 10")

    st.info(generate_reason(winner["name"], winner["scores"], runner_up))
    st.caption(f"Analyzed at {st.session_state.get('analyzed_at', 'unknown time')}")

    # Manual override sliders
    st.divider()
    st.subheader("Fine-tune story & skill scores")
    st.caption(
        "Auto-scored (from APIs): content gap, Google Trends, YT demand. "
        "Manually editable: story richness and teachable skill."
    )

    for i, r in enumerate(ranked):
        with st.expander(f"#{i + 1}  {r['name']}  —  {r['total']:.1f}/10"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Auto-scored (from APIs)**")
                gap_detail = (
                    f"_{r['raw']['gap_count']} existing animated videos_"
                    if r["raw"]["gap_count"] >= 0
                    else "_(fetch failed)_"
                )
                st.write(f"Content gap: **{r['scores']['contentGap']}/10**  {gap_detail}")
                st.write(
                    f"Google Trends: **{r['scores']['googleTrends']}/10**  "
                    f"_({r['raw']['trend_pct']:+.0f}% over 90d)_"
                )
                views_detail = (
                    f"_{r['raw']['demand_views']:,} total views_"
                    if r["raw"]["demand_views"] >= 0
                    else "_(fetch failed)_"
                )
                st.write(f"YT demand: **{r['scores']['ytSearchDemand']}/10**  {views_detail}")
            with col2:
                st.markdown("**Your manual scores**")
                # Find original index in results list (sorting changes order)
                original_idx = results.index(r)
                st.slider(
                    "Story richness",
                    1, 10,
                    r["scores"]["storyRichness"],
                    key=f"story_{original_idx}",
                )
                st.slider(
                    "Teachable skill",
                    1, 10,
                    r["scores"]["skillTeachable"],
                    key=f"skill_{original_idx}",
                )

    # Full table + export
    st.divider()
    st.subheader("Full rankings")
    df = pd.DataFrame([
        {
            "Rank": i + 1,
            "Player": r["name"],
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
