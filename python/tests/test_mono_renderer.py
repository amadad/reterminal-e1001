from reterminal.render import MonoRenderer
from reterminal.scenes import SceneSpec


def test_renderer_supports_two_day_agenda_scene():
    scene = SceneSpec(
        id="today-board",
        kind="agenda",
        title="",
        meta={
            "agenda_style": "two_day",
            "hide_header": True,
            "hide_footer": True,
            "today_label": "Today",
            "tomorrow_label": "Tomorrow",
            "today_rows": [
                {"chip": "A", "icon": "sports", "time": "3:00 PM", "title": "Baseball"},
                {"chip": "N", "icon": "health", "time": "3:45 PM", "title": "Doctor"},
            ],
            "tomorrow_rows": [
                {"chip": "L", "icon": "school", "time": "7:50 AM", "title": "Play Group"},
            ],
            "dinner_label": "Dinner",
            "dinner_value": "Chicken kebabs",
            "dinner_icon": "food",
        },
    )

    image = MonoRenderer().render(scene)

    assert image.size == (800, 480)
    assert image.mode == "1"


def test_renderer_supports_grouped_agenda_scene():
    scene = SceneSpec(
        id="upcoming-board",
        kind="agenda",
        title="Upcoming",
        meta={
            "agenda_style": "grouped",
            "hide_header": True,
            "hide_footer": True,
            "sections": [
                {
                    "label": "Fri",
                    "rows": [
                        {"chip": "H", "icon": "faith", "time": "4:00 PM", "title": "Quran"},
                    ],
                },
                {
                    "label": "Sat",
                    "rows": [
                        {"chip": "F", "icon": "family", "time": "All day", "title": "Family Trip"},
                    ],
                },
            ],
        },
    )

    image = MonoRenderer().render(scene)

    assert image.size == (800, 480)
    assert image.mode == "1"
