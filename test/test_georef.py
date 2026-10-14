import pytest

from fra_mauro.georef import distribution_warnings, fit_affine


def test_affine_recovers_known_mapping():
    points = []
    for index, (x, y) in enumerate(((0, 0), (100, 0), (0, 100), (100, 100))):
        points.append(
            {
                "id": index,
                "pixel_x": x,
                "pixel_y": y,
                "longitude": 0.1 * x + 0.02 * y - 10,
                "latitude": -0.03 * x + 0.08 * y + 40,
                "enabled": True,
            }
        )
    result = fit_affine(points)
    lon, lat = result.transform(25, 75)
    assert lon == pytest.approx(-6.0)
    assert lat == pytest.approx(45.25)
    assert result.max_error_m < 0.001


def test_affine_rejects_collinear_points():
    points = [
        {"pixel_x": value, "pixel_y": value, "longitude": value, "latitude": value, "enabled": True}
        for value in (0, 1, 2)
    ]
    with pytest.raises(ValueError, match="collinear"):
        fit_affine(points)


def test_distribution_warns_for_three_clustered_points():
    points = [
        {"pixel_x": x, "pixel_y": y, "enabled": True}
        for x, y in ((10, 10), (20, 10), (10, 20))
    ]
    warnings = distribution_warnings(points, 1000, 1000)
    assert len(warnings) == 2
