from learnbuddy_core.config import LearnBuddyConfig
from learnbuddy_core.delivery import DeliveryMessage, DryRunDeliveryAdapter, TelegramDeliveryAdapter, delivery_adapter_from_config


def test_config_loads_telegram_child_delivery_settings(tmp_path):
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        """
delivery:
  mode: telegram
  telegram:
    child_bot_env: LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN
    allowed_child_chat_id_env: LEARNBUDDY_ALLOWED_CHILD_CHAT_ID
""".strip(),
        encoding="utf-8",
    )

    config = LearnBuddyConfig.from_yaml(config_path)

    assert config.delivery_mode == "telegram"
    assert config.child_telegram_bot_token_env == "LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN"
    assert config.child_telegram_chat_id_env == "LEARNBUDDY_ALLOWED_CHILD_CHAT_ID"


def test_config_loads_child_delivery_shape_for_future_setup_wizard(tmp_path):
    config_path = tmp_path / "learnbuddy.yaml"
    config_path.write_text(
        """
delivery:
  child:
    type: telegram
    bot_token_env: CHILD_BOT_TOKEN_ENV
    allowed_chat_ids_env: CHILD_CHAT_ID_ENV
""".strip(),
        encoding="utf-8",
    )

    config = LearnBuddyConfig.from_yaml(config_path)

    assert config.delivery_mode == "telegram"
    assert config.child_telegram_bot_token_env == "CHILD_BOT_TOKEN_ENV"
    assert config.child_telegram_chat_id_env == "CHILD_CHAT_ID_ENV"
    assert isinstance(delivery_adapter_from_config(config), TelegramDeliveryAdapter)


def test_dry_run_delivery_adapter_returns_public_result_without_side_effects():
    adapter = DryRunDeliveryAdapter(adapter_name="telegram")

    result = adapter.deliver_child(DeliveryMessage(text="Was ist 2 + 2?", metadata={"session_id": "sess-1"}))

    assert result.status == "dry_run"
    assert result.adapter == "telegram"
    assert result.target == "child"
    assert result.message_id is None
    assert result.to_dict() == {
        "status": "dry_run",
        "adapter": "telegram",
        "target": "child",
        "message_id": None,
        "error": None,
    }


def test_telegram_delivery_adapter_uses_env_and_redacts_public_result(monkeypatch):
    calls = []

    def fake_transport(url, payload):
        calls.append((url, payload))
        return {"ok": True, "result": {"message_id": 42}}

    monkeypatch.setenv("LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("LEARNBUDDY_ALLOWED_CHILD_CHAT_ID", "12345")
    adapter = TelegramDeliveryAdapter(
        bot_token_env="LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN",
        chat_id_env="LEARNBUDDY_ALLOWED_CHILD_CHAT_ID",
        transport=fake_transport,
    )

    result = adapter.deliver_child(DeliveryMessage(text="Hallo Lernwelt"))

    assert calls == [("https://api.telegram.org/botsecret-token/sendMessage", {"chat_id": "12345", "text": "Hallo Lernwelt"})]
    assert result.status == "sent"
    assert result.adapter == "telegram"
    assert result.target == "LEARNBUDDY_ALLOWED_CHILD_CHAT_ID"
    assert result.message_id == "42"
    assert "secret-token" not in str(result.to_dict())
    assert "12345" not in str(result.to_dict())


def test_telegram_delivery_adapter_reports_missing_env_without_network(monkeypatch):
    called = False

    def fake_transport(url, payload):
        nonlocal called
        called = True
        return {"ok": True}

    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    monkeypatch.delenv("MISSING_CHAT", raising=False)
    adapter = TelegramDeliveryAdapter(bot_token_env="MISSING_TOKEN", chat_id_env="MISSING_CHAT", transport=fake_transport)

    result = adapter.deliver_child(DeliveryMessage(text="Hallo"))

    assert result.status == "not_configured"
    assert result.error == "missing environment variables: MISSING_TOKEN, MISSING_CHAT"
    assert called is False


def test_telegram_delivery_adapter_wraps_transport_exceptions_without_leaking_secrets(monkeypatch):
    def failing_transport(url, payload):
        raise ValueError("bad json near secret-token and 12345")

    monkeypatch.setenv("LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("LEARNBUDDY_ALLOWED_CHILD_CHAT_ID", "12345")
    adapter = TelegramDeliveryAdapter(
        bot_token_env="LEARNBUDDY_CHILD_TELEGRAM_BOT_TOKEN",
        chat_id_env="LEARNBUDDY_ALLOWED_CHILD_CHAT_ID",
        transport=failing_transport,
    )

    result = adapter.deliver_child(DeliveryMessage(text="Hallo"))

    assert result.status == "error"
    assert result.error == "telegram delivery failed"
    assert "secret-token" not in str(result.to_dict())
    assert "12345" not in str(result.to_dict())


def test_delivery_adapter_factory_rejects_unknown_modes():
    config = LearnBuddyConfig(delivery_mode="telegran")

    try:
        delivery_adapter_from_config(config)
    except ValueError as exc:
        assert str(exc) == "unsupported delivery mode: telegran"
    else:
        raise AssertionError("expected ValueError")
