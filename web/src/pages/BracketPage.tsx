import { Link } from "react-router-dom";
import { ChevronDown, GitBranch, ShieldCheck, Trophy } from "lucide-react";

const rounds = [
  { key: "champion", title: "冠军预测", description: "等待淘汰赛路径生成后展示冠军概率或冠军结果。" },
  { key: "final", title: "决赛", description: "暂无真实决赛对阵。" },
  { key: "semifinal", title: "半决赛", description: "暂无真实半决赛对阵。" },
  { key: "quarterfinal", title: "四分之一决赛", description: "暂无真实四分之一决赛对阵。" },
  { key: "round16", title: "十六强", description: "小组赛完成后根据真实晋级结果生成。" },
];

const desktopColumns = [
  ["16强", "8强", "4强", "半决赛"],
  ["决赛", "冠军预测 / 冠军结果"],
  ["半决赛", "4强", "8强", "16强"],
];

export function BracketPage() {
  const dataStatus = "not_generated";

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-medium text-gold">晋级图</p>
            <h1 className="mt-1 text-2xl font-semibold md:text-3xl">预测晋级图</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/68">
              根据赛程、赛果和模型预测生成的世界杯晋级路径。对阵未生成时不会编造。
            </p>
          </div>
          <div className="rounded-lg border border-gold/25 bg-gold/10 px-4 py-3 text-sm text-gold">
            data_status: {dataStatus}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-gold/25 bg-gold/10 p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-gold/35 bg-pitch/70">
              <GitBranch className="text-gold" size={22} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-paper">淘汰赛对阵暂未生成。</h2>
              <p className="mt-2 text-sm leading-6 text-paper/68">
                小组赛完成后，系统会根据真实赛果和模型预测生成晋级图。当前页面只展示骨架和空状态，不展示假对阵。
              </p>
            </div>
          </div>
          <Link to="/matches" className="inline-flex shrink-0 items-center justify-center rounded-lg bg-gold px-4 py-3 text-sm font-semibold text-pitch">
            查看赛程
          </Link>
        </div>
      </section>

      <section className="hidden rounded-lg border border-white/10 bg-white/[0.045] p-5 lg:block">
        <div className="mb-4 flex items-center gap-2 text-lg font-semibold">
          <Trophy size={18} className="text-gold" />
          桌面晋级图骨架
        </div>
        <div className="grid gap-4 lg:grid-cols-[1fr_0.8fr_1fr]">
          {desktopColumns.map((column, columnIndex) => (
            <div key={columnIndex} className="space-y-3">
              {column.map((title) => (
                <EmptyBracketNode key={`${columnIndex}-${title}`} title={title} />
              ))}
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs leading-5 text-paper/45">
          这里预留真实晋级路径的展示结构。没有真实淘汰赛对阵时，不显示球队名、概率或晋级路线。
        </p>
      </section>

      <section className="space-y-3 lg:hidden">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <Trophy size={18} className="text-gold" />
          移动端分轮次查看
        </div>
        {rounds.map((round, index) => (
          <details key={round.key} open={index === 0} className="rounded-lg border border-white/10 bg-white/[0.055] p-4">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-semibold">
              <span>{round.title}</span>
              <ChevronDown size={18} className="text-paper/45" />
            </summary>
            <div className="mt-3 rounded-lg border border-dashed border-white/15 bg-pitch/50 p-4 text-sm leading-6 text-paper/62">
              {round.description}
            </div>
          </details>
        ))}
      </section>

      <section className="rounded-lg border border-white/10 bg-white/[0.05] p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-gold" />
          <p className="text-sm leading-6 text-paper/66">
            真实性规则：有真实晋级数据就显示；没有数据就明确提示数据不足。页面不会硬编码球队晋级、冠军预测或淘汰赛路径。
          </p>
        </div>
      </section>
    </div>
  );
}

function EmptyBracketNode({ title }: { title: string }) {
  return (
    <div className="rounded-lg border border-dashed border-white/15 bg-pitch/52 p-4">
      <div className="text-sm font-semibold text-paper/75">{title}</div>
      <div className="mt-2 text-xs text-paper/45">数据不足，暂未生成</div>
    </div>
  );
}
