from pathlib import Path

from fra_mauro.db import ResearchDB


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "samples" / "fra_mauro_sample.sqlite3"


def main() -> None:
    OUTPUT.unlink(missing_ok=True)
    db = ResearchDB(OUTPUT)
    project_id = db.projects()[0]["id"]
    db.save_record(
        project_id,
        {
            "title": "Demonstration test region",
            "category": "uncertain",
            "pixel_x": 30_175.5,
            "pixel_y": 30_175.5,
            "x1": 28_000.0,
            "y1": 28_000.0,
            "x2": 32_000.0,
            "y2": 32_000.0,
            "crop_path": "",
            "crop_blob": None,
            "raw_ocr": "[sample OCR output]",
            "transcription": "[unclear]",
            "transliteration": "",
            "translation": "",
            "translation_provenance": "",
            "confidence": 0.1,
            "status": "unreviewed",
            "notes": "Synthetic workflow example; not a historical identification.",
            "tags": "sample synthetic",
            "longitude": None,
            "latitude": None,
        },
    )
    examples = (
        ("Synthetic northwest", 10_000.0, 10_000.0, -50.0, 50.0),
        ("Synthetic northeast", 50_000.0, 10_000.0, 50.0, 50.0),
        ("Synthetic southwest", 10_000.0, 50_000.0, -50.0, -30.0),
        ("Synthetic southeast", 50_000.0, 50_000.0, 50.0, -30.0),
    )
    for name, pixel_x, pixel_y, longitude, latitude in examples:
        db.save_control_point(
            project_id,
            {
                "name": name,
                "category": "uncertain",
                "pixel_x": pixel_x,
                "pixel_y": pixel_y,
                "longitude": longitude,
                "latitude": latitude,
                "source_reasoning": "Synthetic affine demonstration only",
                "confidence": 0.0,
                "notes": "Not an authentic Fra Mauro control point.",
                "enabled": True,
            },
        )
    print(OUTPUT)


if __name__ == "__main__":
    main()
