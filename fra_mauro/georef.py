from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Iterable

import numpy as np


EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class AffineResult:
    coefficients: tuple[float, float, float, float, float, float]
    predicted: list[tuple[float, float]]
    residuals_m: list[float]
    rmse_m: float
    mean_error_m: float
    max_error_m: float
    rank: int
    condition_number: float

    def transform(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.coefficients
        return a * x + b * y + c, d * x + e * y + f


def haversine_m(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> float:
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    value = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(value)))


def fit_affine(points: Iterable[dict]) -> AffineResult:
    enabled = [point for point in points if point.get("enabled", True)]
    if len(enabled) < 3:
        raise ValueError("At least three enabled control points are required.")

    design = np.array(
        [[float(p["pixel_x"]), float(p["pixel_y"]), 1.0] for p in enabled],
        dtype=float,
    )
    if np.linalg.matrix_rank(design) < 3:
        raise ValueError("Control points must not be collinear or duplicated.")

    targets = np.array(
        [[float(p["longitude"]), float(p["latitude"])] for p in enabled],
        dtype=float,
    )
    parameters, _, rank, singular = np.linalg.lstsq(design, targets, rcond=None)
    prediction = design @ parameters
    residuals = [
        haversine_m(actual[0], actual[1], estimate[0], estimate[1])
        for actual, estimate in zip(targets, prediction, strict=True)
    ]
    coefficients = (
        float(parameters[0, 0]),
        float(parameters[1, 0]),
        float(parameters[2, 0]),
        float(parameters[0, 1]),
        float(parameters[1, 1]),
        float(parameters[2, 1]),
    )
    condition = float(singular[0] / singular[-1]) if singular[-1] else float("inf")
    return AffineResult(
        coefficients=coefficients,
        predicted=[(float(row[0]), float(row[1])) for row in prediction],
        residuals_m=residuals,
        rmse_m=float(sqrt(sum(value * value for value in residuals) / len(residuals))),
        mean_error_m=float(sum(residuals) / len(residuals)),
        max_error_m=float(max(residuals)),
        rank=int(rank),
        condition_number=condition,
    )


def distribution_warnings(points: Iterable[dict], width: int, height: int) -> list[str]:
    enabled = [point for point in points if point.get("enabled", True)]
    warnings: list[str] = []
    if len(enabled) < 3:
        return ["Fewer than three enabled points: an affine transform cannot be fitted."]

    xs = [float(point["pixel_x"]) for point in enabled]
    ys = [float(point["pixel_y"]) for point in enabled]
    coverage_x = (max(xs) - min(xs)) / width
    coverage_y = (max(ys) - min(ys)) / height
    if coverage_x < 0.2 or coverage_y < 0.2:
        warnings.append(
            "Control points are clustered; predictions outside their area are extrapolations."
        )
    if len(enabled) == 3:
        warnings.append(
            "Three points fit an affine transform exactly, so residuals cannot reveal overfitting."
        )
    return warnings


def normalized_to_pixel(x: float, y: float, width: int, height: int) -> tuple[int, int]:
    return round(x * width), round(y * height)


def pixel_to_normalized(x: float, y: float, width: int, height: int) -> tuple[float, float]:
    return x / width, y / height
