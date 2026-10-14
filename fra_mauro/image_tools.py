from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .config import COMMONS_PREVIEW_URL, MAP_HEIGHT, MAP_WIDTH, USER_AGENT


LOGGER = logging.getLogger(__name__)
MAX_PREVIEW_BYTES = 80 * 1024 * 1024


@dataclass(frozen=True)
class OCRResult:
    method: str
    rotation: int
    text: str


def download_preview(
    destination: Path,
    url: str = COMMONS_PREVIEW_URL,
    contact: str = "",
    progress: Callable[[int], None] | None = None,
) -> Path:
    import requests

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 100_000:
        return destination

    headers = {"User-Agent": f"{USER_AGENT} {contact}".strip()}
    temporary = destination.with_suffix(".download")
    try:
        with requests.get(url, headers=headers, stream=True, timeout=(10, 90)) as response:
            response.raise_for_status()
            expected = int(response.headers.get("content-length", 0))
            if expected > MAX_PREVIEW_BYTES:
                raise ValueError("Preview is unexpectedly large; download cancelled.")
            received = 0
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > MAX_PREVIEW_BYTES:
                        raise ValueError("Preview exceeded the safety size limit.")
                    handle.write(chunk)
                    if progress and expected:
                        progress(min(100, int(received * 100 / expected)))
        with Image.open(temporary) as image:
            image.verify()
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def open_image(payload: bytes | Path) -> Image.Image:
    source = io.BytesIO(payload) if isinstance(payload, bytes) else payload
    image = Image.open(source)
    image.load()
    return image.convert("RGB")


def crop_preview_from_full_pixels(
    image: Image.Image, x1: float, y1: float, x2: float, y2: float
) -> Image.Image:
    left, right = sorted((max(0.0, x1), min(float(MAP_WIDTH), x2)))
    top, bottom = sorted((max(0.0, y1), min(float(MAP_HEIGHT), y2)))
    if right - left < 5 or bottom - top < 5:
        raise ValueError("The selected region is too small.")
    scale_x = image.width / MAP_WIDTH
    scale_y = image.height / MAP_HEIGHT
    box = (
        round(left * scale_x),
        round(top * scale_y),
        round(right * scale_x),
        round(bottom * scale_y),
    )
    return image.crop(box)


def preprocess(image: Image.Image, method: str, scale: int = 2) -> Image.Image:
    working = image.convert("RGB")
    if scale > 1:
        working = working.resize(
            (working.width * scale, working.height * scale), Image.Resampling.LANCZOS
        )
    if method == "colour sharpen":
        return ImageEnhance.Sharpness(working).enhance(1.8)
    gray = ImageOps.grayscale(working)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    if method == "grayscale":
        return gray.filter(ImageFilter.SHARPEN)
    if method == "adaptive contrast":
        return ImageEnhance.Contrast(gray).enhance(2.1).filter(ImageFilter.SHARPEN)
    if method == "red ink isolation":
        array = np.asarray(working, dtype=np.int16)
        score = array[:, :, 0] - ((array[:, :, 1] + array[:, :, 2]) // 2)
        normalized = np.clip(255 - (score + 30) * 3, 0, 255).astype(np.uint8)
        return Image.fromarray(normalized, mode="L")
    if method == "blue ink isolation":
        array = np.asarray(working, dtype=np.int16)
        score = array[:, :, 2] - ((array[:, :, 0] + array[:, :, 1]) // 2)
        normalized = np.clip(255 - (score + 20) * 3, 0, 255).astype(np.uint8)
        return Image.fromarray(normalized, mode="L")
    if method == "threshold":
        return gray.point(lambda value: 255 if value > 155 else 0)
    raise ValueError(f"Unknown preprocessing method: {method}")


def run_tesseract(
    image: Image.Image,
    methods: list[str],
    rotations: list[int],
    language: str = "lat+eng",
) -> list[OCRResult]:
    import pytesseract

    results: list[OCRResult] = []
    for method in methods:
        prepared = preprocess(image, method)
        for rotation in rotations:
            rotated = prepared.rotate(rotation, expand=True, fillcolor="white")
            try:
                text = pytesseract.image_to_string(
                    rotated,
                    lang=language,
                    config="--oem 1 --psm 6 -c preserve_interword_spaces=1",
                    timeout=60,
                ).strip()
            except (RuntimeError, pytesseract.TesseractError) as error:
                LOGGER.warning("Tesseract failed for %s/%s: %s", method, rotation, error)
                text = ""
            results.append(OCRResult(method=method, rotation=rotation, text=text))
    return results


def image_to_jpeg_bytes(image: Image.Image, quality: int = 94) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def safe_crop_name(image_bytes: bytes) -> str:
    return f"crop-{hashlib.sha256(image_bytes).hexdigest()[:16]}.jpg"
