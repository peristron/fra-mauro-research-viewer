from PIL import Image

from fra_mauro.image_tools import crop_preview_from_full_pixels, preprocess


def test_crop_scales_full_coordinates_to_preview():
    image = Image.new("RGB", (1000, 1000), "white")
    crop = crop_preview_from_full_pixels(image, 0, 0, 30_175.5, 30_175.5)
    assert crop.size == (500, 500)


def test_all_preprocessing_modes_return_images():
    image = Image.new("RGB", (20, 10), (180, 60, 40))
    for method in (
        "colour sharpen", "grayscale", "adaptive contrast", "red ink isolation",
        "blue ink isolation", "threshold",
    ):
        result = preprocess(image, method, scale=1)
        assert result.size == image.size
