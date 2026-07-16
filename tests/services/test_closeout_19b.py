"""v0.8.20 19b — F2（use_agent 成功公式源头修 + fallback 残留）+ F7（default-admin 初始口令）单测。"""
import os
import tempfile

import bcrypt

from knot.services.agents import sql_planner


def test_F2_fallback_reexecute_failure_marks_not_success(monkeypatch):
    """守护者 must-fix #2：末步走 fallback re-execute 失败 + max_steps 耗尽 → success=False（非旧恒真 True）。"""
    calls = {"n": 0}

    def fake_execute(engine, sql):
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"x": 1}], ""            # _run_tool 首次执行成功 → observation "查询成功"
        return [], "Unknown column 'boom'"   # fallback 重执行失败（:187）

    monkeypatch.setattr(sql_planner.db_connector, "execute_query", fake_execute)
    monkeypatch.setattr(
        sql_planner, "_call_llm",
        lambda *a, **k: ("Thought: t\nAction: execute_sql\nAction Input: SELECT boom FROM t", 10, 5),
    )
    res = sql_planner.run_sql_agent("q", "## t\n- boom INT", engine=object(), max_steps=1)
    assert res.success is False, "fallback 重执行失败应 success=False（守护者 must-fix #2 闭合残留）"
    assert res.error, "final_error 应非空（承载 fallback 的 exec_err）"


def test_F2_clean_success_still_true(monkeypatch):
    """无回归：__FINAL__ 干净执行 → success=True（final_error 清空，第二子句删除不误杀）。"""
    monkeypatch.setattr(sql_planner.db_connector, "execute_query", lambda e, s: ([{"x": 1}], ""))
    monkeypatch.setattr(
        sql_planner, "_call_llm",
        lambda *a, **k: ("Thought: done\nAction: final_answer\nAction Input: SELECT x FROM t", 10, 5),
    )
    res = sql_planner.run_sql_agent("q", "## t\n- x INT", engine=object(), max_steps=2)
    assert res.success is True and not res.error


def test_F2_stale_error_cleared_by_later_final(monkeypatch):
    """守护者 Stage 4 补：无 stale 回归 —— 某步 fallback 失败设 final_error 后，后续 __FINAL__ 干净成功
    须**清 stale** → success=True。naive「仅 fallback 补 final_error、__FINAL__ 不清」会误判 False；
    本测正是守精修（两执行点均 `final_error = exec_err or ""`）的回归。"""
    ex = {"n": 0}

    def fake_execute(engine, sql):
        ex["n"] += 1
        if ex["n"] == 2:               # step1 fallback re-execute → 失败（设 final_error=stale）
            return [], "transient boom"
        return [{"x": 1}], ""          # call1 _run_tool 成功 / call3 __FINAL__ 成功

    monkeypatch.setattr(sql_planner.db_connector, "execute_query", fake_execute)
    llm = {"n": 0}

    def fake_llm(*a, **k):
        llm["n"] += 1
        if llm["n"] == 1:              # step1：execute_sql → 触发 fallback（call2 失败设 stale）
            return ("Thought: t\nAction: execute_sql\nAction Input: SELECT x FROM t", 10, 5)
        return ("Thought: done\nAction: final_answer\nAction Input: SELECT x FROM t", 10, 5)

    monkeypatch.setattr(sql_planner, "_call_llm", fake_llm)
    res = sql_planner.run_sql_agent("q", "## t\n- x INT", engine=object(), max_steps=3)
    assert res.success is True and not res.error, "后续 __FINAL__ 干净成功须清 fallback 设的 stale final_error"


def _seed_fresh_db(monkeypatch):
    from knot.repositories import base as base_mod
    fd, path = tempfile.mkstemp(suffix=".db", prefix="knot_f7_")
    os.close(fd)
    os.unlink(path)
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", path)
    base_mod.init_db()
    from knot.repositories import user_repo
    h = user_repo.get_user_by_username("admin")["password_hash"]
    os.path.exists(path) and os.unlink(path)
    return h


def test_F7_env_password_used_when_set(monkeypatch):
    """KNOT_INITIAL_ADMIN_PASSWORD 设定 → seed admin 用该口令。"""
    monkeypatch.setenv("KNOT_INITIAL_ADMIN_PASSWORD", "custom-pw-xyz")
    h = _seed_fresh_db(monkeypatch)
    assert bcrypt.checkpw(b"custom-pw-xyz", h.encode())


def test_F7_random_password_when_env_unset(monkeypatch):
    """无 env → 随机强口令（绝不再是硬编 admin123，消除跨部署同一已知口令）。"""
    monkeypatch.delenv("KNOT_INITIAL_ADMIN_PASSWORD", raising=False)
    h = _seed_fresh_db(monkeypatch)
    assert not bcrypt.checkpw(b"admin123", h.encode()), "随机 seed 绝不能匹配旧硬编 admin123"
