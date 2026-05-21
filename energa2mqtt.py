#!/usr/bin/env python

# -------------------------------------------------------------------------------
# Name:        Energa - Mój licznik - scrapping integration
# Purpose:     Integration with mqtt/home assistant
#
# Author:      arabiczko@gmail.com
#
# Created:     2022-06-30
# Licence:     GPL
# -------------------------------------------------------------------------------

import json
import logging
import queue
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
import requests
from bs4 import BeautifulSoup
from paho.mqtt.enums import CallbackAPIVersion

logger = logging.getLogger(__name__)
mqtt_auth_result = queue.Queue()

class ConfigDict(dict):
    def __init__(self, defaults: dict):
        super().__init__(defaults)
        self._defaults = defaults

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"Key not found: '{key}'")

    def get(self, key, default=None):
        return super().get(key, default if default is not None else self._defaults.get(key))

    def reset(self):
        """Restore default values."""
        self.clear()
        self.update(self._defaults)

@dataclass
class AppConfig:
    energa_web_version: str = "2.5.5.eb1dde25"

    logging: ConfigDict = field(default_factory=lambda: ConfigDict({
        "verbose": False,
        "log": "",
        "log_date_format": "%Y-%m-%d %H:%M:%S",
        "log_to_screen": False
    }))

    energa_access: ConfigDict = field(default_factory=lambda: ConfigDict({
        "ssl_verify": True,
        "login_url": "https://mojlicznik.energa-operator.pl/dp/UserLogin.do",
        "logout_url": "https://mojlicznik.energa-operator.pl/dp/MainLogout.go",
        "data_url": "https://mojlicznik.energa-operator.pl/dp/UserData.do",
        "payload": {
            "j_username": "",
            "j_password": "",
            "selectedForm": "1",
            "save": "save",
            "clientOS": "web",
            "loginNow": "zaloguj+się",
            "_antixsrf": "invalid",
        },
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:102.0) Gecko/20100101 Firefox/102.0"
        }
        }))

    mqtt_config: ConfigDict = field(default_factory=lambda: ConfigDict({
        "mqtt_clientid": "energa2mqtt_client",
        "mqtt_retain_flag": True,
        "mqtt_broker": "mqtt.broker.address.local",
        "mqtt_broker_port": 1883,
        "mqtt_username": None,
        "mqtt_password": None,
        "mqtt_topic_name": "home/mojlicznik/{}/{}",
        "mqtt_topic_supplier_info": "home/mojlicznik/{}/supplier_info"
    },
    ))
    accounts: list = field(default_factory=lambda: [
        {
            "name": "my home account",
            "active": False,
            "username": "",
            "password": ""
        }
    ])

    @classmethod
    def load(cls, config_path: str | Path = "energa2mqtt.json") -> "AppConfig":
        instance = cls()

        try:
            with Path(config_path).open(encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {config_path}")
            return instance

        for section, values in data.items():
            if not hasattr(instance, section):
                raise KeyError(f"Unknown section: '{section}'")

            target = getattr(instance, section)

            if isinstance(target, ConfigDict):
                # validate keys and overwrite values from JSON
                unknown = values.keys() - target._defaults.keys()
                if unknown:
                    raise KeyError(f"Unknown keys in section '{section}': {unknown}")
                target.update(values)
            else:
                # normal field
                setattr(instance, section, values)

        return instance

def create_counter_record(name, description, last_update, last_refresh, value):
    return {
        "name": name,
        "description": description,
        "last_update": last_update,
        "last_refresh": last_refresh,
        "value": value,
        "unit": "kWh",
    }

def get_web_version(html):
    web_version = None
    soup = BeautifulSoup(html, "lxml")
    footer_details = soup.find("div", class_="footer", id="footer")
    if footer_details is not None:
        version_div = footer_details.find("div")
        if version_div:
            web_version = version_div.text.strip().split()[1].strip()
    
    return web_version

def get_supplier_details(details_info):
    details = []
    for a in details_info:
        parsed = re.sub(r' {2,}', ';', a.text.strip().replace("\n", "").replace("\xa0", " ")).split(";")
        details.extend([item for item in parsed if item])

    result = {}
    for i in range(0, len(details)):
        if "Sprzedawca " in details[i]:
            result['supplier'] = details[i].replace("Sprzedawca ", "")
        elif "Okres umowy" in details[i]:
            result['contract_period_from'] = details[i+1].replace("Od ", "")
        elif "Numer PPE " in details[i]:
            result['ppe'] = details[i].replace("Numer PPE ", "")
        elif "Taryfa" in details[i]:
            result['tariff'] = details[i+1]
        elif "Typ " in details[i]:
            result['customer_type'] = details[i].replace("Typ ", "")
        elif "Adres PPE " in details[i]:
            result['ppe_address'] = details[i].replace("Adres PPE ", "")
    
    return result


def get_meter_readings(html):
    soup = BeautifulSoup(html, "lxml")

    # supplier details
    a_details = soup.find_all("div", class_="detailsInfo")

    # all meter readings are in td with class "first" and "last"
    a_plus_minus = soup.find_all("td", class_="first")
    a_plus_minus_values = soup.find_all("td", class_="last")

    a_headers = []
    a_values = []
    result = {}

    for a in a_plus_minus:
        cols = [element.text.strip() for element in a]
        a_headers.append([element for element in cols if element])

    for a in a_plus_minus_values:
        cols = [element.text.strip() for element in a]
        a_values.append(float(''.join([element for element in cols if element and element in "0123456789.,"])
                              .replace(",", ".")))

    now = str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    for header, value in zip(a_headers, a_values):
        record = create_counter_record(
            name = header[0]
            .replace(" ", "_")
            .replace('+', '_plus')
            .replace('-', '_minus')
            .replace('_strefa_1', '')
            .lower(),
            description=f"{'Zużycie'+' '+header[0] if 'A+' in header[0] else 'Produkcja'+' '+header[0]}",
            last_update=str(datetime.strptime(header[1], "%Y-%m-%d %H:%M")),
            last_refresh=f"{now}",
            value=value
        )
        result.update({record["name"]: record})

    result["supplier_info"] = get_supplier_details(a_details)
    logger.debug(f"Parsed meter readings:\n{json.dumps(result, indent=2)}\n")
    return result


def get_meter_page(account):
    s = requests.Session()
    r = s.get(appcfg.energa_access.login_url,
              headers=appcfg.energa_access.headers, verify=appcfg.energa_access.ssl_verify)
    if r.status_code == 200:
      soup = BeautifulSoup(r.text, "lxml")
      if soup.find("form", id="loginForm"):
        form = soup.find("form", id="loginForm")
        if form is not None:
            input_tag = form.find("input", {"name": "_antixsrf"})
            if input_tag and input_tag.has_attr("value"):
                antixsrf = input_tag["value"]
                appcfg.energa_access.payload["_antixsrf"] = antixsrf
                appcfg.energa_access.payload["j_username"] = account['username']
                appcfg.energa_access.payload["j_password"] = account['password']
            else:
                raise Exception("Unable to find '_antixsrf' input field in the login form.")
        
      else:
        raise Exception("No expected html structure received. Check if the page is not in maintenance mode.")

      logger.info("Gathering data for '{}' account".format(account['name']))

      r = s.post(appcfg.energa_access.login_url, data=appcfg.energa_access.payload,
                 headers=appcfg.energa_access.headers, verify=appcfg.energa_access.ssl_verify)
      if (r.status_code) == 200:
          logger.info("login (code: {})".format(r.status_code))
          r = s.get(appcfg.energa_access.data_url)
          if r.status_code == 200:
            logger.info("downloaded meter data (code: {})".format(r.status_code))
            page_out = r.text
            # logout
            r = s.get(appcfg.energa_access.logout_url, headers=appcfg.energa_access.headers)
            logger.info("logout (code: {})".format(r.status_code))
            return page_out
      else:
        logger.error("Unable to login, http error: {}".format(r.status_code))
    else:
        err_msg = "Service returned http error: {}".format(r.status_code)
        logger.exception(err_msg)
        raise Exception(err_msg)

def mqtt_setup():
    try:
        mqtt_client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2,
                              client_id=appcfg.mqtt_config["mqtt_clientid"])
        if all([appcfg.mqtt_config["mqtt_username"] is not None,
                appcfg.mqtt_config["mqtt_password"] is not None]):
            mqtt_client.username_pw_set(appcfg.mqtt_config["mqtt_username"],
                                        appcfg.mqtt_config["mqtt_password"])


        if appcfg.mqtt_config["mqtt_broker"] is not None:
            mqtt_client.on_connect = mqtt_on_connect
            return mqtt_client

    except Exception as e:
        logger.error(f"mqtt setup error: {e}")


def mqtt_on_connect(client, userdata, flags, reason_code, properties):
    mqtt_auth_result.put(reason_code)

def mqtt_on_publish(client, userdata, mid, reason_code, properties):
    try:
        if reason_code == 0:
            logger.info(f"MQTT data published successfully (mid: {mid})")
        else:
            logger.info(f"MQTT data published to reason_code={reason_code}")

    except Exception as e:
        logger.error(f"Error in mqtt_on_publish: {e}")


def mqtt_on_disconnect(client, userdata, flags, reason_code, properties):
    try:
        if reason_code == 0:
            logger.info("MQTT client disconnected ok")
        if reason_code > 0:
            logger.exception(f"MQTT client disconnected with error (code: {reason_code})")
    except Exception as e:
        logger.error(f"Error in mqtt_on_disconnect: {e}")


def mqtt_on_message(client, userdata, message):
    try:
        logger.info("message received {}s".format(message.payload.decode("utf-8")))
        logger.info("message topic={} qos={} retain flag={}".format(message.topic, message.qos, message.retain))
    except Exception as e:
        logger.error(f"Error in mqtt_on_message: {e}")

def mqtt_send_to_broker(client, account, readings):
    try:
        client.connect(host=appcfg.mqtt_config["mqtt_broker"], port=appcfg.mqtt_config["mqtt_broker_port"])
        client.loop_start()
        mqtt_rc_code = mqtt_auth_result.get(timeout=5)  # Wait for authentication result
        # After successful connection, remove authentication callback to avoid handling reconnects
        client.on_connect = None

        if mqtt_rc_code != 0:
            client.loop_stop()
            client.disconnect()
            raise ConnectionError(f"MQTT connection error: {f'{mqtt_rc_code}'}")

        # connect ok, set callbacks for publish and disconnect events
        client.on_publish = mqtt_on_publish
        client.on_disconnect = mqtt_on_disconnect
        # we don't expect to receive any messages, but set on_message callback just in case
        client.on_message = mqtt_on_message

        # extract supplier info and send it as separate message
        supplier_info = readings.pop("supplier_info", None)
        logger.debug(f"Dump supplier_info data:\n{json.dumps(supplier_info, indent=2)}\n")
        if supplier_info:
            info = client.publish(
                appcfg.mqtt_config["mqtt_topic_supplier_info"].format(account["name"]),
                json.dumps(supplier_info), retain=appcfg.mqtt_config["mqtt_retain_flag"], qos=1
                )
            info.wait_for_publish()

        for _, (key, _) in enumerate(readings.items()):
            info = client.publish(
                appcfg.mqtt_config["mqtt_topic_name"].format(account["name"], key),
                json.dumps(readings[key]), retain=appcfg.mqtt_config["mqtt_retain_flag"], qos=1
                )
            info.wait_for_publish()
        
        client.loop_stop()
        client.disconnect()
    except Exception as e:
        logger.error(f"MQTT message publish error: {e}")

def main():
    try:
        logger.info("Starting Energa - Mój licznik - scrapping integration")
        for account in appcfg.accounts:
            if account['active']:
                page = get_meter_page(account)
                if page:
                    web_version = get_web_version(page)
                    if web_version != appcfg.energa_web_version:
                        logger.warning(
                        f"Web page version mismatch!\n\
                        Expected: {appcfg.energa_web_version}, actual: {web_version}\n\
                        Please check if the page structure has changed and update the parser accordingly.\n\
                        Continue with parsing, but some errors may occur \
                        if the structure is different than expected."
                        )
    
                    readings = get_meter_readings(page)
                    if readings:
                        mqtt_client = mqtt_setup()
                        if mqtt_client:
                            mqtt_send_to_broker(mqtt_client, account, readings)    
                else:
                    logger.error("No meter readings received from Energa server.")
    except Exception as e:
            logger.exception(e)


if __name__ == "__main__":
    try:
        appcfg = AppConfig.load()
        
        logging_level_formatter = "[%(asctime)s] %(levelname)s %(message)s"
        
        if appcfg.logging.verbose:
            logging_level_formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)s [%(filename)s.%(funcName)s:%(lineno)d] %(message)s",
                datefmt=appcfg.logging.log_date_format,
            )
            logging_level = logging.DEBUG
        else:
            logging_level_formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)s %(message)s",
                datefmt=appcfg.logging.log_date_format,
            )
            logging_level = logging.INFO

        if appcfg.logging.log and len(appcfg.logging.log) != 0:
            fh = logging.FileHandler(appcfg.logging.log)
            fh.setFormatter(logging_level_formatter)
            logger.addHandler(fh)

        if appcfg.logging.log_to_screen:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(logging_level_formatter)
            logger.addHandler(sh)

        logger.setLevel(logging_level)

        main()
    except Exception as e:
        logger.exception(e, exc_info=True)