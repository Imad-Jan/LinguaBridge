from app.twilio_service import build_stream_twiml, websocket_public_url


def test_public_https_becomes_wss():
    assert websocket_public_url("https://calls.example.com") == (
        "wss://calls.example.com"
    )


def test_twiml_has_bidirectional_stream_and_one_time_parameters():
    twiml = build_stream_twiml(
        public_base_url="https://calls.example.com",
        call_id="call-123",
        stream_token="token-456",
    )
    assert "<Connect>" in twiml
    assert 'url="wss://calls.example.com/ws/twilio"' in twiml
    assert 'name="call_id"' in twiml and 'value="call-123"' in twiml
    assert 'name="token"' in twiml and 'value="token-456"' in twiml

