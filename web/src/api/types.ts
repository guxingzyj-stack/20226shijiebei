export type OddsMap = Record<string, number>;

export type OddsSnapshot = {
  id: number;
  match_id: string;
  play_type: string;
  goal_line: string | number | null;
  odds: OddsMap;
  source: string;
  fetched_at: string;
};

export type Prediction = {
  id: number;
  match_id: string;
  p_home: string | number;
  p_draw: string | number;
  p_away: string | number;
  score_matrix: number[][];
  lambda_home?: string | number;
  lambda_away?: string | number;
  created_at?: string;
};

export type EvSignal = {
  match_id: string;
  play_type: string;
  selection: string;
  model_prob: string | number;
  odds: string | number;
  ev: string | number;
  snapshot_id?: number | null;
  model_version?: number | null;
  created_at?: string;
  research_only?: boolean;
  reason?: string | null;
};

export type Match = {
  match_id: string;
  match_num?: string;
  league?: string;
  home_team: string;
  away_team: string;
  kickoff_at: string;
  status: string;
  result_home?: number | null;
  result_away?: number | null;
  ht_home?: number | null;
  ht_away?: number | null;
  latest_odds?: OddsSnapshot[];
  latest_prediction?: Prediction | null;
  verdict?: string;
  verdict_type?: string;
  banter?: string;
  banter_type?: string;
  vig?: {
    had?: {
      margin: number;
      vig: number;
    } | null;
  };
  market_implied_prob?: {
    had?: {
      home: number;
      draw: number;
      away: number;
    } | null;
  };
  prediction_status?: {
    available: boolean;
    reason: string | null;
    message: string | null;
  };
  ev_signals?: EvSignal[];
};

export type Suggestion = {
  match_id: string;
  play_type: string | null;
  selection: string | null;
  model_prob: number | null;
  odds: number | null;
  ev: number | null;
  suggested_stake: string | number;
  reason?: string | null;
};

export type TeamFormItem = {
  date: string;
  opponent: string;
  score: string;
  home_away: "home" | "away" | string;
  outcome: "W" | "D" | "L" | string;
  tournament?: string | null;
};

export type TeamFormResponse = {
  match_id: string;
  data_status: "ok" | "insufficient_data" | string;
  source?: string;
  home_team: string;
  away_team: string;
  home_form: TeamFormItem[];
  away_form: TeamFormItem[];
};

export type PredictionHistoryPoint = {
  created_at: string;
  model_version?: number | string | null;
  model_version_name?: string | null;
  p_home: string | number;
  p_draw: string | number;
  p_away: string | number;
};

export type PredictionHistoryResponse = {
  match_id: string;
  data_status: "ok" | "insufficient_data" | string;
  points: PredictionHistoryPoint[];
};

export type HealthStatus = {
  ok: boolean;
  scheduler_stale?: boolean;
  betting_open_gate_status?: string;
  recommend_open_betting?: boolean;
  betting_open_blockers?: string[];
  betting_open_warnings?: string[];
};

export type BracketTeam = {
  name?: string;
  team?: string;
  flag?: string;
  flag_url?: string;
  flag_emoji?: string;
  country_code?: string;
  iso2?: string;
  seed?: string | number | null;
};

export type BracketMatch = {
  id?: string | number;
  match_id?: string;
  round?: string;
  slot?: string | number;
  home_team?: string | BracketTeam | null;
  away_team?: string | BracketTeam | null;
  home_flag?: string | null;
  away_flag?: string | null;
  winner_team?: string | BracketTeam | null;
  winner_flag?: string | null;
  model_pick?: string | BracketTeam | null;
  home_prob?: string | number | null;
  away_prob?: string | number | null;
  score?: string | null;
  status?: string | null;
};

export type BracketRound = {
  key?: string;
  round?: string;
  title?: string;
  matches?: BracketMatch[];
};

export type BracketResponse = {
  data_status?: "ok" | "not_generated" | "insufficient_data" | string;
  message?: string;
  rounds?: BracketRound[];
  champion?: string | BracketTeam | null;
};

export type BetLeg = {
  match_id: string;
  play_type: string;
  selection: string;
  odds?: string | number;
  snapshot_id?: number;
  goal_line?: string | number | null;
  label?: string;
};

export type Bet = {
  id: number;
  legs: BetLeg[];
  parlay: string;
  stake: string | number;
  potential_payout: string | number;
  payout?: string | number | null;
  status: string;
  balance?: string | number | null;
  placed_at?: string;
  settled_at?: string | null;
};

export type LeaderboardEntry = {
  username: string;
  balance: string | number;
  roi?: string | number;
  settled_bets?: number;
};

export type ScriptOverview = {
  total_predictions: number;
  compared_count: number;
  pending_count: number;
  not_yet_count: number;
  direction_hits: number;
  exact_hits: number;
  direction_accuracy: number | null;
  exact_accuracy: number | null;
};

export type ScriptModelProb = {
  home: number;
  draw: number;
  away: number;
};

export type ScriptMatchItem = {
  group: string;
  stage: string;
  home_team: string;
  away_team: string;
  script_score: string;
  narrative?: string | null;
  status: "COMPARED" | "PENDING" | "NOT_YET" | string;
  real_score?: string | null;
  direction_hit?: boolean | null;
  exact_hit?: boolean | null;
  model_prob?: ScriptModelProb | null;
  comment: string;
  match_id?: string | null;
  match_num?: string | null;
  kickoff_at?: string | null;
  match_status?: string | null;
};

export type ScriptMatchesResponse = {
  overview: ScriptOverview;
  matches: ScriptMatchItem[];
};

export type RecapStatus = {
  status: string;
  message?: string;
  finished_matches?: number;
  buckets?: unknown[];
  points?: unknown[];
  rows?: unknown[];
};

export type RecapRecentItem = {
  match_id: string;
  match_num?: string;
  home_team: string;
  away_team: string;
  scoreline: string;
  prediction_correct: boolean | null;
  title: string;
};

export type RecapRecentResponse = {
  items: RecapRecentItem[];
  count: number;
};

export type MatchRecap = {
  match_id: string;
  match_num?: string;
  home_team: string;
  away_team: string;
  kickoff_at: string;
  status: string;
  result: {
    home: number;
    away: number;
    winner: string;
    scoreline: string;
    had_selection: string;
  };
  data_quality: {
    has_result: boolean;
    has_had_odds: boolean;
    has_prediction: boolean;
    has_ev_signal: boolean;
    has_settlement: boolean;
    warnings: string[];
  };
  market: {
    had_open: OddsMap;
    had_close: OddsMap;
    close_implied_probabilities: Record<string, number>;
    favorite: string | null;
    market_result: string | null;
  };
  model: {
    model_version: number | null;
    created_at: string | null;
    probs: Record<string, number>;
    predicted_outcome: string | null;
    confidence: number | null;
    prediction_correct: boolean | null;
    message?: string;
  };
  ev: {
    signals: Array<EvSignal & {
      hit?: boolean | null;
      recommendation_label?: string;
      suggestion_eligible?: boolean;
    }>;
    total_ev_signals: number;
    high_ev_count: number;
    research_only_count: number;
    suggestion_eligible_count: number;
    hit_count: number;
    miss_count: number;
  };
  settlement: {
    settled_bets: number;
    won_bets: number;
    lost_bets: number;
    void_bets: number;
    open_bets: number;
    settlement_status: string;
    cumulative_vig?: CumulativeVigSummary;
  };
  summary: {
    title: string;
    bullets: string[];
  };
};

export type MatchRecapResponse = {
  available: boolean;
  reason?: string;
  recap?: MatchRecap;
};

export type RecapSummary = {
  finished_matches: number;
  recap_available_matches: number;
  model_correct_count: number;
  model_wrong_count: number;
  model_missing_count: number;
  ev_signal_count: number;
  settled_bets: number;
  cumulative_vig?: CumulativeVigSummary;
};

export type CumulativeVigSummary = {
  bet_count: number;
  total_virtual_stake: number;
  cumulative_vig: number;
  cumulative_vig_points: number;
};
