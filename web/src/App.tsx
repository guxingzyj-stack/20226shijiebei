import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AuthPage } from "./pages/AuthPage";
import { BetPage } from "./pages/BetPage";
import { BracketPage } from "./pages/BracketPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { HelpPage } from "./pages/HelpPage";
import { MatchDetailPage } from "./pages/MatchDetailPage";
import { MatchesPage } from "./pages/MatchesPage";
import { MyBetsPage } from "./pages/MyBetsPage";
import { RecapPage } from "./pages/RecapPage";
import { RecapDailyPage } from "./pages/RecapDailyPage";
import { RecapDetailPage } from "./pages/RecapDetailPage";
import { RecapEvPage } from "./pages/RecapEvPage";
import { RecapModelPage } from "./pages/RecapModelPage";
import { RecapsPage } from "./pages/RecapsPage";
import { ScriptPage } from "./pages/ScriptPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<MatchesPage />} />
        <Route path="/matches" element={<MatchesPage />} />
        <Route path="/matches/:matchId" element={<MatchDetailPage />} />
        <Route path="/bracket" element={<BracketPage />} />
        <Route path="/bet" element={<BetPage />} />
        <Route path="/bets" element={<MyBetsPage />} />
        <Route path="/leaderboard" element={<LeaderboardPage />} />
        <Route path="/help" element={<HelpPage />} />
        <Route path="/script" element={<ScriptPage />} />
        <Route path="/recap" element={<RecapPage />} />
        <Route path="/recaps" element={<RecapsPage />} />
        <Route path="/recaps/model" element={<RecapModelPage />} />
        <Route path="/recaps/ev" element={<RecapEvPage />} />
        <Route path="/recaps/daily" element={<RecapDailyPage />} />
        <Route path="/recaps/:matchId" element={<RecapDetailPage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
