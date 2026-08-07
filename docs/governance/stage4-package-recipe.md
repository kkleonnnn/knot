# Stage 4 送审包生成配方（v3.1-A 可满足化）

> **立于 v0.9.15 Stage 4 终审** —— 守护者 §III-2：
> 「下一片的包 1 过滤 `CHANGELOG.md` + `docs/plans/*`（已有 `knot/static/` 的先例），
> 否则那条子句**永远不可满足**。」
> 本文把它固化成配方，免得每片重新想一遍（而想漏一次就等于没执行 v3.1-A）。

## 为什么必须过滤（不是洁癖）

v3.1-A 要求：**给评审者的输入只有** ① Stage 1 文档 ② 最终 diff ③ 闸门输出；
**不给**实现期的探索过程、执行者自辩、「我试过 A 但不行」这类叙述。

⚠️ **而「最终 diff」里必然含那些叙述** —— `CHANGELOG.md` 与 `docs/plans/*` 正是
**记录「我为什么这么做 / 我错在哪」的地方**。v0.9.15 实测：
整片 diff（已去 `knot/static`）**3114 行**，其中 `CHANGELOG` + `docs/plans` 占 **673 行**（21%）。

⇒ 不过滤，则 v3.1-A 的「不给实现期叙述」这条子句**在本仓结构上不可满足**
（v0.9.15 那片实际就没满足 —— 守护者读包 1 时已经读到了那 673 行里的自辩）。

## 配方

### 包 1（先送）
```bash
BASE=<上一片终点>   # 例：147b21e
TIP=<本片分支终点>  # 例：900e842
OUT=~/Documents/knot-review/<版本>-stage4        # ⚠️ 仓外（免被 git 跟踪 / 触发构建上下文哨兵）

mkdir -p "$OUT/pkg1" "$OUT/pkg2"

# ① 最终 diff —— 三重排除
git diff $BASE..$TIP -- . \
  ':(exclude)knot/static' \
  ':(exclude)CHANGELOG.md' \
  ':(exclude)docs/plans' \
  > "$OUT/pkg1/pkg1-final-diff.patch"

# ② commit 清单（只给标题，不给 body —— body 里同样是实现期叙述）
git log --format='%h %s' $BASE..$TIP > "$OUT/pkg1/pkg1-commits.txt"

# ③ Stage 1 文档：截到 §8 之前（§8 实施记录 / §9 Stage 4 记录属包 2）
# ④ 闸门输出：四闸门 + 前端三件 + 全量那一行的**原文**
```

**三重排除的理由各不相同**：
| 排除 | 理由 |
|---|---|
| `knot/static/` | 机器产物（bundle ~557KB），由 doc-invariant 两条守，**无需人读** |
| `CHANGELOG.md` | **含实现期叙述**（v3.1-A 明禁）—— 且它的内容会在包 2 里以 §9 的形态给到 |
| `docs/plans/*` | 同上；**Stage 1 文档单独给**（截到 §8 之前），不走 diff |

⚠️ **`git log` 只取 `%s`（标题）不取 `%b`（body）** —— 本仓的 commit body 常有
「我犯的错 / 取材实证 / 为什么不那样做」，那正是 v3.1-A 要挡的东西。

### 包 2（守护者交出初步发现**之后**才送）
- Stage 1 文档的 **§8 实施记录 + §9 Stage 4 记录**（含 CHANGELOG 那部分内容的实质）。

## 送之前的三条自检（机械）

```bash
# ① 包 1 不含实施叙述
grep -c '## §8\|## §9' "$OUT/pkg1/"*.md            # 应 0
# ② 包 2 确实含
grep -c '## §8\|### §9' "$OUT/pkg2/"*.md           # 应 >0
# ③ 全包零凭据形状（bcrypt 哈希 / 明文口令行）
grep -rcE '\$2[aby]\$[0-9]{2}\$|admin / [A-Za-z0-9_-]{12,}' "$OUT" | awk -F: '{s+=$2} END {print s+0}'   # 应 0
```

## ⚠️ 诚实边界

这个配方**只挡住「diff 里的叙述」**。它挡不住：
- 评审者自己去看仓库当前状态（那里什么都有）；
- 执行者在对话里主动说漏（v3.1-A 靠的是纪律，不是机制）。

⇒ 它把「结构上不可满足」变成「结构上可满足」，**不等于**「一定被满足」。
