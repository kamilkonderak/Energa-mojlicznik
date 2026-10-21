# Energa S.A. "Mój licznik"

Odczyty licznika z https://mojlicznik.energa-operator.pl w Home Assistancie — jako
**natywna integracja** (zalecane) albo jako skrypt wysyłający dane do MQTT (starsza metoda, niżej).

*Daily meter readings from Energa's "Mój licznik" portal, as a native Home Assistant
integration (recommended) or an MQTT bridge script. The rest of the documentation is in Polish.*

## Integracja Home Assistant (zalecane)

### Instalacja

1. HACS → ⋮ → **Custom repositories** → dodaj `https://github.com/kamilkonderak/Energa-mojlicznik`
   jako *Integration*, zainstaluj **Energa Mój Licznik** i zrestartuj HA.
   Bez HACS: skopiuj `custom_components/energa_mojlicznik` do `<config>/custom_components/`.
2. **Ustawienia → Urządzenia i usługi → Dodaj integrację → Energa Mój Licznik**, wpisz
   e-mail i hasło do Mój licznik. Hasło trzyma Home Assistant (magazyn wpisów
   konfiguracji), nie plik w repozytorium.

### Encje

Identyfikatory są stałe, niezależne od języka HA:

| Encja | Co to jest |
|---|---|
| `sensor.energa_pobor_strefa_1` | A+ strefa 1 (dzienna, szczyt) — kWh, `total_increasing` |
| `sensor.energa_pobor_strefa_2` | A+ strefa 2 (nocna / weekend, pozaszczyt) |
| `sensor.energa_pobor_razem` | Suma stref |
| `sensor.energa_oddanie_strefa_1` / `_2` / `_razem` | A− (energia oddana), jeśli licznik ją pokazuje |
| `sensor.energa_pobor` | Taryfy jednostrefowe (G11) zamiast stref |
| `sensor.energa_odczyt` | Czas ostatniego odczytu (zwykle północ) — diagnostyczna |
| `sensor.energa_taryfa` | Taryfa, sprzedawca, początek umowy — diagnostyczna |

Atrybuty rejestrów: `odczyt` (czas odczytu), `strefa`, `nazwa_strefy` (z opisu na stronie:
„dzienna”, „nocna”). Adres PPE nie jest wystawiany w encjach; numer PPE jest numerem seryjnym
urządzenia.

### Panel Energia

Energa publikuje odczyt raz na dobę (około północy), a integracja pobiera go kilka godzin
później. Gdyby panel Energia korzystał z samych encji, zużycie z wczoraj trafiałoby na dziś.
Dlatego integracja zapisuje też **statystyki zewnętrzne** we właściwej godzinie (23:00–24:00
dnia, którego odczyt dotyczy):

- `energa_mojlicznik:pobor_strefa_1` — „Energa pobór strefa 1”
- `energa_mojlicznik:pobor_strefa_2` — „Energa pobór strefa 2”
- (oraz `oddanie_*`, jeśli są; drugi dodany licznik dostaje numer PPE w identyfikatorze,
  np. `energa_mojlicznik:<PPE>_pobor_strefa_1`)

W **Ustawienia → Panele → Energia → Pobór z sieci** dodaj obie strefy *pobór* (wybierz je po
nazwie) i przypisz każdej cenę: strefie 1 cenę szczytową, strefie 2 pozaszczytową. Panel
pokazuje dane dobowe — godzinowych Energa na tej stronie nie publikuje.

Pierwszy odczyt po instalacji jest punktem startowym (zużycie 0); dane pojawiają się od
następnej doby.

### Opcje

- **Sprawdzaj co (godzin)** — domyślnie 4 h. Częściej nie ma sensu (odczyt jest raz na dobę), a
  zbyt częste logowanie może zablokować konto.
- **Statystyki we właściwym dniu** — można wyłączyć, jeśli nie używasz panelu Energia.

### Bezpieczeństwo

- Integracja łączy się wyłącznie z `https://mojlicznik.energa-operator.pl` (z weryfikacją
  certyfikatu), loguje się, pobiera stronę licznika i wylogowuje.
- Hasło nie trafia do logów. Diagnostyka ukrywa e-mail, hasło, PPE i adres.
- Gdy Energa odrzuci hasło, HA poprosi o nowe (ponowne uwierzytelnienie).
- To scraping strony — jeśli Energa zmieni jej strukturę, integracja zgłosi błąd zamiast
  zapisywać złe dane. Cała logika parsowania jest w `custom_components/energa_mojlicznik/parser.py`.

### Testy

Testy integracji wymagają Linuksa (np. kontener):

```
pip install pytest-homeassistant-custom-component beautifulsoup4 lxml
python -m pytest tests/test_parser.py tests/test_config_flow.py tests/test_init.py
```

---

## Starsza metoda: skrypt energa2mqtt (MQTT)

> Plik `energa2mqtt.json` zawiera hasła — jest w `.gitignore`, nigdy go nie commituj.
> Dla panelu Energia używaj czujników z `state_class: total_increasing` (drugi przykład niżej).

### Yet another "scrapping" integration for Energa S.A. meters.

This piece of software can be used to gather energy production and consumption published on https://mojlicznik.energa-operator.pl and send it to mqtt broker. From that point, meter readings can be easy picked up by Home Assistant or similar software which is mqtt capable. As this is "local" application so the rest of the documentation will be provided in polish.


#### Kolejna integracja typu "scrapping" dla strony "Mój licznik" dostawcy Energa. Oczywiście wszystko jest zależne od struktury strony, więc jeśli Energa zmieni coś na stronie koniecznie będą zmiany w kodzie.


Program odczytuje wartości energii ze strony https://mojlicznik.energa-operator.pl i publikuje je do brokera mqtt.

- Może zostać uruchomiony "z ręki", z crona (patrz niżej) albo jako usługa systemd (patrz niżej), pewnie także na Windowsie - czego akurat nie sprawdzałem.

- Napisana w Python 3.13 - niewykluczone, że będzie działać w starszych/nowszych wersjach.

- Musisz mieć zainstalowane [uv](docs.astral.sh/uv/getting-started/installation/) żeby w prosty sposób odtworzyć środowisko uruchomieniowe.

- Wszystkie pakiety niezbędne do  działania są w `dependencies` w pliku `pyproject.toml`. Wykonaj `uv sync`, żeby stworzyć środowisko uruchomieniowe.


## Ficzery

- Przesyła odczytane wartości do brokera mqtt zdefiniowanego w pliku konfiguracyjnym.
- Obsługuje wiele kont (np Twoje, rodziców, albo szwagra), produkcję energii (A-) oraz zużycie (A+), także w taryfach strefowych - sprawdzone na G12W.
- Na pewno nie obsługuje wiecej niż jednego licznika (PPE) - nie miałem jak tego sprawdzić --> potrzebne dodatkowe dane --> napisz / przyslij źródło strony z takim przypadkiem
- Z dużą dozą pewności zawiera błędy

## Znane błędy

- na razie wszystkie błędy są niezname, program działa u mnie już jakiś czas bez wiekszych problemow, no ale wiadomo, że u autora zawsze działa dobrze. :)

## Konfiguracja

- Obecnie program domyślnie korzysta z pliku `energa2mqtt.json` jako magazynu konfiguracji, więc jeśli masz konfigurację z poprzedniej wersji (`config.py`), to możesz używając pliku `energa2mqtt_example.json`, "przerobić" swoją konfigurację na nową wesję.

- Wyedytuj `energa2mqtt.json` i wpisz swoje dane do konta ze strony Mój licznik (sekacja `accounts`). Ustaw active na `true` jeśli chesz żeby to konto było sprawdzane.

    ```
     "accounts":[
        {
            "name": "my home account",
            "active": true,
            "username": "email@example.com",
            "password": "change me"
        }
     ]
    ```

- Wpisz namiary na broker mqtt
    ```
    "mqtt_broker": "mqtt.broker.local",
    "mqtt_broker_port": 1883,
    "mqtt_username": "",
    "mqtt_password": ""
    ```

- Jeśli chcesz stworzyć plik logu, ustaw nazwe pliku w `log`
- Jeśli chcesz logować tylko na enran (stdout), ustaw `log_to_screen` na `true`

- Uruchom energa2mqtt.py (np: `python3 energa2mqtt.py`, albo `uv run energa2mqtt.py`)
- topic mqtt zostanie będzie ustawiony na `/home/mojlicznik/<nazwa twojego konta>`. Możesz to zmienić edytując:

```
"mqtt_topic_name": "home/mojlicznik/{}/{}",
```
- Do brokera mqtt wysyłane są następujące informacje:
  - name: `a_plus` dla energii zużytej, `a_minus` dla oddanej do sieci
  - description: Opis pola - "Energia konsumpcja" albo "Energia produkcja"
  - last_update: data i czas kiedy `Energa` zaktualizowała dane (przeważnie codziennie o północy)
  - last_refresh: data i czas kiedy dane ostani raz zostały odświeżone (kiedy ostatni razy był uruchomiony program)
  - value: wartość odczytu w kilowatogodzinach
  - unit: jednostka - kWh

- Jeśli mamy taryfę dwustrefową, dodatkowo wysyłane są następujące encje:
  - `a_plus_strefa_2` - dla energii zużytej w strefie 2
  - `a_minus_strefa_2` - dla energii wyprodukowanej w strefie 2

- Dodatkowo wysyłane są informacje o niektórych parametrach dostawcy energii:
  - nazwa operatora
  - od kiedy zawarta jest umowa
  - numer punktu poboru energii (PPE)
  - nazwa bieżącej taryfy
  - typ odbiorcy
  - adres punktu PPE

```
  "supplier_info": {
    "supplier": "ENERGA-Obrót SA",
    "contract_period_from": "2026-05-12",
    "ppe": "XXXXXXXXXXXXXXXXX",
    "tariff": "G12W",
    "customer_type": "Wytwórca",
    "ppe_address": "xx-xxx Miasto, Ulica numer"
  }

```

### Przykład (z home assistant developer tools):

```
unit_of_measurement: kWh
friendly_name: Licznik Energa produkcja
description: Energia produkcja
last_update: '2022-07-15 00:00:00'
last_refresh: '2022-07-15 21:57:38'
value: 1111.111
unit: kWh
```

### Przykładowa konfiguracja Home Assistant dla taryfy G11 (do wpisania do /config/configuration.yaml)

```
mqtt:
    # Licznik energa
    - name: "Licznik Energa zużycie"
      json_attributes_topic: "home/mojlicznik/my home account/a_plus"
      state_topic: "home/mojlicznik/my home account/a_plus"
      unit_of_measurement: "kWh"
      state_class: measurement
      value_template: "{{ value_json.value }}"
    - name: "Licznik Energa produkcja"
      json_attributes_topic: "home/mojlicznik/my home account/a_minus"
      state_topic: "home/mojlicznik/my home account/a_minus"
      unit_of_measurement: "kWh"
      state_class: measurement
      value_template: "{{ value_json.value }}"
    - name: "Licznik Energa supplier info"
      json_attributes_topic: "home/mojlicznik/my home account/supplier_info"
      state_topic: "home/mojlicznik/my home account/supplier_info"
      value_template: "{{ value_json.value }}"
```

W HA powinniśmy zobaczyć:
```
    - sensor.licznik_energa_produkcja
    - sensor.licznik_energa_zuzycie
    - sensor.licznik_energa_supplier_info
```

### Przykładowa konfiguracja Home Assistant dla taryfy strefowej G12W wraz z sensorami kompatybilnymi z zakładką 'Energy' HA

```
mqtt:
    # Licznik energa
    - name: "Licznik Energa zużycie"
      json_attributes_topic: "home/mojlicznik/my home account/a_plus"
      state_topic: "home/mojlicznik/my home account/a_plus"
      unit_of_measurement: "kWh"
      state_class: measurement
      value_template: "{{ value_json.value }}"
    - name: "Licznik Energa produkcja"
      json_attributes_topic: "home/mojlicznik/my home account/a_minus"
      state_topic: "home/mojlicznik/my home account/a_minus"
      unit_of_measurement: "kWh"
      state_class: measurement
      value_template: "{{ value_json.value }}"
    - name: "Licznik Energa zużycie strefa 2"
      json_attributes_topic: "home/mojlicznik/my home account/a_plus_strefa_2"
      state_topic: "home/mojlicznik/my home account/a_plus_strefa_2"
      unit_of_measurement: "kWh"
      state_class: measurement
      value_template: "{{ value_json.value }}"
    - name: "Licznik Energa produkcja strefa 2"
      json_attributes_topic: "home/mojlicznik/my home account/a_minus_strefa_2"
      state_topic: "home/mojlicznik/my home account/a_minus_strefa_2"
      unit_of_measurement: "kWh"
      state_class: measurement
      value_template: "{{ value_json.value }}"
    - name: "Licznik Energa supplier info"
      json_attributes_topic: "home/mojlicznik/my home account/supplier_info"
      state_topic: "home/mojlicznik/my home account/supplier_info"
      value_template: "{{ value_json.value }}"


    # Licznik energa zakładka Energy
    - name: "Licznik Energa zużycie energy tab"
      json_attributes_topic: "home/mojlicznik/my home account/a_plus"
      state_topic: "home/mojlicznik/my home account/a_plus"
      unit_of_measurement: "kWh"
      value_template: "{{ value_json.value }}"
      state_class: total_increasing
      device_class: energy
    - name: "Licznik Energa produkcja energy tab"
      json_attributes_topic: "home/mojlicznik/my home account/a_minus"
      state_topic: "home/mojlicznik/my home account/a_minus"
      unit_of_measurement: "kWh"
      value_template: "{{ value_json.value }}"
      state_class: total_increasing
      device_class: energy
    - name: "Licznik Energa zużycie strefa 2 energy tab"
      json_attributes_topic: "home/mojlicznik/my home account/a_plus_strefa_2"
      state_topic: "home/mojlicznik/my home account/a_plus_strefa_2"
      unit_of_measurement: "kWh"
      value_template: "{{ value_json.value }}"
      state_class: total_increasing
      device_class: energy
    - name: "Licznik Energa produkcja strefa 2 energy tab"
      json_attributes_topic: "home/mojlicznik/my home account/a_minus_strefa_2"
      state_topic: "home/mojlicznik/my home account/a_minus_strefa_2"
      unit_of_measurement: "kWh"
      value_template: "{{ value_json.value }}"
      state_class: total_increasing
      device_class: energy
```

W HA powinniśmy zobaczyć:
```
    - sensor.licznik_energa_produkcja
    - sensor.licznik_energa_zuzycie
    - sensor.licznik_energa_produkcja_strefa_2
    - sensor.licznik_energa_zuzycie_strefa_2
    - sensor.licznik_energa_supplier_info
```

### Przykładowa konfiguracja HA dla `supplier_info`

```
🏢 **Dostawca**: {{ state_attr('sensor.licznik_energa_supplier_info', 'supplier') }}
🏷️ **Taryfa**: {{ state_attr('sensor.licznik_energa_supplier_info', 'tariff') }}
📅 **Umowa od**: {{ state_attr('sensor.licznik_energa_supplier_info', 'contract_period_from') }}
👤 **Typ klienta**: {{ state_attr('sensor.licznik_energa_supplier_info', 'customer_type') }}
🔌**PPE**: {{ state_attr('sensor.licznik_energa_supplier_info', 'ppe') }}
📍 **Adres PPE**: {{ state_attr('sensor.licznik_energa_supplier_info', 'ppe_address') }}

```

### Pliki systemd do konfiguracji periodycznego odczytu danych z poiomu użytkownika, można też skorzystać z cron-a (odsyłam do [podobnego projektu](https://github.com/PapuutekAPT/Energa-HomeAssistant-Integration#automatyczne-uruchanianie-skryptu))


Usługa systemd może być uruchamiana z poziomu zwykłego użytkownia. W tym przypadku uzyskujemy możliwość jej rekonfiguracji bez posiadania uprawnień superusera. Dodaj --user po poleceniu systemd np:

```
systemctl --user status energa2mqtt
systemctl --user stop energa2mqtt

```

Najpierw z poziomu root-a wykonaj nastepujące polecenie:
```
loginctl enable-linger username
```

gdzie username to nazwa użytkownika, który będzie uruchamiać usługę systemd

Następnie utworz pliki usługi w katalogu:

```
/home/<user>/.config/systemd/user
```

energa2mqtt.service
```
[Unit]
Description=Periodically run task to gather energy meter data from Energa webpage
Wants=network-online.target
After=network.target


[Service]
# python is run from virtual environment
Type=simple
ExecStart=/home/<user>/mojlicznik/.venv/bin/python /home/<user>/mojlicznik/energa2mqtt.py
WorkingDirectory=/home/<user>/mojlicznik/
KillMode=mixed

[Install]
WantedBy=energa2mgtt.timer
```

energa2mqtt.timer
```
[Unit]
Description=Triggers energa2mqtt everyday

[Timer]
OnCalendar=*-*-* 01:00:00

[Install]
WantedBy=timers.target

```

Dalej postępuj w/g standardowych zasad:
```
systemctl --user enable energa2mqtt.service
systemctl --user enable energa2mqtt.timer

systemctl --user start energa2mqtt.timer

```
Sprawdz czy działa:

```
$ systemctl --user status energa2mqtt
● energa2mqtt.service - Periodically run task to gather energy meter data from webpage (Energa - mojlicznik.pl)
     Loaded: loaded (/home/<REDACTED>/.config/systemd/user/energa2mqtt.service; enabled; vendor preset: enabled)
     Active: inactive (dead) since Fri 2022-07-15 01:00:40 CEST; 22h ago
TriggeredBy: ● energa2mqtt.timer
    Process: 26506 ExecStart=/usr/bin/python3 /home/<REDACTED>/mojlicznik/energa2mqtt.py (code=exited, status=0/SUCCESS)
   Main PID: 26506 (code=exited, status=0/SUCCESS)
        CPU: 433ms

$ systemctl --user status energa2mqtt.timer
● energa2mqtt.timer - Triggers energa2mqtt everyday
     Loaded: loaded (/home/<REDACTED>/.config/systemd/user/energa2mqtt.timer; enabled; vendor preset: enabled)
     Active: active (waiting) since Tue 2022-07-12 14:19:45 CEST; 3 days ago
    Trigger: Sat 2022-07-16 01:00:00 CEST; 1h 55min left
   Triggers: ● energa2mqtt.service

```
Have fun!
