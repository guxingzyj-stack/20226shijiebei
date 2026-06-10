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
  created_at?: string;
};

export type Match = {
  match_id: string;
  match_num?: string;
  league?: string;
  home_team: string;
  away_team: string;
  kickoff_at: string;
  status: string;
  ht_home?: number | null;
  ht_away?: number | null;
  latest_odds?: OddsSnapshot[];
  latest_prediction?: Prediction | null;
  score_matrix?: number[][] | null;
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
  id?: number;
  username: string;
  balance: string | number;
  roi?: string | number;
  settled_bets?: number;
};
