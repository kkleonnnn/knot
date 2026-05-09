"""conversation + message_repo happy-path 单测。"""
from knot.repositories import conversation_repo, message_repo, user_repo


def _admin_id(_):
    return user_repo.get_user_by_username("admin")["id"]


def test_create_and_list_conversation(tmp_db_path):
    uid = _admin_id(tmp_db_path)
    cid = conversation_repo.create_conversation(uid, title="测试")
    convs = conversation_repo.list_conversations(uid)
    assert len(convs) == 1
    assert convs[0]["id"] == cid
    assert convs[0]["title"] == "测试"


def test_update_conversation_title(tmp_db_path):
    uid = _admin_id(tmp_db_path)
    cid = conversation_repo.create_conversation(uid)
    conversation_repo.update_conversation_title(cid, "改名了")
    convs = conversation_repo.list_conversations(uid)
    assert convs[0]["title"] == "改名了"


def test_delete_cascades_messages(tmp_db_path):
    uid = _admin_id(tmp_db_path)
    cid = conversation_repo.create_conversation(uid)
    message_repo.save_message(cid, "Q", "SELECT 1", "ok", "high",
                              [{"a": 1}], None, 0.01, 10, 5, 0)
    assert len(message_repo.get_messages(cid)) == 1
    conversation_repo.delete_conversation(cid)
    assert message_repo.get_messages(cid) == []


def test_save_and_get_messages(tmp_db_path):
    uid = _admin_id(tmp_db_path)
    cid = conversation_repo.create_conversation(uid)
    message_repo.save_message(cid, "Q1", "SELECT 1", "ok", "high",
                              [{"x": 1}], None, 0.001, 10, 5, 0)
    message_repo.save_message(cid, "Q2", "SELECT 2", "ok", "medium",
                              [{"x": 2}], None, 0.002, 20, 10, 1)
    msgs = message_repo.get_messages(cid)
    assert len(msgs) == 2
    assert msgs[0]["question"] == "Q1"
    assert msgs[0]["rows"] == [{"x": 1}]
    assert msgs[1]["confidence"] == "medium"


def test_semantic_layer_roundtrip(tmp_db_path):
    uid = _admin_id(tmp_db_path)
    assert message_repo.get_semantic_layer() == ""
    message_repo.save_semantic_layer("业务约定 X = Y", updated_by=uid)
    assert message_repo.get_semantic_layer() == "业务约定 X = Y"
    message_repo.save_semantic_layer("更新了", updated_by=uid)
    assert message_repo.get_semantic_layer() == "更新了"
