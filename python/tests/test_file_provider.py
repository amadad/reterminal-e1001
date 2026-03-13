import json

from reterminal.providers import FileSceneProvider


def test_file_provider_loads_scene_specs(tmp_path):
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "id": "agent-overview",
                        "kind": "hero",
                        "title": "Agents online",
                        "priority": 80,
                        "body": ["orb", "kara"],
                    },
                    {
                        "id": "ops-metrics",
                        "kind": "metrics",
                        "title": "Ops",
                        "metrics": [
                            {"label": "Runs", "value": "12"},
                            {"label": "Cost", "value": "$4.10"},
                        ],
                    },
                ]
            }
        )
    )

    scenes = FileSceneProvider(feed_path).fetch()

    assert [scene.id for scene in scenes] == ["agent-overview", "ops-metrics"]
    assert scenes[1].metrics[0].label == "Runs"
