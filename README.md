# worldcup-jingcai

2026 世界杯竞彩预测系统 P0：赔率采集器。当前阶段只包含赔率数据源探测、PostgreSQL 表初始化、轮询采集、赔率变化检测与快照入库。

> 本项目为体育赛事预测研究与虚拟资金模拟游戏，不提供任何真实购彩、代购功能，不构成投注建议。竞彩固定奖金游戏理论返还率约 71%–73%，长期投注期望为负，请理性娱乐。

## Structure

- `crawler/probe.py`: 数据源连通性探测脚本。
- `crawler/main.py`: 常驻采集器入口。
- `crawler/sources/sporttery.py`: 竞彩官网 webapi 适配器。
- `crawler/sources/m500.py`: 500 彩票交易页备用适配器。
- `crawler/db.py`: 建表、运行记录、比赛与赔率快照写入。
- `crawler/schema.sql`: PostgreSQL DDL。

## Local Usage

```bash
cd crawler
cp ../.env.example .env
python -m venv .venv
pip install -r requirements.txt
python probe.py
python main.py
```

`DATABASE_URL` must be provided through environment variables in production.
