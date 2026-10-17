from __future__ import annotations

from typing import Any

import folium
from branca.element import MacroElement
from folium import plugins
from jinja2 import Template

from .config import (
    CLOUDFLARE_TILE_URL,
    CLOUDFLARE_TILE_SIZE,
    CLOUDFLARE_ZOOM_OFFSET,
    COMMONS_PREVIEW_URL,
    MAP_HEIGHT,
    MAP_WIDTH,
)
from .georef import AffineResult


class FlickerOverlay(MacroElement):
    _template = Template(
        """
        {% macro script(this, kwargs) %}
        let {{ this.get_name() }}_visible = true;
        setInterval(function() {
            {{ this.get_name() }}_visible = !{{ this.get_name() }}_visible;
            {{ this.overlay_name }}.setOpacity({{ this.get_name() }}_visible ? {{ this.opacity }} : 0);
        }, {{ this.interval }});
        {% endmacro %}
        """
    )

    def __init__(self, overlay_name: str, opacity: float, interval: int = 700):
        super().__init__()
        self._name = "FlickerOverlay"
        self.overlay_name = overlay_name
        self.opacity = opacity
        self.interval = interval


class HistoricalTileLayer(MacroElement):
    """Native CRS.Simple Leaflet tiles with a seven-level URL zoom offset.

    The Wikimedia-derived pyramid uses 512 px tiles, z=0..7. At CRS.Simple
    map zoom 0 the image is 60,351 px wide, corresponding to pyramid z=7.
    Leaflet handles tile x/y natively; the offset changes only the URL zoom.
    Historical Leaflet latitude is NEGATIVE pixel_y, placing the tile
    pyramid origin at the upper-left and keeping all tile indices positive.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.tileLayer(
            {{ this.url | tojson }},
            {
                tileSize: {{ this.tile_size }},
                zoomOffset: {{ this.zoom_offset }},
                minZoom: {{ this.min_zoom }},
                maxZoom: {{ this.max_zoom }},
                minNativeZoom: {{ this.min_zoom }},
                maxNativeZoom: {{ this.max_zoom }},
                noWrap: true,
                bounds: [[-{{ this.height }}, 0], [0, {{ this.width }}]],
                opacity: {{ this.opacity }},
                attribution: 'Map source: Wikimedia Commons',
                errorTileUrl: ''
            }
        ).addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, opacity: float = 1.0):
        super().__init__()
        self._name = "HistoricalTileLayer"
        self.url = CLOUDFLARE_TILE_URL
        self.tile_size = CLOUDFLARE_TILE_SIZE
        self.zoom_offset = CLOUDFLARE_ZOOM_OFFSET
        self.min_zoom = -CLOUDFLARE_ZOOM_OFFSET
        self.max_zoom = 0
        self.width = MAP_WIDTH
        self.height = MAP_HEIGHT
        self.opacity = max(0.0, min(1.0, float(opacity)))


def historical_map(
    records: list[dict[str, Any]],
    control_points: list[dict[str, Any]],
    opacity: float = 1.0,
    selected_record_id: int | None = None,
) -> folium.Map:
    center = [-MAP_HEIGHT / 2, MAP_WIDTH / 2]
    fmap = folium.Map(
        location=center,
        crs="Simple",
        zoom_start=-4,
        min_zoom=-8,
        max_zoom=0,
        tiles=None,
        control_scale=False,
        prefer_canvas=True,
    )
    # CRS.Simple projects y = -latitude. Negative latitude therefore makes
    # historical pixel_y increase downwards from the upper-left (0, 0).
    # Keep the preview underneath for a useful fallback while tiles load.
    # The overlay can be disabled from Leaflet's layer menu if necessary.
    preview = folium.raster_layers.ImageOverlay(
        image=COMMONS_PREVIEW_URL,
        bounds=[[-MAP_HEIGHT, 0], [0, MAP_WIDTH]],
        opacity=opacity,
        interactive=True,
        cross_origin=False,
        zindex=1,
        name="Wikimedia preview fallback",
        show=True,
    )
    preview.add_to(fmap)
    HistoricalTileLayer(opacity=opacity).add_to(fmap)

    for record in records:
        selected = record["id"] == selected_record_id
        color = "#d1493f" if selected else "#2f718a"
        lat = -float(record["pixel_y"])
        lon = float(record["pixel_x"])
        folium.CircleMarker(
            [lat, lon],
            radius=7 if selected else 5,
            color=color,
            fill=True,
            fill_opacity=0.9,
            tooltip=f"{record['title']} · {record['status']}",
        ).add_to(fmap)
        if all(record.get(key) is not None for key in ("x1", "y1", "x2", "y2")):
            folium.Rectangle(
                bounds=[
                    [-float(record["y2"]), float(record["x1"])],
                    [-float(record["y1"]), float(record["x2"])],
                ],
                color=color,
                weight=2,
                fill=selected,
                fill_opacity=0.12,
            ).add_to(fmap)
    for point in control_points:
        if not point["enabled"]:
            continue
        folium.Marker(
            [-float(point["pixel_y"]), float(point["pixel_x"])],
            tooltip=f"Control point: {point['name']}",
            icon=folium.Icon(color="darkred", icon="crosshairs", prefix="fa"),
        ).add_to(fmap)
    plugins.Draw(
        export=False,
        draw_options={
            "polyline": False,
            "polygon": False,
            "circle": False,
            "circlemarker": False,
            "marker": True,
            "rectangle": {"shapeOptions": {"color": "#9f3f32", "weight": 2}},
        },
        edit_options={"edit": False, "remove": False},
    ).add_to(fmap)
    plugins.Fullscreen(position="topright").add_to(fmap)
    folium.LayerControl(collapsed=True).add_to(fmap)
    selected = next((record for record in records if record["id"] == selected_record_id), None)
    if selected and all(selected.get(key) is not None for key in ("x1", "y1", "x2", "y2")):
        fmap.fit_bounds(
            [
                [-float(selected["y2"]), float(selected["x1"])],
                [-float(selected["y1"]), float(selected["x2"])],
            ],
            padding=(80, 80),
        )
    elif selected:
        fmap.location = [-float(selected["pixel_y"]), float(selected["pixel_x"])]
        fmap.options["zoom"] = 0
    else:
        fmap.location = center
        fmap.options["zoom"] = -4
    return fmap


def extract_historical_selection(map_state: dict[str, Any] | None) -> dict[str, float] | None:
    if not map_state:
        return None
    drawing = map_state.get("last_active_drawing")
    if drawing and drawing.get("geometry", {}).get("type") == "Polygon":
        coordinates = drawing["geometry"]["coordinates"][0]
        xs = [float(item[0]) for item in coordinates]
        ys = [-float(item[1]) for item in coordinates]
        return {
            "x1": max(0.0, min(xs)),
            "y1": max(0.0, min(ys)),
            "x2": min(float(MAP_WIDTH), max(xs)),
            "y2": min(float(MAP_HEIGHT), max(ys)),
            "pixel_x": sum(xs) / len(xs),
            "pixel_y": sum(ys) / len(ys),
        }
    clicked = map_state.get("last_clicked")
    if clicked:
        return {
            "pixel_x": min(float(MAP_WIDTH), max(0.0, float(clicked["lng"]))),
            "pixel_y": min(float(MAP_HEIGHT), max(0.0, -float(clicked["lat"]))),
        }
    return None


def modern_map(
    control_points: list[dict[str, Any]],
    result: AffineResult | None = None,
    tiles: str = "OpenStreetMap",
    projection: str = "Web Mercator (EPSG:3857)",
) -> folium.Map:
    enabled = [point for point in control_points if point["enabled"]]
    center = [20.0, 10.0]
    if enabled:
        center = [
            sum(float(point["latitude"]) for point in enabled) / len(enabled),
            sum(float(point["longitude"]) for point in enabled) / len(enabled),
        ]
    tile_name = "CartoDB positron" if tiles == "CartoDB Positron" else "OpenStreetMap"
    geographic = projection.startswith("WGS84")
    fmap = folium.Map(
        location=center,
        zoom_start=2,
        tiles=None if geographic else tile_name,
        crs="EPSG4326" if geographic else "EPSG3857",
        control_scale=True,
    )
    prediction = result.predicted if result else []
    for index, point in enumerate(enabled):
        actual = [float(point["latitude"]), float(point["longitude"])]
        folium.Marker(
            actual,
            tooltip=f"Actual reference: {point['name']}",
            icon=folium.Icon(color="blue", icon="location-dot", prefix="fa"),
        ).add_to(fmap)
        if result:
            predicted_lon, predicted_lat = prediction[index]
            predicted = [predicted_lat, predicted_lon]
            error = result.residuals_m[index]
            folium.CircleMarker(
                predicted,
                radius=5,
                color="#9f3f32",
                fill=True,
                tooltip=f"Affine prediction · {error / 1000:,.1f} km residual",
            ).add_to(fmap)
            folium.PolyLine(
                [actual, predicted],
                color="#9f3f32",
                weight=2,
                opacity=0.8,
                tooltip=f"Displacement: {error / 1000:,.1f} km",
            ).add_to(fmap)
    plugins.Fullscreen(position="topright").add_to(fmap)
    return fmap


def aligned_overlay_map(
    result: AffineResult,
    opacity: float,
    mode: str,
    tiles: str = "OpenStreetMap",
    projection: str = "Web Mercator (EPSG:3857)",
) -> folium.Map:
    corners = [
        result.transform(0, 0),
        result.transform(MAP_WIDTH, 0),
        result.transform(0, MAP_HEIGHT),
        result.transform(MAP_WIDTH, MAP_HEIGHT),
    ]
    lons = [point[0] for point in corners]
    lats = [point[1] for point in corners]
    bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]
    tile_name = "CartoDB positron" if tiles == "CartoDB Positron" else "OpenStreetMap"
    geographic = projection.startswith("WGS84")
    fmap = folium.Map(
        tiles=None,
        crs="EPSG4326" if geographic else "EPSG3857",
        control_scale=True,
    )
    modern = None
    if not geographic:
        modern = folium.TileLayer(tile_name, name="Modern basemap", overlay=False)
        modern.add_to(fmap)
    historical = folium.raster_layers.ImageOverlay(
        image=COMMONS_PREVIEW_URL,
        bounds=bounds,
        opacity=opacity,
        name="Approximate historical overlay",
        zindex=10,
        cross_origin=False,
    )
    historical.add_to(fmap)
    if mode == "Swipe" and modern is not None:
        plugins.SideBySideLayers(modern, historical).add_to(fmap)
    elif mode == "Flicker":
        fmap.add_child(FlickerOverlay(historical.get_name(), opacity))
    folium.LayerControl(collapsed=False).add_to(fmap)
    fmap.fit_bounds(bounds)
    return fmap
