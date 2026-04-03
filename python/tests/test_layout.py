from PIL import Image, ImageDraw

from reterminal.render.layout import Rect, fit_text_block


def test_rect_split_helpers_preserve_total_space():
    rect = Rect(10, 20, 300, 180)

    top, bottom = rect.split_top(60, gap=12)
    left, right = rect.split_left(120, gap=10)

    assert top == Rect(10, 20, 300, 60)
    assert bottom == Rect(10, 92, 300, 108)
    assert left == Rect(10, 20, 120, 180)
    assert right == Rect(140, 20, 170, 180)


def test_rect_columns_evenly_distribute_available_width():
    rect = Rect(0, 0, 320, 120)

    columns = rect.columns(3, gap=10)

    assert columns == [
        Rect(0, 0, 100, 120),
        Rect(110, 0, 100, 120),
        Rect(220, 0, 100, 120),
    ]


def test_fit_text_block_respects_width_height_and_line_budget():
    image = Image.new("L", (800, 480), color=255)
    draw = ImageDraw.Draw(image)
    rect = Rect(0, 0, 260, 120)

    fitted = fit_text_block(
        draw,
        "A very long headline that must shrink and wrap into a constrained region",
        rect,
        max_font_size=52,
        min_font_size=18,
        max_lines=3,
        line_spacing=6,
    )

    assert 18 <= fitted.font_size <= 52
    assert len(fitted.lines) <= 3
    assert fitted.height <= rect.height
    for line in fitted.lines:
        bbox = draw.textbbox((0, 0), line, font=fitted.font)
        assert bbox[2] - bbox[0] <= rect.width


def test_fit_text_block_ellipsizes_when_content_cannot_fit_without_truncation():
    image = Image.new("L", (800, 480), color=255)
    draw = ImageDraw.Draw(image)
    rect = Rect(0, 0, 180, 42)

    fitted = fit_text_block(
        draw,
        "This sentence is too long to fit without being truncated at the edge of the card",
        rect,
        max_font_size=28,
        min_font_size=16,
        max_lines=1,
        line_spacing=4,
    )

    assert len(fitted.lines) == 1
    assert fitted.height <= rect.height
    assert fitted.overflowed is True
    assert fitted.lines[0].endswith("…")


def test_fit_text_block_reduces_line_budget_to_match_box_height():
    image = Image.new("L", (800, 480), color=255)
    draw = ImageDraw.Draw(image)
    rect = Rect(0, 0, 220, 40)

    fitted = fit_text_block(
        draw,
        "Two lines would normally fit this width but the height budget only allows one line",
        rect,
        max_font_size=24,
        min_font_size=16,
        max_lines=3,
        line_spacing=4,
    )

    assert len(fitted.lines) == 1
    assert fitted.height <= rect.height
