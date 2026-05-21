import importlib
import inspect
import os
import sys
import types

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

@pytest.fixture
def energa_web_version():
    return "2.5.5.eb1dde25"

@pytest.fixture
def sample_page_output():
    with open("tests/licznik_g12w.html", "r") as f:
        return f.read()

@pytest.fixture
def sample_readings(sample_page_output):
    from energa2mqtt import get_meter_readings
    return get_meter_readings(sample_page_output)

@pytest.fixture
def sample_config():
    from energa2mqtt import AppConfig
    return AppConfig.load("energa2mqtt_example.json")


def test_energa2mqtt_importable():
    module = importlib.import_module("energa2mqtt")
    assert isinstance(module, types.ModuleType)


def test_energa2mqtt_module_file():
    module = importlib.import_module("energa2mqtt")
    assert module.__file__ is not None
    assert os.path.basename(module.__file__) == "energa2mqtt.py"


def test_energa2mqtt_has_entrypoint():
    module = importlib.import_module("energa2mqtt")
    assert any(callable(getattr(module, name, None)) for name in ("main", "run", "cli"))


def test_energa2mqtt_main_signature():
    module = importlib.import_module("energa2mqtt")
    main = getattr(module, "main", None)
    if main is None:
        pytest.skip("energa2mqtt does not define main()")

    assert callable(main)
    params = inspect.signature(main).parameters
    assert len(params) <= 1


def test_read_config(sample_config):
    from energa2mqtt import AppConfig
    config = sample_config
    assert isinstance(config, AppConfig)
    assert config.mqtt_config is not None
    assert config.accounts is not None and isinstance(config.accounts, list)
    assert config.logging.verbose is not None
    assert config.logging.log is not None
    assert config.logging.log_date_format is not None
    assert config.logging.log_to_screen is not None
    assert config.energa_access.ssl_verify is not None and isinstance(config.energa_access.ssl_verify, bool)
    assert config.energa_access.login_url is not None
    assert config.energa_access.logout_url is not None
    assert config.energa_access.data_url is not None
    assert config.energa_access.payload is not None and isinstance(config.energa_access.payload, dict)
    assert config.energa_access.headers is not None


def test_mqtt_config(sample_config):
    config = sample_config
    mqtt_config = config.mqtt_config
    assert isinstance(mqtt_config, dict)
    assert "mqtt_broker" in mqtt_config and isinstance(mqtt_config["mqtt_broker"], str) and mqtt_config["mqtt_broker"] != ""
    assert "mqtt_broker_port" in mqtt_config and isinstance(mqtt_config["mqtt_broker_port"], int) and 0 < mqtt_config["mqtt_broker_port"] < 65536
    assert "mqtt_topic_name" in mqtt_config and isinstance(mqtt_config["mqtt_topic_name"], str) and mqtt_config["mqtt_topic_name"] != ""
    assert "mqtt_topic_supplier_info" in mqtt_config and isinstance(mqtt_config["mqtt_topic_supplier_info"], str) and mqtt_config["mqtt_topic_supplier_info"] != ""
    assert "mqtt_clientid" in mqtt_config and isinstance(mqtt_config["mqtt_clientid"], str) and mqtt_config["mqtt_clientid"] != ""
    assert "mqtt_retain_flag" in mqtt_config and isinstance(mqtt_config["mqtt_retain_flag"], bool)


def test_energa_config(sample_config):
    config = sample_config
    energa_config = config.energa_access
    assert isinstance(energa_config["login_url"], str) and energa_config["login_url"].startswith("http")
    assert isinstance(energa_config["logout_url"], str) and energa_config["logout_url"].startswith("http")
    assert isinstance(energa_config["data_url"], str) and energa_config["data_url"].startswith("http")
    assert isinstance(energa_config["payload"], dict)
    assert isinstance(energa_config["headers"], dict)


def test_get_meter_readings_at_least_one_tariff(sample_page_output):
    from energa2mqtt import get_meter_readings
    readings = get_meter_readings(sample_page_output)
    assert isinstance(readings, dict)
    keys = readings.keys()
    # at least one tariff should be present
    assert "a_plus" in keys and isinstance(readings["a_plus"], dict)
    assert "a_minus" in keys and isinstance(readings["a_minus"], dict)


def test_meter_readings_values(sample_readings):
    readings = sample_readings
    keys = readings.keys()

    for key in keys - {"supplier_info"}:
        assert "name" in readings[key] and isinstance(readings[key]["name"], str)
        assert "description" in readings[key] and isinstance(readings[key]["description"], str)
        assert "last_update" in readings[key] and isinstance(readings[key]["last_update"], str)
        assert "last_refresh" in readings[key] and isinstance(readings[key]["last_refresh"], str)
        assert "value" in readings[key] and isinstance(readings[key]["value"], (int, float))
        assert "unit" in readings[key] and isinstance(readings[key]["unit"], str)

    assert "a_minus" in readings and "value" in readings["a_minus"] and isinstance(readings["a_minus"]["value"], (int, float))
    assert "a_plus" in readings and "value" in readings["a_plus"] and isinstance(readings["a_plus"]["value"], (int, float))

    if "a_plus_strefa_2" in keys:
        assert "value" in readings["a_plus_strefa_2"] and isinstance(readings["a_plus_strefa_2"]["value"], (int, float))
    if "a_minus_strefa_2" in keys:
        assert "value" in readings["a_minus_strefa_2"] and isinstance(readings["a_minus_strefa_2"]["value"], (int, float))

def test_energa_operator_app_web_version(sample_page_output, energa_web_version):
    from bs4 import BeautifulSoup
    readings = sample_page_output
    web_version = None
    soup = BeautifulSoup(readings, "lxml")
    footer_details = soup.find("div", class_="footer", id="footer")
    if footer_details is not None:
        version_div = footer_details.find("div")
        if version_div:
            web_version = version_div.text.strip().split()[1].strip()
    assert web_version == energa_web_version
