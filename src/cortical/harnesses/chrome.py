"""Chrome Profile Resolver, Authenticated CDP (:9222) Launcher & Form Automation for Pi/Harnesses."""

from __future__ import annotations

import html.parser
import json
import os
import platform
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional


DEFAULT_CHROME_PORT = 9222


def _system_chrome_dir() -> Path:
    if platform.system() == "Darwin":
        return (Path.home() / "Library" / "Application Support" / "Google" / "Chrome").expanduser()
    return (Path.home() / ".config" / "google-chrome").expanduser()


def _profile_cfg_path() -> Path:
    return (Path.home() / ".cortical_data" / "chrome_profile.json").resolve()


def _find_chrome_executable() -> Optional[str]:
    if platform.system() == "Darwin":
        mac_app = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if Path(mac_app).exists():
            return mac_app
    for cand in ("google-chrome", "google-chrome-stable", "chromium"):
        found = shutil.which(cand)
        if found:
            return found
    return None


def _is_chrome_running() -> bool:
    try:
        cmd = ["pgrep", "-x", "Google Chrome"] if platform.system() == "Darwin" else ["pgrep", "-f", "chrome"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
        return res.returncode == 0 and bool(res.stdout.strip())
    except Exception:
        return False


def _read_devtools_active_port() -> Optional[dict[str, Any]]:
    port_file = _system_chrome_dir() / "DevToolsActivePort"
    try:
        if not port_file.exists() or not _is_chrome_running():
            return None
        lines = [ln.strip() for ln in port_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(lines) >= 2 and lines[0].isdigit() and lines[1].startswith("/devtools/"):
            p = int(lines[0])
            return {
                "port": p,
                "ws_path": lines[1],
                "webSocketDebuggerUrl": f"ws://127.0.0.1:{p}{lines[1]}",
                "via": "devtools_active_port",
            }
    except Exception:
        return None
    return None


def probe_cdp(port: int = DEFAULT_CHROME_PORT, timeout: float = 0.8) -> Optional[dict[str, Any]]:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/version", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
            if isinstance(data, dict) and (data.get("webSocketDebuggerUrl") or data.get("Browser")):
                return data
    except Exception:
        pass
    if port == DEFAULT_CHROME_PORT:
        return _read_devtools_active_port()
    return None


def _cdp_connect_target(cdp: dict[str, Any], port: int = DEFAULT_CHROME_PORT) -> str:
    if cdp.get("via") == "devtools_active_port" and cdp.get("webSocketDebuggerUrl"):
        return str(cdp["webSocketDebuggerUrl"])
    return f"http://127.0.0.1:{port}"


def discover_chrome_profiles(system_dir: Optional[Path] = None) -> dict[str, Any]:
    sys_dir = Path(system_dir) if system_dir else _system_chrome_dir()
    profiles: list[dict[str, Any]] = []
    local_state = sys_dir / "Local State"
    error = ""
    try:
        if local_state.exists():
            raw = json.loads(local_state.read_text(encoding="utf-8"))
            cache = ((raw.get("profile") or {}).get("info_cache")) or {}
            for dir_name, info in cache.items():
                if not isinstance(info, dict):
                    continue
                profiles.append({
                    "profile_directory": dir_name,
                    "email": str(info.get("user_name") or "").strip(),
                    "name": str(info.get("name") or dir_name).strip(),
                    "user_data_dir": str(sys_dir),
                })
    except Exception as exc:
        error = str(exc)

    cfg_path = _profile_cfg_path()
    selected = {"mode": "system_chrome", "profile_directory": "Default", "email": "", "user_data_dir": str(sys_dir)}
    if cfg_path.exists():
        try:
            selected.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        except Exception:
            pass

    return {
        "ok": True,
        "selected": selected,
        "profiles": profiles,
        "chrome_running": _is_chrome_running(),
        "debug_port_active": bool(probe_cdp()),
        "error": error,
    }


def resolve_and_save_profile(email_or_dir: str = "ccancellieri@gmail.com", system_dir: Optional[Path] = None) -> dict[str, Any]:
    needle = (email_or_dir or "Default").strip().lower()
    sys_dir = Path(system_dir) if system_dir else _system_chrome_dir()
    disc = discover_chrome_profiles(sys_dir)
    matched = None
    for p in disc.get("profiles", []):
        if needle in (p["email"].lower(), p["profile_directory"].lower(), p["name"].lower()):
            matched = p
            break
    cfg = {
        "mode": "system_chrome",
        "profile_directory": (matched or {}).get("profile_directory") or ("Default" if "@" in needle else email_or_dir),
        "email": (matched or {}).get("email") or (email_or_dir if "@" in email_or_dir else ""),
        "user_data_dir": str(sys_dir),
    }
    cfg_p = _profile_cfg_path()
    cfg_p.parent.mkdir(parents=True, exist_ok=True)
    cfg_p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return cfg


def relaunch_chrome_with_profile(
    email_or_dir: str = "ccancellieri@gmail.com",
    *,
    port: int = DEFAULT_CHROME_PORT,
    target_url: str = "",
    isolated_cdp_dir: bool = True,
    kill_personal_chrome: bool = False,
) -> dict[str, Any]:
    cfg = resolve_and_save_profile(email_or_dir)
    profile_dir = cfg["profile_directory"]
    if probe_cdp(port):
        if target_url:
            enc = urllib.parse.quote(target_url, safe=":/?&=#%+~")
            try:
                urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{enc}", method="PUT"), timeout=2.0)  # noqa: S310
            except Exception:
                pass
        return {"ok": True, "already_active": True, "port": port, **cfg}

    exe = _find_chrome_executable()
    if not exe:
        return {"ok": False, "error": "chrome_executable_not_found"}

    # Never kill the user's personal Google Chrome unless explicitly requested.
    # Modern Chrome (136+) ignores --remote-debugging-port on the default User Data Dir,
    # so Cortical uses a persistent dedicated CDP profile (~/.cortical_data/chrome_cdp_profile).
    if kill_personal_chrome and not isolated_cdp_dir and platform.system() == "Darwin" and _is_chrome_running():
        subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to quit'], capture_output=True, timeout=4.0)
        for _ in range(20):
            if not _is_chrome_running():
                break
            time.sleep(0.25)

    cmd = [
        exe,
        f"--remote-debugging-port={port}",
        f"--profile-directory={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if isolated_cdp_dir:
        cdp_dir = (Path.home() / ".cortical_data" / "chrome_cdp_profile").resolve()
        cdp_dir.mkdir(parents=True, exist_ok=True)
        cmd.append(f"--user-data-dir={cdp_dir}")
    else:
        cmd.append("--restore-last-session")
    if target_url:
        cmd.append(target_url)
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    for _ in range(24):
        info = probe_cdp(port)
        if info:
            return {"ok": True, "relaunched": True, "isolated_cdp_dir": isolated_cdp_dir, "port": port, "ws_endpoint": info.get("webSocketDebuggerUrl", ""), **cfg}
        time.sleep(0.25)
    return {"ok": False, "error": "chrome_debug_relaunch_timeout", "port": port, **cfg}


class _PageParser(html.parser.HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._skip = 0
        self._in_title = False
        self.title = ""
        self.text_parts: list[str] = []
        self.forms: list[dict[str, Any]] = []
        self.links: list[dict[str, str]] = []
        self._href = ""
        self._link_txt: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        t = tag.lower()
        am = {k.lower(): (v or "") for k, v in attrs}
        if t in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        elif t == "title":
            self._in_title = True
        elif t == "a" and am.get("href"):
            self._href = urllib.parse.urljoin(self.base_url, am["href"])
            self._link_txt = []
        elif t in {"input", "textarea", "select"}:
            tp = am.get("type", "text" if t == "input" else t).lower()
            if tp not in {"hidden", "submit", "button"}:
                self.forms.append({"tag": t, "type": tp, "name": am.get("name", ""), "id": am.get("id", ""), "placeholder": am.get("placeholder", ""), "required": "required" in am})

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {"script", "style", "noscript", "svg"} and self._skip > 0:
            self._skip -= 1
        elif t == "title":
            self._in_title = False
        elif t == "a" and self._href:
            lbl = " ".join(self._link_txt).strip()
            if lbl and self._href.startswith(("http://", "https://")) and len(self.links) < 20:
                self.links.append({"text": lbl[:100], "url": self._href})
            self._href = ""

    def handle_data(self, data: str) -> None:
        if self._skip > 0:
            return
        clean = " ".join(data.split())
        if not clean:
            return
        if self._in_title and not self.title:
            self.title = clean
        if self._href:
            self._link_txt.append(clean)
        self.text_parts.append(clean)


def ensure_chrome_connected(
    email_or_dir: str = "ccancellieri@gmail.com",
    *,
    port: int = DEFAULT_CHROME_PORT,
    auto_relaunch: bool = True,
) -> dict[str, Any]:
    """Ensures an autonomous connection to the user's open Chrome session (:9222)."""
    if probe_cdp(port):
        return {"ok": True, "cdp_attached": True, "port": port, "tabs": list_open_tabs(port=port, auto_attach=False)}
    if auto_relaunch:
        rel = relaunch_chrome_with_profile(email_or_dir, port=port)
        if rel.get("ok"):
            return {"ok": True, "cdp_attached": True, "port": port, "relaunched": True, "tabs": list_open_tabs(port=port, auto_attach=False)}
        return rel
    return {"ok": False, "cdp_attached": False, "port": port, "error": "chrome_cdp_not_active"}


def list_open_tabs(*, port: int = DEFAULT_CHROME_PORT, auto_attach: bool = False) -> list[dict[str, str]]:
    """Lists open Chrome page tabs via CDP :9222 without killing the user's personal Chrome."""
    if auto_attach and not probe_cdp(port):
        relaunch_chrome_with_profile("ccancellieri@gmail.com", port=port)
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/list", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:  # noqa: S310
            targets = json.loads(resp.read().decode("utf-8", errors="ignore") or "[]")
        tabs = []
        for t in targets:
            if isinstance(t, dict) and t.get("type") == "page":
                u = str(t.get("url") or "")
                if u.startswith(("http://", "https://")):
                    tabs.append({"id": str(t.get("id") or ""), "title": str(t.get("title") or ""), "url": u})
        return tabs
    except Exception:
        return []


def read_active_or_url_tab(url: str = "", *, port: int = DEFAULT_CHROME_PORT) -> dict[str, Any]:
    """Reads the currently open active Chrome tab OR navigates to `url` cleanly."""
    if url:
        return extract_page_and_forms(url, port=port)
    if not probe_cdp(port):
        relaunch_chrome_with_profile("ccancellieri@gmail.com", port=port)
    tabs = list_open_tabs(port=port, auto_attach=False)
    if not tabs:
        return {"ok": False, "error": "no_open_http_tabs_found"}
    return extract_page_and_forms(tabs[0]["url"], port=port)


def _launch_headless_persistent(p: Any) -> Any:
    persist_dir = (Path.home() / ".cortical_data" / "chrome_headless_fallback").resolve()
    persist_dir.mkdir(parents=True, exist_ok=True)
    try:
        return p.chromium.launch_persistent_context(str(persist_dir), channel="chrome", headless=True)
    except Exception:
        return p.chromium.launch_persistent_context(str(persist_dir), headless=True)


def click_in_chrome(
    selector_or_text: str,
    *,
    url: str = "",
    port: int = DEFAULT_CHROME_PORT,
) -> dict[str, Any]:
    """Clicks a button/link by CSS selector or visible text via CDP (:9222) or Playwright fallback."""
    cdp = probe_cdp(port)
    if not cdp and not url:
        return {"ok": False, "error": "chrome_cdp_not_active: pass url or run chrome_attach first"}
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        with sync_playwright() as p:
            persistent_ctx = None
            if cdp:
                browser = p.chromium.connect_over_cdp(_cdp_connect_target(cdp, port), timeout=4000)
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.pages[-1] if (not url and ctx.pages) else ctx.new_page()
            else:
                persistent_ctx = _launch_headless_persistent(p)
                page = persistent_ctx.new_page()
            try:
                if url:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1000)
                target = selector_or_text.strip()
                clicked = ""
                try:
                    loc = page.locator(target).first
                    if loc.count() > 0:
                        loc.click(timeout=5000)
                        clicked = f"selector:{target}"
                except Exception:
                    pass
                if not clicked:
                    loc = page.get_by_text(target, exact=False).first
                    loc.click(timeout=5000)
                    clicked = f"text:{target}"
                page.wait_for_timeout(1200)
                return {
                    "ok": True,
                    "via": "chrome_cdp" if cdp else "playwright_persistent",
                    "cdp_attached": bool(cdp),
                    "clicked": clicked,
                    "final_url": page.url,
                    "title": page.title(),
                }
            finally:
                if persistent_ctx is not None:
                    persistent_ctx.close()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _extract_from_page(page: Any) -> dict[str, Any]:
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:
        pass
    page.wait_for_timeout(800)
    return page.evaluate("""() => ({
        title: document.title || '',
        url: location.href,
        text: (document.body ? document.body.innerText : '').slice(0, 4500),
        forms: Array.from(document.querySelectorAll('input,textarea,select')).map(e => ({
            tag: e.tagName.toLowerCase(), type: e.type || e.tagName.toLowerCase(),
            name: e.name || '', id: e.id || '', placeholder: e.placeholder || '', required: !!e.required
        })).filter(f => !['hidden','submit','button'].includes(f.type)).slice(0, 40),
        links: Array.from(document.querySelectorAll('a[href]')).slice(0, 20).map(a => ({text: (a.innerText||'').trim().slice(0,100), url: a.href}))
    })""")


def extract_page_and_forms(url: str, port: int = DEFAULT_CHROME_PORT) -> dict[str, Any]:
    target = str(url or "").strip()
    if not target.startswith(("http://", "https://")):
        return {"ok": False, "error": f"invalid_url:{target}"}
    cdp = probe_cdp(port)
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        with sync_playwright() as p:
            if cdp:
                try:
                    browser = p.chromium.connect_over_cdp(_cdp_connect_target(cdp, port), timeout=4000)
                    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                    page = ctx.new_page()
                    try:
                        page.goto(target, wait_until="domcontentloaded", timeout=20000)
                        data = _extract_from_page(page)
                        return {"ok": True, "via": "chrome_cdp", "cdp_attached": True, **data}
                    finally:
                        try:
                            page.close()
                        except Exception:
                            pass
                except Exception:
                    pass
            persistent_ctx = _launch_headless_persistent(p)
            try:
                page = persistent_ctx.new_page()
                page.goto(target, wait_until="domcontentloaded", timeout=20000)
                data = _extract_from_page(page)
                return {"ok": True, "via": "playwright_persistent", "cdp_attached": False, **data}
            finally:
                persistent_ctx.close()
    except Exception:
        pass
    try:
        req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) Cortical/0.4"})
        with urllib.request.urlopen(req, timeout=15.0) as resp:  # noqa: S310
            html_txt = resp.read().decode("utf-8", errors="ignore")
        parser = _PageParser(target)
        parser.feed(html_txt)
        return {"ok": True, "via": "http_parser", "cdp_attached": False, "title": parser.title, "url": target, "text": "\n".join(parser.text_parts)[:4500], "forms": parser.forms[:40], "links": parser.links[:20]}
    except Exception as exc:
        return {"ok": False, "url": target, "error": str(exc)}


def fill_form_and_upload(
    url: str,
    fields: dict[str, str],
    *,
    upload_file: str = "",
    submit: bool = False,
    port: int = DEFAULT_CHROME_PORT,
) -> dict[str, Any]:
    target = str(url or "").strip()
    if not target.startswith(("http://", "https://")):
        return {"ok": False, "error": f"invalid_url:{target}"}
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except Exception as exc:
        return {"ok": False, "error": f"playwright_not_available:{exc}"}

    cdp = probe_cdp(port)
    filled: list[str] = []
    missing: list[str] = []
    with sync_playwright() as p:
        persistent_ctx = None
        if cdp:
            try:
                browser = p.chromium.connect_over_cdp(_cdp_connect_target(cdp, port), timeout=4000)
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            except Exception:
                cdp = None
                persistent_ctx = _launch_headless_persistent(p)
                ctx = persistent_ctx
        else:
            persistent_ctx = _launch_headless_persistent(p)
            ctx = persistent_ctx
        try:
            page = ctx.new_page()
            page.goto(target, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1200)
            for key, val in (fields or {}).items():
                k, v = str(key).strip(), str(val)
                loc = None
                for sel in (f"[name='{k}']", f"#{k}", f"[id*='{k}' i]", f"[placeholder*='{k}' i]", f"[aria-label*='{k}' i]"):
                    try:
                        cand = page.locator(sel).first
                        if cand.count() > 0:
                            loc = cand
                            break
                    except Exception:
                        continue
                if loc is not None:
                    if loc.evaluate("e => e.tagName.toLowerCase()") == "select":
                        loc.select_option(label=v)
                    else:
                        loc.fill(v)
                    filled.append(k)
                else:
                    missing.append(k)
            uploaded = False
            if upload_file and Path(upload_file).expanduser().is_file():
                f_loc = page.locator("input[type='file']").first
                if f_loc.count() > 0:
                    f_loc.set_input_files(str(Path(upload_file).expanduser().resolve()))
                    uploaded = True
            submitted = False
            if submit:
                sb = page.locator("button[type='submit'], input[type='submit']").first
                if sb.count() > 0:
                    sb.click()
                    page.wait_for_timeout(1500)
                    submitted = True
            return {"ok": True, "via": "chrome_cdp" if cdp else "playwright_persistent", "cdp_attached": bool(cdp), "final_url": page.url, "filled": filled, "missing": missing, "uploaded": uploaded, "submitted": submitted}
        finally:
            if persistent_ctx is not None:
                persistent_ctx.close()
