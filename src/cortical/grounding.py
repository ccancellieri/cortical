"""Real-Time Grounding Engine for Cortical & `pi` (Weather, Visual Chrome Navigation & Page Reading).

Ensures that when the user asks Cortical or `pi` to:
1. Check the weather (e.g. "cerca il meteo a roma per domani"), real-time verified data is fetched.
2. Perform a visual browser search (e.g. "fai una ricerca per me, apri il browser e vai in wikipedia
   e cerca Albert Einstain"), Google Chrome is brought into focus, navigated to the requested site,
   and the search form is visually filled & submitted via DOM interaction.
3. Read or summarize the currently open Chrome tab ("leggi la pagina aperta", "riassumi i concetti
   della pagina aperta"), the active tab's text is extracted and read/summarized in Italian.
"""

from __future__ import annotations

import datetime
import html.parser
import json
import platform
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

_LAST_OPENED_BROWSER_PAGE: dict[str, Any] = {}

SITE_SEARCH_CONFIGS: dict[str, dict[str, Any]] = {
    "wikipedia": {
        "base_url": "https://it.wikipedia.org",
        "search_url": "https://it.wikipedia.org/w/index.php?search={query}",
        "input_selectors": [
            "#searchInput",
            "input[name='search']",
            "input.cdx-text-input__input",
            "input[type='search']",
        ],
        "submit_selectors": [
            ".cdx-search-input__end-button",
            "#searchButton",
            "button[type='submit']",
        ],
    },
    "google": {
        "base_url": "https://www.google.com",
        "search_url": "https://www.google.com/search?q={query}",
        "input_selectors": ["textarea[name='q']", "input[name='q']", "input[type='search']"],
        "submit_selectors": ["input[name='btnK']", "button[type='submit']"],
    },
    "youtube": {
        "base_url": "https://www.youtube.com",
        "search_url": "https://www.youtube.com/results?search_query={query}",
        "input_selectors": ["input#search", "input[name='search_query']", "input[type='search']"],
        "submit_selectors": ["button#search-icon-legacy", "button[aria-label*='Search']"],
    },
    "duckduckgo": {
        "base_url": "https://duckduckgo.com",
        "search_url": "https://duckduckgo.com/?q={query}",
        "input_selectors": ["#searchbox_input", "input[name='q']", "input[type='search']"],
        "submit_selectors": ["button[type='submit']"],
    },
    "github": {
        "base_url": "https://github.com",
        "search_url": "https://github.com/search?q={query}",
        "input_selectors": ["input[name='q']", "#query-builder-test", "input[type='search']"],
        "submit_selectors": ["button[type='submit']"],
    },
    "amazon": {
        "base_url": "https://www.amazon.it",
        "search_url": "https://www.amazon.it/s?k={query}",
        "input_selectors": ["#twotabsearchtextbox", "input[name='field-keywords']"],
        "submit_selectors": ["#nav-search-submit-button", "input[type='submit']"],
    },
    "treccani": {
        "base_url": "https://www.treccani.it",
        "search_url": "https://www.treccani.it/enciclopedia/ricerca/{query}/",
        "input_selectors": ["input[name='q']", "input[type='search']", "input[placeholder*='Cerca' i]"],
        "submit_selectors": ["button[type='submit']"],
    },
}

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

WMO_WEATHER_EN = {
    0: "clear sky",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "freezing fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "light rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "light snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "light rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "severe thunderstorm with hail",
}

CITY_DEFAULT_COORDS = {
    "roma": (41.8919, 12.5113, "Roma"),
    "rome": (41.8919, 12.5113, "Rome"),
    "milano": (45.4642, 9.1900, "Milano"),
    "milan": (45.4642, 9.1900, "Milan"),
    "napoli": (40.8518, 14.2681, "Napoli"),
    "naples": (40.8518, 14.2681, "Naples"),
    "torino": (45.0703, 7.6869, "Torino"),
    "turin": (45.0703, 7.6869, "Turin"),
    "firenze": (43.7696, 11.2558, "Firenze"),
    "florence": (43.7696, 11.2558, "Florence"),
    "bologna": (44.4949, 11.3426, "Bologna"),
    "barcellona": (41.3874, 2.1686, "Barcellona"),
    "barcelona": (41.3874, 2.1686, "Barcelona"),
    "valencia": (39.4699, -0.3763, "Valencia"),
    "london": (51.5074, -0.1278, "London"),
    "londra": (51.5074, -0.1278, "Londra"),
    "new york": (40.7128, -74.0060, "New York"),
    "paris": (48.8566, 2.3522, "Paris"),
    "parigi": (48.8566, 2.3522, "Parigi"),
    "berlin": (52.5200, 13.4050, "Berlin"),
    "madrid": (40.4168, -3.7038, "Madrid"),
}

_IT_DETECT_TOKENS = frozenset({
    "che", "ore", "sono", "meteo", "domani", "oggi", "dopodomani", "apri", "cerca",
    "ricerca", "vai", "pagina", "riassumi", "leggi", "scheda", "concetti", "ciao",
    "grazie", "come", "per", "con", "nella", "sul", "sulla", "della", "delle",
    "fammi", "dimmi", "crea", "nuovo", "chiudi", "fermati", "basta", "silenzio",
    "chi", "sei", "cosa", "puoi", "fare", "fai", "parlami", "spiega", "italiano",
})

_EN_DETECT_TOKENS = frozenset({
    "the", "what", "when", "where", "who", "how", "why", "which", "weather",
    "forecast", "tomorrow", "today", "open", "search", "find", "look", "browser",
    "page", "tab", "summarize", "summary", "read", "explain", "concepts", "hello",
    "hey", "please", "thank", "thanks", "create", "new", "close", "stop", "quiet",
    "cancel", "wait", "time", "date", "about", "with", "for", "from", "into",
    "your", "you", "are", "can", "english", "switch", "language",
})


def detect_language(text: str, default: str = "it") -> str:
    """Detects whether an utterance is predominantly English ('en') or Italian ('it')."""
    raw = (text or "").strip()
    if not raw:
        return default
    if any(ch in raw.lower() for ch in ("à", "è", "é", "ì", "ò", "ù")):
        return "it"
    words = re.findall(r"[a-zA-Z]+", raw.lower())
    if not words:
        return default
    it_score = sum(2 if w in _IT_DETECT_TOKENS else 0 for w in words)
    en_score = sum(2 if w in _EN_DETECT_TOKENS else 0 for w in words)
    # Lightweight inflection bonus for common English phrasing
    if re.search(r"\b(what's|what is|open the|search for|go to|read the|summarize the|hey cortical|create a task)\b", raw.lower()):
        en_score += 3
    if re.search(r"\b(che ore|apri il|fai una|vai su|vai in|leggi la|riassumi i|ehi cortical|crea un task)\b", raw.lower()):
        it_score += 3
    if en_score > it_score:
        return "en"
    if it_score > en_score:
        return "it"
    return default


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
    """Detects IT/EN weather prompts and extracts (city, day_offset, day_label, lang)."""
    norm = text.lower().strip()
    weather_kw = (
        "meteo",
        "che tempo fa",
        "previsioni",
        "temperatura",
        "pioverà",
        "piove",
        "weather",
        "forecast",
        "temperature",
        "will it rain",
    )
    if not any(w in norm for w in weather_kw):
        return None

    lang = detect_language(text)
    day_offset = 0
    day_label = "today" if lang == "en" else "oggi"
    if "dopodomani" in norm or "day after tomorrow" in norm:
        day_offset = 2
        day_label = "the day after tomorrow" if lang == "en" else "dopodomani"
    elif "domani" in norm or "tomorrow" in norm:
        day_offset = 1
        day_label = "tomorrow" if lang == "en" else "domani"

    city = "Rome" if lang == "en" else "Roma"
    for known_key, (_, _, canonical) in CITY_DEFAULT_COORDS.items():
        if re.search(rf"\b{re.escape(known_key)}\b", norm):
            city = canonical
            break
    else:
        m = re.search(
            r"\b(?:meteo|tempo|previsioni|weather|forecast)\s+(?:a|in|di|per|for|at)\s+([a-zA-ZàèéìòùÀÈÉÌÒÙ]+(?:\s+[a-zA-Z]+)?)",
            norm,
        )
        if m:
            candidate = m.group(1).strip()
            skip_words = {"oggi", "domani", "dopodomani", "adesso", "ora", "today", "tomorrow", "now"}
            if candidate not in skip_words:
                city = " ".join(part.capitalize() for part in candidate.split())

    open_browser = any(w in norm for w in ("chrome", "browser", "apri", "cerca", "procedi", "open", "search"))
    return {
        "city": city,
        "day_offset": day_offset,
        "day_label": day_label,
        "open_browser": open_browser,
        "lang": lang,
    }


def fetch_weather_forecast(
    city: str = "Roma",
    day_offset: int = 1,
    open_chrome: bool = False,
    open_browser: bool = False,
    lang: str = "auto",
) -> dict[str, Any]:
    """Fetches real weather forecast from Open-Meteo API in IT or EN and optionally opens Chrome."""
    eff_lang = "en" if lang == "en" else "it"
    should_open = open_chrome or open_browser
    city_key = city.lower().strip()
    default_name = "Rome" if eff_lang == "en" and city_key in ("roma", "rome", "") else city.capitalize()
    lat, lon, display_city = CITY_DEFAULT_COORDS.get(city_key, (41.8919, 12.5113, default_name))

    if city_key not in CITY_DEFAULT_COORDS:
        try:
            geo_url = (
                "https://geocoding-api.open-meteo.com/v1/search?name="
                + urllib.parse.quote(city)
                + f"&count=1&language={eff_lang}&format=json"
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
    day_labels = {0: "today", 1: "tomorrow", 2: "day after tomorrow"} if eff_lang == "en" else {0: "oggi", 1: "domani", 2: "dopodomani"}
    day_label = day_labels.get(day_offset, target_date)

    chrome_url = (
        f"https://www.weather.com/weather/today/l/{lat},{lon}"
        if eff_lang == "en"
        else f"https://www.ilmeteo.it/meteo/{urllib.parse.quote(display_city)}"
    )
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
            cond_it = WMO_WEATHER_IT.get(code, "variabile")
            cond_en = WMO_WEATHER_EN.get(code, "variable")
            cond = cond_en if eff_lang == "en" else cond_it

            summary_it = (
                f"Previsioni meteo per {display_city} ({day_label}, {daily['time'][idx]}): cielo {cond_it}, "
                f"temperature comprese tra {t_min}°C e {t_max}°C, "
                f"probabilità di pioggia del {precip}% e vento fino a {wind} km/h."
            )
            summary_en = (
                f"Weather forecast for {display_city} ({day_label}, {daily['time'][idx]}): {cond_en}, "
                f"temperatures between {t_min}°C and {t_max}°C, "
                f"rain probability {precip}% and wind up to {wind} km/h."
            )
            if chrome_opened:
                summary_it += f" Ho aperto anche la scheda meteo di {display_city} su Chrome."
                summary_en += f" I also opened the weather tab for {display_city} in Chrome."

            return {
                "ok": True,
                "lang": eff_lang,
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
                "summary": summary_en if eff_lang == "en" else summary_it,
                "summary_it": summary_it,
            }
    except Exception as exc:  # noqa: BLE001
        err_it = (
            f"Previsioni meteo per {display_city} ({day_label}): aperta scheda Chrome ({chrome_url})."
            if chrome_opened
            else f"Previsioni meteo per {display_city} ({day_label}): servizio offline ({exc})."
        )
        err_en = (
            f"Weather forecast for {display_city} ({day_label}): opened Chrome tab ({chrome_url})."
            if chrome_opened
            else f"Weather forecast for {display_city} ({day_label}): service offline ({exc})."
        )
        return {
            "ok": False,
            "lang": eff_lang,
            "city": display_city,
            "date": target_date,
            "day_label": day_label,
            "chrome_opened": chrome_opened,
            "chrome_url": chrome_url,
            "summary": err_en if eff_lang == "en" else err_it,
            "summary_it": err_it,
        }


class _ReadableHTMLParser(html.parser.HTMLParser):
    """Extracts clean visible text & headings from HTML while ignoring script/style/nav noise."""

    SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "nav", "footer", "header"})

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._in_title = False
        self._in_heading = False
        self.title = ""
        self.headings: list[str] = []
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        t = tag.lower()
        if t in self.SKIP_TAGS:
            self._skip_depth += 1
        elif t == "title":
            self._in_title = True
        elif t in {"h1", "h2", "h3"}:
            self._in_heading = True

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif t == "title":
            self._in_title = False
        elif t in {"h1", "h2", "h3"}:
            self._in_heading = False
        elif t in {"p", "div", "li", "br", "tr"} and self._skip_depth == 0:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        clean = re.sub(r"\s+", " ", data).strip()
        if not clean:
            return
        if self._in_title and not self.title:
            self.title = clean
        elif self._in_heading:
            self.headings.append(clean)
            self.chunks.append(f"\n{clean}\n")
        else:
            self.chunks.append(clean + " ")


def _clean_web_text(raw: str) -> str:
    """Strips wiki edit/citation artifacts and collapses excessive whitespace."""
    out = re.sub(r"\[\s*(?:modifica(?:\s+wikitesto)?|edit|\d+|nota\s+\d+|senza\s+fonte)\s*\]", "", raw, flags=re.IGNORECASE)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def extract_page_read_intent(text: str) -> Optional[dict[str, Any]]:
    """Detects IT/EN follow-up requests to read or summarize concepts from the currently open browser page."""
    norm = re.sub(r"\s+", " ", text.lower()).strip()
    lang = detect_language(text)
    page_refs = (
        "pagina", "scheda", "tab", "articolo", "sito", "wikipedia", "browser", "chrome", "aperta", "aperto",
        "page", "article", "site", "website", "open page", "current page",
    )
    has_page_ref = any(r in norm for r in page_refs)
    if not has_page_ref:
        return None

    summarize_words = (
        "riassumi", "riassumere", "riassunto", "sintetizza", "concetti", "punti chiave",
        "spiega", "spiegami", "cosa dice", "di cosa parla",
        "summarize", "summarise", "summary", "concepts", "key points", "explain",
        "what does it say", "what is it about",
    )
    if any(w in norm for w in summarize_words):
        return {"mode": "summarize"}

    read_words = ("leggi", "leggimi", "leggere", "recita", "leggi ad alta voce", "read", "read aloud", "read me")
    if any(w in norm for w in read_words):
        return {"mode": "read"}
    return None


def extract_browser_intent(text: str) -> Optional[dict[str, Any]]:
    """Extracts visual Chrome navigation, site target, and form-search query from IT/EN speech."""
    raw = text.strip()
    norm = re.sub(r"\s+", " ", raw.lower()).strip()
    lang = detect_language(text)

    # Do not intercept follow-up read/summarize commands on an already-open page
    if extract_page_read_intent(norm) is not None:
        return None

    has_browser_verb = any(
        k in norm
        for k in (
            "apri il browser",
            "apri browser",
            "apri chrome",
            "apri google chrome",
            "nel browser",
            "sul browser",
            "su chrome",
            "con chrome",
            "fai una ricerca",
            "cercami",
            "vai in ",
            "vai su ",
            "apri il sito",
            "cerca su ",
            "cerca in ",
            "open the browser",
            "open browser",
            "open chrome",
            "open google chrome",
            "in browser",
            "on chrome",
            "in chrome",
            "do a search",
            "search for ",
            "search on ",
            "search in ",
            "look up ",
            "go to ",
            "open the site",
            "open website",
        )
    )
    known_sites = list(SITE_SEARCH_CONFIGS.keys())
    mentioned_site: Optional[str] = None
    for s in known_sites:
        if re.search(rf"\b{re.escape(s)}\b", norm):
            mentioned_site = s
            break

    url_match = re.search(r"(https?://[^\s,;]+|\b[a-z0-9-]+\.(?:com|org|it|net|io|ai|edu|gov)(?:/[^\s,;]*)?)", raw, flags=re.IGNORECASE)
    explicit_url = url_match.group(1) if url_match else None
    if explicit_url and not explicit_url.lower().startswith(("http://", "https://")):
        explicit_url = "https://" + explicit_url

    if not has_browser_verb and not mentioned_site and not explicit_url:
        return None

    query: Optional[str] = None
    m_search = re.search(
        r"\b(?:e\s+|poi\s+|and\s+|then\s+)?(?:cercami|cerca(?:\s+su\s+[a-z0-9._-]+|\s+in\s+[a-z0-9._-]+|\s+sul\s+browser|\s+su\s+chrome)?|trova|cercare|search\s+for|search(?:\s+on\s+[a-z0-9._-]+|\s+in\s+[a-z0-9._-]+)?|look\s+up|find)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m_search:
        candidate = m_search.group(1).strip(" .,;:!?\"'")
        site_alts = "|".join(known_sites)
        candidate = re.sub(rf"^(?:su|in|per|on|for)\s+(?:{site_alts}|browser|chrome)\s+", "", candidate, flags=re.IGNORECASE).strip()
        candidate = re.sub(rf"\s+(?:su|in|con|nel|on)\s+(?:il\s+|the\s+)?(?:{site_alts}|browser|chrome|google\s+chrome)$", "", candidate, flags=re.IGNORECASE).strip()
        if candidate and not re.match(r"^(?:per me|for me|su|in|on)\b", candidate, flags=re.IGNORECASE):
            query = candidate

    if not query:
        m_ricerca = re.search(
            r"\b(?:fai\s+una\s+ricerca(?:\s+per\s+me)?|do\s+a\s+search(?:\s+for\s+me)?)(?:\s+(?:su|in|on)\s+(?:[a-z0-9._-]+))?\s*(?:,|su|di|per|for|about)?\s+(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
        if m_ricerca:
            tail = m_ricerca.group(1).strip(" .,;:!?\"'")
            if not any(p in tail.lower() for p in ("apri il browser", "apri chrome", "vai in ", "vai su ", "open chrome", "open the browser", "go to ")):
                query = tail

    site = mentioned_site or ("google" if query and not explicit_url else None)
    if not site and not explicit_url and not query:
        return None

    return {
        "action": "search_site" if query else "open_url",
        "site": site,
        "url": explicit_url,
        "query": query,
        "focus": True,
        "lang": lang,
    }


def _default_osascript_runner(script: str, timeout: float = 10.0) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return (proc.returncode == 0, (proc.stdout or proc.stderr).strip())
    except Exception as exc:  # noqa: BLE001
        return (False, str(exc))


def _escape_applescript_str(val: str) -> str:
    return val.replace("\\", "\\\\").replace('"', '\\"')


def _build_dom_search_js(query: str, site_cfg: dict[str, Any]) -> str:
    selectors = site_cfg.get("input_selectors") or ["input[type='search']", "input[name='q']", "input[name='search']", "textarea[name='q']"]
    submits = site_cfg.get("submit_selectors") or ["button[type='submit']", "input[type='submit']"]
    return (
        "(() => {"
        f"const q = {json.dumps(query)};"
        f"const sels = {json.dumps(selectors)};"
        f"const subs = {json.dumps(submits)};"
        "let inp = null;"
        "for (const s of sels) {"
        "  const els = document.querySelectorAll(s);"
        "  for (const el of els) { if (el && el.offsetParent !== null) { inp = el; break; } }"
        "  if (!inp && els.length) inp = els[0];"
        "  if (inp) break;"
        "}"
        "if (!inp) return JSON.stringify({filled:false, reason:'no_input'});"
        "inp.focus();"
        "const proto = inp.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;"
        "const desc = Object.getOwnPropertyDescriptor(proto, 'value');"
        "if (desc && desc.set) desc.set.call(inp, q); else inp.value = q;"
        "inp.dispatchEvent(new Event('input', {bubbles:true}));"
        "inp.dispatchEvent(new Event('change', {bubbles:true}));"
        "const form = inp.closest('form');"
        "let clicked = false;"
        "for (const sb of subs) {"
        "  const btn = (form ? form.querySelector(sb) : null) || document.querySelector(sb);"
        "  if (btn && btn.offsetParent !== null) { btn.click(); clicked = true; break; }"
        "}"
        "if (!clicked && form) { if (form.requestSubmit) form.requestSubmit(); else form.submit(); clicked = true; }"
        "if (!clicked) { inp.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, bubbles:true})); }"
        "return JSON.stringify({filled:true, submitted:true});"
        "})()"
    )


def visual_chrome_navigate_and_search(
    site: Optional[str] = None,
    query: Optional[str] = None,
    url: Optional[str] = None,
    focus: bool = True,
    runner: Optional[Callable[[str, float], tuple[bool, str]]] = None,
    lang: str = "auto",
) -> dict[str, Any]:
    """Opens Google Chrome in focus, navigates visually, fills the search form, and submits the search."""
    global _LAST_OPENED_BROWSER_PAGE
    eff_lang = "en" if lang == "en" else "it"
    cfg = dict(SITE_SEARCH_CONFIGS.get((site or "").lower(), {}))
    if eff_lang == "en" and (site or "").lower() == "wikipedia" and not url:
        cfg["base_url"] = "https://en.wikipedia.org"
        cfg["search_url"] = "https://en.wikipedia.org/w/index.php?search={query}"
    target_url = url or cfg.get("base_url") or "https://www.google.com"
    exec_apple = runner or _default_osascript_runner
    sys_name = platform.system() if runner is None else "Darwin"

    method = "url_fallback"
    final_url = target_url
    page_title = site.capitalize() if site else target_url
    snippet = ""

    if sys_name == "Darwin":
        focus_line = "activate\n" if focus else ""
        open_script = (
            'tell application "Google Chrome"\n'
            f"  {focus_line}"
            "  if (count of windows) is 0 then make new window\n"
            f'  set newTab to make new tab at end of tabs of front window with properties {{URL:"{_escape_applescript_str(target_url)}"}}\n'
            "  set active tab index of front window to (count of tabs of front window)\n"
            "end tell"
        )
        ok_open, _ = exec_apple(open_script, 8.0)

        if ok_open and query:
            # Wait briefly for page DOM ready
            for _ in range(18):
                ok_load, load_out = exec_apple(
                    'tell application "Google Chrome" to get loading of active tab of front window',
                    4.0,
                )
                if ok_load and load_out.lower() == "false":
                    break
                if runner is None:
                    time.sleep(0.25)

            js_fill = _build_dom_search_js(query, cfg)
            fill_script = (
                'tell application "Google Chrome"\n'
                f"  {focus_line}"
                f'  execute active tab of front window javascript "{_escape_applescript_str(js_fill)}"\n'
                "end tell"
            )
            ok_fill, fill_out = exec_apple(fill_script, 8.0)
            filled_ok = False
            try:
                filled_ok = bool(json.loads(fill_out).get("filled"))
            except Exception:
                filled_ok = ok_fill and '"filled":true' in fill_out

            if filled_ok:
                method = "chrome_applescript_form_fill"
                if runner is None:
                    time.sleep(1.2)
                    for _ in range(14):
                        ok_l2, l2_out = exec_apple(
                            'tell application "Google Chrome" to get loading of active tab of front window',
                            4.0,
                        )
                        if ok_l2 and l2_out.lower() == "false":
                            break
                        time.sleep(0.25)
            else:
                # Fallback if site JS didn't allow Apple Events JS or form wasn't ready
                tmpl = cfg.get("search_url") or "https://www.google.com/search?q={query}"
                direct_url = tmpl.format(query=urllib.parse.quote_plus(query))
                exec_apple(
                    'tell application "Google Chrome"\n'
                    f"  {focus_line}"
                    f'  set URL of active tab of front window to "{_escape_applescript_str(direct_url)}"\n'
                    "end tell",
                    8.0,
                )
                method = "chrome_applescript_search_url"
                final_url = direct_url
                if runner is None:
                    time.sleep(1.2)

            # Inspect resulting opened page metadata
            info_js = (
                "(() => JSON.stringify({"
                "url: location.href, "
                "title: document.title, "
                "excerpt: ((document.querySelector('#mw-content-text p, main p, article p, p') || {}).innerText || '').slice(0, 260)"
                "}))()"
            )
            ok_info, info_raw = exec_apple(
                'tell application "Google Chrome" to execute active tab of front window javascript "'
                + _escape_applescript_str(info_js)
                + '"',
                6.0,
            )
            try:
                parsed_info = json.loads(info_raw)
                final_url = parsed_info.get("url") or final_url
                page_title = parsed_info.get("title") or page_title
                snippet = _clean_web_text(str(parsed_info.get("excerpt") or ""))
            except Exception:
                ok_u, u_out = exec_apple('tell application "Google Chrome" to get URL of active tab of front window', 4.0)
                ok_t, t_out = exec_apple('tell application "Google Chrome" to get title of active tab of front window', 4.0)
                if ok_u and u_out:
                    final_url = u_out
                if ok_t and t_out:
                    page_title = t_out
        elif ok_open:
            method = "chrome_applescript_open"
    else:
        # Cross-platform Linux visual browser launch
        tmpl = cfg.get("search_url") if query else None
        final_url = tmpl.format(query=urllib.parse.quote_plus(query)) if (tmpl and query) else (
            f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}" if query else target_url
        )
        open_url_in_chrome(final_url, background=not focus)
        method = "linux_chrome_open"

    _LAST_OPENED_BROWSER_PAGE = {
        "url": final_url,
        "title": page_title,
        "site": site or "web",
        "query": query,
        "snippet": snippet,
    }

    site_disp_it = site.capitalize() if site else "il browser"
    site_disp_en = site.capitalize() if site else "the browser"
    if query:
        summary_it = (
            f"Ho portato Chrome in primo piano, aperto {site_disp_it}, compilato il campo di ricerca con "
            f"'{query}' e inviato la ricerca. Pagina aperta: {page_title}."
        )
        summary_en = (
            f"I brought Chrome to the front, opened {site_disp_en}, filled the search field with "
            f"'{query}', and submitted the search. Opened page: {page_title}."
        )
        if snippet:
            summary_it += f" Anteprima: {snippet[:180]}"
            summary_en += f" Preview: {snippet[:180]}"
        summary_it += " Se vuoi, chiedimi di leggere o riassumere i concetti della pagina aperta."
        summary_en += " If you want, ask me to read or summarize the key concepts of the open page."
    else:
        summary_it = f"Ho aperto {final_url} su Google Chrome in primo piano."
        summary_en = f"I opened {final_url} in Google Chrome in the foreground."

    return {
        "ok": True,
        "lang": eff_lang,
        "skill": "visual-chrome-navigation",
        "method": method,
        "site": site,
        "query": query,
        "focus": focus,
        "target_url": target_url,
        "final_url": final_url,
        "page_title": page_title,
        "snippet": snippet,
        "summary": summary_en if eff_lang == "en" else summary_it,
        "summary_it": summary_it,
    }


def _fetch_html_text(url: str, timeout: float = 5.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Cortical-Browser-Reader)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw_html = resp.read().decode("utf-8", errors="ignore")
    parser = _ReadableHTMLParser()
    parser.feed(raw_html)
    return {
        "title": parser.title,
        "headings": parser.headings[:12],
        "text": _clean_web_text("".join(parser.chunks)),
    }


def read_active_chrome_page(
    runner: Optional[Callable[[str, float], tuple[bool, str]]] = None,
    fetch_fn: Optional[Callable[[str], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Extracts URL, title, headings, and clean semantic content from the currently focused Chrome tab."""
    exec_apple = runner or _default_osascript_runner
    sys_name = platform.system() if runner is None else "Darwin"
    url = str(_LAST_OPENED_BROWSER_PAGE.get("url") or "")
    title = str(_LAST_OPENED_BROWSER_PAGE.get("title") or "")
    headings: list[str] = []
    text = ""

    if sys_name == "Darwin":
        extract_js = (
            "(() => {"
            "const root = document.querySelector('#mw-content-text .mw-parser-output, #bodyContent, main, article') || document.body;"
            "const hs = Array.from(root.querySelectorAll('h1, h2, h3')).map(h => h.innerText.trim()).filter(Boolean).slice(0, 12);"
            "const ps = Array.from(root.querySelectorAll('p')).map(p => p.innerText.trim()).filter(t => t.length > 25);"
            "const bodyTxt = ps.length ? ps.join('\\n\\n') : (root.innerText || '');"
            "return JSON.stringify({url: location.href, title: document.title, headings: hs, text: bodyTxt.slice(0, 7000)});"
            "})()"
        )
        ok_js, raw_js = exec_apple(
            'tell application "Google Chrome" to execute active tab of front window javascript "'
            + _escape_applescript_str(extract_js)
            + '"',
            8.0,
        )
        try:
            parsed = json.loads(raw_js) if ok_js and raw_js else {}
            url = parsed.get("url") or url
            title = parsed.get("title") or title
            headings = list(parsed.get("headings") or [])
            text = _clean_web_text(str(parsed.get("text") or ""))
        except Exception:
            ok_u, u_out = exec_apple('tell application "Google Chrome" to get URL of active tab of front window', 4.0)
            ok_t, t_out = exec_apple('tell application "Google Chrome" to get title of active tab of front window', 4.0)
            if ok_u and u_out:
                url = u_out
            if ok_t and t_out:
                title = t_out

    if not text and url and url.startswith(("http://", "https://")):
        try:
            fetcher = fetch_fn or _fetch_html_text
            fetched = fetcher(url)
            title = title or str(fetched.get("title") or "")
            headings = headings or list(fetched.get("headings") or [])
            text = _clean_web_text(str(fetched.get("text") or ""))
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": bool(text),
        "url": url,
        "title": title or "Pagina aperta su Chrome",
        "headings": headings,
        "text": text,
    }


def format_page_reading_response(
    page: dict[str, Any],
    mode: str = "summarize",
    summarize_llm_fn: Optional[Callable[[str], str]] = None,
    lang: str = "it",
) -> str:
    """Formats either a concept summary or clean spoken reading of the active Chrome page in IT or EN."""
    eff_lang = "en" if lang == "en" else "it"
    title = str(page.get("title") or ("Web page" if eff_lang == "en" else "Pagina web"))
    text = str(page.get("text") or "").strip()
    headings = [str(h) for h in (page.get("headings") or []) if h]
    if not text:
        if eff_lang == "en":
            return f"I cannot read the text content of the open tab ({page.get('url') or 'Chrome'}). Make sure Allow JavaScript from Apple Events is enabled in Chrome or that the page finished loading."
        return f"Non riesco a leggere il contenuto testuale della scheda aperta ({page.get('url') or 'Chrome'}). Assicurati che in Chrome sia abilitato JavaScript da eventi Apple o che la pagina sia caricata."

    if mode == "read":
        excerpt = text[:850]
        last_dot = excerpt.rfind(".")
        if last_dot > 250:
            excerpt = excerpt[: last_dot + 1]
        return (f"Reading page {title}. {excerpt}" if eff_lang == "en" else f"Lettura della pagina {title}. {excerpt}")

    if summarize_llm_fn is not None:
        if eff_lang == "en":
            llm_prompt = (
                "You are Cortical. Summarize the main concepts of this open Chrome web page in clear, natural spoken English (4-5 complete sentences).\n"
                f"Title: {title}\n"
                f"Sections: {', '.join(headings[:6])}\n\n"
                f"Extracted text:\n{text[:3200]}"
            )
        else:
            llm_prompt = (
                "Sei Cortical. Riassumi in italiano chiaro, scorrevole e naturale i concetti principali di questa pagina web aperta su Chrome (4-5 frasi complete da ascoltare a voce).\n"
                f"Titolo: {title}\n"
                f"Sezioni: {', '.join(headings[:6])}\n\n"
                f"Testo estratto:\n{text[:3200]}"
            )
        llm_out = summarize_llm_fn(llm_prompt)
        if llm_out and "ho ricevuto la richiesta" not in llm_out.lower():
            return llm_out

    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 40]
    lead = paragraphs[0][:380] if paragraphs else text[:380]
    if eff_lang == "en":
        sec_note = f" Key sections cover: {', '.join(headings[:5])}." if headings else ""
        extra = f" Additionally: {paragraphs[1][:260]}" if len(paragraphs) > 1 else ""
        return f"Key concepts from {title}: {lead}.{sec_note}{extra}".replace("..", ".")
    sec_note = f" Le sezioni principali trattano: {', '.join(headings[:5])}." if headings else ""
    extra = f" Inoltre: {paragraphs[1][:260]}" if len(paragraphs) > 1 else ""
    return f"Concetti chiave dalla pagina {title}: {lead}.{sec_note}{extra}".replace("..", ".")
