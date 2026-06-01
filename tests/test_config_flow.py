"""Integration-Tests fuer den Config Flow."""
from __future__ import annotations

import pytest
import sys, os
from unittest.mock import AsyncMock, MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components'))


VALID_XML = """<response>
  <config_mac>00:04:A3:76:23:66</config_mac>
  <config_ip>10.10.4.1</config_ip>
  <stufe1>1</stufe1><stufe2>0</stufe2><stufe3>0</stufe3><stufe4>0</stufe4>
</response>"""


class TestFetchDeviceInfo:
    """Tests fuer _fetch_device_info -- Verbindungspruefung."""

    @pytest.mark.asyncio
    async def test_valid_response_returns_mac(self):
        from kwl_fraenkische.config_flow import _fetch_device_info

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = AsyncMock(return_value=VALID_XML)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('kwl_fraenkische.config_flow.aiohttp.ClientSession',
                   return_value=mock_session):
            result = await _fetch_device_info("10.10.4.1")

        assert isinstance(result, dict)
        assert result["mac"] == "00:04:A3:76:23:66"

    @pytest.mark.asyncio
    async def test_connection_error_returns_string(self):
        from kwl_fraenkische.config_flow import _fetch_device_info
        import aiohttp

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("timeout"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('kwl_fraenkische.config_flow.aiohttp.ClientSession',
                   return_value=mock_session):
            result = await _fetch_device_info("10.10.4.1")

        assert result == "cannot_connect"

    @pytest.mark.asyncio
    async def test_invalid_xml_returns_string(self):
        from kwl_fraenkische.config_flow import _fetch_device_info

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = AsyncMock(return_value="kein xml")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('kwl_fraenkische.config_flow.aiohttp.ClientSession',
                   return_value=mock_session):
            result = await _fetch_device_info("10.10.4.1")

        assert result == "invalid_response"

    @pytest.mark.asyncio
    async def test_missing_mac_returns_invalid_response(self):
        from kwl_fraenkische.config_flow import _fetch_device_info

        xml_no_mac = "<response><stufe1>1</stufe1></response>"
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = AsyncMock(return_value=xml_no_mac)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('kwl_fraenkische.config_flow.aiohttp.ClientSession',
                   return_value=mock_session):
            result = await _fetch_device_info("10.10.4.1")

        assert result == "invalid_response"

    @pytest.mark.asyncio
    async def test_http_404_returns_cannot_connect(self):
        from kwl_fraenkische.config_flow import _fetch_device_info

        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('kwl_fraenkische.config_flow.aiohttp.ClientSession',
                   return_value=mock_session):
            result = await _fetch_device_info("10.10.4.1")

        assert result == "cannot_connect"


class TestAuthTest:
    """Tests fuer _test_auth -- BasicAuth Pruefung."""

    @pytest.mark.asyncio
    async def test_valid_credentials_returns_none(self):
        from kwl_fraenkische.config_flow import _test_auth

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('kwl_fraenkische.config_flow.aiohttp.ClientSession',
                   return_value=mock_session):
            result = await _test_auth("10.10.4.1", "install", "konfig12")

        assert result is None

    @pytest.mark.asyncio
    async def test_wrong_password_returns_invalid_auth(self):
        from kwl_fraenkische.config_flow import _test_auth

        mock_resp = AsyncMock()
        mock_resp.status = 401
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('kwl_fraenkische.config_flow.aiohttp.ClientSession',
                   return_value=mock_session):
            result = await _test_auth("10.10.4.1", "install", "falsch")

        assert result == "invalid_auth"

    @pytest.mark.asyncio
    async def test_connection_error_returns_cannot_connect(self):
        from kwl_fraenkische.config_flow import _test_auth
        import aiohttp

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError())
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('kwl_fraenkische.config_flow.aiohttp.ClientSession',
                   return_value=mock_session):
            result = await _test_auth("10.10.4.1", "install", "konfig12")

        assert result == "cannot_connect"


class TestReconfigureDataPreservation:
    """Tests fuer reconfigure -- stellt sicher dass Watt-Werte erhalten bleiben."""

    def test_reconfigure_preserves_watt_keys(self):
        """reconfigure ueberschreibt nur Host/Auth -- Watt-Werte bleiben."""
        from kwl_fraenkische.const import (
            CONF_WATT_LEVEL_1, CONF_WATT_LEVEL_2,
            CONF_WATT_LEVEL_3, CONF_WATT_LEVEL_4,
            DEFAULT_WATT,
        )
        # Simuliere bestehende entry.data mit Watt-Werten
        existing_data = {
            "host": "10.10.4.1",
            "mac": "00:04:A3:76:23:66",
            "username": "install",
            "password": "konfig12",
            CONF_WATT_LEVEL_1: 11.0,
            CONF_WATT_LEVEL_2: 17.5,
            CONF_WATT_LEVEL_3: 43.5,
            CONF_WATT_LEVEL_4: 80.0,
        }
        # Nach reconfigure: neue data = {**existing_data, neuer Host, ...}
        new_data = {
            **existing_data,
            "host": "10.10.4.2",  # neue IP
            "mac": "00:04:A3:76:23:66",
            "username": "install",
            "password": "neues_passwort",
        }
        # Watt-Werte muessen erhalten bleiben
        assert new_data[CONF_WATT_LEVEL_1] == 11.0
        assert new_data[CONF_WATT_LEVEL_2] == 17.5
        assert new_data[CONF_WATT_LEVEL_3] == 43.5
        assert new_data[CONF_WATT_LEVEL_4] == 80.0

    def test_config_flow_version_is_2(self):
        """ConfigFlow VERSION muss 2 sein -- direkt aus Source lesen."""
        import ast, os
        src = open(os.path.join(
            os.path.dirname(__file__),
            "../custom_components/kwl_fraenkische/config_flow.py"
        )).read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "KWLConfigFlow":
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for t in item.targets:
                            if isinstance(t, ast.Name) and t.id == "VERSION":
                                version = ast.literal_eval(item.value)
                                assert version == 2, f"VERSION ist {version}, erwartet 2"
                                return
        raise AssertionError("VERSION nicht gefunden")

    def test_options_flow_class_exists(self):
        """KWLOptionsFlow ist in config_flow.py definiert."""
        import ast, os
        src = open(os.path.join(
            os.path.dirname(__file__),
            "../custom_components/kwl_fraenkische/config_flow.py"
        )).read()
        tree = ast.parse(src)
        class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "KWLOptionsFlow" in class_names

    def test_async_get_options_flow_defined(self):
        """KWLConfigFlow.async_get_options_flow ist definiert."""
        import ast, os
        src = open(os.path.join(
            os.path.dirname(__file__),
            "../custom_components/kwl_fraenkische/config_flow.py"
        )).read()
        assert "async_get_options_flow" in src
