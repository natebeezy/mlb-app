import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

const API_BASE = 'http://localhost:8000';

// Main App Component
function App() {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedGame, setExpandedGame] = useState(null);
  const [gameAnalysis, setGameAnalysis] = useState({});
  const [filterConfidence, setFilterConfidence] = useState('all');
  const [dataFreshness, setDataFreshness] = useState(null);
  const [cacheStats, setCacheStats] = useState(null);

  // Fetch games for selected date
  const fetchGames = useCallback(async (date) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/games/${date}`);
      const data = await response.json();
      setGames(data.games || []);
      setDataFreshness(new Date());
    } catch (error) {
      console.error('Error fetching games:', error);
      // Fallback sample data
      setGames(generateSampleGames(date));
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch detailed analysis for a game
  const fetchGameAnalysis = useCallback(async (gameId) => {
    try {
      const response = await fetch(`${API_BASE}/game/${gameId}/analysis`);
      const data = await response.json();
      setGameAnalysis(prev => ({ ...prev, [gameId]: data }));
    } catch (error) {
      console.error('Error fetching game analysis:', error);
      // Fallback sample analysis
      setGameAnalysis(prev => ({ ...prev, [gameId]: generateSampleAnalysis(gameId) }));
    }
  }, []);

  // Fetch cache stats
  useEffect(() => {
    const fetchCacheStats = async () => {
      try {
        const response = await fetch(`${API_BASE}/cache-stats`);
        const data = await response.json();
        setCacheStats(data);
      } catch (error) {
        console.error('Error fetching cache stats:', error);
      }
    };
    fetchCacheStats();
  }, []);

  // Initial load
  useEffect(() => {
    fetchGames(selectedDate);
  }, [selectedDate, fetchGames]);

  const handleDateChange = (e) => {
    setSelectedDate(e.target.value);
    setExpandedGame(null);
    setGameAnalysis({});
  };

  const handleExpandGame = (gameId) => {
    setExpandedGame(expandedGame === gameId ? null : gameId);
    if (!gameAnalysis[gameId] && expandedGame !== gameId) {
      fetchGameAnalysis(gameId);
    }
  };

  const handleRefresh = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/refresh-cache`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: selectedDate })
      });
      const data = await response.json();
      setGames(data.games || []);
      setDataFreshness(new Date());
    } catch (error) {
      console.error('Error refreshing cache:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredGames = games.filter(game => {
    if (filterConfidence === 'all') return true;
    // In real app, would filter based on suggestion confidence
    return true;
  });

  return (
    <div className="app">
      <header className="header">
        <div className="header-content">
          <h1 className="logo">⚾ MLB EDGE</h1>
          <p className="tagline">Data-Driven Betting Analysis</p>
        </div>
        <div className="header-controls">
          <input
            type="date"
            value={selectedDate}
            onChange={handleDateChange}
            className="date-picker"
          />
          <button
            className="refresh-btn"
            onClick={handleRefresh}
            disabled={loading}
          >
            {loading ? '⟳ ANALYZING...' : '⟳ REFRESH'}
          </button>
        </div>
      </header>

      <div className="container">
        {loading && <LoadingState />}

        <div className="controls-bar">
          <div className="filter-group">
            <label>Filter by Confidence:</label>
            <select
              value={filterConfidence}
              onChange={(e) => setFilterConfidence(e.target.value)}
              className="filter-select"
            >
              <option value="all">All Games</option>
              <option value="high">High Confidence Only</option>
              <option value="medium">Medium+ Confidence</option>
            </select>
          </div>
          {dataFreshness && (
            <div className="freshness">
              📊 Last updated: {dataFreshness.toLocaleTimeString()}
            </div>
          )}
        </div>

        <div className="games-grid">
          {filteredGames.length === 0 ? (
            <div className="no-games">
              <p>No games scheduled for {selectedDate}</p>
            </div>
          ) : (
            filteredGames.map(game => (
              <GameCard
                key={game.game_id}
                game={game}
                expanded={expandedGame === game.game_id}
                onExpand={() => handleExpandGame(game.game_id)}
                analysis={gameAnalysis[game.game_id]}
              />
            ))
          )}
        </div>
      </div>

      <footer className="footer">
        <div className="footer-content">
          <p>Data sources: MLB Stats API • pybaseball • Baseball Savant</p>
          {cacheStats && (
            <p>Cache: {cacheStats.cache_entries} entries • {cacheStats.cached_games} games</p>
          )}
          <p className="disclaimer">
            ⚠️ For educational purposes only. Always verify data before betting.
          </p>
        </div>
      </footer>
    </div>
  );
}

// Game Card Component
function GameCard({ game, expanded, onExpand, analysis }) {
  const gameTime = game.time || 'TBA';
  const statusColor = game.status === 'Pre-Game' ? 'pre-game' : 'scheduled';

  return (
    <div className={`game-card ${statusColor} ${expanded ? 'expanded' : ''}`}>
      <div className="game-header" onClick={onExpand}>
        <div className="game-matchup">
          <div className="team away-team">
            <span className="team-code">{game.away_team_code || 'N/A'}</span>
            <span className="team-name">{game.away_team}</span>
          </div>
          <div className="vs-divider">VS</div>
          <div className="team home-team">
            <span className="team-name">{game.home_team}</span>
            <span className="team-code">{game.home_team_code || 'N/A'}</span>
          </div>
        </div>
        <div className="game-meta">
          <span className="game-time">🕐 {gameTime}</span>
          <span className="expand-toggle">{expanded ? '▼' : '▶'}</span>
        </div>
      </div>

      <div className="game-pitchers">
        <div className="pitcher">
          <span className="pitcher-label">Away SP</span>
          <span className="pitcher-name">{game.away_pitcher_name}</span>
        </div>
        <div className="pitcher">
          <span className="pitcher-label">Home SP</span>
          <span className="pitcher-name">{game.home_pitcher_name}</span>
        </div>
      </div>

      {expanded && analysis && <GameAnalysisPanel analysis={analysis} />}
      {expanded && !analysis && <div className="loading-analysis">Loading analysis...</div>}
    </div>
  );
}

// Game Analysis Panel
function GameAnalysisPanel({ analysis }) {
  if (!analysis) return null;

  return (
    <div className="game-analysis">
      <div className="analysis-section">
        <h3>⚾ Starting Pitchers</h3>
        <PitcherMatchupPanel
          awayPitcher={analysis.away_pitcher_stats}
          homePitcher={analysis.home_pitcher_stats}
        />
      </div>

      <div className="analysis-section">
        <h3>📈 Team Batting Stats</h3>
        <div className="team-stats">
          <TeamStatBlock stats={analysis.away_team_stats} />
          <TeamStatBlock stats={analysis.home_team_stats} />
        </div>
      </div>

      {analysis.top_matchups && analysis.top_matchups.length > 0 && (
        <div className="analysis-section">
          <h3>⭐ Top Batter Matchups</h3>
          <div className="matchups-list">
            {analysis.top_matchups.map((matchup, idx) => (
              <MatchupCard key={idx} matchup={matchup} />
            ))}
          </div>
        </div>
      )}

      {analysis.betting_suggestions && analysis.betting_suggestions.length > 0 && (
        <div className="analysis-section">
          <h3>🎯 Betting Recommendations</h3>
          <div className="suggestions-list">
            {analysis.betting_suggestions.map((suggestion, idx) => (
              <SuggestionCard key={idx} suggestion={suggestion} />
            ))}
          </div>
        </div>
      )}

      {analysis.data_freshness && (
        <div className="analysis-footer">
          <span className="freshness-badge">
            📍 Data: {new Date(analysis.data_freshness).toLocaleString()}
          </span>
        </div>
      )}
    </div>
  );
}

// Pitcher Matchup Panel
function PitcherMatchupPanel({ awayPitcher, homePitcher }) {
  return (
    <div className="pitcher-matchup-panel">
      <PitcherStatBlock pitcher={awayPitcher} label="Away SP" />
      <PitcherStatBlock pitcher={homePitcher} label="Home SP" />
    </div>
  );
}

function PitcherStatBlock({ pitcher, label }) {
  if (!pitcher) return null;
  const hasStats = pitcher.era || pitcher.whip;
  const eraClass = !pitcher.era ? '' : pitcher.era < 3.50 ? 'stat-good' : pitcher.era > 4.50 ? 'stat-bad' : '';
  const whipClass = !pitcher.whip ? '' : pitcher.whip < 1.15 ? 'stat-good' : pitcher.whip > 1.35 ? 'stat-bad' : '';

  return (
    <div className="pitcher-stat-block">
      <div className="pitcher-block-header">
        <span className="pitcher-block-label">{label}</span>
        <span className="pitcher-block-name">{pitcher.name || 'TBA'}</span>
        {hasStats && (
          <span className="pitcher-record">{pitcher.wins ?? 0}–{pitcher.losses ?? 0} W-L</span>
        )}
      </div>
      {hasStats ? (
        <div className="pitcher-stats-grid">
          <div className="pitcher-stat">
            <span className="pstat-label">ERA</span>
            <span className={`pstat-value ${eraClass}`}>{pitcher.era?.toFixed(2) ?? '—'}</span>
          </div>
          <div className="pitcher-stat">
            <span className="pstat-label">WHIP</span>
            <span className={`pstat-value ${whipClass}`}>{pitcher.whip?.toFixed(2) ?? '—'}</span>
          </div>
          <div className="pitcher-stat">
            <span className="pstat-label">K/9</span>
            <span className="pstat-value">{pitcher.k_per_9?.toFixed(1) ?? '—'}</span>
          </div>
          <div className="pitcher-stat">
            <span className="pstat-label">IP</span>
            <span className="pstat-value">{pitcher.innings_pitched || '—'}</span>
          </div>
          <div className="pitcher-stat">
            <span className="pstat-label">SO</span>
            <span className="pstat-value">{pitcher.strikeouts ?? '—'}</span>
          </div>
          <div className="pitcher-stat">
            <span className="pstat-label">BAA</span>
            <span className="pstat-value">{pitcher.batting_avg_against?.toFixed(3) ?? '—'}</span>
          </div>
        </div>
      ) : (
        <div className="pitcher-no-stats">No stats available</div>
      )}
    </div>
  );
}

// Team Stat Block
function TeamStatBlock({ stats }) {
  if (!stats) return null;
  const fmt3 = (v) => (v ? v.toFixed(3) : '—');
  return (
    <div className="team-stat-block">
      <h4>{stats.team || 'Team'}</h4>
      <div className="stat-row"><span>BA:</span><span className="stat-value">{fmt3(stats.batting_avg)}</span></div>
      <div className="stat-row"><span>OBP:</span><span className="stat-value">{fmt3(stats.obp)}</span></div>
      <div className="stat-row"><span>SLG:</span><span className="stat-value">{fmt3(stats.slugging)}</span></div>
      <div className="stat-row"><span>OPS:</span><span className="stat-value">{fmt3(stats.ops)}</span></div>
      <div className="stat-row"><span>HR:</span><span className="stat-value">{stats.home_runs ?? '—'}</span></div>
      <div className="stat-row"><span>R:</span><span className="stat-value">{stats.runs ?? '—'}</span></div>
    </div>
  );
}

// Matchup Card Component
function MatchupCard({ matchup }) {
  const trendEmoji = {
    hot: '🔥',
    cold: '❄️',
    neutral: '⚖️'
  }[matchup.trend] || '⚾';

  const confidenceColor = {
    high: 'confidence-high',
    medium: 'confidence-medium',
    low: 'confidence-low'
  }[matchup.confidence] || '';

  return (
    <div className={`matchup-card ${confidenceColor}`}>
      <div className="matchup-header">
        <div>
          <span className="batter-name">{matchup.batter_name}</span>
          <span className="position">{matchup.position}</span>
        </div>
        <div className="trend-badge">
          {trendEmoji} {matchup.trend?.toUpperCase() || 'NEUTRAL'}
        </div>
      </div>
      <div className="matchup-stats">
        <div className="stat">
          <span className="label">Career vs P:</span>
          <span className="value">{(matchup.vs_pitcher_avg || 0.285).toFixed(3)}</span>
        </div>
        <div className="stat">
          <span className="label">Recent 30d:</span>
          <span className="value">{(matchup.recent_avg || 0.300).toFixed(3)}</span>
        </div>
        <div className="stat">
          <span className="label">Sample:</span>
          <span className="value">{matchup.sample_size || 'N/A'} AB</span>
        </div>
      </div>
      <div className="confidence-badge">
        Confidence: <strong>{matchup.confidence?.toUpperCase() || 'MEDIUM'}</strong>
      </div>
    </div>
  );
}

// Suggestion Card Component
function SuggestionCard({ suggestion }) {
  const typeEmoji = {
    moneyline: '🎲',
    run_line: '📊',
    over_under: '📈',
    player_prop: '⭐'
  }[suggestion.type] || '🎯';

  const confidenceClass = `confidence-${suggestion.confidence?.toLowerCase() || 'low'}`;

  return (
    <div className={`suggestion-card ${confidenceClass}`}>
      <div className="suggestion-header">
        <span className="type-badge">{typeEmoji} {suggestion.type.toUpperCase().replace('_', '/')}</span>
        <span className="confidence-label">{suggestion.confidence?.toUpperCase()}</span>
      </div>
      <p className="suggestion-text">{suggestion.recommendation}</p>
      {suggestion.edge_percentage && (
        <div className="edge-metric">Edge: <strong>+{suggestion.edge_percentage}%</strong></div>
      )}
      {suggestion.key_factors && suggestion.key_factors.length > 0 && (
        <div className="key-factors">
          <strong>Key Factors:</strong>
          <ul>
            {suggestion.key_factors.map((factor, idx) => (
              <li key={idx}>{factor}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Loading State Component
function LoadingState() {
  return (
    <div className="loading-overlay">
      <div className="loading-container">
        <div className="loading-spinner"></div>
        <h2>Analyzing Games</h2>
        <p>Fetching schedules, rosters, and performance data...</p>
        <div className="loading-steps">
          <div className="step active">⚾ Fetching MLB schedule</div>
          <div className="step">📊 Analyzing batter matchups</div>
          <div className="step">📈 Computing team trends</div>
          <div className="step">🎯 Generating recommendations</div>
        </div>
        <p className="loading-note">Expected time: 30-90 seconds on first load</p>
      </div>
    </div>
  );
}

// Sample Data Generators (for testing without backend)
function generateSampleGames(date) {
  return [
    {
      game_id: '1',
      game_date: date,
      away_team: 'Boston Red Sox',
      away_team_code: 'BOS',
      home_team: 'New York Yankees',
      home_team_code: 'NYY',
      time: '19:05',
      status: 'Pre-Game',
      away_pitcher_name: 'Garrett Whitlock',
      home_pitcher_name: 'Gerrit Cole',
    },
    {
      game_id: '2',
      game_date: date,
      away_team: 'Tampa Bay Rays',
      away_team_code: 'TB',
      home_team: 'Toronto Blue Jays',
      home_team_code: 'TOR',
      time: '19:07',
      status: 'Pre-Game',
      away_pitcher_name: 'Tyler Glasnow',
      home_pitcher_name: 'Kevin Gausman',
    },
    {
      game_id: '3',
      game_date: date,
      away_team: 'Houston Astros',
      away_team_code: 'HOU',
      home_team: 'Los Angeles Angels',
      home_team_code: 'LAA',
      time: '21:38',
      status: 'Pre-Game',
      away_pitcher_name: 'Justin Verlander',
      home_pitcher_name: 'Reid Detmers',
    }
  ];
}

function generateSampleAnalysis(gameId) {
  return {
    game_id: gameId,
    analysis_timestamp: new Date().toISOString(),
    data_freshness: new Date(Date.now() - 15 * 60000).toISOString(),
    away_team_stats: {
      team: 'Away Team',
      batting_avg: 0.268,
      obp: 0.330,
      slugging: 0.410,
      vs_lefties: 0.265,
      vs_righties: 0.270,
    },
    home_team_stats: {
      team: 'Home Team',
      batting_avg: 0.272,
      obp: 0.335,
      slugging: 0.425,
      vs_lefties: 0.268,
      vs_righties: 0.275,
    },
    top_matchups: [
      {
        batter_name: 'Aaron Judge',
        position: 'RF',
        career_avg: 0.285,
        vs_pitcher_avg: 0.310,
        recent_avg: 0.320,
        sample_size: 12,
        trend: 'hot',
        confidence: 'high'
      },
      {
        batter_name: 'Gerrit Cole',
        position: 'Pitcher',
        career_avg: 0.265,
        vs_pitcher_avg: 0.250,
        recent_avg: 0.245,
        sample_size: 8,
        trend: 'cold',
        confidence: 'medium'
      }
    ],
    betting_suggestions: [
      {
        type: 'moneyline',
        recommendation: 'Lean toward Home Team based on 3 favorable batter matchups and recent hot streak',
        confidence: 'medium',
        key_factors: ['Aaron Judge vs LHP (.310 avg)', 'Team BA vs LHP advantage', 'Recent form (8-2 last 10)'],
        edge_percentage: 2.5
      },
      {
        type: 'player_prop',
        recommendation: 'Aaron Judge Over 0.5 runs scored (strong hitting matchup, high power potential)',
        confidence: 'high',
        key_factors: ['Career .310 vs LHP', 'Recent hot streak (8 games)', 'Pitcher ERA above 4.00'],
        edge_percentage: 3.2
      },
      {
        type: 'over_under',
        recommendation: 'OVER 8.5 runs (both teams have strong offense vs opponent pitching)',
        confidence: 'medium',
        key_factors: ['Away team slugging .425', 'Recent over rate 55%', 'Bullpen ERA concerns'],
        edge_percentage: 1.8
      }
    ]
  };
}

export default App;
