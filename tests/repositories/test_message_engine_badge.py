"""tests/repositories/test_message_engine_badge.py — v0.7.4 C3 F2 engine 徽标派生（R-SL-46）。

get_messages enrich engine（守护者 Stage 3 near-miss 修正 + 执行者 is_corrected=0 精化）：
- 原始行（is_corrected=0）compile_error_reason 空 = semantic；
- 原始行非空（near-miss 回退 LLM）或无侧表行 = llm；
- 修正行（is_corrected=1）**不参与**派生（反映原始查询引擎，非事后修正）。
单查询防 N+1（同 conn）。
"""
from knot.repositories import conversation_repo, message_repo, semantic_audit_repo


def _msg(cid, q="q"):
    return message_repo.save_message(cid, q, "SELECT 1", "", "high", [], "", 0.0, 0, 0, 0)


def test_engine_badge_derivation(tmp_db_path):
    cid = conversation_repo.create_conversation(1)
    m_sem = _msg(cid, "semantic")            # 原始命中
    m_near = _msg(cid, "near-miss")          # 原始 near-miss（回退 LLM）
    m_llm = _msg(cid, "pure-llm")            # 无侧表行
    m_corr = _msg(cid, "only-correction")    # 仅修正行（无原始）

    semantic_audit_repo.create_audit(message_id=m_sem, catalog_id=1, logicform_json='{"metrics":["gmv"]}')
    semantic_audit_repo.create_audit(message_id=m_near, catalog_id=1,
                                     logicform_json='{"metrics":["gmv"]}', compile_error_reason="维度归属歧义→回退")
    semantic_audit_repo.create_audit(message_id=m_corr, catalog_id=1,
                                     logicform_json='{"metrics":["gmv"]}', is_corrected=1, parent_message_id=m_corr)

    by_id = {m["id"]: m for m in message_repo.get_messages(cid)}
    assert by_id[m_sem]["engine"] == "semantic"      # 原始命中 → semantic
    assert by_id[m_near]["engine"] == "llm"          # near-miss 回退（R-SL-46：不误标 semantic）
    assert by_id[m_llm]["engine"] == "llm"           # 无侧表行 → llm
    assert by_id[m_corr]["engine"] == "llm"          # 仅修正行 is_corrected=1 不参与 → 原始引擎 llm


def test_engine_badge_with_viewer_feedback_path(tmp_db_path):
    """viewer_user_id 分支（LEFT JOIN feedback）同样 enrich engine（两分支一致）。"""
    cid = conversation_repo.create_conversation(1)
    mid = _msg(cid, "semantic")
    semantic_audit_repo.create_audit(message_id=mid, catalog_id=1, logicform_json='{"metrics":["gmv"]}')
    msgs = message_repo.get_messages(cid, viewer_user_id=1)
    assert msgs[0]["engine"] == "semantic"
