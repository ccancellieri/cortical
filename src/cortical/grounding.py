"""Real-Time Grounding Engine for Cortical & `pi` (Weather, Web Search & Chrome Automation).

Ensures that when the user asks Cortical or `pi` to check the weather (e.g. "cerca il meteo a roma
per domani") or search the web, real-time verified data is fetched deterministically and optionally
opened in Google Chrome without stealing window focus.
"""

from __future__ import annotations

import datetime
import json
import platform
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from typing import Any, Optional

WMO_WEATHER_IT = {
    0: "sereno",
    1: "prevalentemente sereno",
    2: "parzialmente nuvoloso",
    3: "coperto",
    45: "nebbia",
    48: "nebbia con brina",
    51: "pioviggine leggera",
    53: "pioviggine moderata",
    55: "pioviggine intensa",
    61: "pioggia leggera",
    63: "pioggia moderata",
    65: "pioggia forte",
    71: "neve leggera",
    73: "neve moderata",
    75: "neve forte",
    80: "rovesci di pioggia leggeri",
    81: "rovesci di pioggia moderati",
    82: "rovesci di pioggia violenti",
    95: "temporale",
    96: "temporale con grandine",
    99: "temporale forte con grandine",
}

CITY_DEFAULT_COORDS = {
    "roma": (41.8919, 12.5113, "Roma"),
    "rome": (41.8919, 12.5113, "Roma"),
    "milano": (45.4642, 9.1900, "Milano"),
    "napoli": (40.8518, 14.2681, "Napoli"),
    "torino": (45.0703, 7.6869, "Torino"),
    "firenze": (43.7696, 11.2558, "Firenze"),
    "bologna": (44.4949, 11.3426, "Bologna"),
    "barcellona": (41.3874, 2.1686, "Barcellona"),
    "valencia": (39.4699, -0.3763, "Valencia"),
}


def open_url_in_chrome(url: str, background: bool = True) -> bool:
    """Opens a URL in Google Chrome (background by default to respect zero focus-stealing)."""
    try:
        sys_name = platform.system()
        if sys_name == "Darwin":
            cmd = ["open"]
            if background:
                cmd.append("-g")
            cmd.extend(["-a", "Google Chrome", url])
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if sys_name == "Linux":
            for browser in ("google-chrome", "chromium", "xdg-open"):
                if shutil.which(browser):
                    subprocess.Popen(
                        [browser, url],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
    except Exception:  # noqa: BLE001
        pass
    return False


def extract_weather_intent(text: str) -> Optional[dict[str, Any]]:
    """Detects if a prompt asks for weather and extracts (city, day_offset, day_label)."""
    norm = text.lower().strip()
    if not any(w in norm for w in ("meteo", "che tempo fa", "previsioni", "temperatura", "pioverà", "piove")):
        return None

    day_offset = 0
    day_label = "oggi"
    if "dopodomani" in norm:
        day_offset = 2
        day_label = "dopodomani"
    elif "domani" in norm:
        day_offset = 1
        day_label = "domani"

    # Extract city after 'a ', 'in ', 'per ', 'di ' or match known cities
    city = "Roma"
    for known_key, (_, _, canonical) in CITY_DEFAULT_COORDS.items():
        if re.search(rf"\b{re.escape(known_key)}\b", norm):
            city = canonical
            break
    else:
        m = re.search(
            r"\b(?:meteo|tempo|previsioni)\s+(?:a|in|di|per)\s+([a-zA-ZàèéìòùÀÈÉÌÒÙ]+)",
            norm,
        )
        if m:
            candidate = m.group(1).strip()
            if candidate not in {"oggi", "domani", "dopodomani", "adesso", "ora"}:
                city = candidate.capitalize()

    open_browser = any(w in norm for w in ("chrome", "browser", "apri", "cerca", "procedi"))
    return {
        "city": city,
        "day_offset": day_offset,
        "day_label": day_label,
        "open_browser": open_browser,
    }


def fetch_weather_forecast(
    city: str = "Roma",
    day_offset: int = 1,
    open_chrome: bool = False,
    open_browser: bool = False,
) -> dict[str, Any]:
    """Fetches real weather forecast from Open-Meteo API and optionally opens Chrome."""
    should_open = open_chrome or open_browser
    city_key = city.lower().strip()
    lat, lon, display_city = CITY_DEFAULT_COORDS.get(city_key, (41.8919, 12.5113, city.capitalize()))

    if city_key not in CITY_DEFAULT_COORDS:
        try:
            geo_url = (
                "https://geocoding-api.open-meteo.com/v1/search?name="
                + urllib.parse.quote(city)
                + "&count=1&language=it&format=json"
            )
            with urllib.request.urlopen(geo_url, timeout=3.5) as r:  # noqa: S310
                gdata = json.loads(r.read().decode("utf-8"))
                if gdata.get("results"):
                    first = gdata["results"][0]
                    lat = float(first["latitude"])
                    lon = float(first["longitude"])
                    display_city = first.get("name", display_city)
        except Exception:  # noqa: BLE001
            pass

    target_date = (datetime.date.today() + datetime.timedelta(days=day_offset)).isoformat()
    day_label = {0: "oggi", 1: "domani", 2: "dopodomani"}.get(day_offset, target_date)

    chrome_url = f"https://www.ilmeteo.it/meteo/{urllib.parse.quote(display_city)}"
    chrome_opened = open_url_in_chrome(chrome_url, background=True) if should_open else False

    api_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max,windspeed_10m_max"
        "&timezone=Europe%2FRome"
    )
    try:
        with urllib.request.urlopen(api_url, timeout=4.0) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
            daily = data["daily"]
            idx = min(day_offset, len(daily["time"]) - 1)
            code = int(daily["weathercode"][idx])
            t_max = round(float(daily["temperature_2m_max"][idx]), 1)
            t_min = round(float(daily["temperature_2m_min"][idx]), 1)
            precip = int(daily.get("precipitation_probability_max", [0])[idx] or 0)
            wind = round(float(daily.get("windspeed_10m_max", [0])[idx] or 0), 1)
            cond = WMO_WEATHER_IT.get(code, "variabile")

            summary_it = (
                f"Previsioni meteo per {display_city} ({day_label}, {daily['time'][idx]}): cielo {cond}, "
                f"temperature comprese tra {t_min}°C e {t_max}°C, "
                f"probabilità di pioggia del {precip}% e vento fino a {wind} km/h."
            )
            if chrome_opened:
                summary_it += f" Ho aperto anche la scheda meteo di {display_city} su Chrome."

            return {
                "ok": True,
                "city": display_city,
                "date": daily["time"][idx],
                "day_label": day_label,
                "condition": cond,
                "temp_min_c": t_min,
                "temp_max_c": t_max,
                "precipitation_prob_pct": precip,
                "wind_kmh": wind,
                "chrome_opened": chrome_opened,
                "chrome_url": chrome_url,
                "summary_it": summary_it,
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "city": display_city,
            "date": target_date,
            "day_label": day_label,
            "chrome_opened": chrome_opened,
            "chrome_url": chrome_url,
            "summary_it": (
                f"Previsioni meteo per {display_city} ({day_label}): aperta scheda Chrome ({chrome_url})."
                if chrome_opened
                else f"Previsioni meteo per {display_city} ({day_label}): servizio offline ({exc})."
            ),
        }
