import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AuthPage } from "./pages/AuthPage";
import { BetPage } from "./pages/BetPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { MatchDetailPage } from "./pages/MatchDetailPage";
import { MatchesPage } from "./pages/MatchesPage";
import { MyBetsPage } from "./pages/MyBetsPage";
import { RecapPage } from "./pages/RecapPage";
import { RecapDetailPage } from "./pages/RecapDetailPage";
import { RecapsPage } from "./pages/RecapsPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<MatchesPage />} />
        <Route path="/matches/:matchId" element={<MatchDetailPage />} />
        <Route path="/bet" element={<BetPage />} />
        <Route path="/bets" element={<MyBetsPage />} />
        <Route path="/leaderboard" element={<LeaderboardPage />} />
        <Route path="/recap" element={<RecapPage />} />
        <Route path="/recaps" element={<RecapsPage />} />
        <Route path="/recaps/:matchId" element={<RecapDetailPage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
