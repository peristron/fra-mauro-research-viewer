from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image
from streamlit_folium import st_folium

from fra_mauro.ai import analyze, configured, effective_model_id, preset_by_label
from fra_mauro.config import (
    APP_NAME,
    APP_VERSION,
    COMMONS_FILE_PAGE,
    COMMONS_ORIGINAL_URL,
    COMMONS_PREVIEW_URL,
    CROP_DIR,
    DEFAULT_DB_PATH,
    FACTUM_VIEWER_URL,
    MAP_CRS,
    MAP_HEIGHT,
    MAP_ORIENTATION,
    MAP_WIDTH,
    MODEL_PRESETS,
    PREVIEW_CACHE_PATH,
    ensure_runtime_dirs,
)
from fra_mauro.db import ResearchDB
from fra_mauro.exports import project_json, records_csv, records_geojson
from fra_mauro.georef import distribution_warnings, fit_affine
from fra_mauro.image_tools import (
    crop_preview_from_full_pixels,
    download_preview,
    image_to_jpeg_bytes,
    open_image,
    preprocess,
    run_tesseract,
    safe_crop_name,
)
from fra_mauro.map_views import (
    aligned_overlay_map,
    extract_historical_selection,
    historical_map,
    modern_map,
)
from fra_mauro.styles import APP_CSS


st.set_page_config(
    page_title=APP_NAME,
    page_icon=":material/map:",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)
st.markdown(
    """
    <style>
        :root {
            --ink: #eee9df;
            --muted: #aeb8b1;
            --paper: #111715;
            --accent: #d17863;
            --line: #34413c;
            --water: #72a8b8;
        }
        .stApp {
            background: #111715;
            color: #eee9df;
        }
        [data-testid="stHeader"] {
            background: rgba(17, 23, 21, .94);
        }
        [data-testid="stSidebar"] {
            background: #171f1c;
            border-right: 1px solid #34413c;
        }
        [data-testid="stSidebar"] * {
            color: #eee9df;
        }
        h1, h2, h3, h4, p, label {
            color: #eee9df;
        }
        .fm-kicker {
            color: #d98a76;
        }
        .fm-subtle, [data-testid="stCaptionContainer"] {
            color: #aeb8b1;
        }
        .fm-status {
            color: #e6efea;
            background: #182824;
            border-left-color: #72a8b8;
        }
        .fm-warning {
            color: #f2e5df;
            background: #30211e;
            border-left-color: #d17863;
        }
        div[data-testid="stExpander"] {
            background: #171f1c;
            border-color: #34413c;
            border-radius: 4px;
        }
        div[data-testid="stDataFrame"] {
            border-color: #34413c;
        }
        .stTabs [data-baseweb="tab-list"] {
            border-bottom-color: #34413c;
        }
        .stTabs [data-baseweb="tab"] {
            color: #bcc5bf;
        }
        .stTabs [aria-selected="true"] {
            color: #f4efe5;
        }
        .stButton > button,
        .stDownloadButton > button,
        .stLinkButton > a {
            border-color: #46564f;
        }
        hr {
            border-color: #34413c;
        }
    </style>
    """,
    unsafe_allow_html=True,
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
ensure_runtime_dirs()


@st.cache_resource
def database() -> ResearchDB:
    custom_path = os.environ.get("FRA_MAURO_DB_PATH", "")
    return ResearchDB(Path(custom_path) if custom_path else DEFAULT_DB_PATH)


db = database()


def secret_value(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default))
    except FileNotFoundError:
        return default


def money_distance(value_m: float) -> str:
    return f"{value_m / 1000:,.1f} km" if value_m >= 1000 else f"{value_m:,.0f} m"


def current_project() -> tuple[int, dict]:
    projects = db.projects()
    labels = {project["name"]: project for project in projects}
    selected_name = st.sidebar.selectbox("Project", list(labels), key="project_name")
    selected = labels[selected_name]
    return int(selected["id"]), selected


def selection_values() -> dict[str, float]:
    default = {"pixel_x": MAP_WIDTH / 2, "pixel_y": MAP_HEIGHT / 2}
    return st.session_state.get("historical_selection", default)


def selected_record(records: list[dict]) -> dict | None:
    record_id = st.session_state.get("selected_record_id")
    return next((record for record in records if record["id"] == record_id), None)


st.sidebar.markdown('<div class="fm-kicker">Research workspace</div>', unsafe_allow_html=True)
st.sidebar.title("Fra Mauro")
project_id, project = current_project()
st.sidebar.caption("Local work is temporary on Community Cloud. Download a backup before leaving.")

with st.sidebar.expander("New project"):
    with st.form("new_project", clear_on_submit=True):
        new_name = st.text_input("Project name")
        new_description = st.text_area("Description")
        if st.form_submit_button("Create project", use_container_width=True):
            if not new_name.strip():
                st.error("Enter a project name.")
            else:
                try:
                    db.add_project(new_name, new_description)
                    st.session_state.project_name = new_name.strip()
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("A project with that name already exists.")

records = db.records(project_id)
control_points = db.control_points(project_id)

st.markdown('<div class="fm-kicker">1459 · South-up · evidence-led alignment</div>', unsafe_allow_html=True)
st.title(APP_NAME)
st.caption(
    "Inspect, annotate, transcribe, translate, and approximately compare the map with modern geography. "
    "Pixel observations and geographic interpretations are stored separately."
)

with st.expander("How to use this app", expanded=False):
    st.markdown(
        """
        1. **Inspect the historical map.** Pan and zoom in **Map**. Click a position or use the rectangle tool to select a region. The displayed values are historical-image pixels, not latitude and longitude.
        2. **Save a pin or region.** Expand **Save pin or region**, give the selection a title and confidence level, and record why it matters.
        3. **Work with detailed text.** Open **OCR & text**. For the best results, upload a high-resolution crop from the linked Factum source viewer; the research canvas uses a lower-resolution display derivative.
        4. **Keep text stages separate.** Preserve raw OCR, corrected transcription, modern-character transliteration, and English translation in their respective fields. Use `[unclear]`, `[illegible]`, and `[possible reading: ...]` where appropriate.
        5. **Review AI suggestions.** AI output is optional and remains unreviewed until you verify and edit it. The selected provider and model are saved as provenance.
        6. **Add geographic hypotheses.** In **Georeference**, associate historical pixels with modern WGS84 locations. Use at least three non-collinear, well-distributed control points and record the reasoning for each match.
        7. **Interpret alignment cautiously.** Residuals measure how the selected affine model fits the chosen points; they do not prove that an identification is historically correct.
        8. **Find previous work.** Use **Search** to locate transcription, transliteration, translation, tags, and notes, then return to the highlighted map region.
        9. **Back up every session.** Open **Export** and download the complete SQLite backup. Streamlit Community Cloud local storage may be replaced during a restart or redeployment.

        The map is conventionally displayed south-up. Modern overlays are adjustable research comparisons, not claims of exact historical geolocation.
        """
    )

tabs = st.tabs(["Map", "OCR & text", "Georeference", "Search", "Export", "Method & sources"])


with tabs[0]:
    toolbar = st.columns([1.2, 1, 1.3, 1, 1.25])
    opacity = toolbar[0].slider("Historical opacity", 0.1, 1.0, 1.0, 0.05)
    layer = toolbar[1].selectbox("Modern layer", ["OpenStreetMap", "CartoDB Positron"])
    projection = toolbar[2].selectbox(
        "Modern projection",
        ["Web Mercator (EPSG:3857)", "WGS84 geographic (EPSG:4326)"],
    )
    comparison = toolbar[3].selectbox("Comparison", ["Side by side", "Overlay", "Swipe", "Flicker"])
    toolbar[4].link_button("Factum source viewer", FACTUM_VIEWER_URL, use_container_width=True)
    if projection.startswith("WGS84"):
        st.caption("WGS84 geographic mode uses an un-tiled coordinate canvas because standard OSM/Carto tiles are Web Mercator.")

    selected = selected_record(records)
    selected_id = int(selected["id"]) if selected else None
    if comparison == "Side by side":
        historical_column, modern_column = st.columns(2, gap="small")
        with historical_column:
            st.subheader("Historical image space")
            state = st_folium(
                historical_map(records, control_points, opacity, selected_id),
                height=620,
                use_container_width=True,
                returned_objects=["last_clicked", "last_active_drawing", "bounds", "zoom"],
                key=f"historical-{project_id}-{selected_id}",
            )
        try:
            affine = fit_affine(control_points)
        except ValueError:
            affine = None
        with modern_column:
            st.subheader("Modern reference space")
            st_folium(
                modern_map(control_points, affine, layer, projection),
                height=620,
                use_container_width=True,
                returned_objects=[],
                key=f"modern-{project_id}-{len(control_points)}",
            )
    else:
        try:
            affine = fit_affine(control_points)
        except ValueError as error:
            affine = None
            st.warning(f"Add at least three well-distributed control points first. {error}")
        if affine:
            st.markdown(
                '<div class="fm-warning"><strong>Approximate comparison.</strong> '
                "The browser overlay uses the affine corner envelope; it is not a rectified scientific raster.</div>",
                unsafe_allow_html=True,
            )
            st_folium(
                aligned_overlay_map(affine, opacity, comparison, layer, projection),
                height=680,
                use_container_width=True,
                returned_objects=[],
                key=f"aligned-{project_id}-{comparison}-{opacity}",
            )
        state = None

    if state:
        new_selection = extract_historical_selection(state)
        if new_selection:
            st.session_state.historical_selection = new_selection

    selection = selection_values()
    status_columns = st.columns([1, 1, 1, 2])
    status_columns[0].metric("Pixel X", f"{selection['pixel_x']:,.0f}")
    status_columns[1].metric("Pixel Y", f"{selection['pixel_y']:,.0f}")
    status_columns[2].metric("Saved items", len(records))
    if {"x1", "y1", "x2", "y2"}.issubset(selection):
        status_columns[3].caption(
            f"Selected box: ({selection['x1']:.0f}, {selection['y1']:.0f}) to "
            f"({selection['x2']:.0f}, {selection['y2']:.0f})"
        )
    else:
        status_columns[3].caption("Click the map or use the rectangle tool to select a research region.")

    with st.expander("Save pin or region", expanded=False):
        with st.form("quick_record"):
            title = st.text_input("Title", placeholder="Unidentified red inscription")
            left, right = st.columns(2)
            category = left.selectbox(
                "Category",
                ["city", "river", "coastline", "island", "mountain", "region", "sea", "port", "historical place", "uncertain"],
            )
            confidence = right.slider("Confidence", 0.0, 1.0, 0.5, 0.05)
            notes = st.text_area("Research notes")
            if st.form_submit_button("Save annotation", type="primary"):
                if not title.strip():
                    st.error("Enter a title.")
                else:
                    values = {
                        "title": title.strip(),
                        "category": category,
                        "pixel_x": selection["pixel_x"],
                        "pixel_y": selection["pixel_y"],
                        "x1": selection.get("x1"),
                        "y1": selection.get("y1"),
                        "x2": selection.get("x2"),
                        "y2": selection.get("y2"),
                        "crop_path": "",
                        "crop_blob": None,
                        "raw_ocr": "",
                        "transcription": "",
                        "transliteration": "",
                        "translation": "",
                        "translation_provenance": "",
                        "confidence": confidence,
                        "status": "unreviewed",
                        "notes": notes,
                        "tags": "",
                        "longitude": None,
                        "latitude": None,
                    }
                    st.session_state.selected_record_id = db.save_record(project_id, values)
                    st.success("Annotation saved.")
                    st.rerun()

    download_columns = st.columns(3)
    download_columns[0].link_button("Open 890 MB original", COMMONS_ORIGINAL_URL, use_container_width=True)
    download_columns[1].link_button("Source and licence record", COMMONS_FILE_PAGE, use_container_width=True)
    download_columns[2].link_button("Open 3,840 px derivative", COMMONS_PREVIEW_URL, use_container_width=True)
    st.caption(
        "The original download is sent directly from Wikimedia to your browser. The app does not load it into Community Cloud memory."
    )


with tabs[1]:
    st.subheader("OCR and editorial record")
    st.caption("Raw OCR, corrected transcription, transliteration, and English translation remain separate fields.")
    chosen_record = selected_record(records)
    source_choice = st.radio(
        "Crop source", ["Upload a crop", "Current map rectangle"], horizontal=True
    )
    crop_image: Image.Image | None = None
    crop_bytes: bytes | None = None
    if source_choice == "Upload a crop":
        uploaded_crop = st.file_uploader("Map crop", type=["jpg", "jpeg", "png", "webp"])
        if uploaded_crop:
            crop_bytes = uploaded_crop.getvalue()
            crop_image = open_image(crop_bytes)
    else:
        selection = selection_values()
        if not {"x1", "y1", "x2", "y2"}.issubset(selection):
            st.info("Draw a rectangle in the Map tab first.")
        else:
            if st.button("Fetch/cache display derivative", help="Downloads the 3,840 px public-domain derivative once."):
                bar = st.progress(0, text="Downloading display derivative")
                try:
                    download_preview(
                        PREVIEW_CACHE_PATH,
                        contact=secret_value("APP_CONTACT"),
                        progress=lambda value: bar.progress(value, text="Downloading display derivative"),
                    )
                    bar.empty()
                except Exception as error:
                    bar.empty()
                    st.error(f"Could not download the display derivative: {error}")
            if PREVIEW_CACHE_PATH.exists():
                preview = open_image(PREVIEW_CACHE_PATH)
                crop_image = crop_preview_from_full_pixels(
                    preview, selection["x1"], selection["y1"], selection["x2"], selection["y2"]
                )
                crop_bytes = image_to_jpeg_bytes(crop_image)

    if crop_image:
        image_column, controls_column = st.columns([1.6, 1])
        image_column.image(crop_image, caption="Working crop · derived display image", use_container_width=True)
        method = controls_column.selectbox(
            "Preview preprocessing",
            ["colour sharpen", "grayscale", "adaptive contrast", "red ink isolation", "blue ink isolation", "threshold"],
        )
        processed = preprocess(crop_image, method)
        controls_column.image(processed, caption=method, use_container_width=True)

        with st.expander("Run Tesseract experiments", expanded=True):
            ocr_methods = st.multiselect(
                "Methods",
                ["colour sharpen", "grayscale", "adaptive contrast", "red ink isolation", "blue ink isolation", "threshold"],
                default=["grayscale", "adaptive contrast"],
            )
            rotations = st.multiselect("Rotations", [0, 90, 180, 270], default=[0, 90, 270])
            if st.button("Run Tesseract OCR", type="primary", disabled=not ocr_methods or not rotations):
                with st.spinner("Testing OCR variants..."):
                    st.session_state.ocr_results = run_tesseract(crop_image, ocr_methods, rotations)
            results = st.session_state.get("ocr_results", [])
            if results:
                labels = [f"{item.method} · {item.rotation}°" for item in results]
                selected_variant = st.selectbox("Result variant", labels)
                variant = results[labels.index(selected_variant)]
                st.text_area("Raw OCR result", variant.text, height=160, key="ocr_result_display")
                if st.button("Use as raw OCR"):
                    st.session_state.editor_raw_ocr = variant.text

        st.markdown("#### Optional AI-assisted reading")
        model_label = st.selectbox("Model", [preset.label for preset in MODEL_PRESETS])
        preset = preset_by_label(model_label)
        model_id = effective_model_id(preset, st.secrets)
        model_columns = st.columns([1, 1, 2])
        model_columns[0].write(f"Provider: `{preset.provider}`")
        model_columns[1].write(f"Image input: `{'yes' if preset.supports_images else 'text only'}`")
        model_columns[2].caption(f"{model_id} · {preset.status}")
        draft_for_ai = st.text_area(
            "Draft supplied to the model",
            value=st.session_state.get("editor_raw_ocr", ""),
            height=120,
        )
        if st.button("Generate editorial suggestions", disabled=not configured(preset, st.secrets)):
            try:
                with st.spinner(f"Consulting {model_label}..."):
                    result = analyze(model_label, draft_for_ai, st.secrets, crop_bytes)
                st.session_state.editor_transcription = result.transcription
                st.session_state.editor_transliteration = result.transliteration
                st.session_state.editor_translation = result.translation
                st.session_state.editor_notes = result.uncertainty_notes
                st.session_state.editor_provenance = result.provenance
                st.success("AI suggestions generated. Review every field before marking the item reviewed.")
            except Exception as error:
                st.error(f"The provider request failed: {error}")
        if not configured(preset, st.secrets):
            st.info(f"Configure `{preset.secret_name}` in Streamlit secrets to enable this model.")

    edit_options = {f"#{record['id']} · {record['title']}": record for record in records}
    chosen_label = st.selectbox(
        "Edit existing record",
        ["Create a new record", *edit_options],
        index=0,
    )
    editing = edit_options.get(chosen_label)
    if editing and st.session_state.get("editor_loaded_id") != editing["id"]:
        for field in ("raw_ocr", "transcription", "transliteration", "translation", "notes"):
            st.session_state[f"editor_{field}"] = editing.get(field, "") or ""
        st.session_state.editor_provenance = editing.get("translation_provenance", "") or ""
        st.session_state.editor_loaded_id = editing["id"]
    elif not editing and st.session_state.get("editor_loaded_id"):
        for field in ("raw_ocr", "transcription", "transliteration", "translation", "notes", "provenance"):
            st.session_state[f"editor_{field}"] = ""
        st.session_state.pop("editor_loaded_id", None)

    selection = selection_values()
    with st.form("editor_form"):
        title = st.text_input("Record title", value=editing["title"] if editing else "")
        editor_columns = st.columns(2)
        categories = ["city", "river", "coastline", "island", "mountain", "region", "sea", "port", "historical place", "uncertain"]
        category = editor_columns[0].selectbox(
            "Category",
            categories,
            index=categories.index(editing["category"]) if editing and editing["category"] in categories else 8,
        )
        statuses = ["unreviewed", "machine-corrected", "human-corrected", "human-reviewed"]
        status = editor_columns[1].selectbox(
            "Review status", statuses,
            index=statuses.index(editing["status"]) if editing and editing["status"] in statuses else 0,
        )
        raw_ocr = st.text_area("Raw OCR (machine output)", key="editor_raw_ocr", height=120)
        transcription = st.text_area("Corrected transcription", key="editor_transcription", height=120)
        transliteration = st.text_area("Modern-character transliteration", key="editor_transliteration", height=100)
        translation = st.text_area("English translation", key="editor_translation", height=100)
        provenance = st.text_input("Translation provenance", key="editor_provenance")
        detail_columns = st.columns(3)
        confidence = detail_columns[0].slider(
            "Confidence", 0.0, 1.0, float(editing["confidence"]) if editing else 0.5, 0.05
        )
        longitude = detail_columns[1].number_input(
            "Approx. longitude", -180.0, 180.0, value=float(editing["longitude"]) if editing and editing["longitude"] is not None else 0.0
        )
        latitude = detail_columns[2].number_input(
            "Approx. latitude", -90.0, 90.0, value=float(editing["latitude"]) if editing and editing["latitude"] is not None else 0.0
        )
        tags = st.text_input("Tags", value=editing["tags"] if editing else "")
        notes = st.text_area("Notes and uncertainty", key="editor_notes")
        save = st.form_submit_button("Save research record", type="primary")
        if save:
            if not title.strip():
                st.error("Enter a record title.")
            else:
                saved_crop = editing["crop_path"] if editing else ""
                saved_crop_blob = editing.get("crop_blob") if editing else None
                if crop_bytes:
                    crop_name = safe_crop_name(crop_bytes)
                    crop_path = CROP_DIR / crop_name
                    if not crop_path.exists():
                        crop_path.write_bytes(crop_bytes)
                    saved_crop = crop_name
                    saved_crop_blob = crop_bytes
                source = editing or selection
                values = {
                    "title": title.strip(),
                    "category": category,
                    "pixel_x": float(source["pixel_x"]),
                    "pixel_y": float(source["pixel_y"]),
                    "x1": source.get("x1"), "y1": source.get("y1"),
                    "x2": source.get("x2"), "y2": source.get("y2"),
                    "crop_path": saved_crop,
                    "crop_blob": saved_crop_blob,
                    "raw_ocr": raw_ocr,
                    "transcription": transcription,
                    "transliteration": transliteration,
                    "translation": translation,
                    "translation_provenance": provenance,
                    "confidence": confidence,
                    "status": status,
                    "notes": notes,
                    "tags": tags,
                    "longitude": longitude if longitude or latitude else None,
                    "latitude": latitude if longitude or latitude else None,
                }
                record_id = db.save_record(project_id, values, editing["id"] if editing else None)
                st.session_state.selected_record_id = record_id
                st.success("Research record saved.")
                st.rerun()


with tabs[2]:
    st.subheader("Ground-control points and affine alignment")
    st.markdown(
        '<div class="fm-warning"><strong>Interpretive model.</strong> Control points are hypotheses. '
        "A small residual does not confirm a historical identification.</div>",
        unsafe_allow_html=True,
    )
    selection = selection_values()
    form_column, diagnostics_column = st.columns([1, 1.45])
    with form_column:
        st.write("Associate the currently selected historical pixel with a modern location.")
        with st.form("control_point"):
            point_name = st.text_input("Point name")
            point_category = st.selectbox(
                "Point type", ["city", "river", "coastline", "island", "mountain", "region", "sea", "port", "historical place", "uncertain"]
            )
            pixel_columns = st.columns(2)
            pixel_x = pixel_columns[0].number_input("Historical pixel X", 0.0, float(MAP_WIDTH), float(selection["pixel_x"]))
            pixel_y = pixel_columns[1].number_input("Historical pixel Y", 0.0, float(MAP_HEIGHT), float(selection["pixel_y"]))
            geo_columns = st.columns(2)
            longitude = geo_columns[0].number_input("Modern longitude", -180.0, 180.0, 0.0, format="%.6f")
            latitude = geo_columns[1].number_input("Modern latitude", -90.0, 90.0, 0.0, format="%.6f")
            reasoning = st.text_area("Source or reasoning")
            confidence = st.slider("Identification confidence", 0.0, 1.0, 0.5, 0.05)
            notes = st.text_area("Notes")
            if st.form_submit_button("Add control point", type="primary"):
                if not point_name.strip():
                    st.error("Enter a point name.")
                else:
                    db.save_control_point(
                        project_id,
                        {
                            "name": point_name.strip(), "category": point_category,
                            "pixel_x": pixel_x, "pixel_y": pixel_y,
                            "longitude": longitude, "latitude": latitude,
                            "source_reasoning": reasoning, "confidence": confidence,
                            "notes": notes, "enabled": True,
                        },
                    )
                    st.success("Control point added.")
                    st.rerun()

    with diagnostics_column:
        control_points = db.control_points(project_id)
        if control_points:
            table = pd.DataFrame(control_points)[
                ["id", "name", "category", "pixel_x", "pixel_y", "longitude", "latitude", "confidence", "enabled"]
            ]
            st.dataframe(table, hide_index=True, use_container_width=True, height=250)
            removal = st.selectbox(
                "Manage point", ["Select a point", *[f"#{point['id']} · {point['name']}" for point in control_points]]
            )
            if removal != "Select a point":
                point_id = int(removal.split(" · ", 1)[0][1:])
                action_columns = st.columns(2)
                target = next(point for point in control_points if point["id"] == point_id)
                if action_columns[0].button("Enable/disable", use_container_width=True):
                    updated = dict(target)
                    updated["enabled"] = not target["enabled"]
                    db.save_control_point(project_id, updated, point_id)
                    st.rerun()
                if action_columns[1].button("Delete", type="secondary", use_container_width=True):
                    db.delete_control_point(project_id, point_id)
                    st.rerun()
        try:
            affine = fit_affine(control_points)
            metrics = st.columns(3)
            metrics[0].metric("RMS error", money_distance(affine.rmse_m))
            metrics[1].metric("Mean error", money_distance(affine.mean_error_m))
            metrics[2].metric("Maximum error", money_distance(affine.max_error_m))
            warnings = distribution_warnings(control_points, MAP_WIDTH, MAP_HEIGHT)
            for warning in warnings:
                st.warning(warning)
            enabled = [point for point in control_points if point["enabled"]]
            residual_table = pd.DataFrame(
                {
                    "Point": [point["name"] for point in enabled],
                    "Residual km": [round(value / 1000, 2) for value in affine.residuals_m],
                    "Predicted lon": [round(value[0], 5) for value in affine.predicted],
                    "Predicted lat": [round(value[1], 5) for value in affine.predicted],
                }
            )
            st.dataframe(residual_table, hide_index=True, use_container_width=True)
            st.caption(f"Matrix condition number: {affine.condition_number:,.2f}. Errors use great-circle distance.")
            if st.button("Save this affine solution"):
                db.save_transformation(
                    project_id,
                    {"coefficients": affine.coefficients, "source_crs": "pixel", "target_crs": "EPSG:4326"},
                    {"rmse_m": affine.rmse_m, "mean_error_m": affine.mean_error_m, "max_error_m": affine.max_error_m},
                    [point["id"] for point in enabled],
                )
                st.success("Transformation and its control-point IDs were saved.")
        except ValueError as error:
            st.info(str(error))


with tabs[3]:
    st.subheader("Search map text and notes")
    search_columns = st.columns([2, 1, 1])
    query = search_columns[0].text_input("Search", placeholder="Cirenayca, port, [unclear]...")
    status_filter = search_columns[1].selectbox(
        "Status", ["All", "unreviewed", "machine-corrected", "human-corrected", "human-reviewed"]
    )
    confidence_filter = search_columns[2].slider("Minimum confidence", 0.0, 1.0, 0.0, 0.05)
    matches = db.search_records(project_id, query, status_filter, confidence_filter)
    st.caption(f"{len(matches)} result{'s' if len(matches) != 1 else ''}")
    for record in matches:
        label = record["translation"] or record["transliteration"] or record["transcription"] or record["raw_ocr"]
        with st.expander(f"{record['title']} · {record['category']} · {record['confidence']:.0%}"):
            st.write(label or "No text entered yet.")
            st.caption(
                f"Pixel ({record['pixel_x']:.0f}, {record['pixel_y']:.0f}) · {record['status']} · "
                f"{record.get('_match_type', 'all')} match · "
                f"{record['translation_provenance'] or 'no translation provenance'}"
            )
            action_columns = st.columns([1, 1, 4])
            if action_columns[0].button("Locate", key=f"locate-{record['id']}"):
                st.session_state.selected_record_id = record["id"]
                st.session_state.historical_selection = {
                    key: record[key] for key in ("pixel_x", "pixel_y", "x1", "y1", "x2", "y2") if record[key] is not None
                }
                st.success("Selected. Open the Map tab to inspect the highlighted record.")
            if action_columns[1].button("Delete", key=f"delete-{record['id']}"):
                db.delete_record(project_id, record["id"])
                if st.session_state.get("selected_record_id") == record["id"]:
                    st.session_state.pop("selected_record_id", None)
                st.rerun()
            if record.get("crop_blob"):
                st.download_button(
                    "Download source crop",
                    record["crop_blob"],
                    file_name=record.get("crop_path") or f"record-{record['id']}-crop.jpg",
                    mime="image/jpeg",
                    key=f"crop-{record['id']}",
                )


with tabs[4]:
    st.subheader("Portable project files")
    st.markdown(
        '<div class="fm-status"><strong>Backup before the app sleeps.</strong> '
        "Community Cloud may replace its local filesystem during restart or redeployment.</div>",
        unsafe_allow_html=True,
    )
    records = db.records(project_id)
    control_points = db.control_points(project_id)
    transforms = db.transformations(project_id)
    exports = st.columns(4)
    exports[0].download_button(
        "Project JSON", project_json(project, records, control_points, transforms),
        file_name=f"fra-mauro-project-{project_id}.json", mime="application/json", use_container_width=True,
    )
    exports[1].download_button(
        "Records CSV", records_csv(records), file_name=f"fra-mauro-records-{project_id}.csv",
        mime="text/csv", use_container_width=True,
    )
    exports[2].download_button(
        "Records GeoJSON", records_geojson(records), file_name=f"fra-mauro-records-{project_id}.geojson",
        mime="application/geo+json", use_container_width=True,
    )
    exports[3].download_button(
        "Complete SQLite backup", db.backup_bytes(), file_name="fra-mauro-research.sqlite3",
        mime="application/vnd.sqlite3", use_container_width=True,
    )
    st.divider()
    restore = st.file_uploader("Restore a complete SQLite backup", type=["sqlite3", "sqlite", "db"])
    confirm_restore = st.checkbox("I understand this replaces all projects currently in this app instance")
    if st.button("Restore backup", disabled=not restore or not confirm_restore):
        try:
            db.restore_bytes(restore.getvalue())
            st.session_state.clear()
            st.success("Backup restored.")
            st.rerun()
        except Exception as error:
            st.error(f"Restore rejected: {error}")


with tabs[5]:
    st.subheader("Technical basis and limitations")
    facts = pd.DataFrame(
        [
            ("Image dimensions", f"{MAP_WIDTH:,} × {MAP_HEIGHT:,} pixels"),
            ("Display orientation", MAP_ORIENTATION),
            ("Historical image CRS", MAP_CRS),
            ("Modern control-point CRS", "WGS84 / EPSG:4326"),
            ("Included transformation", "2D affine, fitted by least squares"),
            ("Display derivative", "3,840 px Wikimedia thumbnail"),
            ("Full image", "Wikimedia original, approximately 890 MB"),
            ("OCR", "Tesseract experiments; never authoritative"),
            ("Persistence", "Local SQLite plus explicit backup/restore"),
        ],
        columns=["Property", "Value"],
    )
    st.dataframe(facts, hide_index=True, use_container_width=True)
    st.markdown(
        """
        **What this release does well**

        - Keeps original pixels, OCR, editorial corrections, AI suggestions, and geographic interpretations distinct.
        - Preserves the control points and diagnostics used for each saved affine solution.
        - Sends the very large original image directly to the browser instead of exhausting server memory.
        - Supports reversible, portable research through JSON, CSV, GeoJSON, and SQLite exports.

        **Known limits**

        - The research canvas uses a 3,840 px derivative. Use the linked Factum viewer for source-detail inspection and upload a crop for OCR when the derivative is insufficient.
        - The aligned browser overlay is a visual corner-envelope approximation. It is not a resampled or scientifically rectified raster.
        - Automated recognition of medieval hands and abbreviations is unreliable; human review remains essential.
        - OpenStreetMap and CartoDB availability and terms are controlled by their providers.
        - Factum's exact tile pattern and permission for automated harvesting remain unverified, so this release does not scrape its tiles.
        """
    )
    with st.expander("AI model configuration"):
        model_rows = []
        for preset in MODEL_PRESETS:
            model_rows.append(
                {
                    "Menu label": preset.label,
                    "Provider": preset.provider,
                    "Default model ID": effective_model_id(preset, st.secrets),
                    "Crop input": "Yes" if preset.supports_images else "Text only",
                    "Configured": "Yes" if configured(preset, st.secrets) else "No",
                    "Status": preset.status,
                }
            )
        st.dataframe(pd.DataFrame(model_rows), hide_index=True, use_container_width=True)

st.caption(f"{APP_NAME} v{APP_VERSION} · Research claims remain subject to human verification.")
