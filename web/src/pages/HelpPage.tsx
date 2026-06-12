import { ShieldCheck } from "lucide-react";
import { glossaryItems } from "../recaps/glossary";

const categories = ["模型", "赔率", "EV", "结算", "健康", "安全"] as const;

export function HelpPage() {
  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-white/10 bg-white/[0.06] p-5 shadow-soft">
        <p className="text-sm font-medium text-gold">新手引导</p>
        <h1 className="mt-1 text-2xl font-semibold md:text-3xl">世界杯竞猜模拟系统指标说明</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/68">
          这里解释页面里的模型、赔率、EV、结算和健康状态。所有内容仅用于虚拟资金模拟与研究，不提供真实购彩服务。
        </p>
      </section>

      <section className="rounded-lg border border-gold/25 bg-gold/10 p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 shrink-0 text-gold" size={18} />
          <p className="text-sm leading-6 text-paper/72">
            EV 与候选信号都是研究观察，不是投注建议。样本少时，命中率和 ROI 都不能代表长期结果。
          </p>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {categories.map((category) => (
          <section key={category} className="rounded-lg border border-white/10 bg-white/[0.055] p-4">
            <h2 className="text-lg font-semibold text-gold">{category}</h2>
            <div className="mt-3 space-y-3">
              {glossaryItems
                .filter((item) => item.category === category)
                .map((item) => (
                  <div key={item.term} className="rounded-lg border border-white/10 bg-pitch/55 p-3">
                    <div className="font-semibold">{item.term}</div>
                    <p className="mt-1 text-sm leading-6 text-paper/65">{item.short}</p>
                  </div>
                ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
