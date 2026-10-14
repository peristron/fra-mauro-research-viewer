# Technical feasibility assessment

Assessment date: 2026-10-13

## Source image and viewer

Factum Foundation describes its high-resolution browsers as multi-layer viewers. Its published production manual documents a krpano `MAKE PANO (MULTIRES)` workflow. The supplied screenshots are consistent with that legacy viewer family. Direct retrieval of the live HTML and configuration was blocked in the assessment environment, so the exact Fra Mauro tile size, levels, naming pattern, and programmatic-access permission could not be verified responsibly.

The application therefore does not scrape or reconstruct Factum tiles. It links to the source viewer for source-detail inspection and uses the public-domain Wikimedia copy as the research coordinate reference.

Wikimedia reports the square copy as:

- 60,351 × 60,351 pixels;
- JPEG;
- 933,359,955 bytes, approximately 890 MB;
- normal EXIF orientation;
- public-domain marked;
- derived from the Factum viewer by a Wikimedia contributor.

The historical map is conventionally displayed south-up. It has no defined modern coordinate reference system or embedded calibration suitable for direct overlay.

## Download and caching

Loading a 933 MB JPEG into a Community Cloud Python process would require substantially more decoded memory and risks terminating the app. The original-file control therefore links the browser directly to Wikimedia. The server caches only the 3,840 px display derivative, on demand, with a size limit and image verification.

For source-quality OCR, the researcher should crop an area in the Factum viewer or another local image tool and upload that crop. A later local-desktop release can add libvips-based region extraction from a user-owned full-resolution copy.

## Viewer and comparison

The Streamlit canvas uses Leaflet through Folium:

- historical image in pixel space;
- click and rectangle selection;
- pins, control points, and saved bounding boxes;
- OpenStreetMap or CartoDB modern reference layer;
- side-by-side, opacity overlay, swipe, and flicker modes after an affine solution exists.

The overlay is intentionally labelled approximate. Leaflet's basic image layer displays an axis-aligned corner envelope and does not perform scientific raster rectification. Exact resampling should be implemented later with GDAL/rasterio against a user-controlled full-resolution source.

## Georeferencing

Version 1 implements a six-parameter affine least-squares model from historical `(pixel_x, pixel_y)` to WGS84 `(longitude, latitude)`. It requires three non-collinear points. With exactly three points the fit is exact, so residuals cannot diagnose overfitting. More distributed points are strongly preferred.

Diagnostics include per-point great-circle residual, mean error, maximum error, RMS error, clustering warnings, and matrix condition number. Extrapolation beyond the control-point envelope remains unreliable.

## OCR and AI

Tesseract is useful for generating candidates but is not expected to read the map reliably. The app compares colour sharpening, grayscale, contrast, threshold, red isolation, blue isolation, and several rotations. It always stores raw OCR separately from human corrections.

AI adapters are optional. They preserve provider/model provenance and label output as not human-reviewed. Some requested models are text-only for this workflow, and Claude Opus 4.1 has been retired. Model IDs are configuration, not hard-coded guarantees.

## Persistence and privacy

SQLite is appropriate for the first private release. Community Cloud local storage is not durable, so the user must download and restore backups. Uploaded crops and API payloads may contain research material; using an AI provider sends that crop or text to that provider under its terms. No API key is stored in the database or exported project files.

## External services and terms

- Wikimedia API and media use must follow its User-Agent, rate-limit, robot, and licence requirements.
- OpenStreetMap and CartoDB tiles must not be bulk-downloaded.
- Factum tiles are not harvested until access permission and technical details are confirmed.
- Each AI provider controls model availability, retention, pricing, and quotas.

## Practical workarounds

| Limitation | Version 1 workaround |
|---|---|
| Factum configuration cannot be verified | Link the official viewer; do not scrape it |
| Full JPEG is too large for Community Cloud | Direct browser download; cache only a derivative |
| Display derivative lacks source detail | Upload a user-selected high-resolution crop |
| Medieval OCR is unreliable | Compare preprocessing/rotation variants and require review |
| Map has no CRS | User-supplied control points with visible diagnostics |
| Browser overlay is not rectified | Label it approximate and retain raw transform data |
| Cloud disk is temporary | Download/restore complete SQLite backups |
| Model names change | Editable model IDs in Streamlit secrets |
