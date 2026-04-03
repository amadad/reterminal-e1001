from PIL import ImageStat

from reterminal.render.bitmap import generate_bitmap


def test_generate_bitmap_supports_sparkline_specs():
    image = generate_bitmap({"kind": "sparkline", "values": [3, 7, 5, 9, 4, 11, 8]}, 320, 120)

    assert image.size == (320, 120)
    assert image.mode == "L"
    stat = ImageStat.Stat(image)
    assert stat.extrema[0][0] < 255


def test_generate_bitmap_supports_bar_specs():
    image = generate_bitmap({"kind": "bars", "values": [12, 5, 9, 15, 7]}, 320, 120)

    assert image.size == (320, 120)
    assert image.mode == "L"
    stat = ImageStat.Stat(image)
    assert stat.extrema[0][0] < 255
