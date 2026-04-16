from PIL import Image, ImageDraw

from reterminal.encoding import pil_to_raw, raw_to_pil


def test_raw_to_pil_round_trips_device_bitmap_bytes():
    image = Image.new("1", (800, 480), color=1)
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 160, 160), fill=0)
    draw.line((0, 479, 799, 0), fill=0, width=3)

    raw = pil_to_raw(image)
    decoded = raw_to_pil(raw)

    assert decoded.size == (800, 480)
    assert decoded.mode == "1"
    assert pil_to_raw(decoded) == raw
