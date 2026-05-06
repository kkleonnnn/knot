"""bi_agent.services.knot — KNOT 核心数据分析业务（3-Agent 调度层）

knot/ 是产品的核心资产；与 services/ 平铺的 auth_service / rag_service / catalog
等通用支撑业务区分开。Go 重写时本目录映射为 internal/service/knot/。

子模块：
  - catalog       : 业务目录加载/编辑（DB → ohx_catalog → ohx_catalog.example）
  - orchestrator  : 3-Agent Pipeline 编排（Clarifier / SQL Planner / Presenter）
  - sql_planner   : SQL Agent ReAct 推理链
  # FIXME-v0.3.1.next: 后续把 clarifier / presenter 从 orchestrator 中拆出独立文件
"""
