from __future__ import annotations

import json
from typing import Any

import folium
from branca.element import MacroElement
from folium import plugins
from folium.map import Layer
from jinja2 import Template

from .config import (
    COMMONS_PREVIEW_URL,
    FACTUM_TILED_HEIGHT,
    FACTUM_TILED_WIDTH,
    FACTUM_TILE_LEVELS,
    FACTUM_TILE_SIZE,
    FACTUM_TILES_BASE_URL,
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


class FactumTileLayer(Layer):
    """Leaflet layer for Factum's non-power-of-two krpano tile pyramid."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }}_levels = {{ this.levels | safe }};
        var {{ this.get_name() }}_pane = "{{ this.get_name() }}_pane";
        {{ this._parent.get_name() }}.createPane({{ this.get_name() }}_pane);
        {{ this._parent.get_name() }}.getPane({{ this.get_name() }}_pane).style.zIndex = 250;

        var {{ this.get_name() }}_class = L.GridLayer.extend({
            getTileSize: function() {
                var zoom = this._tileZoom;
                var specification = {{ this.get_name() }}_levels[String(zoom)];
                if (!specification) {
                    return L.GridLayer.prototype.getTileSize.call(this);
                }
                var scale = Math.pow(2, zoom);
                return L.point(
                    {{ this.tile_size }} * {{ this.full_width }} * scale / specification.width,
                    {{ this.tile_size }} * {{ this.full_height }} * scale / specification.height
                );
            },
            getTileUrl: function(coords) {
                var specification = {{ this.get_name() }}_levels[String(coords.z)];
                if (!specification) {
                    return "";
                }
                var row = String(coords.y).padStart(3, "0");
                var column = String(coords.x).padStart(3, "0");
                return {{ this.base_url | tojson }} + "/l" + specification.level + "/" + row
                    + "/l" + specification.level + "_" + row + "_" + column + ".jpg";
            },
            createTile: function(coords, done) {
                var tile = document.createElement("div");
                var image = document.createElement("img");
                image.alt = "";
                image.setAttribute("role", "presentation");
                image.style.display = "block";
                image.onload = function() {
                    image.style.width = (image.naturalWidth / {{ this.tile_size }} * 100) + "%";
                    image.style.height = (image.naturalHeight / {{ this.tile_size }} * 100) + "%";
                    done(null, tile);
                };
                image.onerror = function(error) {
                    done(error, tile);
                };
                image.src = this.getTileUrl(coords);
                tile.appendChild(image);
                return tile;
            }
        });

        var {{ this.get_name() }} = new {{ this.get_name() }}_class("", {
            minZoom: -7,
            maxZoom: 0,
            minNativeZoom: -7,
            maxNativeZoom: 0,
            tileSize: {{ this.tile_size }},
            noWrap: true,
            bounds: [[-{{ this.full_height }}, 0], [0, {{ this.full_width }}]],
            opacity: {{ this.opacity }},
            pane: {{ this.get_name() }}_pane,
            updateWhenIdle: true,
            keepBuffer: 2,
            attribution: "Fra Mauro map high-resolution imagery &amp;copy; Factum Foundation"
        }).addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, opacity: float = 1.0):
        super().__init__(
            name="Fra Mauro map (Factum high-resolution tiles)",
            overlay=True,
            control=True,
            show=True,
        )
        self.base_url = FACTUM_TILES_BASE_URL.rstrip("/")
        self.full_width = FACTUM_TILED_WIDTH
        self.full_height = FACTUM_TILED_HEIGHT
        self.tile_size = FACTUM_TILE_SIZE
        self.opacity = max(0.0, min(1.0, float(opacity)))
        self.levels = json.dumps(
            {
                str(level - 8): {
                    "level": level,
                    "width": dimensions[0],
                    "height": dimensions[1],
                }
                for level, dimensions in FACTUM_TILE_LEVELS.items()
            }
        )


def _research_to_factum(pixel_x: float, pixel_y: float) -> list[float]:
    """Convert stable research pixels to the rectangular Factum tile canvas."""

    longitude = float(pixel_x) * FACTUM_TILED_WIDTH / MAP_WIDTH
    latitude = -float(pixel_y) * FACTUM_TILED_HEIGHT / MAP_HEIGHT
    return [latitude, longitude]


def _factum_to_research(latitude: float, longitude: float) -> tuple[float, float]:
    """Convert a Factum canvas location back to stable research pixels."""

    pixel_x = float(longitude) * MAP_WIDTH / FACTUM_TILED_WIDTH
    pixel_y = -float(latitude) * MAP_HEIGHT / FACTUM_TILED_HEIGHT
    return pixel_x, pixel_y


def historical_map(
    records: list[dict[str, Any]],
    control_points: list[dict[str, Any]],
    opacity: float = 1.0,
    selected_record_id: int | None = None,
) -> folium.Map:
    center = [-FACTUM_TILED_HEIGHT / 2, FACTUM_TILED_WIDTH / 2]
    image_bounds = [[-FACTUM_TILED_HEIGHT, 0], [0, FACTUM_TILED_WIDTH]]
    fmap = folium.Map(
        location=center,
        crs="Simple",
        zoom_start=-6,
        min_zoom=-7,
        max_zoom=0,
        tiles=None,
        control_scale=False,
        prefer_canvas=True,
    )
    folium.raster_layers.ImageOverlay(
        image=COMMONS_PREVIEW_URL,
        bounds=image_bounds,
        opacity=opacity,
        interactive=True,
        cross_origin=False,
        zindex=1,
        pane="tilePane",
        name="Wikimedia display fallback",
    ).add_to(fmap)
    FactumTileLayer(opacity=opacity).add_to(fmap)

    for record in records:
        selected = record["id"] == selected_record_id
        color = "#d1493f" if selected else "#2f718a"
        lat, lon = _research_to_factum(record["pixel_x"], record["pixel_y"])
        folium.CircleMarker(
            [lat, lon],
            radius=7 if selected else 5,
            color=color,
            fill=True,
            fill_opacity=0.9,
            tooltip=f"{record['title']} · {record['status']}",
        ).add_to(fmap)
        if all(record.get(key) is not None for key in ("x1", "y1", "x2", "y2")):
            north_west = _research_to_factum(record["x1"], record["y1"])
            south_east = _research_to_factum(record["x2"], record["y2"])
            folium.Rectangle(
                bounds=[[south_east[0], north_west[1]], [north_west[0], south_east[1]]],
                color=color,
                weight=2,
                fill=selected,
                fill_opacity=0.12,
            ).add_to(fmap)

    for point in control_points:
        if not point["enabled"]:
            continue
        folium.Marker(
            _research_to_factum(point["pixel_x"], point["pixel_y"]),
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
        north_west = _research_to_factum(selected["x1"], selected["y1"])
        south_east = _research_to_factum(selected["x2"], selected["y2"])
        fmap.fit_bounds(
            [[south_east[0], north_west[1]], [north_west[0], south_east[1]]],
            padding=(80, 80),
        )
    elif selected:
        fmap.location = _research_to_factum(selected["pixel_x"], selected["pixel_y"])
        fmap.options["zoom"] = -2
    else:
        fmap.location = center
        fmap.options["zoom"] = -6
    return fmap


def extract_historical_selection(map_state: dict[str, Any] | None) -> dict[str, float] | None:
    if not map_state:
        return None
    drawing = map_state.get("last_active_drawing")
    if drawing and drawing.get("geometry", {}).get("type") == "Polygon":
        coordinates = drawing["geometry"]["coordinates"][0]
        research_coordinates = [
            _factum_to_research(float(item[1]), float(item[0])) for item in coordinates
        ]
        xs = [item[0] for item in research_coordinates]
        ys = [item[1] for item in research_coordinates]
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
        pixel_x, pixel_y = _factum_to_research(clicked["lat"], clicked["lng"])
        return {
            "pixel_x": min(float(MAP_WIDTH), max(0.0, pixel_x)),
            "pixel_y": min(float(MAP_HEIGHT), max(0.0, pixel_y)),
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
