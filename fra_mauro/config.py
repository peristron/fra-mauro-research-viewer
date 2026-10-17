from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Fra Mauro Research Viewer"
APP_VERSION = "1.0.1"

MAP_WIDTH = 60_351
MAP_HEIGHT = 60_351
MAP_ORIENTATION = "South-up"
MAP_CRS = "None (historical image pixel space)"
COMMONS_FILE_PAGE = (
    "https://commons.wikimedia.org/wiki/File:Fra_Mauro_Map_FactumArte.jpg"
)
COMMONS_ORIGINAL_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/9/97/"
    "Fra_Mauro_Map_FactumArte.jpg"
)
COMMONS_PREVIEW_URL = (
    "https://thumb.wikimedia.org/wikipedia/commons/thumb/9/97/"
    "Fra_Mauro_Map_FactumArte.jpg/3840px-Fra_Mauro_Map_FactumArte.jpg"
)
FACTUM_VIEWER_URL = (
    "https://www.highres.factum-arte.org/Fra_Mauro_Map/shared/viewer.html"
)
# Independently hosted Wikimedia-derived tiles, not Factum's blocked tile server.
CLOUDFLARE_TILE_BASE_URL = "https://fra-mauro-map-tiles.omarakhtar01.workers.dev"
CLOUDFLARE_TILE_URL = CLOUDFLARE_TILE_BASE_URL + "/tiles/{z}/{y}/{x}.jpg"
CLOUDFLARE_TILE_SIZE = 512
CLOUDFLARE_MIN_ZOOM = 0
CLOUDFLARE_MAX_ZOOM = 7
# At Leaflet CRS.Simple zoom 0, one map pixel equals one image pixel.
# The image pyramid's highest level is z=7, so tile z = map zoom + 7.
CLOUDFLARE_ZOOM_OFFSET = 7
USER_AGENT = (
    "FraMauroResearchViewer/1.0 research application "
    "(set contact in .streamlit/secrets.toml)"
)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ".runtime"
DEFAULT_DB_PATH = RUNTIME_DIR / "fra_mauro.sqlite3"
PREVIEW_CACHE_PATH = RUNTIME_DIR / "fra_mauro_3840.jpg"
CROP_DIR = RUNTIME_DIR / "crops"

@dataclass(frozen=True)
class ModelPreset:
    label: str
    provider: str
    model_id: str
    secret_name: str
    supports_images: bool
    status: str = "Available when enabled for your provider account"

MODEL_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        "Claude Opus 4.1",
        "anthropic",
        "claude-opus-4-1-20250805",
        "ANTHROPIC_API_KEY",
        True,
        "Retired by Anthropic; retained as requested and expected to fail unless proxied",
    ),
    ModelPreset("GPT-5", "openai", "gpt-5", "OPENAI_API_KEY", True),
    ModelPreset(
        "Claude Sonnet 4.5",
        "anthropic",
        "claude-sonnet-4-5-20250929",
        "ANTHROPIC_API_KEY",
        True,
    ),
    ModelPreset(
        "Gemini 2.5 Pro",
        "gemini",
        "gemini-2.5-pro",
        "GEMINI_API_KEY",
        True,
    ),
    ModelPreset(
        "Grok 4",
        "xai",
        "grok-4",
        "XAI_API_KEY",
        False,
        "Text translation enabled; use a currently documented xAI vision model for image reading",
    ),
    ModelPreset(
        "Claude Haiku 4.5",
        "anthropic",
        "claude-haiku-4-5-20251001",
        "ANTHROPIC_API_KEY",
        True,
    ),
    ModelPreset(
        "Gemini 2.5 Flash",
        "gemini",
        "gemini-2.5-flash",
        "GEMINI_API_KEY",
        True,
    ),
    ModelPreset(
        "DeepSeek 3.2",
        "deepseek",
        "deepseek-chat",
        "DEEPSEEK_API_KEY",
        False,
        "Text translation enabled; use the provider's current vision model for image reading",
    ),
    ModelPreset(
        "Kimi K2 Thinking",
        "moonshot",
        "kimi-k2-thinking",
        "MOONSHOT_API_KEY",
        False,
        "Text translation enabled; this preset is not treated as a vision model",
    ),
    ModelPreset(
        "Qwen3 Max",
        "qwen",
        "qwen3-max",
        "DASHSCOPE_API_KEY",
        False,
        "Text translation enabled; use a Qwen VL model for image reading",
    ),
)
PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "moonshot": "https://api.moonshot.ai/v1",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
}


def ensure_runtime_dirs() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    CROP_DIR.mkdir(parents=True, exist_ok=True)
