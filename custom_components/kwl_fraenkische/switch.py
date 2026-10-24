"""Switch-Plattform: nur für profi-air 140/200 lite (REST, experimentell).

Touch- und flex/flat-Einträge forwarden diese Plattform nicht (siehe
``PLATFORMS`` / ``PLATFORMS_LITE`` in ``__init__.py``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import KWLConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .lite_entities import async_setup_lite_switches

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    await async_setup_lite_switches(entry.runtime_data, async_add_entities)
