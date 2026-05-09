"""upload_repo happy-path 单测。"""
from knot.repositories import upload_repo


def test_create_list_get(tmp_db_path):
    uid = upload_repo.create_file_upload(
        user_id=1, filename="data.csv", table_name="upload_1",
        row_count=42, columns=[{"name": "id"}, {"name": "value"}],
    )
    rows = upload_repo.list_file_uploads(1)
    assert len(rows) == 1
    assert rows[0]["row_count"] == 42
    assert rows[0]["columns"] == [{"name": "id"}, {"name": "value"}]
    fetched = upload_repo.get_file_upload(uid)
    assert fetched["filename"] == "data.csv"


def test_get_missing_returns_none(tmp_db_path):
    assert upload_repo.get_file_upload(99999) is None


def test_delete(tmp_db_path):
    uid = upload_repo.create_file_upload(1, "f", "t", 1, [])
    upload_repo.delete_file_upload(uid)
    assert upload_repo.list_file_uploads(1) == []
