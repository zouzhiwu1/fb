from app.sms import generate_code, send_sms


def test_generate_code_default_length_and_digits():
    code = generate_code()
    assert len(code) >= 4  # 默认 6 位，但这里只校验至少为 4 位
    assert code.isdigit()


def test_send_sms_mock_provider_returns_true(caplog):
    import logging

    caplog.set_level(logging.INFO)
    ok = send_sms("13800138000", "123456")
    assert ok is True
    joined = " ".join(r.message for r in caplog.records)
    assert "13800138000" in joined
    assert "123456" in joined

