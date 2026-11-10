"""Which sensors a config entry creates."""

from custom_components.greenchoice.model import SensorUpdate
from custom_components.greenchoice.sensor import sensor_infos, supplied_sensors


def test_every_sensor_is_created_when_the_response_has_not_answered():
    """An unset flag must never remove an entity."""
    assert supplied_sensors(None) == list(sensor_infos)
    assert supplied_sensors(SensorUpdate()) == list(sensor_infos)


def test_absent_gas_removes_only_the_gas_sensors():
    names = supplied_sensors(SensorUpdate(has_electricity=True, has_gas=False))

    assert "gas_consumption" not in names
    assert "gas_price" not in names
    assert "electricity_consumption_total" in names


def test_absent_electricity_removes_only_the_electricity_sensors():
    names = supplied_sensors(SensorUpdate(has_electricity=False, has_gas=True))

    assert not any(name.startswith("electricity_") for name in names)
    assert "gas_consumption" in names
    assert "gas_price" in names
