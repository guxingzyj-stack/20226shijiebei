import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { HelpCircle, LogIn, ReceiptText, Ticket } from "lucide-react";
import { apiGet } from "../api/client";
import type { Bet } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { formatDateTime, formatMoney, playTypeLabel, selectionLabel } from "../utils/format";

export function MyBetsPage() {
  const { token, isAuthenticated, username, logout } = useAuth();
  const [bets, setBets] = useState<Bet[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    apiGet<Bet[]>("/bets/me", token).then(setBets).catch((err) => setError(err instanceof Error ? err.message : "注单加载失败"));
  }, [token]);

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <p className="text-sm font-medium text-gold">我的</p>
        <h1 className="mt-1 text-2xl font-semibold md:text-3xl">{isAuthenticated ? username : "未登录"}</h1>
        <p className="mt-2 text-sm leading-6 text-paper/62">这里集中放置我的虚拟注单、模拟记录、指标说明和登录入口。</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <QuickLink to="/bet" icon={Ticket} title="模拟注单" text="查看当前加入的模拟选项和虚拟投注确认信息。" />
        <QuickLink to="/help" icon={HelpCircle} title="指标说明" text="解释模型、赔率、EV、ROI 和系统健康状态。" />
        {isAuthenticated ? (
          <button
            type="button"
            onClick={logout}
            className="rounded-lg border border-white/10 bg-white/[0.05] p-4 text-left transition hover:border-gold/50 hover:bg-white/[0.075]"
          >
            <div className="flex items-center gap-2 font-semibold">
              <LogIn size={18} className="text-gold" />
              退出登录
            </div>
            <p className="mt-2 text-sm leading-5 text-paper/58">退出当前模拟账号。</p>
          </button>
        ) : (
          <QuickLink to="/auth" icon={LogIn} title="登录 / 注册" text="登录后查看我的模拟记录和注单。" />
        )}
      </div>

      {!isAuthenticated ? (
        <section className="rounded-lg border border-white/10 bg-white/[0.06] p-6">
          <h2 className="text-xl font-semibold">我的模拟注单</h2>
          <p className="mt-3 text-paper/65">登录后查看虚拟下注记录。</p>
          <Link to="/auth" className="mt-5 inline-block rounded-lg bg-gold px-4 py-3 font-semibold text-pitch">
            登录 / 注册
          </Link>
        </section>
      ) : (
        <>
          <div>
            <h2 className="text-xl font-semibold">我的模拟注单</h2>
            <p className="mt-2 text-sm text-paper/60">open / won / lost / void 状态仅用于虚拟资金结算。</p>
          </div>
          {error ? <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm">{error}</div> : null}
          {bets.map((bet) => (
            <article key={bet.id} className="rounded-lg border border-white/10 bg-white/[0.06] p-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="font-semibold">投注单号 #{bet.id}</div>
                  <div className="text-sm text-paper/55">{bet.placed_at ? formatDateTime(bet.placed_at) : "-"} · {parlayLabel(bet.parlay)}</div>
                </div>
                <span className="w-fit rounded-full border border-white/15 px-3 py-1 text-sm text-paper/75">{statusLabel(bet.status)}</span>
              </div>
              <div className="mt-4 space-y-2">
                {bet.legs.map((leg, index) => (
                  <div key={`${bet.id}-${index}`} className="rounded-lg bg-pitch/65 px-3 py-2 text-sm">
                    <div className="font-semibold text-paper">{leg.label || matchLabel(leg)}</div>
                    <div className="mt-1 text-paper/62">
                      玩法：{playTypeLabel(leg.play_type)} · 选择：{selectionLabel(leg.selection)} · 赔率：{moneyOrDash(leg.odds)}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 grid gap-2 text-sm text-paper/70 md:grid-cols-4">
                <div>投注金额：{formatMoney(bet.stake)}</div>
                <div>预计返还：{formatMoney(bet.potential_payout)}</div>
                <div>实际返还：{moneyOrDash(bet.payout)}</div>
                <div>结算时间：{bet.settled_at ? formatDateTime(bet.settled_at) : "未结算"}</div>
              </div>
            </article>
          ))}
          {!bets.length ? <div className="rounded-lg border border-white/10 p-5 text-sm text-paper/60">暂无模拟注单。</div> : null}
        </>
      )}
    </section>
  );
}

function matchLabel(leg: Bet["legs"][number]): string {
  if (leg.home_team && leg.away_team) return `${leg.home_team} vs ${leg.away_team}`;
  return leg.match_id;
}

function parlayLabel(parlay: string): string {
  return parlay === "single" ? "单关" : parlay;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    open: "待结算",
    won: "已中奖",
    lost: "未中奖",
    void: "已退款",
  };
  return labels[status] || status;
}

function moneyOrDash(value: string | number | null | undefined): string {
  return value === null || value === undefined ? "-" : formatMoney(value);
}

function QuickLink({ to, icon: Icon, title, text }: { to: string; icon: typeof ReceiptText; title: string; text: string }) {
  return (
    <Link to={to} className="rounded-lg border border-white/10 bg-white/[0.05] p-4 transition hover:border-gold/50 hover:bg-white/[0.075]">
      <div className="flex items-center gap-2 font-semibold">
        <Icon size={18} className="text-gold" />
        {title}
      </div>
      <p className="mt-2 text-sm leading-5 text-paper/58">{text}</p>
    </Link>
  );
}
