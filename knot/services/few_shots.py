"""knot/services/few_shots.py — v0.5.2 起从 llm_client.py 抽出。

源行号区间（v0.5.1 final 状态 llm_client.py 574 行）：
- L37-73   `_load_few_shots`（DB 优先，回退 .yaml / .example.yaml — v0.2.4 隐私分层）
- L76-83   `classify_question_type`
- L86-127  `get_few_shot_examples`

R-106 单向依赖：本模块仅依赖 stdlib + delayed knot.repositories.few_shot_repo；
严禁反向 import knot.services.llm_client / 其他兄弟。
R-107 Private 前缀保留：`_load_few_shots` 仍为私有；外部已 public 的 classify_question_type
和 get_few_shot_examples 保持 public（llm_client.py re-export 给测试 / 业务用）。
"""
import json
import os


def _load_few_shots() -> dict:
    """优先从 DB 读取（admin 维护）；DB 为空时回退本地 few_shots.yaml；
    再缺失时回退仓库自带的 few_shots.example.yaml（v0.2.4 隐私分层）。"""
    yaml_data = {"examples": [], "type_keywords": {}}
    here = os.path.dirname(__file__)
    for fname in ("few_shots.yaml", "few_shots.example.yaml"):
        yaml_path = os.path.join(here, fname)
        if os.path.exists(yaml_path):
            try:
                import yaml
                with open(yaml_path, encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f) or yaml_data
                break
            except Exception:
                pass

    try:
        from knot.repositories.few_shot_repo import list_few_shots
        rows = list_few_shots(only_active=True)
        if rows:
            return {
                "examples": [
                    {
                        "id": r["id"],
                        "question": r["question"],
                        "sql": r["sql"],
                        "type": r.get("type") or "aggregation",
                        "explanation": "",
                        "confidence": "medium",
                    }
                    for r in rows
                ],
                "type_keywords": yaml_data.get("type_keywords", {}),
            }
    except Exception:
        pass
    return yaml_data


def classify_question_type(question: str, type_keywords: dict) -> str:
    q_lower = question.lower()
    scores: dict = {}
    for qtype, keywords in type_keywords.items():
        hit = sum(1 for kw in keywords if kw.lower() in q_lower)
        if hit > 0:
            scores[qtype] = hit
    return max(scores, key=scores.get) if scores else "aggregation"


def get_few_shot_examples(question: str, max_examples: int = 4) -> str:
    data = _load_few_shots()
    examples = data.get("examples", [])
    type_keywords = data.get("type_keywords", {})

    if not examples:
        return ""

    question_type = classify_question_type(question, type_keywords)
    typed: dict = {}
    for ex in examples:
        t = ex.get("type", "aggregation")
        typed.setdefault(t, []).append(ex)

    selected = []
    primary = typed.get(question_type, [])
    selected.extend(primary[: max(1, max_examples // 2)])

    remaining = max_examples - len(selected)
    other_types = [t for t in typed if t != question_type]
    for t in other_types:
        if remaining <= 0:
            break
        for ex in typed[t][:1]:
            if remaining <= 0:
                break
            selected.append(ex)
            remaining -= 1

    lines = []
    for ex in selected:
        lines.append(f"问题: {ex['question']}")
        sql_str = ex["sql"].replace("\n", " ")
        out = json.dumps(
            {"sql": sql_str, "explanation": ex.get("explanation", ""),
             "confidence": ex.get("confidence", "medium"), "error": ""},
            ensure_ascii=False,
        )
        lines.append(f"输出: {out}")
        lines.append("")

    return "\n".join(lines).strip()
