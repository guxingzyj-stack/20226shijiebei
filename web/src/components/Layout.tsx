import { NavLink, Outlet } from "react-router-dom";
import { BarChart3, CalendarDays, GitBranch, HelpCircle, History, LogIn, Medal, ReceiptText } from "lucide-react";
import { Disclaimer } from "./Disclaimer";
import { useAuth } from "../auth/AuthContext";

const desktopNavItems = [
  { to: "/matches", label: "赛程", icon: CalendarDays },
  { to: "/bracket", label: "晋级图", icon: GitBranch },
  { to: "/recaps", label: "复盘", icon: History },
  { to: "/leaderboard", label: "排行", icon: Medal },
  { to: "/help", label: "指标", icon: HelpCircle },
  { to: "/bets", label: "我的", icon: ReceiptText },
  { to: "/auth", label: "登录", icon: LogIn },
];

const mobileNavItems = [
  { to: "/matches", label: "赛程", icon: CalendarDays },
  { to: "/bracket", label: "晋级图", icon: GitBranch },
  { to: "/recaps", label: "复盘", icon: History },
  { to: "/leaderboard", label: "排行", icon: Medal },
  { to: "/bets", label: "我的", icon: ReceiptText },
];

export function Layout() {
  const { username, logout } = useAuth();
  return (
    <div className="min-h-screen overflow-x-hidden bg-pitch text-paper">
      <div className="fixed inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,rgba(232,179,60,0.16),transparent_34%),linear-gradient(135deg,#0D3826,#14513A_56%,#0D3826)]" />
      <div className="fixed inset-0 -z-10 field-lines opacity-60" />
      <header className="sticky top-0 z-30 border-b border-white/10 bg-pitch/92 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-3 py-3 sm:px-4">
          <NavLink to="/matches" className="flex min-w-0 items-center gap-2 sm:gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-gold/50 bg-gold/15 sm:h-10 sm:w-10">
              <BarChart3 className="text-gold" size={22} />
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold sm:text-base">世界杯竞彩模拟</div>
              <div className="truncate text-[11px] text-paper/55 sm:text-xs">虚拟资金模拟游戏</div>
            </div>
          </NavLink>
          <nav className="hidden items-center gap-1 md:flex">
            {desktopNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/matches"}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-sm ${isActive ? "bg-gold text-pitch" : "text-paper/70 hover:bg-white/10 hover:text-paper"}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="hidden items-center gap-3 md:flex">
            {username ? <span className="max-w-[140px] truncate text-sm text-paper/70">{username}</span> : <span className="text-sm text-paper/45">未登录</span>}
            {username ? (
              <button type="button" onClick={logout} className="rounded-lg border border-white/15 px-3 py-2 text-sm text-paper/75 hover:bg-white/10">
                退出
              </button>
            ) : null}
          </div>
        </div>
      </header>
      <main className="mx-auto min-h-[calc(100vh-120px)] max-w-7xl px-3 pb-32 pt-4 sm:px-4 sm:pb-28 md:pb-8 md:pt-5">
        <Outlet />
      </main>
      <div className="fixed bottom-0 left-0 right-0 z-40 md:static">
        <nav className="grid grid-cols-5 border-t border-white/10 bg-pitch/95 px-1 py-1 backdrop-blur md:hidden">
          {mobileNavItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/matches"}
                className={({ isActive }) =>
                  `flex min-w-0 flex-col items-center gap-1 rounded-lg px-1 py-2 text-[11px] ${isActive ? "bg-gold text-pitch" : "text-paper/65"}`
                }
              >
                <Icon size={17} />
                <span className="max-w-full truncate whitespace-nowrap">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
        <Disclaimer />
      </div>
    </div>
  );
}
