"""
MLB Betting Analysis Backend
FastAPI server with SQLite caching and multi-source data integration
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3
import json
import asyncio
from typing import Optional, List, Dict
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MLB Betting Analysis API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database initialization
DB_PATH = "mlb_cache.db"

def init_db():
    """Initialize SQLite database for caching"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Cache table for daily stats
    c.execute('''CREATE TABLE IF NOT EXISTS cache
                 (key TEXT PRIMARY KEY, 
                  data TEXT, 
                  timestamp DATETIME,
                  expires_at DATETIME)''')
    
    # Batter-pitcher matchups
    c.execute('''CREATE TABLE IF NOT EXISTS matchups
                 (id INTEGER PRIMARY KEY,
                  batter_id INTEGER,
                  pitcher_id INTEGER,
                  career_avg REAL,
                  vs_lefty_avg REAL,
                  vs_righty_avg REAL,
                  recent_avg REAL,
                  sample_size INTEGER,
                  updated_at DATETIME)''')
    
    # Game data
    c.execute('''CREATE TABLE IF NOT EXISTS games
                 (game_id TEXT PRIMARY KEY,
                  game_date TEXT,
                  home_team TEXT,
                  away_team TEXT,
                  home_pitcher_id INTEGER,
                  home_pitcher_name TEXT,
                  away_pitcher_id INTEGER,
                  away_pitcher_name TEXT,
                  home_pitcher_hand TEXT,
                  away_pitcher_hand TEXT,
                  analysis TEXT,
                  cached_at DATETIME)''')
    
    conn.commit()
    conn.close()

init_db()

# Models
class GameInfo(BaseModel):
    game_id: str
    game_date: str
    home_team: str
    away_team: str
    home_pitcher_name: str
    away_pitcher_name: str
    time: str

class BatterMatchup(BaseModel):
    batter_name: str
    batter_id: int
    position: str
    career_avg: Optional[float] = None
    vs_pitcher_avg: Optional[float] = None
    vs_handedness_avg: Optional[float] = None
    recent_avg: Optional[float] = None
    sample_size: Optional[int] = None
    trend: Optional[str] = None  # "hot", "cold", "neutral"
    confidence: Optional[str] = None  # "high", "medium", "low"

class BettingSuggestion(BaseModel):
    type: str  # "moneyline", "run_line", "over_under", "player_prop"
    recommendation: str
    confidence: str  # "high", "medium", "low"
    key_factors: List[str]
    edge_percentage: Optional[float] = None

class GameAnalysis(BaseModel):
    game_info: GameInfo
    home_team_stats: Dict
    away_team_stats: Dict
    top_matchups: List[BatterMatchup]
    betting_suggestions: List[BettingSuggestion]
    analysis_timestamp: str
    data_freshness: str

# Utility functions
def get_cache(key: str) -> Optional[dict]:
    """Retrieve from cache if not expired"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT data, expires_at FROM cache WHERE key = ?', (key,))
        result = c.fetchone()
        conn.close()
        
        if result:
            data, expires_at = result
            if datetime.fromisoformat(expires_at) > datetime.now():
                return json.loads(data)
    except Exception as e:
        logger.error(f"Cache read error: {e}")
    return None

def set_cache(key: str, data: dict, hours: int = 24):
    """Store in cache with expiration"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        expires_at = (datetime.now() + timedelta(hours=hours)).isoformat()
        c.execute('INSERT OR REPLACE INTO cache (key, data, timestamp, expires_at) VALUES (?, ?, ?, ?)',
                  (key, json.dumps(data), datetime.now().isoformat(), expires_at))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Cache write error: {e}")

def fetch_mlb_schedule(date: str) -> List[dict]:
    """
    Fetch MLB schedule from statsapi.mlb.com
    date format: YYYY-MM-DD
    """
    try:
        import requests
        
        cache_key = f"schedule_{date}"
        cached = get_cache(cache_key)
        if cached:
            logger.info(f"Using cached schedule for {date}")
            return cached
        
        # MLB Stats API endpoint
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&hydrate=team,probablePitcher"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        dates = data.get('dates', [])
        games_list = dates[0].get('games', []) if dates else []

        # Parse game data
        parsed_games = []
        for game in games_list:
            try:
                # Skip if game status is not what we want
                if 'status' not in game or 'abstractGameState' not in game['status']:
                    continue
                    
                status = game['status']['abstractGameState']
                if status == 'Final':
                    continue
                
                game_date_str = game.get('gameDate', '')
                game_info = {
                    'game_id': str(game.get('gamePk', 'unknown')),
                    'game_date': game.get('officialDate', game_date_str.split('T')[0]),
                    'home_team': game['teams']['home']['team']['name'],
                    'away_team': game['teams']['away']['team']['name'],
                    'home_team_code': game['teams']['home']['team'].get('abbreviation', ''),
                    'away_team_code': game['teams']['away']['team'].get('abbreviation', ''),
                    'time': game_date_str.split('T')[1][:5] if 'T' in game_date_str else 'TBA',
                    'status': status,
                    'home_pitcher_name': game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBA'),
                    'away_pitcher_name': game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBA'),
                    'home_pitcher_id': game['teams']['home'].get('probablePitcher', {}).get('id'),
                    'away_pitcher_id': game['teams']['away'].get('probablePitcher', {}).get('id'),
                }
                
                parsed_games.append(game_info)
            except KeyError as e:
                logger.warning(f"Missing key in game data: {e}")
                continue
            except Exception as e:
                logger.warning(f"Error parsing game: {e}")
                continue
        
        set_cache(cache_key, parsed_games, hours=6)
        return parsed_games
    
    except Exception as e:
        logger.error(f"Error fetching schedule: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch schedule: {str(e)}")

def fetch_team_stats(team_id: str, pitcher_hand: str) -> dict:
    """
    Fetch team stats vs. handedness
    Returns: batting avg, OBP, SLG vs left/right
    """
    try:
        import requests
        
        cache_key = f"team_stats_{team_id}_{pitcher_hand}"
        cached = get_cache(cache_key)
        if cached:
            return cached
        
        # MLB Stats API for team stats
        url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}?hydrate=record,stats"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        team_data = response.json()['teams'][0]
        
        # Extract relevant stats (simplified - real implementation would need more detailed parsing)
        stats = {
            'team_name': team_data['name'],
            'batting_avg': 0.270,  # Placeholder
            'obp': 0.330,
            'slugging': 0.420,
            'vs_lefties_avg': 0.268,
            'vs_righties_avg': 0.272,
        }
        
        set_cache(cache_key, stats, hours=24)
        return stats
    
    except Exception as e:
        logger.error(f"Error fetching team stats: {e}")
        return {
            'team_name': 'Unknown',
            'batting_avg': 0.270,
            'obp': 0.330,
            'slugging': 0.420,
        }

def fetch_batter_matchups(batter_id: int, pitcher_id: int, pitcher_hand: str) -> Optional[dict]:
    """
    Fetch batter vs pitcher matchup data
    Uses pybaseball or Baseball Reference data
    """
    try:
        cache_key = f"matchup_{batter_id}_{pitcher_id}"
        cached = get_cache(cache_key)
        if cached:
            return cached
        
        # NOTE: In production, would integrate with pybaseball here
        # For now, returning realistic placeholder data structure
        matchup = {
            'career_avg': 0.285,
            'vs_pitcher_avg': 0.310,
            'sample_size': 8,
            'recent_avg': 0.300,
            'trend': 'hot',
        }
        
        set_cache(cache_key, matchup, hours=24)
        return matchup
    
    except Exception as e:
        logger.error(f"Error fetching matchup data: {e}")
        return None

def fetch_savant_stats() -> dict:
    """Fetch xBA and xwOBA for all batters from Baseball Savant"""
    try:
        import requests, csv, io
        cache_key = "savant_xstats_2026"
        cached = get_cache(cache_key)
        if cached:
            return cached

        url = "https://baseballsavant.mlb.com/leaderboard/expected_statistics?type=batter&year=2026&position=&team=&min=10&csv=true"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, timeout=20, headers=headers)
        response.raise_for_status()

        stats = {}
        text = response.content.decode('utf-8-sig')  # strip BOM
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                player_id = int(row.get('player_id', 0))
                if player_id:
                    stats[player_id] = {
                        'xba': float(row.get('est_ba') or 0),
                        'xwoba': float(row.get('est_woba') or 0),
                    }
            except (ValueError, KeyError):
                continue

        set_cache(cache_key, stats, hours=12)
        logger.info(f"Fetched Savant xstats for {len(stats)} batters")
        return stats
    except Exception as e:
        logger.error(f"Error fetching Savant stats: {e}")
        return {}


def fetch_batter_season_stats(player_id: int) -> dict:
    """Fetch batter 2026 season hitting stats"""
    try:
        import requests
        cache_key = f"batter_season_{player_id}_2026"
        cached = get_cache(cache_key)
        if cached:
            return cached

        url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&season=2026&group=hitting"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        stats = {}
        for stat_group in data.get('stats', []):
            splits = stat_group.get('splits', [])
            if splits:
                s = splits[0].get('stat', {})
                stats = {
                    'ba': float(s.get('avg') or 0) or None,
                    'obp': float(s.get('obp') or 0) or None,
                    'slg': float(s.get('slg') or 0) or None,
                    'ab': s.get('atBats', 0),
                }
                break

        set_cache(cache_key, stats, hours=6)
        return stats
    except Exception as e:
        logger.error(f"Error fetching batter season stats for {player_id}: {e}")
        return {}


def fetch_batter_vs_pitcher(batter_id: int, pitcher_id: int) -> dict:
    """Fetch career batter vs pitcher matchup stats"""
    try:
        import requests
        cache_key = f"bvp_{batter_id}_{pitcher_id}"
        cached = get_cache(cache_key)
        if cached:
            return cached

        url = f"https://statsapi.mlb.com/api/v1/people/{batter_id}/stats?stats=vsPlayerTotal&opposingPlayerId={pitcher_id}&group=hitting"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        result = {'ba': None, 'ab': 0, 'hits': 0}
        for stat_group in data.get('stats', []):
            splits = stat_group.get('splits', [])
            if splits:
                s = splits[0].get('stat', {})
                ab = s.get('atBats', 0)
                result = {
                    'ba': float(s.get('avg') or 0) if ab > 0 else None,
                    'ab': ab,
                    'hits': s.get('hits', 0),
                }
                break

        set_cache(cache_key, result, hours=24)
        return result
    except Exception as e:
        logger.error(f"Error fetching BvP {batter_id} vs {pitcher_id}: {e}")
        return {'ba': None, 'ab': 0, 'hits': 0}


def fetch_game_lineup_raw(game_id: str) -> dict:
    """Fetch confirmed lineup from MLB game live feed"""
    try:
        import requests
        url = f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        teams = data.get('liveData', {}).get('boxscore', {}).get('teams', {})
        home = teams.get('home', {})
        away = teams.get('away', {})

        return {
            'confirmed': len(home.get('battingOrder', [])) > 0,
            'home_batting_order': home.get('battingOrder', []),
            'away_batting_order': away.get('battingOrder', []),
            'home_players': home.get('players', {}),
            'away_players': away.get('players', {}),
        }
    except Exception as e:
        logger.error(f"Error fetching lineup for game {game_id}: {e}")
        return {'confirmed': False, 'home_batting_order': [], 'away_batting_order': [], 'home_players': {}, 'away_players': {}}


def fetch_game_details(game_id: str) -> dict:
    """Fetch game teams and probable pitchers by gamePk"""
    try:
        import requests
        cache_key = f"game_info_{game_id}"
        cached = get_cache(cache_key)
        if cached:
            return cached

        url = f"https://statsapi.mlb.com/api/v1/schedule?gamePk={game_id}&hydrate=team,probablePitcher"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        dates = data.get('dates', [])
        if not dates or not dates[0].get('games'):
            return {}

        game = dates[0]['games'][0]
        home = game['teams']['home']
        away = game['teams']['away']

        result = {
            'home_team_id': home['team']['id'],
            'away_team_id': away['team']['id'],
            'home_team_name': home['team']['name'],
            'away_team_name': away['team']['name'],
            'home_pitcher_id': home.get('probablePitcher', {}).get('id'),
            'away_pitcher_id': away.get('probablePitcher', {}).get('id'),
            'home_pitcher_name': home.get('probablePitcher', {}).get('fullName', 'TBA'),
            'away_pitcher_name': away.get('probablePitcher', {}).get('fullName', 'TBA'),
        }

        set_cache(cache_key, result, hours=6)
        return result
    except Exception as e:
        logger.error(f"Error fetching game details: {e}")
        return {}


def fetch_team_season_stats(team_id: int) -> dict:
    """Fetch team season batting stats"""
    try:
        import requests
        cache_key = f"team_batting_{team_id}_2026"
        cached = get_cache(cache_key)
        if cached:
            return cached

        url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season&season=2026&group=hitting"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        stats = {}
        for stat_group in data.get('stats', []):
            splits = stat_group.get('splits', [])
            if splits:
                s = splits[0].get('stat', {})
                stats = {
                    'batting_avg': float(s.get('avg') or 0),
                    'obp': float(s.get('obp') or 0),
                    'slugging': float(s.get('slg') or 0),
                    'ops': float(s.get('ops') or 0),
                    'home_runs': s.get('homeRuns', 0),
                    'runs': s.get('runs', 0),
                    'strikeouts': s.get('strikeOuts', 0),
                    'walks': s.get('baseOnBalls', 0),
                }
                break

        set_cache(cache_key, stats, hours=6)
        return stats
    except Exception as e:
        logger.error(f"Error fetching team batting stats: {e}")
        return {}


def fetch_pitcher_stats(pitcher_id: int) -> dict:
    """Fetch pitcher season stats"""
    try:
        import requests
        cache_key = f"pitcher_{pitcher_id}_2026"
        cached = get_cache(cache_key)
        if cached:
            return cached

        url = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=season&season=2026&group=pitching"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        stats = {}
        for stat_group in data.get('stats', []):
            splits = stat_group.get('splits', [])
            if splits:
                s = splits[0].get('stat', {})
                stats = {
                    'era': float(s.get('era') or 0),
                    'whip': float(s.get('whip') or 0),
                    'innings_pitched': s.get('inningsPitched', '0.0'),
                    'strikeouts': s.get('strikeOuts', 0),
                    'walks': s.get('baseOnBalls', 0),
                    'wins': s.get('wins', 0),
                    'losses': s.get('losses', 0),
                    'home_runs_allowed': s.get('homeRuns', 0),
                    'batting_avg_against': float(s.get('avg') or 0),
                    'k_per_9': float(s.get('strikeoutsPer9Inn') or 0),
                    'games_started': s.get('gamesStarted', 0),
                }
                break

        set_cache(cache_key, stats, hours=6)
        return stats
    except Exception as e:
        logger.error(f"Error fetching pitcher stats: {e}")
        return {}


def generate_betting_suggestions(game_data: dict, matchups: List[dict]) -> List[BettingSuggestion]:
    """
    Generate betting recommendations based on analysis
    """
    suggestions = []
    
    # Analyze matchups for strong signals
    favorable_matchups = [m for m in matchups if m.get('confidence') == 'high']
    
    if len(favorable_matchups) >= 3:
        suggestions.append(BettingSuggestion(
            type="moneyline",
            recommendation=f"Lean toward {game_data.get('away_team', 'Away Team')} based on favorable batter matchups",
            confidence="medium",
            key_factors=[m['batter_name'] for m in favorable_matchups[:3]],
            edge_percentage=2.5
        ))
    
    # Over/Under suggestions
    suggestions.append(BettingSuggestion(
        type="over_under",
        recommendation="Monitor recent pace of play; no strong signal yet",
        confidence="low",
        key_factors=["Pitcher bullpen depth", "Recent game scores"],
    ))
    
    # Player prop suggestions
    if favorable_matchups:
        top_batter = favorable_matchups[0]
        suggestions.append(BettingSuggestion(
            type="player_prop",
            recommendation=f"{top_batter['batter_name']} over 0.5 runs scored (strong hitting matchup)",
            confidence="medium",
            key_factors=[f"Career avg vs pitcher: {top_batter.get('vs_pitcher_avg', 0):.3f}"],
        ))
    
    return suggestions

# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/games/{date}")
async def get_games(date: str):
    """
    Get all MLB games for a specific date with initial analysis
    date format: YYYY-MM-DD
    """
    try:
        games = fetch_mlb_schedule(date)
        
        return {
            "date": date,
            "games_count": len(games),
            "games": games,
            "cached": False,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/game/{game_id}/lineup")
async def get_lineup(game_id: str):
    """
    Returns confirmed lineup (or empty if not yet announced) with per-batter
    BA, xBA, xwOBA, and career BA vs the opposing starting pitcher.
    """
    try:
        cache_key = f"lineup_analysis_{game_id}"
        cached = get_cache(cache_key)
        if cached and cached.get('lineup_confirmed'):
            return cached

        game_details = fetch_game_details(game_id)
        if not game_details:
            raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

        raw = fetch_game_lineup_raw(game_id)
        confirmed = raw.get('confirmed', False)
        savant = fetch_savant_stats()

        home_pitcher_id = game_details.get('home_pitcher_id')
        away_pitcher_id = game_details.get('away_pitcher_id')

        def build_lineup(batting_order, players_dict, opp_pitcher_id):
            lineup = []
            for i, player_id in enumerate(batting_order):
                pdata = players_dict.get(f"ID{player_id}", {})
                name = pdata.get('person', {}).get('fullName', 'Unknown')
                pos = pdata.get('position', {}).get('abbreviation', '')

                season = fetch_batter_season_stats(player_id)
                vs_p = fetch_batter_vs_pitcher(player_id, opp_pitcher_id) if opp_pitcher_id else {}
                sx = savant.get(player_id, {})

                lineup.append({
                    'batting_order': i + 1,
                    'player_id': player_id,
                    'name': name,
                    'position': pos,
                    'ba': season.get('ba'),
                    'xba': sx.get('xba') or None,
                    'xwoba': sx.get('xwoba') or None,
                    'vs_pitcher_ba': vs_p.get('ba'),
                    'vs_pitcher_ab': vs_p.get('ab', 0),
                    'vs_pitcher_hits': vs_p.get('hits', 0),
                })
            return lineup

        result = {
            'game_id': game_id,
            'lineup_confirmed': confirmed,
            'home_team': game_details['home_team_name'],
            'away_team': game_details['away_team_name'],
            'home_pitcher': {'name': game_details['home_pitcher_name'], 'id': home_pitcher_id},
            'away_pitcher': {'name': game_details['away_pitcher_name'], 'id': away_pitcher_id},
            'home_lineup': build_lineup(raw['home_batting_order'], raw['home_players'], away_pitcher_id),
            'away_lineup': build_lineup(raw['away_batting_order'], raw['away_players'], home_pitcher_id),
            'timestamp': datetime.now().isoformat(),
        }

        set_cache(cache_key, result, hours=1 if confirmed else 0.25)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lineup for game {game_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/game/{game_id}/analysis")
async def analyze_game(game_id: str):
    """
    Detailed analysis for a specific game using real MLB Stats API data
    """
    try:
        cache_key = f"analysis_{game_id}"
        cached = get_cache(cache_key)
        if cached:
            logger.info(f"Using cached analysis for game {game_id}")
            return cached

        game_details = fetch_game_details(game_id)
        if not game_details:
            raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

        home_pitcher_id = game_details.get('home_pitcher_id')
        away_pitcher_id = game_details.get('away_pitcher_id')

        home_team_stats = fetch_team_season_stats(game_details['home_team_id'])
        away_team_stats = fetch_team_season_stats(game_details['away_team_id'])
        home_pitcher_stats = fetch_pitcher_stats(home_pitcher_id) if home_pitcher_id else {}
        away_pitcher_stats = fetch_pitcher_stats(away_pitcher_id) if away_pitcher_id else {}

        # ERA-based moneyline suggestion
        home_era = home_pitcher_stats.get('era') or None
        away_era = away_pitcher_stats.get('era') or None
        suggestions = []

        if home_era and away_era:
            era_diff = abs(home_era - away_era)
            if home_era < away_era - 0.5:
                confidence = "medium" if era_diff >= 1.0 else "low"
                suggestions.append({
                    "type": "moneyline",
                    "recommendation": f"Lean {game_details['home_team_name']} — home SP ERA advantage ({home_era:.2f} vs {away_era:.2f})",
                    "confidence": confidence,
                    "key_factors": [
                        f"{game_details['home_pitcher_name']}: {home_era:.2f} ERA, {home_pitcher_stats.get('whip', 0):.2f} WHIP",
                        f"{game_details['away_pitcher_name']}: {away_era:.2f} ERA, {away_pitcher_stats.get('whip', 0):.2f} WHIP",
                        "Home field advantage",
                    ],
                    "edge_percentage": round(era_diff * 0.6, 1),
                })
            elif away_era < home_era - 0.5:
                confidence = "medium" if era_diff >= 1.0 else "low"
                suggestions.append({
                    "type": "moneyline",
                    "recommendation": f"Lean {game_details['away_team_name']} — away SP ERA advantage ({away_era:.2f} vs {home_era:.2f})",
                    "confidence": confidence,
                    "key_factors": [
                        f"{game_details['away_pitcher_name']}: {away_era:.2f} ERA, {away_pitcher_stats.get('whip', 0):.2f} WHIP",
                        f"{game_details['home_pitcher_name']}: {home_era:.2f} ERA, {home_pitcher_stats.get('whip', 0):.2f} WHIP",
                    ],
                    "edge_percentage": round(era_diff * 0.6, 1),
                })
            else:
                suggestions.append({
                    "type": "moneyline",
                    "recommendation": f"Even matchup — starters closely matched ({home_era:.2f} vs {away_era:.2f} ERA)",
                    "confidence": "low",
                    "key_factors": [
                        f"{game_details['home_pitcher_name']}: {home_era:.2f} ERA",
                        f"{game_details['away_pitcher_name']}: {away_era:.2f} ERA",
                    ],
                })

        # Over/Under from avg ERA + team OPS
        avg_era = ((home_era or 4.50) + (away_era or 4.50)) / 2
        home_ops = home_team_stats.get('ops', 0)
        away_ops = away_team_stats.get('ops', 0)

        if avg_era < 3.75:
            ou_rec = f"Lean UNDER — elite pitching matchup (avg ERA {avg_era:.2f})"
            ou_conf = "medium"
        elif avg_era > 4.75 or max(home_ops, away_ops) > 0.780:
            ou_rec = f"Lean OVER — vulnerable pitching and/or strong offense (avg ERA {avg_era:.2f})"
            ou_conf = "low"
        else:
            ou_rec = f"No strong over/under signal (avg ERA {avg_era:.2f}) — monitor line movement"
            ou_conf = "low"

        ou_factors = [f"Avg starter ERA: {avg_era:.2f}"]
        if home_ops:
            ou_factors.append(f"{game_details['home_team_name']} OPS: {home_ops:.3f}")
        if away_ops:
            ou_factors.append(f"{game_details['away_team_name']} OPS: {away_ops:.3f}")

        suggestions.append({
            "type": "over_under",
            "recommendation": ou_rec,
            "confidence": ou_conf,
            "key_factors": ou_factors,
        })

        analysis = {
            "game_id": game_id,
            "analysis_timestamp": datetime.now().isoformat(),
            "data_freshness": datetime.now().isoformat(),
            "home_team_stats": {
                "team": game_details['home_team_name'],
                "batting_avg": home_team_stats.get('batting_avg', 0),
                "obp": home_team_stats.get('obp', 0),
                "slugging": home_team_stats.get('slugging', 0),
                "ops": home_team_stats.get('ops', 0),
                "home_runs": home_team_stats.get('home_runs', 0),
                "runs": home_team_stats.get('runs', 0),
            },
            "away_team_stats": {
                "team": game_details['away_team_name'],
                "batting_avg": away_team_stats.get('batting_avg', 0),
                "obp": away_team_stats.get('obp', 0),
                "slugging": away_team_stats.get('slugging', 0),
                "ops": away_team_stats.get('ops', 0),
                "home_runs": away_team_stats.get('home_runs', 0),
                "runs": away_team_stats.get('runs', 0),
            },
            "home_pitcher_stats": {
                "name": game_details['home_pitcher_name'],
                **home_pitcher_stats,
            },
            "away_pitcher_stats": {
                "name": game_details['away_pitcher_name'],
                **away_pitcher_stats,
            },
            "top_matchups": [],
            "betting_suggestions": suggestions,
        }

        set_cache(cache_key, analysis, hours=6)
        return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing game {game_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refresh-cache")
async def refresh_cache(date: str):
    """
    Manually trigger cache refresh for a specific date
    """
    try:
        cache_key = f"schedule_{date}"
        
        # Clear cache entry
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM cache WHERE key = ?', (cache_key,))
        conn.commit()
        conn.close()
        
        # Refetch data
        games = fetch_mlb_schedule(date)
        
        return {
            "status": "refreshed",
            "date": date,
            "games_count": len(games),
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cache-stats")
async def get_cache_stats():
    """Get cache statistics"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('SELECT COUNT(*) FROM cache')
        cache_count = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM games')
        games_count = c.fetchone()[0]
        
        conn.close()
        
        return {
            "cache_entries": cache_count,
            "cached_games": games_count,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
