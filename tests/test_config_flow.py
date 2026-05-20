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
