def test_normalize_filter_preset_deduplicates_extensions(app_env):
    # Preset normalization should:
    # - normalize extension casing
    # - enforce leading dots
    # - remove duplicates/empties
    app = app_env["app"]

    preset = app._normalize_filter_preset(
        {
            "name": "CAD Only",
            "filter_mode": "Include Only",
            "extensions": ["dwg", ".dwg", "PDF", ".pdf", ""],
        }
    )

    assert preset is not None
    assert preset["name"] == "CAD Only"
    assert preset["filter_mode"] == "Include Only"
    assert preset["extensions"] == [".dwg", ".pdf"]
