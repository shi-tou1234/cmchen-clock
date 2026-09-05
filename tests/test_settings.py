import json

from settings import DEFAULTS, load_settings, normalize_color, save_settings, settings_path


class TestDefaults:
    def test_missing_file_returns_defaults(self, tmp_path):
        assert load_settings(base=tmp_path) == DEFAULTS

    def test_config_bad_json_falls_back_to_defaults(self, tmp_path):
        save_settings({"font_size": 100}, base=tmp_path)
        settings_path(base=tmp_path).write_text("{bad json!!", encoding="utf-8")
        assert load_settings(base=tmp_path) == DEFAULTS

    def test_config_bad_top_level_type_falls_back(self, tmp_path):
        settings_path(base=tmp_path).write_text('["not", "a", "dict"]', encoding="utf-8")
        assert load_settings(base=tmp_path) == DEFAULTS

    def test_missing_fields_filled_from_defaults(self, tmp_path):
        save_settings({"font_size": 100}, base=tmp_path)
        loaded = load_settings(base=tmp_path)
        assert loaded["font_size"] == 100
        for key, value in DEFAULTS.items():
            if key != "font_size":
                assert loaded[key] == value, key

    def test_wrong_types_fall_back(self, tmp_path):
        raw = {"font_size": "abc", "show_date": "yes", "opacity": "high", "pos_x": "left"}
        settings_path(base=tmp_path).write_text(json.dumps(raw), encoding="utf-8")
        loaded = load_settings(base=tmp_path)
        assert loaded["font_size"] == DEFAULTS["font_size"]
        assert loaded["show_date"] == DEFAULTS["show_date"]
        assert loaded["opacity"] == DEFAULTS["opacity"]
        assert loaded["pos_x"] is None

    def test_font_size_out_of_range_falls_back(self, tmp_path):
        save_settings({"font_size": 500}, base=tmp_path)
        assert load_settings(base=tmp_path)["font_size"] == DEFAULTS["font_size"]
        save_settings({"font_size": 7}, base=tmp_path)
        assert load_settings(base=tmp_path)["font_size"] == DEFAULTS["font_size"]

    def test_opacity_out_of_range_falls_back(self, tmp_path):
        save_settings({"opacity": 1.5}, base=tmp_path)
        assert load_settings(base=tmp_path)["opacity"] == DEFAULTS["opacity"]
        save_settings({"opacity": 0.05}, base=tmp_path)
        assert load_settings(base=tmp_path)["opacity"] == DEFAULTS["opacity"]

    def test_save_load_roundtrip(self, tmp_path):
        cfg = dict(DEFAULTS)
        cfg.update({
            "font_family": "Consolas",
            "font_size": 96,
            "color": "#00ff88",
            "show_date": False,
            "show_seconds": False,
            "hour24": False,
            "opacity": 0.5,
            "window_behavior": "floating",
            "pos_locked": True,
            "pos_x": 120,
            "pos_y": 240,
        })
        save_settings(cfg, base=tmp_path)
        loaded = load_settings(base=tmp_path)
        assert loaded["font_family"] == "Consolas"
        assert loaded["font_size"] == 96
        assert loaded["color"] == "#00FF88"
        assert loaded["show_date"] is False
        assert loaded["show_seconds"] is False
        assert loaded["hour24"] is False
        assert loaded["opacity"] == 0.5
        assert loaded["window_behavior"] == "floating"
        assert loaded["pos_locked"] is True
        assert loaded["pos_x"] == 120
        assert loaded["pos_y"] == 240


class TestNormalizeColor:
    def test_color_valid_kept_and_uppercased(self):
        assert normalize_color("#ff8800") == "#FF8800"

    def test_color_short_or_long_falls_back(self):
        assert normalize_color("#fff") == DEFAULTS["color"]
        assert normalize_color("#RRGGBBAA") == DEFAULTS["color"]

    def test_color_non_hex_falls_back(self):
        assert normalize_color("#GGHHII") == DEFAULTS["color"]
        assert normalize_color("red") == DEFAULTS["color"]
        assert normalize_color(None) == DEFAULTS["color"]

    def test_color_custom_default(self):
        assert normalize_color("oops", default="#123456") == "#123456"


class TestPathSafety:
    def test_settings_path_is_fixed_filename_in_base(self, tmp_path):
        assert settings_path(base=tmp_path) == tmp_path / "settings.json"


class TestWindowBehavior:
    def test_window_behavior_defaults_to_desktop(self, tmp_path):
        assert DEFAULTS["window_behavior"] == "desktop"
        assert load_settings(base=tmp_path)["window_behavior"] == "desktop"

    def test_window_behavior_invalid_falls_back(self, tmp_path):
        save_settings({"window_behavior": "sky"}, base=tmp_path)
        assert load_settings(base=tmp_path)["window_behavior"] == "desktop"

    def test_window_behavior_valid_kept(self, tmp_path):
        for mode in ("floating", "normal", "desktop"):
            save_settings({"window_behavior": mode}, base=tmp_path)
            assert load_settings(base=tmp_path)["window_behavior"] == mode

    def test_legacy_always_on_top_true_migrates_to_floating(self, tmp_path):
        settings_path(base=tmp_path).write_text('{"always_on_top": true}', encoding="utf-8")
        loaded = load_settings(base=tmp_path)
        assert loaded["window_behavior"] == "floating"
        assert "always_on_top" not in loaded

    def test_legacy_always_on_top_false_migrates_to_desktop(self, tmp_path):
        settings_path(base=tmp_path).write_text('{"always_on_top": false}', encoding="utf-8")
        assert load_settings(base=tmp_path)["window_behavior"] == "desktop"

    def test_window_behavior_overrides_legacy_key(self, tmp_path):
        raw = '{"window_behavior": "normal", "always_on_top": true}'
        settings_path(base=tmp_path).write_text(raw, encoding="utf-8")
        assert load_settings(base=tmp_path)["window_behavior"] == "normal"


class TestPosLocked:
    def test_pos_locked_defaults_false(self, tmp_path):
        assert DEFAULTS["pos_locked"] is False
        assert load_settings(base=tmp_path)["pos_locked"] is False

    def test_pos_locked_kept_and_coerced(self, tmp_path):
        save_settings({"pos_locked": True}, base=tmp_path)
        assert load_settings(base=tmp_path)["pos_locked"] is True
        settings_path(base=tmp_path).write_text('{"pos_locked": "yes"}', encoding="utf-8")
        assert load_settings(base=tmp_path)["pos_locked"] is False
