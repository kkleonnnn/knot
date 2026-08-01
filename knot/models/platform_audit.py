"""platform_audit —— 平台侧审计动作的 Literal 值域（v0.9.8）。

与租户侧 `models/audit.AuditAction` **分开**是刻意的：平台动作的对象是**租户本身**
（建 / 停 / 改元数据），而租户侧动作的对象是租户**内**的资源（用户 / 数据源 / 指标 …）。
混在一个 Literal 里会让两侧的前缀守护互相干扰。

⭐ **纪律（v0.9.8 D2 · 守护者 M1）：只声明「本片有生产者」的动作。**
`tests/test_platform_audit.py` 的前缀守护断的是**精确集合相等** + 每条 ≥1 emit
（照 `test_metric_invariant_guards` 先例）⇒ 它**同时封住两个方向**：
- 「声明了但从不 emit」（= 死声明，v0.9.5 E4「零消费者 = 死码」的同族）；
- 「emit 了但没声明」（= 裸字符串绕过 Literal）。

⇒ **P2 加 `platform.tenant_suspend` / `platform.tenant_delete` 时会打红那条守护**，
逼「Literal + emit + 守护」三者**同片**落地。这正是我们想要的强制，不是麻烦。
"""
from __future__ import annotations

from typing import Literal

PlatformAuditAction = Literal[
    # 生产者：`tenant_repo.seed_default_tenant`（首启建 tenant#1）
    "platform.tenant_create",
    # 生产者：`tenant_repo.update_tenant`（改 status / db_dir / allowed_http_hosts / name 的**单一写口**）
    # 粒度跟着**代码 choke point** 走（一个写口 = 一条 Literal），变更的**字段**放 detail
    # —— 分成 `db_dir_change` / `allowlist_change` 会让「将来加第三个可变字段」又变成一次 Literal + 守护改动。
    "platform.tenant_update",
]
