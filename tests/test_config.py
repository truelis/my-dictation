from dictation import config


def test_round_trip_and_private_permissions(tmp_path):
    path = tmp_path / "config.json"
    config.save(config.Config(groq_api_key="secret", hotkey="fn", vocabulary=["Groq"]), path)

    loaded = config.load(path)

    assert loaded.groq_api_key == "secret"
    assert loaded.hotkey_spec() == config.HOTKEYS["fn"]
    assert loaded.vocabulary == ["Groq"]
    assert path.stat().st_mode & 0o777 == 0o600


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"hotkey": "right_command", "old_setting": 1}')
    assert config.load(path).hotkey == "right_command"


def test_env_var_overrides_saved_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    assert config.Config(groq_api_key="saved").api_key() == "from-env"


def test_unknown_hotkey_falls_back_to_right_option():
    assert config.Config(hotkey="nope").hotkey_spec() == config.HOTKEYS["right_option"]
