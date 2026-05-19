"""
Soccer Player Picker v5
- A+B+C player pool management:
  * Manual add UI in sidebar
  * Wikipedia bulk pull (Ballon d'Or winners preset)
  * SerpAPI News + Claude name extraction for rising-star discovery
- Persistent Google Sheets storage (shared across team)
- All previous features: gap scoring with two factors, 30-day trends, modern UI
"""

import json
import random
import re
import time
import unicodedata
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Optional imports — features degrade gracefully if not installed
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Optional full FC Mobile player pool (800 names from EA's master list)
try:
    from fc_mobile_full_pool import FC_MOBILE_FULL_POOL
    FCM_FULL_AVAILABLE = True
except ImportError:
    FC_MOBILE_FULL_POOL = []
    FCM_FULL_AVAILABLE = False

# ============================================================
# THRESHOLDS
# ============================================================

MIN_COMPETITOR_DURATION_SEC = 180
MIN_COMPETITOR_VIEWS = 50_000


# ============================================================
# DEFAULT PLAYER POOLS (always available, augmented by Sheet)
# ============================================================

DEFAULT_ICONIC = [
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

DEFAULT_RISING = [
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

DEFAULT_ACTIVE = [
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

# FC Mobile featured players from past 2 years of major promos
# Sources: EA FC 25 Heroes (Aug 2024), TOTY 2025 (Jan 2025), LaLiga ICONs/Heroes (Mar 2025),
# UTOTS 25 (Jun 2025), Ballon d'Or 2025 promo (Oct 2025).
# Many TOTY/UTOTS players are already in DEFAULT_ACTIVE — bulk import dedupes automatically.
FC_MOBILE_FEATURED = [
    # FC 25 Heroes (Aug 2024) — these are the under-the-radar bio targets
    ("Eden Hazard", "Iconic retired"),
    ("Jamie Carragher", "Iconic retired"),
    ("Maicon", "Iconic retired"),
    ("Ze Roberto", "Iconic retired"),
    ("Blaise Matuidi", "Iconic retired"),
    ("Fara Williams", "Iconic retired"),
    ("Laura Georges", "Iconic retired"),
    ("Mohammed Noor", "Iconic retired"),
    ("Jaap Stam", "Iconic retired"),
    ("Guti", "Iconic retired"),
    # LaLiga ICONs and Heroes (Mar 2025)
    ("Fernando Hierro", "Iconic retired"),
    ("Xabi Alonso", "Iconic retired"),
    ("Fernando Morientes", "Iconic retired"),
    ("Diego Forlan", "Iconic retired"),
    ("Joan Capdevila", "Iconic retired"),
    ("Fernando Torres", "Iconic retired"),
    # Other prominent recently-retired greats heavily promoted in FC Mobile
    ("Toni Kroos", "Iconic retired"),
    ("Sergio Ramos", "Iconic retired"),
    ("Karim Benzema", "Iconic retired"),
    ("Sergio Busquets", "Iconic retired"),
    ("Jordi Alba", "Iconic retired"),
    ("Marco Reus", "Iconic retired"),
    ("Mesut Ozil", "Iconic retired"),
    # TOTY 2025 + UTOTS 25 active stars (those not already in default pools)
    ("Virgil van Dijk", "Active star"),
    ("Harry Kane", "Active star"),
    ("Ousmane Dembele", "Active star"),
    ("Alexander Isak", "Active star"),
    ("Kevin De Bruyne", "Active star"),
    ("Bruno Fernandes", "Active star"),
    ("Luka Modric", "Active star"),
    ("Bernardo Silva", "Active star"),
    ("Thibaut Courtois", "Active star"),
    ("Manuel Neuer", "Active star"),
    ("Joshua Kimmich", "Active star"),
    ("Antonio Rudiger", "Active star"),
    ("Achraf Hakimi", "Active star"),
    ("Marquinhos", "Active star"),
    # TOTY 2025 women's lineup additions
    ("Ann-Katrin Berger", "Active star"),
    ("Sakina Karchaoui", "Active star"),
    ("Mapi Leon", "Active star"),
    ("Caroline Graham Hansen", "Active star"),
]

# Players from the FC Mobile full pool that should be recategorized
# from "Active star" to "Rising star" (born ~2002 or later / recent breakout).
# Names use the exact Excel spelling so they match the Sheet rows.
RISING_RECLASSIFY = [
    "Ryan Gravenberch", "Joško Gvardiol", "Xavi Simons", "Omar Marmoush",
    "Anthony Gordon", "Lucas Chevalier", "Balde", "Murillo",
    "Piero Hincapié", "Hugo Ekitiké", "Morgan Rogers", "Malik Tillman",
    "Milos Kerkez", "Micky van de Ven", "Jurriën Timber", "Jonathan Burkardt",
    "Dean Huijsen", "Savinho", "Khéphren Thuram", "Carlos Baleba",
    "Johnny Cardoso", "Rayan Aït-Nouri", "Giuliano Simeone", "Anthony Elanga",
    "Rayan Cherki", "Quinten Timber", "Destiny Udogie", "Álvaro Carreras",
    "Curtis Jones", "Elliot Anderson", "Andrey Santos", "Georgiy Sudakov",
    "Tino Livramento", "Benjamin Šeško", "Fermín", "Jérémy Doku",
    "Levi Colwill", "Maghnes Akliouche", "Castello Lukeba", "Ousmane Diomande",
    "Kouadio Manu Koné", "Ian Maatsen", "Pape Matar Sarr", "Ismael Saibari",
    "Alan Varela", "Aleksandar Pavlović", "Malo Gusto", "Arnau Martínez",
    "Thiago Almada", "Lee Kang In", "Nico Paz", "Maximilian Beier",
    "Jhon Durán", "Fábio Silva", "Nick Woltemade", "Illia Zabarnyi",
    "Marcos Leonardo", "Jarrad Branthwaite", "Kenneth Taylor", "Luka Sučić",
    "Hugo Larsson", "Jacob Ramsey", "Luis Henrique", "Myles Lewis-Skelly",
    "Riccardo Calafiori",
]

CATEGORIES = ["Iconic retired", "Rising star", "Active star"]

CATEGORY_STYLES = {
    "Iconic retired": ("#FEF3C7", "#92400E"),
    "Rising star":    ("#D1FAE5", "#065F46"),
    "Active star":    ("#DBEAFE", "#1E40AF"),
    "Custom":         ("#F1F5F9", "#475569"),
}


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Soccer Player Picker",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="expanded",
)

WEIGHTS = {
    "contentGap": 0.20, "googleTrends": 0.40, "ytSearchDemand": 0.20,
    "contentFreshness": 0.20,
}
LABELS = {
    "contentGap": "Content gap", "googleTrends": "Google Trends",
    "ytSearchDemand": "YT demand", "contentFreshness": "Freshness",
}


# ============================================================
# CSS
# ============================================================

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  html, body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
  .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
  .stApp label, .stApp button, .stApp input, .stApp textarea, .stApp select,
  [data-testid="stMarkdownContainer"], [data-testid="stHeading"],
  [data-testid="stCaptionContainer"], [data-testid="stExpander"] summary,
  .stRadio label, .stCheckbox label {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
  }
  [class*="material-symbols"], [class*="material-icons"], .material-icons,
  [data-testid="stExpander"] summary svg,
  [data-testid="stExpander"] summary [class*="icon"] {
      font-family: 'Material Symbols Rounded', 'Material Icons' !important;
  }

  .block-container { padding-top: 2.5rem !important; padding-bottom: 5rem !important; max-width: 880px !important; }
  #MainMenu, footer, header[data-testid="stHeader"] { display: none !important; }

  h1 { font-weight: 700 !important; letter-spacing: -0.025em !important; font-size: 2.25rem !important; }
  h2 { font-weight: 600 !important; letter-spacing: -0.02em !important; }
  h3 { font-weight: 600 !important; letter-spacing: -0.015em !important; }

  .stButton > button {
      border-radius: 10px !important; font-weight: 600 !important;
      padding: 0.65rem 1.5rem !important; border: 1px solid #E2E8F0 !important;
      transition: all 0.15s ease !important; box-shadow: none !important;
  }
  .stButton > button:hover { border-color: #CBD5E1 !important; background: #F8FAFC !important; }
  .stButton > button[kind="primary"] {
      background: #10B981 !important; color: white !important;
      border: 1px solid #10B981 !important;
      padding: 0.8rem 1.5rem !important; font-size: 1rem !important;
  }
  .stButton > button[kind="primary"]:hover {
      background: #059669 !important; border-color: #059669 !important;
      transform: translateY(-1px); box-shadow: 0 6px 16px rgba(16, 185, 129, 0.3) !important;
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
  div[data-testid="stMetricValue"] { font-size: 1.5rem !important; font-weight: 700 !important; color: #0F172A !important; }

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

  .video-item { font-size: 0.85rem; color: #334155; padding: 6px 0; border-bottom: 1px solid #F1F5F9; line-height: 1.4; }
  .video-meta { color: #94A3B8; font-size: 0.75rem; font-weight: 500; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# HELPERS
# ============================================================

def format_count(n):
    if n < 1000: return f"{n:,}"
    if n < 1_000_000: return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n / 1_000_000:.1f}M".replace(".0M", "M")


def parse_iso_duration(iso_str):
    if not iso_str or not iso_str.startswith('PT'):
        return 0
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_str)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mn * 60 + s


def category_badge_html(category):
    bg, fg = CATEGORY_STYLES.get(category, CATEGORY_STYLES["Custom"])
    return (
        f'<span style="display:inline-block;padding:4px 12px;border-radius:9999px;'
        f'font-size:12px;font-weight:600;background:{bg};color:{fg};">{category}</span>'
    )


# ============================================================
# GOOGLE SHEETS PERSISTENCE
# ============================================================

def get_sheet():
    """Connect to the Google Sheet (cached)."""
    if not GSPREAD_AVAILABLE:
        return None
    if "GCP_SERVICE_ACCOUNT" not in st.secrets or "SHEET_NAME" not in st.secrets:
        return None
    try:
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"]) if isinstance(st.secrets["GCP_SERVICE_ACCOUNT"], str) else dict(st.secrets["GCP_SERVICE_ACCOUNT"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open(st.secrets["SHEET_NAME"]).sheet1

        # Ensure headers exist
        try:
            headers = sheet.row_values(1)
            if not headers:
                sheet.update("A1:D1", [["name", "category", "source", "added_at"]])
        except Exception:
            sheet.update("A1:D1", [["name", "category", "source", "added_at"]])

        return sheet
    except Exception as e:
        st.sidebar.error(f"Sheet connection failed: {type(e).__name__}")
        return None


@st.cache_data(ttl=300, show_spinner=False)
def load_sheet_players():
    """Load all players from the Sheet. Returns list of dicts."""
    sheet = get_sheet()
    if sheet is None:
        return []
    try:
        records = sheet.get_all_records()
        return [r for r in records if r.get("name")]
    except Exception:
        return []


def normalize_name(s):
    """Strip accents and lowercase for forgiving name comparison."""
    if not s:
        return ""
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii').lower().strip()


def add_players_to_sheet(new_players, source):
    """Add multiple players. new_players is list of (name, category) tuples."""
    sheet = get_sheet()
    if sheet is None:
        return 0, "Sheets not configured."
    try:
        existing = {normalize_name(r["name"]) for r in sheet.get_all_records() if r.get("name")}
        default_all = {normalize_name(p) for p in (DEFAULT_ICONIC + DEFAULT_RISING + DEFAULT_ACTIVE)}

        rows_to_add = []
        added_count = 0
        for name, category in new_players:
            name_clean = name.strip()
            if not name_clean:
                continue
            norm = normalize_name(name_clean)
            if norm in existing or norm in default_all:
                continue
            rows_to_add.append([
                name_clean, category, source,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ])
            existing.add(norm)
            added_count += 1

        if rows_to_add:
            sheet.append_rows(rows_to_add)
        load_sheet_players.clear()  # invalidate cache
        return added_count, None
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def reclassify_in_sheet(target_names, new_category):
    """
    Update category for matching names in the Sheet (batch update for efficiency).
    Matches by accent-normalized name.
    Returns (updated_count, not_found_list, error).
    """
    sheet = get_sheet()
    if sheet is None:
        return 0, [], "Sheets not configured."
    try:
        records = sheet.get_all_records()
        # Build map from normalized name → row number (header is row 1, so data starts at row 2)
        name_to_row = {}
        for i, r in enumerate(records, start=2):
            if r.get("name"):
                name_to_row[normalize_name(r["name"])] = i

        updates = []
        not_found = []
        for name in target_names:
            row_num = name_to_row.get(normalize_name(name))
            if row_num is None:
                not_found.append(name)
                continue
            updates.append({
                "range": f"B{row_num}",  # column B = category
                "values": [[new_category]],
            })

        if updates:
            sheet.batch_update(updates)
        load_sheet_players.clear()
        return len(updates), not_found, None
    except Exception as e:
        return 0, [], f"{type(e).__name__}: {e}"


def remove_player_from_sheet(player_name):
    sheet = get_sheet()
    if sheet is None:
        return False
    try:
        records = sheet.get_all_records()
        for i, r in enumerate(records, start=2):
            if r.get("name") == player_name:
                sheet.delete_rows(i)
                load_sheet_players.clear()
                return True
        return False
    except Exception:
        return False


def get_combined_pools():
    """
    Combine default pools + Sheet additions.
    Returns dict mapping category -> list of player names.
    Accent-aware dedup: 'Pau Cubarsí' won't be added if 'Pau Cubarsi' is already present.
    """
    pools = {
        "Iconic retired": list(DEFAULT_ICONIC),
        "Rising star": list(DEFAULT_RISING),
        "Active star": list(DEFAULT_ACTIVE),
    }
    seen_normalized = {
        normalize_name(n) for cat_list in pools.values() for n in cat_list
    }
    for p in load_sheet_players():
        cat = p.get("category")
        name = p.get("name", "").strip()
        if not (cat in pools and name):
            continue
        norm = normalize_name(name)
        if norm in seen_normalized:
            continue
        pools[cat].append(name)
        seen_normalized.add(norm)
    return pools


def clean_player_input(raw):
    """
    Clean user-typed player names by stripping common annotations.
    Examples:
      'Marta — Brazil'       → 'Marta'
      'Marta - Brazil'       → 'Marta'
      'Désiré Doué (France)' → 'Désiré Doué'
      'Lamine Yamal, 17'     → 'Lamine Yamal'
      '* Vinicius Junior'    → 'Vinicius Junior'
    """
    if not raw:
        return ""
    s = raw.strip()
    # Strip leading bullets/dashes/asterisks
    s = re.sub(r'^[\s\-\*\u2022\u2023\u25E6\u2043\u2219]+', '', s)
    # Strip trailing annotations starting with em dash, en dash, hyphen-with-spaces, or open paren
    s = re.split(r'\s+[\u2014\u2013]\s+|\s+-\s+|\s*\(', s)[0]
    # Strip trailing commas + anything after (e.g. ', 17 years old')
    s = s.split(',')[0]
    return s.strip()


def get_category_for(name, pools):
    """Accent-tolerant category lookup."""
    target = normalize_name(name)
    for cat, names in pools.items():
        if any(normalize_name(n) == target for n in names):
            return cat
    return "Custom"


# ============================================================
# WIKIPEDIA BULK PULL (Option C)
# ============================================================

WIKI_PRESETS = {
    "Ballon d'Or winners (iconic)": {
        "category": "Ballon d'Or winners",
        "assigned_pool": "Iconic retired",
    },
    "FIFA World Cup-winning captains (iconic)": {
        "category": "FIFA World Cup-winning captains",
        "assigned_pool": "Iconic retired",
    },
    "21st-century women's footballers (active)": {
        "category": "21st-century women association football players",
        "assigned_pool": "Active star",
    },
}


def fetch_wikipedia_category(category_title, limit=200):
    """
    Fetch member articles of a Wikipedia category.
    Returns list of clean player names (no namespace prefixes, no parentheses).
    """
    try:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category_title}",
            "cmlimit": str(limit),
            "cmtype": "page",
            "format": "json",
        }
        response = requests.get(url, params=params, timeout=15,
                                headers={"User-Agent": "SoccerPicker/1.0"})
        response.raise_for_status()
        data = response.json()
        members = data.get("query", {}).get("categorymembers", [])

        names = []
        for m in members:
            title = m.get("title", "")
            # Strip disambiguation suffixes like "(footballer)" or "(footballer, born 1985)"
            clean = re.sub(r'\s*\([^)]*\)\s*', '', title).strip()
            if clean and not clean.startswith(("Category:", "List ", "Template:")):
                names.append(clean)
        return names
    except Exception as e:
        return []


# ============================================================
# NEWS-DRIVEN DISCOVERY (Option B)
# ============================================================

def fetch_soccer_news(serpapi_key, query="soccer transfer breakout player 2026"):
    """Search Google News via SerpAPI for soccer headlines."""
    try:
        url = "https://serpapi.com/search"
        params = {
            "engine": "google_news", "q": query,
            "api_key": serpapi_key,
        }
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        articles = data.get("news_results", []) or []

        headlines = []
        for a in articles[:20]:
            title = a.get("title", "")
            snippet = a.get("snippet", "")
            if title:
                headlines.append(f"{title} — {snippet}".strip(" —"))
        return headlines
    except Exception as e:
        return []


def fetch_totw_articles(serpapi_key, time_window="this week"):
    """
    Search Google for recent TOTW (Team of the Week) articles via SerpAPI.
    Tuned to surface FUTBIN/Sportskeeda/Beebom TOTW recap articles.
    Returns list of title+snippet strings for Claude to extract names from.
    """
    try:
        url = "https://serpapi.com/search"
        query = (
            f"EA FC 26 TOTW Team of the Week {time_window} players list "
            f"site:futbin.com OR site:sportskeeda.com OR site:beebom.com OR site:goal.com"
        )
        params = {
            "engine": "google", "q": query,
            "num": "15", "api_key": serpapi_key,
        }
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        results = data.get("organic_results", []) or []

        snippets = []
        for r in results[:15]:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            if title:
                snippets.append(f"{title} — {snippet}".strip(" —"))
        return snippets
    except Exception:
        return []


def extract_players_from_headlines(headlines, anthropic_api_key):
    """Use Claude to extract soccer player names from news headlines."""
    if not ANTHROPIC_AVAILABLE or not anthropic_api_key or not headlines:
        return []

    try:
        client = Anthropic(api_key=anthropic_api_key)
        headlines_text = "\n".join(f"- {h}" for h in headlines)

        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "Extract soccer/football PLAYER names mentioned in these news "
                    "headlines. Only player names — not coaches, executives, journalists, "
                    "or team names. Return ONLY a JSON array of unique player names, "
                    "no commentary, no markdown.\n\n"
                    f"Headlines:\n{headlines_text}\n\n"
                    'Format: ["Player Name 1", "Player Name 2", ...]'
                ),
            }],
        )

        text = message.content[0].text.strip()
        # Strip markdown code fences if present
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.MULTILINE).strip()
        names = json.loads(text)
        return [n for n in names if isinstance(n, str) and n.strip()]
    except Exception as e:
        st.sidebar.warning(f"Name extraction failed: {type(e).__name__}")
        return []


# ============================================================
# YOUTUBE + TRENDS (analysis pipeline — unchanged from v4)
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_youtube_signals(player_name, api_key):
    empty_result = {
        "gap_score": 10, "comp_count": 0, "comp_total_views": 0,
        "top_competitors": [], "demand_score": 1, "total_views_top10": 0,
        "avg_engagement_pct": 0.0,
        "freshness_score": 10, "most_recent_months": None,
    }
    error_result = {
        "gap_score": 5, "comp_count": -1, "comp_total_views": -1,
        "top_competitors": [], "demand_score": 5, "total_views_top10": -1,
        "avg_engagement_pct": 0.0,
        "freshness_score": 5, "most_recent_months": None,
    }
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        query = f'"{player_name}"'
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
            return empty_result

        stats_resp = youtube.videos().list(
            id=",".join(video_ids), part="statistics,contentDetails,snippet",
        ).execute()
        enriched = []
        for v in stats_resp.get("items", []):
            stats = v.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            duration_sec = parse_iso_duration(v.get("contentDetails", {}).get("duration", "PT0S"))
            snip = v.get("snippet", {})
            enriched.append({
                "title": snip.get("title", ""), "views": views,
                "likes": likes, "comments": comments,
                "duration_sec": duration_sec, "duration_min": duration_sec // 60,
                "published_at": snip.get("publishedAt", ""),
            })
        enriched.sort(key=lambda x: -x["views"])

        # === Content gap: count + view-dominance (unchanged) ===
        substantial = [v for v in enriched
                       if v["duration_sec"] >= MIN_COMPETITOR_DURATION_SEC
                       and v["views"] >= MIN_COMPETITOR_VIEWS]
        comp_count = len(substantial)
        comp_total_views = sum(v["views"] for v in substantial)

        if comp_count == 0: count_score = 10
        elif comp_count == 1: count_score = 9
        elif comp_count == 2: count_score = 8
        elif comp_count <= 4: count_score = 7
        elif comp_count <= 7: count_score = 6
        elif comp_count <= 10: count_score = 5
        elif comp_count <= 15: count_score = 4
        elif comp_count <= 25: count_score = 3
        elif comp_count <= 40: count_score = 2
        else: count_score = 1

        if comp_total_views == 0: views_for_gap = 10
        elif comp_total_views < 200_000: views_for_gap = 9
        elif comp_total_views < 1_000_000: views_for_gap = 8
        elif comp_total_views < 5_000_000: views_for_gap = 7
        elif comp_total_views < 20_000_000: views_for_gap = 6
        elif comp_total_views < 50_000_000: views_for_gap = 5
        elif comp_total_views < 100_000_000: views_for_gap = 4
        elif comp_total_views < 250_000_000: views_for_gap = 3
        elif comp_total_views < 500_000_000: views_for_gap = 2
        else: views_for_gap = 1

        gap_score = round((count_score + views_for_gap) / 2)

        # === YT demand: volume + engagement ===
        top10 = enriched[:10]
        total_views_top10 = sum(v["views"] for v in top10)

        # Volume bucket
        if total_views_top10 < 10_000: volume_score = 1
        elif total_views_top10 < 100_000: volume_score = 3
        elif total_views_top10 < 1_000_000: volume_score = 5
        elif total_views_top10 < 10_000_000: volume_score = 7
        elif total_views_top10 < 100_000_000: volume_score = 9
        else: volume_score = 10

        # Engagement: comments weighted 3x (likes can be hidden by creators since 2021)
        total_signal = sum(v["likes"] + v["comments"] * 3 for v in top10)
        avg_engagement_pct = (total_signal / total_views_top10 * 100) if total_views_top10 > 0 else 0.0

        if avg_engagement_pct >= 8: engagement_score = 10
        elif avg_engagement_pct >= 6: engagement_score = 9
        elif avg_engagement_pct >= 4: engagement_score = 8
        elif avg_engagement_pct >= 3: engagement_score = 7
        elif avg_engagement_pct >= 2: engagement_score = 6
        elif avg_engagement_pct >= 1: engagement_score = 5
        elif avg_engagement_pct >= 0.5: engagement_score = 4
        elif avg_engagement_pct >= 0.2: engagement_score = 3
        else: engagement_score = 2

        demand_score = round(volume_score * 0.65 + engagement_score * 0.35)

        # === Content freshness: months since most recent substantial video ===
        most_recent_months = None
        if comp_count == 0:
            freshness_score = 10  # No competition = max freshness gap
        else:
            recent_dates = [v["published_at"] for v in substantial if v["published_at"]]
            if not recent_dates:
                freshness_score = 5
            else:
                try:
                    most_recent_str = max(recent_dates)
                    pub_dt = datetime.fromisoformat(most_recent_str.replace("Z", "+00:00"))
                    days_ago = (datetime.now(timezone.utc) - pub_dt).days
                    most_recent_months = days_ago / 30.0
                    if most_recent_months < 1: freshness_score = 1
                    elif most_recent_months < 2: freshness_score = 2
                    elif most_recent_months < 4: freshness_score = 3
                    elif most_recent_months < 6: freshness_score = 4
                    elif most_recent_months < 9: freshness_score = 5
                    elif most_recent_months < 12: freshness_score = 6
                    elif most_recent_months < 18: freshness_score = 7
                    elif most_recent_months < 24: freshness_score = 8
                    elif most_recent_months < 36: freshness_score = 9
                    else: freshness_score = 10
                except Exception:
                    freshness_score = 5

        return {
            "gap_score": gap_score, "comp_count": comp_count,
            "comp_total_views": comp_total_views,
            "top_competitors": substantial[:5],
            "demand_score": demand_score, "total_views_top10": total_views_top10,
            "avg_engagement_pct": avg_engagement_pct,
            "freshness_score": freshness_score, "most_recent_months": most_recent_months,
        }
    except HttpError as e:
        st.error(f"YouTube API error for {player_name}: {e}")
        return error_result
    except Exception as e:
        st.warning(f"Could not fetch YouTube data for {player_name}: {e}")
        return error_result


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
        ("a stale content landscape", scores["contentFreshness"], scores["contentFreshness"] * WEIGHTS["contentFreshness"]),
    ]
    items.sort(key=lambda x: -x[2])
    reason = f"Wins on {items[0][0]} ({items[0][1]}/10) and {items[1][0]} ({items[1][1]}/10)."

    if category == "Iconic retired" and scores["googleTrends"] >= 7:
        reason += " Retired icon with rising interest — likely World Cup or anniversary tailwind."
    elif category == "Rising star" and scores["contentGap"] >= 7:
        reason += " Rising star with few real competitors — perfect window to be first."
    elif category == "Active star" and scores["contentGap"] >= 7 and scores["googleTrends"] >= 7:
        reason += " Active star still under-covered with proper bios — uncommon and valuable combo."

    if scores["contentGap"] >= 8 and scores["googleTrends"] >= 8:
        reason += " High demand, low real competition — a rare combo."
    elif scores["contentFreshness"] >= 8 and scores["googleTrends"] >= 7:
        reason += " Existing bios are stale while interest is climbing — fresh content will dominate the search results."
    elif scores["contentGap"] >= 8:
        reason += " The open lane means easier ranking against existing content."
    elif scores["googleTrends"] >= 8:
        reason += " Ride the wave while interest is peaking."

    if runner_up:
        margin = calc_weighted_score(scores) - calc_weighted_score(runner_up["scores"])
        if margin > 0:
            reason += f" Edges {runner_up['name']} by {margin:.1f} points."
    return reason


def suggest_players(pools, num_icons, num_rising, num_active, exclude):
    icons = [p for p in pools["Iconic retired"] if p not in exclude]
    rising = [p for p in pools["Rising star"] if p not in exclude]
    active = [p for p in pools["Active star"] if p not in exclude]
    selection = []
    selection += random.sample(icons, min(num_icons, len(icons)))
    selection += random.sample(rising, min(num_rising, len(rising)))
    selection += random.sample(active, min(num_active, len(active)))
    return selection


# ============================================================
# UI
# ============================================================

st.markdown("# ⚽ Soccer Player Picker")
st.markdown('<p class="hero-tagline">Find under-served, surging players for your animated YouTube channel.</p>',
            unsafe_allow_html=True)

try:
    api_key = st.secrets["YOUTUBE_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("YouTube API key missing. Add `YOUTUBE_API_KEY` under Settings → Secrets.")
    st.stop()

serpapi_key = st.secrets.get("SERPAPI_KEY") if "SERPAPI_KEY" in st.secrets else None
anthropic_key = st.secrets.get("ANTHROPIC_API_KEY") if "ANTHROPIC_API_KEY" in st.secrets else None
sheets_configured = get_sheet() is not None

if not serpapi_key:
    st.warning("SerpAPI key not set. Google Trends will default to 5. Sign up free at serpapi.com.")

if "covered" not in st.session_state:
    st.session_state["covered"] = set()
if "pending_news_players" not in st.session_state:
    st.session_state["pending_news_players"] = []
if "pending_totw_players" not in st.session_state:
    st.session_state["pending_totw_players"] = []

pools = get_combined_pools()
sheet_players = load_sheet_players()


# ============================================================
# SIDEBAR — Player pool management
# ============================================================

with st.sidebar:
    st.markdown("### 📋 Player pool")
    total = sum(len(v) for v in pools.values())
    st.caption(f"**{total} total** · {len(pools['Iconic retired'])} icons · {len(pools['Rising star'])} rising · {len(pools['Active star'])} active")

    if not sheets_configured:
        st.warning("Google Sheets not configured. Additions won't persist. See `GOOGLE_SHEETS_SETUP.md` to enable.")
    else:
        st.success(f"☁ Synced to Sheet ({len(sheet_players)} custom additions)")

    st.divider()

    # === Manual add (Option A) ===
    with st.expander("➕ Add player manually", expanded=False):
        with st.form("add_player_form", clear_on_submit=True):
            new_name = st.text_input("Player name", placeholder="e.g. Jude Bellingham")
            new_cat = st.selectbox("Category", CATEGORIES)
            submitted = st.form_submit_button("Add", use_container_width=True)
            if submitted and new_name.strip():
                if sheets_configured:
                    added, err = add_players_to_sheet([(new_name, new_cat)], "manual")
                    if err:
                        st.error(err)
                    elif added:
                        st.success(f"Added {new_name}")
                        st.rerun()
                    else:
                        st.info(f"{new_name} is already in the pool.")
                else:
                    st.error("Configure Google Sheets first to persist additions.")

    # === Wikipedia bulk (Option C) ===
    with st.expander("📚 Pull from Wikipedia", expanded=False):
        st.caption("Bulk-add players from curated Wikipedia categories.")
        wiki_choice = st.selectbox("Source", list(WIKI_PRESETS.keys()), key="wiki_choice")
        if st.button("Pull players", key="wiki_pull", use_container_width=True):
            if not sheets_configured:
                st.error("Configure Google Sheets first.")
            else:
                preset = WIKI_PRESETS[wiki_choice]
                with st.spinner(f"Fetching from Wikipedia..."):
                    names = fetch_wikipedia_category(preset["category"])
                if not names:
                    st.warning("No players found or fetch failed.")
                else:
                    pairs = [(n, preset["assigned_pool"]) for n in names]
                    added, err = add_players_to_sheet(pairs, "wikipedia")
                    if err:
                        st.error(err)
                    else:
                        st.success(f"Added {added} new players (skipped {len(names) - added} duplicates).")
                        st.rerun()

    # === FC Mobile featured (curated + full pool) ===
    with st.expander("🎮 FC Mobile players", expanded=False):
        st.caption(
            f"Two import options: a curated set of {len(FC_MOBILE_FEATURED)} verified features "
            f"(Heroes, TOTY/UTOTS standouts), or the full FC Mobile master pool "
            f"({len(FC_MOBILE_FULL_POOL)} players from EA's roster). "
            "Saturated names (Messi/Ronaldo/Mbappé/Neymar) are excluded from both."
            if FCM_FULL_AVAILABLE else
            f"One-click import of {len(FC_MOBILE_FEATURED)} verified FC Mobile features."
        )
        if st.button("Add curated set (39)", key="fcm_curated", use_container_width=True):
            if not sheets_configured:
                st.error("Configure Google Sheets first.")
            else:
                added, err = add_players_to_sheet(FC_MOBILE_FEATURED, "fc_mobile_curated")
                if err:
                    st.error(err)
                else:
                    skipped = len(FC_MOBILE_FEATURED) - added
                    st.success(f"Added {added} new players (skipped {skipped} duplicates).")
                    st.rerun()

        if FCM_FULL_AVAILABLE:
            if st.button(f"Add full pool ({len(FC_MOBILE_FULL_POOL)})", key="fcm_full",
                         use_container_width=True, type="primary"):
                if not sheets_configured:
                    st.error("Configure Google Sheets first.")
                else:
                    with st.spinner(f"Importing {len(FC_MOBILE_FULL_POOL)} players..."):
                        added, err = add_players_to_sheet(FC_MOBILE_FULL_POOL, "fc_mobile_full")
                    if err:
                        st.error(err)
                    else:
                        skipped = len(FC_MOBILE_FULL_POOL) - added
                        st.success(f"Added {added} new players (skipped {skipped} duplicates).")
                        st.rerun()

    # === TOTW capture (Option D) ===
    with st.expander("📅 Pull recent TOTW players", expanded=False):
        st.caption(
            "Scans Google for recent EA FC TOTW announcements (FUTBIN, Sportskeeda, Beebom, Goal). "
            "Claude extracts player names from the article titles and snippets."
        )
        if not anthropic_key:
            st.error("Anthropic API key not set.")
        elif not serpapi_key:
            st.error("SerpAPI key required.")
        elif not sheets_configured:
            st.error("Configure Google Sheets first.")
        else:
            totw_window = st.selectbox(
                "Time window",
                ["this week", "last 2 weeks", "this month", "last 3 months", "last 6 months"],
                key="totw_window",
            )
            if st.button("Scan TOTW", key="totw_pull", use_container_width=True):
                with st.spinner("Searching TOTW articles..."):
                    snippets = fetch_totw_articles(serpapi_key, totw_window)
                if not snippets:
                    st.warning("No TOTW articles found. Try a wider time window.")
                else:
                    with st.spinner(f"Extracting names from {len(snippets)} articles..."):
                        names = extract_players_from_headlines(snippets, anthropic_key)
                    existing = {p.lower() for p in (pools["Iconic retired"] + pools["Rising star"] + pools["Active star"])}
                    new_names = [n for n in names if n.lower() not in existing]
                    if not new_names:
                        st.info(f"Found {len(names)} names, all already in pool.")
                    else:
                        st.session_state["pending_totw_players"] = new_names
                        st.rerun()

            if st.session_state.get("pending_totw_players"):
                st.markdown("**Approve to add (as Active star):**")
                approved = []
                for nm in st.session_state["pending_totw_players"]:
                    if st.checkbox(nm, value=True, key=f"totw_approve_{nm}"):
                        approved.append((nm, "Active star"))
                if st.button("Add approved", type="primary", use_container_width=True, key="totw_add"):
                    if approved:
                        added, err = add_players_to_sheet(approved, "totw")
                        if err:
                            st.error(err)
                        else:
                            st.success(f"Added {added} TOTW players.")
                    st.session_state["pending_totw_players"] = []
                    st.rerun()

    # === News-driven discovery (Option B) ===
    with st.expander("📰 Discover from news", expanded=False):
        st.caption("Scans recent soccer headlines and extracts rising player names.")
        if not anthropic_key:
            st.error("Anthropic API key not set. Add `ANTHROPIC_API_KEY` to secrets.")
        elif not serpapi_key:
            st.error("SerpAPI key required for news search.")
        elif not sheets_configured:
            st.error("Configure Google Sheets first.")
        else:
            news_preset = st.selectbox(
                "Query preset",
                options=[
                    "🎮 FC Mobile new cards",
                    "🌟 Rising soccer stars",
                    "🔄 Transfer breakouts",
                    "✏️ Custom...",
                ],
                key="news_preset",
            )
            preset_to_query = {
                "🎮 FC Mobile new cards": "EA FC Mobile new player card release TOTW Hero promo",
                "🌟 Rising soccer stars": "rising soccer star breakout young footballer 2026",
                "🔄 Transfer breakouts": "soccer transfer breakout player 2026",
            }
            if news_preset == "✏️ Custom...":
                news_query = st.text_input(
                    "Custom query",
                    value="soccer transfer breakout player 2026",
                    key="news_query",
                )
            else:
                news_query = preset_to_query[news_preset]
                st.caption(f"_Query: `{news_query}`_")
            if st.button("Scan news", key="news_pull", use_container_width=True):
                with st.spinner("Fetching headlines..."):
                    headlines = fetch_soccer_news(serpapi_key, news_query)
                if not headlines:
                    st.warning("No headlines found.")
                else:
                    with st.spinner(f"Extracting names from {len(headlines)} headlines..."):
                        names = extract_players_from_headlines(headlines, anthropic_key)
                    # Filter to genuinely new names
                    existing = {p.lower() for p in (pools["Iconic retired"] + pools["Rising star"] + pools["Active star"])}
                    new_names = [n for n in names if n.lower() not in existing]
                    if not new_names:
                        st.info("No new players found in headlines (all already in pool).")
                    else:
                        st.session_state["pending_news_players"] = new_names
                        st.rerun()

            # Show pending approvals
            if st.session_state["pending_news_players"]:
                st.markdown("**Approve to add (as Rising star):**")
                approved = []
                for nm in st.session_state["pending_news_players"]:
                    if st.checkbox(nm, value=True, key=f"approve_{nm}"):
                        approved.append((nm, "Rising star"))
                if st.button("Add approved", type="primary", use_container_width=True):
                    if approved:
                        added, err = add_players_to_sheet(approved, "news")
                        if err:
                            st.error(err)
                        else:
                            st.success(f"Added {added} players from news.")
                    st.session_state["pending_news_players"] = []
                    st.rerun()

    # === View / manage custom additions ===
    if sheet_players:
        with st.expander(f"View custom additions ({len(sheet_players)})", expanded=False):
            for p in sheet_players[-30:]:  # last 30 to keep sidebar manageable
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"**{p.get('name')}** · {p.get('category')} · _{p.get('source')}_")
                with col2:
                    if st.button("✕", key=f"rm_{p.get('name')}_{p.get('added_at')}", help="Remove"):
                        remove_player_from_sheet(p.get("name"))
                        st.rerun()

    # === Maintenance ===
    with st.expander("🛠️ Maintenance", expanded=False):
        st.caption(
            f"One-shot tools for cleaning up the pool. "
            f"The reclassify button below moves {len(RISING_RECLASSIFY)} young breakout players "
            "(born ~2002+ or recent breakouts) from Active → Rising star. "
            "Run once after the FC Mobile full pool import."
        )
        if st.button(f"Reclassify {len(RISING_RECLASSIFY)} players as Rising stars",
                     key="reclass_rising", use_container_width=True):
            if not sheets_configured:
                st.error("Configure Google Sheets first.")
            else:
                with st.spinner("Reclassifying..."):
                    updated, not_found, err = reclassify_in_sheet(RISING_RECLASSIFY, "Rising star")
                if err:
                    st.error(err)
                else:
                    st.success(f"Reclassified {updated} players as Rising stars.")
                    if not_found:
                        st.warning(
                            f"{len(not_found)} not found in Sheet (probably not yet imported): "
                            f"{', '.join(not_found[:5])}{'...' if len(not_found) > 5 else ''}"
                        )
                    st.rerun()


# ============================================================
# MAIN — analysis flow (unchanged from v4 structure)
# ============================================================

st.markdown('<div class="section-label">Scoring weights</div>', unsafe_allow_html=True)
cols = st.columns(5)
for i, (k, w) in enumerate(WEIGHTS.items()):
    with cols[i]:
        st.metric(LABELS[k], f"{int(w * 100)}%")

with st.expander("How this finds gaps — quick version"):
    st.markdown(
        """
The picker is fully automated — every score comes from data. It targets a **demand-supply mismatch**: players people are actively searching for, but who don't have enough quality content yet.

- **Google Trends (40%)** — pulls the last 30 days of search interest and detects rising momentum. The highest single weight because rising interest is the strongest signal of upcoming demand.
- **Content gap (20%)** — counts substantial competitors on YouTube (3+ min, 50k+ views) and weighs their combined view dominance. Two videos with 80k combined views is a real gap; two with 5M combined views is not.
- **YT demand (20%)** — combines top-10 view volume with engagement quality (likes + comments per view). High views with low engagement is passive scrolling; high views with high engagement is hungry audience.
- **Freshness (20%)** — months since the most recent substantial bio video was published. Stale top results mean fresh content will dominate the search rankings.

No manual sliders. Every signal is computed live from YouTube + Google.
        """
    )

st.markdown("<br>", unsafe_allow_html=True)

mode = st.radio("Mode", ["🎲 Suggest players for me", "📝 Analyze my list"],
                horizontal=True, label_visibility="collapsed")

players_to_analyze = []
analyze_clicked = False

if mode == "🎲 Suggest players for me":
    st.markdown('<div class="section-label" style="margin-top:1rem;">Player mix</div>', unsafe_allow_html=True)
    st.caption(f"Sampling from your pool of {total} players. Icons benefit from World Cup tailwind. Rising stars ride FC Mobile / news spikes.")

    c1, c2, c3 = st.columns(3)
    with c1: num_icons = st.number_input("Iconic retired", 0, 10, 2)
    with c2: num_rising = st.number_input("Rising stars", 0, 10, 3)
    with c3: num_active = st.number_input("Active stars", 0, 10, 2)

    total_pick = num_icons + num_rising + num_active

    st.markdown("<br>", unsafe_allow_html=True)
    analyze_clicked = st.button(
        f"🎲 Analyze {total_pick} players" if total_pick > 0 else "🎲 Analyze",
        type="primary", use_container_width=True, disabled=(total_pick == 0),
    )
    if analyze_clicked:
        players_to_analyze = suggest_players(
            pools, num_icons, num_rising, num_active,
            exclude=st.session_state["covered"],
        )
else:
    st.markdown('<div class="section-label" style="margin-top:1rem;">Players to analyze</div>', unsafe_allow_html=True)
    st.caption(
        "One name per line. Country suffixes (e.g. `Marta — Brazil`), bullets, and "
        "annotations in parentheses are stripped automatically. Accent-insensitive matching."
    )
    default_players = "Lamine Yamal\nFlorian Wirtz\nTrinity Rodman\nJay-Jay Okocha\nVitor Roque"
    players_input = st.text_area("Names", value=default_players, height=140, label_visibility="collapsed")
    st.markdown("<br>", unsafe_allow_html=True)
    analyze_clicked = st.button("🔍 Analyze players", type="primary", use_container_width=True)
    if analyze_clicked:
        players_to_analyze = [clean_player_input(p) for p in players_input.split("\n") if clean_player_input(p)]


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
            "contentFreshness": yt["freshness_score"],
        }
        results.append({
            "name": name, "category": get_category_for(name, pools),
            "scores": scores,
            "raw": {
                "comp_count": yt["comp_count"],
                "comp_total_views": yt["comp_total_views"],
                "top_competitors": yt["top_competitors"],
                "trend_pct": gt_pct,
                "total_views_top10": yt["total_views_top10"],
                "avg_engagement_pct": yt["avg_engagement_pct"],
                "most_recent_months": yt["most_recent_months"],
            },
        })

    progress.progress(1.0, text="Done")
    time.sleep(0.3)
    progress.empty()
    st.session_state["results"] = results
    st.session_state["analyzed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")


if "results" in st.session_state:
    results = st.session_state["results"]
    for r in results:
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

            # Gap
            if r["raw"]["comp_count"] >= 0:
                if r["raw"]["comp_count"] == 0:
                    gap_detail = "0 substantial competitors — wide open"
                else:
                    gap_detail = (
                        f"{r['raw']['comp_count']} competitors · "
                        f"{format_count(r['raw']['comp_total_views'])} combined views"
                    )
            else:
                gap_detail = "(fetch failed)"
            st.markdown(f"**Content gap: {r['scores']['contentGap']}/10**  \n_{gap_detail}_")

            # Trends
            st.markdown(
                f"**Google Trends: {r['scores']['googleTrends']}/10**  \n"
                f"_{r['raw']['trend_pct']:+.0f}% over the last 30 days_"
            )

            # YT demand with engagement breakdown
            if r["raw"]["total_views_top10"] >= 0:
                eng = r["raw"].get("avg_engagement_pct", 0)
                demand_detail = (
                    f"{format_count(r['raw']['total_views_top10'])} views across top 10 · "
                    f"{eng:.2f}% engagement"
                )
            else:
                demand_detail = "(fetch failed)"
            st.markdown(f"**YT demand: {r['scores']['ytSearchDemand']}/10**  \n_{demand_detail}_")

            # Freshness
            months = r["raw"].get("most_recent_months")
            if r["raw"]["comp_count"] == 0:
                freshness_detail = "no existing bio content — maximum freshness gap"
            elif months is None:
                freshness_detail = "couldn't read publish dates"
            elif months < 1:
                freshness_detail = f"top competing bio is <1 month old — fresh content already exists"
            elif months < 12:
                freshness_detail = f"top competing bio is ~{int(months)} months old"
            else:
                freshness_detail = f"top competing bio is ~{months/12:.1f} years old — significant freshness gap"
            st.markdown(f"**Freshness: {r['scores']['contentFreshness']}/10**  \n_{freshness_detail}_")

            if r["raw"].get("top_competitors"):
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(f"**Top competitors ({len(r['raw']['top_competitors'])} shown):**")
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
            "Freshness": r["scores"]["contentFreshness"],
            "Real competitors": r["raw"]["comp_count"],
            "Competitor views": r["raw"]["comp_total_views"],
            "Trend %": round(r["raw"]["trend_pct"], 1),
            "Top-10 YT views": r["raw"]["total_views_top10"],
            "Engagement %": round(r["raw"].get("avg_engagement_pct", 0), 2),
            "Top bio age (months)": (
                round(r["raw"]["most_recent_months"], 1)
                if r["raw"].get("most_recent_months") is not None else None
            ),
        }
        for i, r in enumerate(ranked)
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False)
    st.download_button("Download as CSV", csv,
                       f"player_rankings_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                       "text/csv", use_container_width=True)

st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("---")
st.markdown('<div class="section-label">How the scoring works</div>', unsafe_allow_html=True)
st.markdown(
    """
**Google Trends — 40% weight — auto-scored from SerpAPI**
Pulls the last 30 days of Google search interest. Compares the most recent third of the window to the earliest third to detect rising or falling momentum. The highest single weight because rising search interest is the leading indicator of upcoming demand.

**Content gap — 20% weight — auto-scored from YouTube**
Searches YouTube for the player's exact name and identifies substantial competitors (3+ min, 50k+ views). Gap score averages two factors: count of competitors and total combined views (how dominant they are). Two videos with 80k combined views is barely competition; two with 5M is real dominance.

**YT demand — 20% weight — auto-scored from YouTube**
Combines two signals weighted 65/35:
- *Volume*: sum of top-10 video view counts (broad audience interest)
- *Engagement quality*: average `(likes + comments × 3) / views` across the top 10 (active interest vs passive scrolling). Comments weighted 3× because creators can hide like counts but rarely hide comment counts.

A player with 100M views and 0.3% engagement scores lower than one with 20M views and 4% engagement — because the second audience is hungry for content, not just casually scrolling.

**Content freshness — 20% weight — auto-scored from YouTube**
Months since the most recent substantial bio video was published. The dimension count alone misses: a player can have a few bios that all came out 2-3 years ago, and the audience has moved on. Fresh content will rank above stale top results almost automatically. No substantial bios at all = max freshness gap.

---
"""
)

# Dynamic pool-source description — reflects actual current counts
default_total = len(DEFAULT_ICONIC) + len(DEFAULT_RISING) + len(DEFAULT_ACTIVE)
sheet_count = len(sheet_players) if sheets_configured else 0
current_total = sum(len(v) for v in pools.values())
st.markdown(
    f"""
**Player pool sources.** Right now you're sampling from **{current_total} total players** —
{default_total} hardcoded defaults ({len(DEFAULT_ICONIC)} iconic · {len(DEFAULT_RISING)} rising · {len(DEFAULT_ACTIVE)} active) plus {sheet_count} custom additions from your Google Sheet.
Custom additions come from the sidebar — manual entry, Wikipedia category pulls, FC Mobile presets, TOTW scanner, or news-driven discovery — and persist in a shared Sheet so your whole team sees the same pool.
"""
)
