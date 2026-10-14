# Data dictionary

## Coordinate spaces

- `pixel_x`, `pixel_y`: coordinates in the 60,351 × 60,351 historical image, origin at the image's upper-left.
- `x1`, `y1`, `x2`, `y2`: optional historical-image bounding box.
- `longitude`, `latitude`: modern WGS84 reference or interpretation. These never replace historical pixels.

## Text fields

- `raw_ocr`: uncorrected machine output.
- `transcription`: editorial reading of the visible historical text.
- `transliteration`: historical characters or abbreviations rendered in a modern character system.
- `translation`: English expression of meaning.
- `translation_provenance`: model, reviewer, or other source of the translation.
- `status`: `unreviewed`, `machine-corrected`, `human-corrected`, or `human-reviewed`.
- `crop_blob`: the source crop embedded in SQLite so a complete backup preserves the visual evidence.

Use `[unclear]`, `[illegible]`, and `[possible reading: ...]` inside editorial fields where appropriate.

## Alignment

Every control point retains both coordinate spaces, its reasoning, confidence, enabled state, notes, and timestamps. A saved transformation stores its coefficients, diagnostics, and the exact control-point IDs used to fit it.
