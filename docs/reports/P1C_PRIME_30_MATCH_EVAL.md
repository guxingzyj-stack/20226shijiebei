# P1-C′ 30场样本权重定案评估报告

> 状态：待生产只读执行生成。
>
> 本机当前没有 `DATABASE_URL`，因此此文件不填入伪造指标。请在 `wc-p2-api`
> 容器内执行以下命令，用真实生产 30 场样本覆盖生成本报告：
>
> ```bash
> PYTHONPATH=. python -m api.p1c_prime_eval --read-only
> ```

## 1. 样本概况
- usable_finished_matches: 待生产执行
- included_matches: 待生产执行
- excluded_matches: 待生产执行
- finished_missing_result: 待生产执行
- non_finished_with_result: 待生产执行

## 2. 当前生产权重
- w_dc: 0.3
- w_market: 0.7
- 注意：本报告生成过程不修改生产权重。

## 3. 评估指标总表
生产执行后生成：

| 方案 | Brier | RPS | LogLoss | Top1 Accuracy | 备注 |
| --- | ---: | ---: | ---: | ---: | --- |

## 4. 候选权重表现
候选权重：

- 0.1 / 0.9
- 0.2 / 0.8
- 0.25 / 0.75
- 0.3 / 0.7
- 0.35 / 0.65
- 0.4 / 0.6
- 0.5 / 0.5

所有候选权重只在内存中评估，不写入 `model_versions`、`predictions` 或任何生产表。

## 5. 市场 vs DC vs 融合
生产执行后生成 market-only、dc-only、current fusion 与候选 fusion 的对照。

## 6. 分层表现
生产执行后生成 favorite / balanced / underdog 分层表现。

## 7. 校准观察
生产执行后按最大预测置信度分档：

- 0.30-0.40
- 0.40-0.50
- 0.50-0.60
- 0.60-0.70
- 0.70+

样本少的分档必须标注“不稳定，仅参考”。

## 8. 风险与限制
- 样本只有约 30 场，仍不足以证明长期优势。
- 小组赛阶段分布有限，不应为短期命中率过拟合。
- 不应据此开放真实投注。

## 9. 建议
生产只读执行后给出 A/B/C：

- A. 保持 0.3 / 0.7
- B. 调整为候选权重，但必须人工确认
- C. 样本仍不足，暂不定案

## 10. 后续动作
- 建议在 45/60 场后二次评估。
- BETTING_ENABLED 继续保持 false，除非投注开放闸门另行通过。
