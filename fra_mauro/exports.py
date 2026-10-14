from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any


def project_json(
    project: dict[str, Any],
    records: list[dict[str, Any]],
    control_points: list[dict[str, Any]],
    transformations: list[dict[str, Any]],
) -> bytes:
    portable_records = []
    for record in records:
        portable = dict(record)
        crop = portable.pop("crop_blob", None)
        portable["crop_embedded_in_sqlite"] = bool(crop)
        portable_records.append(portable)
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "format": "fra-mauro-research-project-v1",
        "project": project,
        "records": portable_records,
        "control_points": control_points,
        "transformations": transformations,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def records_csv(records: list[dict[str, Any]]) -> bytes:
    if not records:
        return b""
    output = io.StringIO()
    portable_records = []
    for record in records:
        portable = dict(record)
        crop = portable.pop("crop_blob", None)
        portable["crop_embedded_in_sqlite"] = bool(crop)
        portable_records.append(portable)
    writer = csv.DictWriter(output, fieldnames=list(portable_records[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(portable_records)
    return output.getvalue().encode("utf-8-sig")


def records_geojson(records: list[dict[str, Any]]) -> bytes:
    features = []
    for record in records:
        longitude, latitude = record.get("longitude"), record.get("latitude")
        geometry = None
        if longitude is not None and latitude is not None:
            geometry = {
                "type": "Point",
                "coordinates": [float(longitude), float(latitude)],
            }
        properties = {
            key: value
            for key, value in record.items()
            if key not in {"longitude", "latitude", "crop_blob"}
        }
        properties["crop_embedded_in_sqlite"] = bool(record.get("crop_blob"))
        properties["coordinate_status"] = "approximate" if geometry else "historical-pixel-only"
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    return json.dumps(
        {"type": "FeatureCollection", "features": features},
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
