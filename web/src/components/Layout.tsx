import { NavLink, Outlet } from "react-router-dom";
import { BarChart3, CalendarDays, History, LogIn, Medal, ReceiptText, Ticket } from "lucide-react";
import { Disclaimer } from "./Disclaimer";
import { useAuth } from "../auth/AuthContext";

const navItems = [
  { to: "/", label: "赛程", icon: CalendarDays },
  { to: "/bet", label: "注单", icon: Ticket },
  { to: "/bets", label: "我的", icon: ReceiptText },
  { to: "/leaderboard", label: "排行", icon: Medal },
  { to: "/recap", label: "复盘", icon: History },
  { to: "/auth", label: "登录", icon: LogIn },
];

export function Layout() {
  const { username, logout } = useAuth();
  return (
    <div className="min-h-screen bg-pitch text-paper">
      <div className="fixed inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,rgba(232,179,60,0.16),transparent_34%),linear-gradient(135deg,#0D3826,#14513A_56%,#0D3826)]" />
      <div className="fixed inset-0 -z-10 field-lines opacity-60" />
      <header className="sticky top-0 z-30 border-b border-white/10 bg-pitch/92 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <NavLink to="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-gold/50 bg-gold/15">
              <BarChart3 className="text-gold" size={22} />
            </div>
            <div>
              <div className="text-base font-semibold">世界杯竞彩模拟</div>
              <div className="text-xs text-paper/55">虚拟资金模拟游戏</div>
            </div>
          </NavLink>
          <nav className="hidden items-center gap-1 md:flex">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-sm ${isActive ? "bg-gold text-pitch" : "text-paper/70 hover:bg-white/10 hover:text-paper"}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="hidden items-center gap-3 md:flex">
            {username ? <span className="text-sm text-paper/70">{username}</span> : <span className="text-sm text-paper/45">未登录</span>}
            {username ? (
              <button type="button" onClick={logout} className="rounded-lg border border-white/15 px-3 py-2 text-sm text-paper/75 hover:bg-white/10">
                退出
              </button>
            ) : null}
          </div>
        </div>
      </header>
      <main className="mx-auto min-h-[calc(100vh-120px)] max-w-7xl px-4 pb-28 pt-5 md:pb-8">
        <Outlet />
      </main>
      <div className="fixed bottom-0 left-0 right-0 z-40 md:static">
        <nav className="grid grid-cols-6 border-t border-white/10 bg-pitch/95 px-1 py-1 backdrop-blur md:hidden">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex flex-col items-center gap-1 rounded-lg px-2 py-2 text-[11px] ${isActive ? "bg-gold text-pitch" : "text-paper/65"}`
                }
              >
                <Icon size={18} />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <Disclaimer />
      </div>
    </div>
  );
}
