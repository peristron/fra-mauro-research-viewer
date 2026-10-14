# Fra Mauro Research Viewer

A private, single-researcher Streamlit workspace for examining the Fra Mauro map, recording text and places, testing OCR, adding ground-control points, and comparing an evidence-based affine alignment with modern geography.

The app never presents OCR, AI output, or geographic alignment as established fact. Raw OCR, corrected transcription, transliteration, translation, and provenance are stored separately.

## Community Cloud deployment

1. Create a new GitHub repository and place this complete directory at its root.
2. In Streamlit Community Cloud, create an app from that repository.
3. Set the entry point to `streamlit_app.py`.
4. Choose a currently supported Python version. Python 3.12 is recommended.
5. Add API keys under **App settings > Secrets** using `.streamlit/secrets.example.toml` as the structure. Add only providers you intend to use.
6. Deploy the app.

`requirements.txt` installs Python packages. `packages.txt` installs Tesseract with English and Latin language data on Community Cloud.

Community Cloud storage is temporary. Use **Export > Complete SQLite backup** after each research session. Restore that file at the beginning of a later session if the app has restarted.

## Local Windows launch

1. Install Python 3.12 and Tesseract OCR.
2. Ensure `tesseract.exe` is available on `PATH`.
3. Double-click `launch.bat`.

Alternatively, from PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Research workflow

1. Open **Map** and inspect the Wikimedia derivative or the linked Factum source viewer.
2. Click a position or draw a rectangle on the historical image.
3. Save a pin or open **OCR & text**.
4. Upload a high-resolution crop when the 3,840 px derivative is insufficient.
5. Compare several Tesseract preprocessing and rotation variants.
6. Correct the transcription manually. Keep transliteration and translation separate.
7. Optionally request an AI suggestion from a configured provider, then review it.
8. Add at least three well-distributed shared points in **Georeference**.
9. Inspect residuals and warnings before saving an affine solution.
10. Export a complete SQLite backup before leaving the app.

## Image handling

- Display canvas: public-domain 3,840 px Wikimedia derivative.
- Full image: 60,351 × 60,351 pixel, approximately 890 MB Wikimedia original.
- Source-detail inspection: linked Factum Arte high-resolution viewer.
- The full original is downloaded directly by the browser. It is not loaded into Streamlit memory.
- Cached files are stored in `.runtime/` and never overwrite the original source.

## AI models

The menu includes every model from the supplied screenshot:

- Claude Opus 4.1
- GPT-5
- Claude Sonnet 4.5
- Gemini 2.5 Pro
- Grok 4
- Claude Haiku 4.5
- Gemini 2.5 Flash
- DeepSeek 3.2
- Kimi K2 Thinking
- Qwen3 Max

Model IDs and availability change. Every default ID can be overridden in Streamlit secrets. Claude Opus 4.1 is retained in the menu as requested but is marked retired. Text-only presets can translate draft text but do not receive the crop image.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall streamlit_app.py fra_mauro
```

## Important limitations

- The map is south-up and has no native geographic CRS.
- Affine alignment is an interpretive comparison derived from user-selected points.
- The visual overlay uses an axis-aligned corner envelope. It is not a rectified raster suitable for measurement.
- Medieval handwriting, abbreviations, pigment colours, and rotated labels make automated OCR unreliable.
- Factum's exact tile pattern and automated-download permission were not confirmed, so the app does not scrape its tiles.
- Public basemap and AI services remain subject to their providers' terms, quotas, and availability.

See `TECHNICAL_ASSESSMENT.md` for the feasibility assessment and `DATA_DICTIONARY.md` for stored-field meanings.

The bundled `samples/fra_mauro_sample.sqlite3` contains synthetic control points and one test region for learning the workflow. It is explicitly not historical research data.
