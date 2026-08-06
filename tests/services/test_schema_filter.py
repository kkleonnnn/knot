"""services.schema_filter happy-path 单测。"""
from knot.services import schema_filter


def test_parse_schema_tables():
    text = """### demo_dwd.dwd_user_reg
- created_at (DATETIME)
- user_id (BIGINT)

### demo_ads.ads_daily_report
- sta_date (DATE)
"""
    pairs = schema_filter.parse_schema_tables(text)
    names = [p[0] for p in pairs]
    assert "demo_dwd.dwd_user_reg" in names
    assert "demo_ads.ads_daily_report" in names


def test_metadata_query_detected():
    assert schema_filter._is_metadata_query("数据库里有哪些表")
    assert schema_filter._is_metadata_query("show tables")
    assert not schema_filter._is_metadata_query("昨天注册了多少人")


def test_basename():
    assert schema_filter._basename("db.tbl") == "tbl"
    assert schema_filter._basename("tbl") == "tbl"


def test_filter_below_max_returns_unchanged():
    text = "### t1\n- f"
    out = schema_filter.filter_schema_for_question(text, "Q", max_tables=12)
    assert out == text


def test_filter_metadata_query_lists_names():
    # ⚠️ 本测原有两行**死代码**（v0.9.15 后 chore 清 lint 时发现并删除）：
    #   `out = f("有哪些表", text, …) if False else f(text, "…", …)` ——
    #   `if False` 让第一个调用（**参数还是反的**）永不执行，而 `out` **从未被断言**。
    #   删掉零覆盖损失（真断言在下面的 out2），但留着会让本测**看起来**覆盖了小文本那一路。
    # 小文本在阈值以下会在 metadata 逻辑之前短路 ⇒ 必须造够多的表才测得到「列所有表名」。
    big = "\n\n".join(f"### t{i}\n- f" for i in range(20))
    out2 = schema_filter.filter_schema_for_question(big, "有哪些表", max_tables=5)
    assert "### 所有表名" in out2
