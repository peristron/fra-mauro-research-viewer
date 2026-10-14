from fra_mauro.db import ResearchDB


def record_values():
    return {
        "title": "Cirenayca",
        "category": "region",
        "pixel_x": 100.0,
        "pixel_y": 200.0,
        "x1": 90.0,
        "y1": 190.0,
        "x2": 120.0,
        "y2": 230.0,
        "crop_path": "",
        "crop_blob": b"sample-crop",
        "raw_ocr": "CIRENAICA",
        "transcription": "Cirenayca",
        "transliteration": "Cirenaica",
        "translation": "Cyrenaica",
        "translation_provenance": "human-reviewed",
        "confidence": 0.9,
        "status": "human-reviewed",
        "notes": "Test record",
        "tags": "africa",
        "longitude": 21.7,
        "latitude": 32.8,
    }


def test_record_round_trip_and_search(tmp_path):
    db = ResearchDB(tmp_path / "test.sqlite3")
    project_id = db.projects()[0]["id"]
    record_id = db.save_record(project_id, record_values())
    assert db.get_record(record_id)["translation"] == "Cyrenaica"
    assert db.get_record(record_id)["crop_blob"] == b"sample-crop"
    assert db.search_records(project_id, "cyren")[0]["id"] == record_id
    assert db.search_records(project_id, "AFRICA")[0]["id"] == record_id


def test_backup_restore_validates_database(tmp_path):
    first = ResearchDB(tmp_path / "first.sqlite3")
    project_id = first.projects()[0]["id"]
    first.save_record(project_id, record_values())
    second = ResearchDB(tmp_path / "second.sqlite3")
    second.restore_bytes(first.backup_bytes())
    assert second.search_records(project_id, "Cirenayca")
