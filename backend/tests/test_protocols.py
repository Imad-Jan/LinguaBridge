from app.providers.gemini import GEMINI_MODEL, gemini_setup_payload
from app.providers.soniox import soniox_stt_config, soniox_tts_config


def test_gemini_live_translate_setup_matches_documented_shape():
    payload = gemini_setup_payload("ur", True)
    setup = payload["setup"]
    config = setup["generationConfig"]
    assert setup["model"] == f"models/{GEMINI_MODEL}"
    assert config["responseModalities"] == ["AUDIO"]
    assert config["translationConfig"] == {
        "targetLanguageCode": "ur",
        "echoTargetLanguage": True,
    }
    assert config["inputAudioTranscription"] == {}
    assert config["outputAudioTranscription"] == {}


def test_soniox_twilio_input_uses_native_mulaw():
    payload = soniox_stt_config(
        api_key="secret",
        source_language="en",
        target_language="ur",
        input_format="mulaw",
    )
    assert payload["audio_format"] == "mulaw"
    assert payload["sample_rate"] == 8_000
    assert payload["num_channels"] == 1
    assert payload["translation"]["target_language"] == "ur"


def test_soniox_twilio_output_uses_native_pcm_mulaw():
    payload = soniox_tts_config(
        api_key="secret",
        stream_id="stream-1",
        language="en",
        voice="Maya",
        output_format="pcm_mulaw",
    )
    assert payload["audio_format"] == "pcm_mulaw"
    assert payload["sample_rate"] == 8_000
    assert payload["stream_id"] == "stream-1"

