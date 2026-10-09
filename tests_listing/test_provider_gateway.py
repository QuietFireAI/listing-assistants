"""Tests for External Provider Gateway and BYOK Integration Registry."""
import json
import os
import tempfile
import pytest
from dispatcher.provider_gateway import ProviderGateway


def test_provider_gateway_template_loading():
    gw = ProviderGateway()
    assert "real_estate_ecosystem" in gw.registry
    assert "workplace_suites" in gw.registry
    assert "digital_signature_and_escrow" in gw.registry
    assert "mobile_communication_channels" in gw.registry

    assert gw.is_service_enabled("real_estate_ecosystem", "zillow") is False
    assert gw.is_service_enabled("workplace_suites", "google_workspace") is False


def test_provider_gateway_secret_masking():
    gw = ProviderGateway()
    # Unconfigured template placeholders
    assert gw.mask_secret("YOUR_ZILLOW_BRIDGE_API_KEY") == "UNCONFIGURED"
    assert gw.mask_secret("") == "UNCONFIGURED"

    # Real secret masking
    masked = gw.mask_secret("sk_live_1234567890abcdef")
    assert masked == "sk_...def"
    assert "1234567890" not in masked

    # Short secret
    assert gw.mask_secret("short") == "***REDACTED***"


def test_provider_gateway_active_services_and_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        conf_path = os.path.join(tmpdir, "integrations.json")
        sample_conf = {
            "real_estate_ecosystem": {
                "zillow": {
                    "enabled": True,
                    "bridge_interactive_api_key": "live_bridge_key_9999",
                    "syndication_auto_push": True
                },
                "redfin": {
                    "enabled": False
                }
            },
            "workplace_suites": {
                "google_workspace": {
                    "enabled": True,
                    "client_id": "google_client_id_secret_123",
                    "authorized_user_email": "broker@test.com"
                }
            }
        }
        with open(conf_path, "w", encoding="utf-8") as f:
            json.dump(sample_conf, f)

        gw = ProviderGateway(config_path=conf_path)
        assert gw.is_service_enabled("real_estate_ecosystem", "zillow") is True
        assert gw.is_service_enabled("real_estate_ecosystem", "redfin") is False
        assert gw.is_service_enabled("workplace_suites", "google_workspace") is True
        assert gw.get_active_providers_count() == 2

        sanitized = gw.get_sanitized_status()
        zillow_sanitized = sanitized["real_estate_ecosystem"]["zillow"]
        assert zillow_sanitized["bridge_interactive_api_key"].startswith("liv...")
        assert zillow_sanitized["syndication_auto_push"] is True

        summary = gw.generate_onboarding_summary()
        assert "Active Connected Services: 2" in summary
        assert "**ZILLOW**: 🟢 CONNECTED" in summary
        assert "**REDFIN**: ⚪ UNCONFIGURED" in summary
        assert "**GOOGLE_WORKSPACE**: 🟢 CONNECTED" in summary
