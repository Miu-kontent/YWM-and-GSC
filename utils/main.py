import os
import sys
import json
import time
import socket
import threading
import subprocess
import webview
import requests
import websocket
import shutil
import zipfile
import io
import ctypes

# import webbrowser

# Отладочные браузеры сервисов: свой порт и профиль на каждый сервис
# (используются для UI-автоматизации и OAuth-авторизации через вкладку браузера).
BROWSER_PORTS = {
    "yandex": 9229,
    "google": 9227,
    "bing": 9225,
}

BROWSER_PROFILES = {
    "yandex": "chrome-debug-yandex",
    "google": "chrome-debug-google",
    "bing": "chrome-debug-bing",
}

# ======================== BING WEBMASTER API / OAUTH ========================

BING_AUTH_URL = "https://www.bing.com/webmasters/oauth/authorize"

# Эндпоинт обмена кода/refresh-токена. В документации Microsoft расходится:
# в тексте — /webmasters/oauth/token, в примере запроса — POST /webmasters/token.
# Поэтому пробуем оба (первый рабочий и запоминаем результат).
BING_TOKEN_URLS = (
    "https://www.bing.com/webmasters/oauth/token",
    "https://www.bing.com/webmasters/token",
)

BING_API_BASE = "https://www.bing.com/webmaster/api.svc/json"
BING_DEFAULT_SCOPE = "webmaster.manage"

# Сколько ждём редиректа с кодом авторизации (вход в Microsoft + согласие).
BING_AUTH_TIMEOUT = 300

# Сколько символов хвоста токена показываем в диагностике авторизации.
TOKEN_TAIL_LEN = 8


def _mask_token(token):
    """Хвост токена для лога: секрет целиком в лог не пишем."""
    token = str(token or "")
    return token[-TOKEN_TAIL_LEN:] if token else "—"

# Профили дебаг-браузеров (debug_profiles/<profile>) хранят входы/сессии (Cookies,
# Local Storage и т.п. — их НЕ трогаем). При старте программы точечно удаляем только
# перекачиваемые кэши и компоненты, чтобы профили не разрастались (см. clean_browser_cache).
BROWSER_CACHE_ITEMS = (
    "Default/Cache",
    "Default/Code Cache",
    "Default/GPUCache",
    "Default/GrShaderCache",
    "GrShaderCache",
    "ShaderCache",
    "component_crx_cache",
    "extensions_crx_cache",
    "optimization_guide_model_store",
    "optimization_guide_model_info_cache",
    "OptimizationGuideModelsManifest",
    "Safe Browsing",
    "Snapshots",
    "WasmTtsEngine",
    "segmentation_platform",
    "OnDeviceHeadSuggestModel",
    "hyphen-data",
    "ZxcvbnData",
    "PKIMetadata",
    "OptimizationHints",
    "Subresource Filter",
    "Crowd Deny",
    "SafetyTips",
    "CertificateRevocation",
    "ActorSafetyLists",
    "TrustTokenKeyCommitments",
    "FirstPartySetsPreloaded",
    "PrivacySandboxAttestationsPreloaded",
    "MEIPreload",
    "FileTypePolicies",
    "AmountExtractionHeuristicRegexes",
    "CaptchaProviders",
    "OriginTrials",
    "SSLErrorAssistant",
    "RecoveryImproved",
    "GPUPersistentCache",
)

class Api:
    def __init__(self):
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.yandex_dir = os.path.join(self.base_dir, "yandex")
        self.google_dir = os.path.join(self.base_dir, "google")
        self.gui_dir = os.path.join(self.base_dir, "gui")
        self.utils_dir = os.path.join(self.base_dir, "utils")
        self.version_path = os.path.join(self.utils_dir, "version.json")
        self.remote_version_url = "https://raw.githubusercontent.com/Miu-kontent/YWM-and-GSC/main/utils/version.json"
        self.repo_zip_url = "https://api.github.com/repos/Miu-kontent/YWM-and-GSC/zipball/main"
        self.yandex_app_config_path = os.path.join(self.yandex_dir, "app_config.json")
        self.yandex_config_path = os.path.join(self.yandex_dir, "config.json")
        self.yandex_accounts_path = os.path.join(self.yandex_dir, "accounts.json")
        self.yandex_arrays_dir = os.path.join(self.yandex_dir, "arrays")
        self.yandex_scripts_dir = os.path.join(self.yandex_dir, "scripts")
        self.google_config_path = os.path.join(self.google_dir, "config.json")
        self.google_app_config_path = os.path.join(self.google_dir, "app_config.json")
        self.google_accounts_path = os.path.join(self.google_dir, "accounts.json")
        self.google_arrays_dir = os.path.join(self.google_dir, "arrays")
        self.google_scripts_dir = os.path.join(self.google_dir, "scripts")

        self.bing_dir = os.path.join(self.base_dir, "bing")
        self.bing_config_path = os.path.join(self.bing_dir, "config.json")
        self.bing_accounts_path = os.path.join(self.bing_dir, "accounts.json")
        self.bing_app_config_path = os.path.join(self.bing_dir, "app_config.json")
        self.bing_arrays_dir = os.path.join(self.bing_dir, "arrays")
        self.bing_scripts_dir = os.path.join(self.bing_dir, "scripts")

        self.running_processes = {}
        self.stopped_scripts = set()

    # ======================== СЕРВИСЫ ========================

    def _service_dir(self, service):
        return {"yandex": self.yandex_dir, "google": self.google_dir, "bing": self.bing_dir}[service]

    def _config_path(self, service):
        return {"yandex": self.yandex_config_path, "google": self.google_config_path,
                "bing": self.bing_config_path}[service]

    def _arrays_dir(self, service):
        return {"yandex": self.yandex_arrays_dir, "google": self.google_arrays_dir,
                "bing": self.bing_arrays_dir}[service]

    def _scripts_dir(self, service):
        return {"yandex": self.yandex_scripts_dir, "google": self.google_scripts_dir,
                "bing": self.bing_scripts_dir}[service]

    def _browser_port(self, service):
        """Порт отладочного браузера сервиса (yandex 9229, google 9227, bing 9225)."""
        return BROWSER_PORTS[service]

    def _browser_profile(self, service):
        return BROWSER_PROFILES[service]

    def _devtools_info(self, port):
        """CDP-инфо (dict), если на порту отвечает реальный Chrome DevTools, иначе None.

        Строгая проверка: ответ должен быть валидным JSON с ключом "Browser".
        Это исключает ложное срабатывание, если порт занят произвольным HTTP-сервером
        или процессом-зомби, который не является отладочным Chrome.
        """
        try:
            r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, dict) and data.get("Browser"):
                return data
        except Exception:
            pass
        return None

    def _browser_is_running(self, port):
        return self._devtools_info(port) is not None

    def _webview2_control(self):
        """WebView2-контроллер окна приложения (None, если окно ещё не готово).

        В pywebview 6.x на Windows: window.native → BrowserForm (winforms),
        у него .browser → EdgeChrome, у того .webview → WebView2.
        """
        if not webview.windows:
            return None
        native = getattr(webview.windows[0], "native", None)
        for holder in (getattr(getattr(native, "browser", None), "webview", None),
                       getattr(native, "webview", None)):
            if holder is not None:
                return holder
        return None

    def open_devtools(self):
        """Открыть консоль разработчика (DevTools) окна приложения.

        Свойство CoreWebView2 у WebView2 доступно ТОЛЬКО из UI-потока, поэтому
        действие выполняется через Control.Invoke — так же, как это делает сам
        pywebview (platforms/edgechromium.py). Требует webview.start(debug=True),
        иначе WebView2 запрещает DevTools (AreDevToolsEnabled). Кнопка в GUI —
        страховка на случай, если F12 не сработает.
        """
        try:
            control = self._webview2_control()
            if control is None:
                return {"success": False, "message": "DevTools недоступны: окно ещё не инициализировано"}

            from System import Func, Object  # pythonnet загружен pywebview при старте окна

            state = {}

            def _open():
                try:
                    core = control.CoreWebView2
                    if core is None:
                        state['error'] = "WebView2 ещё не готов"
                        return
                    core.Settings.AreDevToolsEnabled = True
                    core.OpenDevToolsWindow()
                    state['ok'] = True
                except Exception as e:
                    state['error'] = str(e)

            delegate = Func[Object](_open)

            # WebView2 поднимается не сразу: коротко ждём готовности контроллера
            for _ in range(12):
                state.clear()
                control.Invoke(delegate)  # блокирует до выполнения в UI-потоке
                if state.get('ok'):
                    return {"success": True, "message": "Консоль разработчика открыта"}
                if 'ещё не готов' not in (state.get('error') or ''):
                    break
                time.sleep(0.3)

            reason = state.get('error') or 'неизвестная причина'
            return {"success": False, "message": f"DevTools недоступны: {reason}"}
        except Exception as e:
            return {"success": False, "message": f"Не удалось открыть консоль разработчика: {e}"}

    def clean_browser_cache(self):
        """Точечная очистка кэша дебаг-профилей. Входы сохраняются.

        Удаляются только перекачиваемые кэши/компоненты (Cache, Code Cache, CRX,
        Safe Browsing и т.п.) — Cookies/Local Storage/Login Data не трогаются.
        Если браузер профиля уже запущен (порт открыт) — профиль пропускается,
        чтобы не удалять файлы под работающим Chrome.

        Вызывается из GUI после загрузки окна (а не в __init__), чтобы не задерживать
        старт. Возвращает список сообщений для лога GUI.
        """
        logs = []
        for name, port in BROWSER_PORTS.items():
            profile_name = BROWSER_PROFILES[name]
            if self._browser_is_running(port):
                logs.append(f"ℹ️ Браузер {name} запущен (порт {port}), кэш не трогаю")
                continue
            profile_dir = os.path.join(self.base_dir, "debug_profiles", profile_name)
            if not os.path.isdir(profile_dir):
                logs.append(f"ℹ️ Профиль {name} не найден ({profile_name})")
                continue
            removed = 0
            skipped = 0
            for rel in BROWSER_CACHE_ITEMS:
                target = os.path.join(profile_dir, rel.replace("/", os.sep))
                if not os.path.exists(target):
                    continue
                try:
                    if os.path.isdir(target):
                        shutil.rmtree(target, ignore_errors=True)
                    else:
                        os.remove(target)
                    removed += 1
                except Exception:
                    skipped += 1
            logs.append(f"✅ {name}: очищено элементов кэша: {removed}{', не удалось: ' + str(skipped) if skipped else ''}")
        return logs

    def get_local_version(self):
        if os.path.exists(self.version_path):
            try:
                with open(self.version_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("version", "1.0.0")
            except Exception:
                pass
        return "1.0.0"

    def check_updates(self):
        """Сравнение локальных версий с удаленным репозиторием на GitHub"""
        local_ver = self.get_local_version()
        try:
            cache_buster = f"{self.remote_version_url}?nocache={int(time.time())}"
            headers = {"Cache-Control": "no-cache"}
            response = requests.get(cache_buster, headers=headers, timeout=5)
            if response.status_code == 200:
                remote_ver = response.json().get("version", "1.0.0")
                def parse(v): return [int(x) for x in v.split('.')]
                result = {
                    "success": True,
                    "update_available": parse(remote_ver) > parse(local_ver),
                    "local_version": local_ver,
                    "remote_version": remote_ver
                }
                return result
            else:
                return {"success": False, "update_available": True, "local_version": local_ver, "error_code": response.status_code}
        except Exception as e:
            return {"success": False, "update_available": False, "local_version": local_ver, "error_code": e}

    def update_app(self) -> dict:
        """Загрузка и распаковка обновления лаунчера"""
        try:
            headers = {"Cache-Control": "no-cache"}
            cache_buster = f"?nocache={int(time.time())}"
            response = requests.get(self.repo_zip_url + cache_buster, headers=headers, timeout=60)
            if response.status_code != 200:
                return {"success": False, "message": f"Ошибка сети HTTP {response.status_code}"}

            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                root_prefix = z.namelist()[0].split('/')[0] + '/'
                skip_tail = (
                    ".git/", ".venv", "config.json", "app_config.json",
                    "accounts.json", "ЯВМ и GSC.exe"
                )
                for member in z.namelist():
                    if member == root_prefix:
                        continue
                    rel_path = member[len(root_prefix):]
                    if any(rel_path.endswith(t) or rel_path.startswith(t) for t in skip_tail):
                        continue
                    if "/arrays/" in rel_path:
                        continue

                    target_path = os.path.join(self.base_dir, rel_path)
                    if member.endswith('/'):
                        os.makedirs(target_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with z.open(member) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)

            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def restart_app(self):
        """Чистый перезапуск приложения с очисткой процессов"""
        python = sys.executable
        os.execl(python, python, *sys.argv)
            
    def get_config(self, service):
        path = self._config_path(service)
        default = {
            "yandex": {
                "active_account": "",
                "metric_id": "",
                "contact_path": "",
                "sitemap_path": ""
            },
            "google": {
                "active_account": "",
                "sitemap_path": ""
            },
            # Bing: аккаунт выбирается после OAuth-авторизации
            "bing": {
                "active_account": "",
                "sitemap_path": ""
            },
        }.get(service, {}).copy()

        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                default.update(data)
        except Exception as e:
            print(f"[API] Ошибка чтения {service} config: {e}")
        return default

    def save_config(self, service, data):
        path = self._config_path(service)
        try:
            current = self.get_config(service)
            current.update(data)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=4)
            return {"success": True}
        except Exception as e:
            print(f"[API] Ошибка сохранения {service} config: {e}")
            return {"success": False}

    def get_registry(self, service):
        registry_path = os.path.join(self._service_dir(service), "registry.json")
        if os.path.exists(registry_path):
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[API] Ошибка чтения registry для {service}: {e}")
        return {"categories": [], "excludedScripts": []}

    def get_scripts_list(self, service):
        registry = self.get_registry(service)
        excluded = set(registry.get("excludedScripts", []))
        scripts_dir = self._scripts_dir(service)
        os.makedirs(scripts_dir, exist_ok=True)
        scripts = []
        for f in os.listdir(scripts_dir):
            name = os.path.splitext(f)[0]
            ext = os.path.splitext(f)[1]
            if name in excluded:
                continue
            if ext in (".js", ".py"):
                scripts.append({"name": name, "type": ext[1:]})
        return {"scripts": scripts}

    def _get_arrays_dir(self, service):
        return self._arrays_dir(service)

    def _get_script_array_path(self, service, script_name):
        return os.path.join(self._get_arrays_dir(service), f"{script_name}.json")

    def save_script_data(self, service, script_name, data):
        try:
            path = self._get_script_array_path(service, script_name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return {"success": True}
        except Exception as e:
            print(f"[API] Ошибка сохранения данных скрипта {script_name}: {e}")
            return {"success": False}

    def get_script_data(self, service, script_name):
        path = self._get_script_array_path(service, script_name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def get_scripts_data(self, service):
        arrays_dir = self._get_arrays_dir(service)
        result = {}
        if not os.path.isdir(arrays_dir):
            return result
        for fname in os.listdir(arrays_dir):
            if fname.endswith(".json"):
                script_name = os.path.splitext(fname)[0]
                result[script_name] = self.get_script_data(service, script_name)
        return result

    def generate_arr(self, service, script_name):
        data = self.get_script_data(service, script_name)
        try:
            path = self._get_script_array_path(service, script_name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"[API] Updated {path}")
        except Exception as e:
            print(f"[API] Ошибка генерации {script_name}.json: {e}")

    def check_browser(self, service):
        return {"success": True, "running": self._browser_is_running(self._browser_port(service))}

    def close_browser(self, service):
        """Мягкое закрытие отладочного браузера через CDP Browser.close.

        Chrome завершается корректно (все процессы профиля выходят), входы в профиле
        сохраняются, а очистка кэша при следующем старте уже не пропустится.
        """
        port = self._browser_port(service)
        info = self._devtools_info(port)
        if not info:
            return {"success": False, "message": f"Браузер {service} не запущен"}
        try:
            ws_url = info.get("webSocketDebuggerUrl")
            ws = websocket.create_connection(ws_url, timeout=5)
            ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
            try:
                ws.recv()
            except Exception:
                pass
            ws.close()
            return {"success": True, "message": f"Браузер {service} закрыт"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def launch_browser(self, service):
        port = self._browser_port(service)
        profiles_dir = os.path.join(self.base_dir, "debug_profiles")
        os.makedirs(profiles_dir, exist_ok=True)
        profile_name = self._browser_profile(service)
        profile_path = os.path.join(profiles_dir, profile_name)

        chrome_path = self._find_chrome()
        if not chrome_path:
            return {"success": False, "message": "Chrome не найден"}

        cmd = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_path}",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*"
        ]

        try:
            subprocess.Popen(cmd)
            return {"success": True, "message": f"Браузер для {service} запущен на порту {port}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _find_chrome(self):
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in possible_paths:
            if os.path.exists(p):
                return p
        return None

    def run_script(self, service, script_name):
        self.generate_arr(service, script_name)

        service_dir = self._service_dir(service)
        script_path = os.path.join(service_dir, "scripts", f"{script_name}.js")
        py_script_path = os.path.join(service_dir, "scripts", f"{script_name}.py")

        if os.path.exists(script_path):
            cmd = ["node", script_path]
        elif os.path.exists(py_script_path):
            cmd = [sys.executable, "-B", "-u", py_script_path]
        else:
            return {"success": False, "message": f"Скрипт {script_name} не найден"}

        process_key = f"{service}:{script_name}"
        if process_key in self.running_processes:
            return {"success": False, "message": "Скрипт уже запущен"}

        def stream_output(proc, key):
            for line in iter(proc.stdout.readline, b''):
                if line:
                    text = line.decode('utf-8', errors='replace').rstrip()
                    safe_text = json.dumps(text, ensure_ascii=False)
                    webview.windows[0].evaluate_js(f"appendLog('{key}', {safe_text})")
            proc.stdout.close()
            proc.wait()
            stopped = key in self.stopped_scripts
            self.running_processes.pop(key, None)
            self.stopped_scripts.discard(key)
            webview.windows[0].evaluate_js(
                f"scriptFinished('{key}', {proc.returncode}, {json.dumps(stopped)})"
            )

        try:
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'
            proc = subprocess.Popen(
                cmd,
                cwd=service_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env
            )
            self.running_processes[process_key] = proc
            thread = threading.Thread(target=stream_output, args=(proc, process_key), daemon=True)
            thread.start()
            return {"success": True, "message": f"Скрипт {script_name} запущен"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def stop_script(self, service, script_name):
        """Преждевременная остановка запущенного скрипта (жёстко, дерево процессов).

        Останавливается ТОЛЬКО процесс этого скрипта — параллельно запущенные
        другие скрипты не затрагиваются (у каждого свой PID/ключ).
        """
        process_key = f"{service}:{script_name}"
        proc = self.running_processes.get(process_key)
        if proc is None or proc.poll() is not None:
            return {"success": False, "message": "Процесс уже завершён"}

        self.stopped_scripts.add(process_key)
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, check=False
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        return {"success": True, "message": "Скрипт остановлен"}

    def _run_yandex_script(self, script_name):
        script_path = os.path.join(self.yandex_scripts_dir, f"{script_name}.py")
        if not os.path.exists(script_path):
            return {"success": False, "message": f"{script_name}.py не найден", "log": []}
        try:
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'
            proc = subprocess.run(
                [sys.executable, script_path],
                cwd=self.yandex_dir,
                capture_output=True, text=True, timeout=180, encoding="utf-8",
                env=env
            )
            log_lines = proc.stdout.splitlines()
            return {"success": proc.returncode == 0, "log": log_lines, "stdout": proc.stdout}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Таймаут (180 сек)", "log": ["❌ Таймаут: скрипт не завершился"]}
        except Exception as e:
            return {"success": False, "message": str(e), "log": [f"❌ {e}"]}

    def start_yandex_get_metrika_id(self):
        result = self._run_yandex_script("yandex_metrika_getcounter")
        metric_id = None
        for line in result.get("log", []):
            if line.startswith("METRIKA_ID:"):
                metric_id = line.split(":", 1)[1].strip()
        if metric_id:
            config = self.get_config("yandex")
            config["metric_id"] = metric_id
            self.save_config("yandex", config)

        msg = result.get("message", "")
        if not metric_id and not msg:
            for line in result.get("log", []):
                if line.startswith("⚠️") or line.startswith("❌"):
                    msg = line
                    break
            if not msg:
                msg = "Счётчик не получен"

        return {"success": bool(metric_id), "metric_id": metric_id or "", "message": msg, "log": result.get("log", [])}

    # ======================== YANDEX OAUTH (АККАУНТЫ) ========================

    def _get_yandex_app_config(self):
        if not os.path.exists(self.yandex_app_config_path):
            return {}
        try:
            with open(self.yandex_app_config_path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception as e:
            print(f"[API] Ошибка чтения yandex/app_config.json: {e}")
        return {}

    @staticmethod
    def _normalize_yandex_account_name(login):
        """login из Яндекс ID -> полный ник с доменом (ли <login@yandex.ru>), если не email."""
        login = (login or "").strip()
        if not login or "@" in login:
            return login
        return f"{login}@yandex.ru"

    def _load_yandex_accounts(self):
        data = {}
        if os.path.exists(self.yandex_accounts_path):
            try:
                with open(self.yandex_accounts_path, "r", encoding="utf-8-sig") as f:
                    loaded = json.load(f)
                data = loaded.get("accounts", loaded) if isinstance(loaded, dict) else {}
            except Exception as e:
                print(f"[API] Ошибка чтения yandex/accounts.json: {e}")
        # миграция: ключи-логины без домена -> <login>@yandex.ru
        migrated = {}
        changed = False
        for name, acc in (data or {}).items():
            new_name = self._normalize_yandex_account_name(name)
            migrated[new_name] = acc
            if new_name != name:
                changed = True
        if changed:
            self._save_yandex_accounts(migrated)
            cfg = self.get_config("yandex")
            active = (cfg.get("active_account") or "").strip()
            if active and active not in migrated:
                cfg["active_account"] = self._normalize_yandex_account_name(active)
                self.save_config("yandex", cfg)
        return migrated

    def _save_yandex_accounts(self, accounts):
        os.makedirs(self.yandex_dir, exist_ok=True)
        with open(self.yandex_accounts_path, "w", encoding="utf-8") as f:
            json.dump({"accounts": accounts}, f, ensure_ascii=False, indent=4)

    def _open_in_debug_browser(self, service, url):
        """Открывает URL новой вкладкой в отладочном Chrome сервиса через CDP /json/new.

        Порт берётся из BROWSER_PORTS (yandex 9229, google 9227, bing 9225).
        Возвращает данные цели (id/url/webSocketDebuggerUrl) или поднимает исключение.
        """
        import urllib.parse
        port = self._browser_port(service)
        try:
            resp = requests.put(
                f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(url, safe='')}",
                timeout=5,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"CDP ответил HTTP {resp.status_code}")
            return resp.json()
        except Exception as e:
            print(f"[API] Ошибка открытия вкладки в браузере {port}: {e}")
            raise RuntimeError(f"Не удалось открыть вкладку в браузере {port}: {e}")

    def _open_in_yandex_debug_browser(self, url):
        """Открывает URL новой вкладкой в отладочном Chrome (порт 9229) через CDP /json/new."""
        return self._open_in_debug_browser("yandex", url).get("webSocketDebuggerUrl", "")

    def _wait_for_yandex_token(self, ws_url, timeout=180):
        """Опрашивает страницу авторизации через WebSocket CDP (селектор токена implicit-потока)."""
        TOKEN_SELECTOR = ".verification-code-flow-token-output"
        poll_id = 88888
        try:
            ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)
        except Exception as e:
            raise RuntimeError(f"Ошибка подключения WebSocket CDP: {e}")
        token = ""
        start = time.time()
        try:
            while time.time() - start < timeout:
                try:
                    ws.send(json.dumps({
                        "id": poll_id,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": f"document.querySelector('{TOKEN_SELECTOR}')?.textContent || ''",
                            "returnByValue": True,
                        },
                    }))
                    ws.settimeout(3)
                    while True:
                        resp = json.loads(ws.recv())
                        if resp.get("id") == poll_id:
                            token = (resp.get("result", {}).get("result", {}).get("value", "") or "").strip()
                            break
                except Exception:
                    pass
                if token:
                    break
                time.sleep(2)
        finally:
            try:
                ws.close()
            except Exception:
                pass
        return token

    def yandex_authorize(self):
        browser = self.check_browser("yandex")
        if not browser.get("running"):
            return {"success": False,
                    "message": "Браузер Яндекс (порт 9229) не запущен. Откройте его кнопкой «🌐 Браузер (порт 9229)»"}

        app_cfg = self._get_yandex_app_config()
        client_id = app_cfg.get("client_id", "")
        if not client_id:
            return {"success": False, "message": "client_id не найден в yandex/app_config.json"}

        auth_url = f"https://oauth.yandex.ru/authorize?response_type=token&client_id={client_id}"

        try:
            ws_url = self._open_in_yandex_debug_browser(auth_url)
        except Exception as e:
            return {"success": False, "message": str(e)}
        if not ws_url:
            return {"success": False, "message": "Не удалось получить webSocketDebuggerUrl вкладки браузера"}

        print("[API] 🔐 Авторизуйтесь в открывшейся вкладке браузера (до 180 сек)...")
        try:
            token = self._wait_for_yandex_token(ws_url)
        except Exception as e:
            return {"success": False, "message": f"Ошибка ожидания токена: {e}"}
        if not token:
            return {"success": False,
                    "message": "Таймаут: токен не получен (180 сек). Авторизуйтесь в открывшейся вкладке браузера"}

        headers = {"Authorization": f"OAuth {token}"}

        try:
            r = requests.get("https://login.yandex.ru/info", headers=headers, timeout=10)
        except Exception as e:
            return {"success": False, "message": f"Не удалось получить логин из Яндекс ID: {e}"}
        if r.status_code != 200:
            return {"success": False, "message": f"Не удалось получить логин из Яндекс ID (HTTP {r.status_code})"}
        login = (r.json().get("login", "") or "").strip()
        if not login:
            return {"success": False, "message": "Пустой login в ответе Яндекс ID"}
        login = self._normalize_yandex_account_name(login)

        try:
            r2 = requests.get("https://api.webmaster.yandex.net/v4/user/", headers=headers, timeout=10)
        except Exception as e:
            return {"success": False, "message": f"Не удалось получить user_id из Вебмастера: {e}"}
        if r2.status_code != 200:
            return {"success": False, "message": f"Не удалось получить user_id из Вебмастера (HTTP {r2.status_code})"}
        user_id = str(r2.json().get("user_id", "") or "")
        if not user_id:
            return {"success": False, "message": "Пустой user_id в ответе Вебмастера"}

        accounts = self._load_yandex_accounts()
        account_name = self._normalize_yandex_account_name(login)
        accounts[account_name] = {"oauth_token": token, "user_id": user_id}
        self._save_yandex_accounts(accounts)

        config = self.get_config("yandex")
        config["active_account"] = account_name
        self.save_config("yandex", config)

        return {"success": True, "account": account_name,
                "log": [f"✅ Аккаунт {account_name} авторизован и сохранён (user_id: {user_id})"]}

    def get_yandex_accounts(self):
        accounts = self._load_yandex_accounts()
        config = self.get_config("yandex")
        return {"success": True, "accounts": list(accounts.keys()), "active": config.get("active_account", "")}

    # ======================== GOOGLE OAUTH (DESKTOP) ========================

    GOOGLE_SCOPES = [
        "https://www.googleapis.com/auth/webmasters",
        "https://www.googleapis.com/auth/siteverification",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
    ]

    def _get_google_app_config(self):
        if not os.path.exists(self.google_app_config_path):
            return None
        try:
            with open(self.google_app_config_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            for key in ("installed", "web"):
                if key in data:
                    return data[key]
        except Exception as e:
            print(f"[API] Ошибка чтения google/app_config.json: {e}")
        return None

    def _load_google_accounts(self):
        data = {}
        if os.path.exists(self.google_accounts_path):
            try:
                with open(self.google_accounts_path, "r", encoding="utf-8-sig") as f:
                    loaded = json.load(f)
                data = loaded.get("accounts", loaded) if isinstance(loaded, dict) else {}
            except Exception as e:
                print(f"[API] Ошибка чтения google/accounts.json: {e}")
        return data

    def _save_google_accounts(self, accounts):
        os.makedirs(self.google_dir, exist_ok=True)
        with open(self.google_accounts_path, "w", encoding="utf-8") as f:
            json.dump({"accounts": accounts}, f, ensure_ascii=False, indent=4)

    def _get_google_email(self, creds):
        id_token = getattr(creds, "id_token", None)
        if id_token:
            try:
                import base64
                payload = id_token.split('.')[1]
                payload += '=' * (-len(payload) % 4)
                data = json.loads(base64.urlsafe_b64decode(payload))
                email = data.get("email", "")
                if email:
                    return email
            except Exception:
                pass
        try:
            r = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=10,
            )
            if r.status_code == 200:
                return r.json().get("email", "")
        except Exception:
            pass
        return ""

    def google_authorize(self):
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            return {"success": False,
                    "message": "Не установлены google-auth-oauthlib / google-api-python-client. Установите: pip install -r requirements.txt"}

        app_cfg = self._get_google_app_config()
        if not app_cfg:
            return {"success": False, "message": "Не найден файл google/app_config.json (данные Desktop-приложения)"}

        browser = self.check_browser("google")
        if not browser.get("running"):
            return {"success": False,
                    "message": "Браузер Google (порт 9227) не запущен. Откройте его кнопкой «🌐 Браузер (порт 9227)»"}

        client_key = "installed" if "installed" in app_cfg else "web"

        import webbrowser

        class _DebugChromeController:
            def __init__(self, opener):
                self._opener = opener

            def open(self, url, new=0, autoraise=True):
                return self._opener(url)

            def open_new(self, url):
                return self._opener(url)

            def open_new_tab(self, url):
                return self._opener(url)

        webbrowser.register(
            "google-debug-9227",
            _DebugChromeController,
            instance=_DebugChromeController(self._open_in_google_debug_browser),
        )

        try:
            flow = InstalledAppFlow.from_client_config(
                {client_key: app_cfg}, scopes=self.GOOGLE_SCOPES)
            creds = flow.run_local_server(
                port=0, open_browser=True, prompt="consent", browser="google-debug-9227")
        except Exception as e:
            return {"success": False, "message": f"Ошибка авторизации: {e}"}

        email = self._get_google_email(creds)
        if not email:
            return {"success": False, "message": "Не удалось определить email аккаунта (не получен id_token)"}

        accounts = self._load_google_accounts()
        accounts[email] = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token or "",
            "token_expiry": int(creds.expiry.timestamp()) if creds.expiry else None,
        }
        self._save_google_accounts(accounts)

        config = self.get_config("google")
        config["active_account"] = email
        self.save_config("google", config)

        return {"success": True, "account": email, "log": [f"✅ Аккаунт {email} авторизован и сохранён"]}

    def get_google_accounts(self):
        accounts = self._load_google_accounts()
        config = self.get_config("google")
        return {"success": True, "accounts": list(accounts.keys()), "active": config.get("active_account", "")}

    def _open_in_google_debug_browser(self, url):
        """Открывает URL новой вкладкой в отладочном Chrome (порт 9227) через CDP /json/new."""
        self._open_in_debug_browser("google", url)
        return True

    # ======================== BING OAUTH ========================

    def _get_bing_app_config(self):
        if not os.path.exists(self.bing_app_config_path):
            return None
        try:
            with open(self.bing_app_config_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[API] Ошибка чтения bing/app_config.json: {e}")
            return None
        return data if isinstance(data, dict) else None

    def _load_bing_accounts(self):
        data = {}
        if os.path.exists(self.bing_accounts_path):
            try:
                with open(self.bing_accounts_path, "r", encoding="utf-8-sig") as f:
                    loaded = json.load(f)
                data = loaded.get("accounts", loaded) if isinstance(loaded, dict) else {}
            except Exception as e:
                print(f"[API] Ошибка чтения bing/accounts.json: {e}")
        return data

    def _save_bing_accounts(self, accounts):
        os.makedirs(self.bing_dir, exist_ok=True)
        with open(self.bing_accounts_path, "w", encoding="utf-8") as f:
            json.dump({"accounts": accounts}, f, ensure_ascii=False, indent=4)

    def _bing_post_token(self, data, log):
        """Обмен кода/refresh_token на токены. Пробует оба эндпоинта из документации."""
        last_error = ""
        for url in BING_TOKEN_URLS:
            try:
                r = requests.post(url, data=data, timeout=20)
            except Exception as e:
                last_error = f"{url}: {e}"
                continue
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception as e:
                    last_error = f"{url}: не удалось разобрать ответ ({e})"
                    continue
            last_error = f"HTTP {r.status_code} {r.text[:200]}"
            log.append(f"ℹ️ {url} не подошёл: {last_error}")
        raise RuntimeError(f"Bing не отдал токены ({last_error})")

    def _bing_exchange_code(self, app_cfg, code, redirect_uri, log):
        """Authorization code -> access_token + refresh_token (код живёт 5 минут)."""
        return self._bing_post_token({
            "code": code,
            "client_id": (app_cfg.get("client_id") or "").strip(),
            "client_secret": (app_cfg.get("client_secret") or "").strip(),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, log)

    def _bing_api(self, access_token, method, params=None, body=None, timeout=30):
        """Запрос к Bing Webmaster API. Возвращает (status, payload, error)."""
        url = f"{BING_API_BASE}/{method}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            if body is None:
                r = requests.get(url, params=params or {}, headers=headers, timeout=timeout)
            else:
                r = requests.post(url, params=params or {}, headers=headers,
                                  data=json.dumps(body), timeout=timeout)
        except Exception as e:
            return None, None, str(e)
        try:
            payload = r.json()
        except Exception:
            payload = {}
        error = ""
        if r.status_code != 200:
            error = f"HTTP {r.status_code}: {(payload or {}).get('Message') or r.text[:200]}"
        return r.status_code, payload, error

    def _bing_account_email(self, access_token):
        """Email аккаунта: отдельного эндпоинта профиля у Bing нет — берём Email
        из ролей первого сайта (GetUserSites -> GetSiteRoles)."""
        status, payload, error = self._bing_api(access_token, "GetUserSites")
        if status != 200:
            return "", error
        sites = (payload or {}).get("d") or []
        site_url = next(((s or {}).get("Url", "") for s in sites if (s or {}).get("Url")), "")
        if not site_url:
            return "", "у аккаунта нет сайтов"

        status, payload, error = self._bing_api(
            access_token, "GetSiteRoles",
            params={"siteUrl": site_url, "includeAllSubdomains": "true"})
        if status != 200:
            return "", error
        for role in ((payload or {}).get("d") or []):
            for key in ("Email", "DelegatorEmail", "DelegatedCodeOwnerEmail"):
                value = (role or {}).get(key, "")
                if value:
                    return value, ""
        return "", "в ролях сайта нет email"

    def _wait_for_bing_code(self, redirect_uri, timeout=BING_AUTH_TIMEOUT):
        """Ждёт редиректа с ?code= на зарегистрированный redirect_uri (CDP /json/list).

        Bing отдаёт код только через redirect_uri, поэтому читаем адресную строку вкладки:
        даже если по этому URI ничего не слушается, Chrome оставляет URL с кодом.
        Возвращает ("code"|"error"|"timeout", значение, url).
        """
        import urllib.parse
        port = self._browser_port("bing")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(f"http://127.0.0.1:{port}/json/list", timeout=5)
                targets = r.json() if r.status_code == 200 else []
            except Exception:
                targets = []
            for target in targets:
                url = target.get("url", "") or ""
                if not url.startswith(redirect_uri):
                    continue
                query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                if query.get("code"):
                    return "code", query["code"][0], url
                if query.get("error"):
                    return "error", query.get("error_description", [""])[0] or query["error"][0], url
            time.sleep(1.5)
        return "timeout", "", ""

    def bing_authorize(self):
        """OAuth 2.0 Bing Webmaster: вкладка авторизации в браузере 9225, код из адресной строки."""
        import urllib.parse
        log = []

        if not self.check_browser("bing").get("running"):
            return {"success": False,
                    "message": "Браузер Bing (порт 9225) не запущен. Откройте его кнопкой «🌐 Браузер»"}

        app_cfg = self._get_bing_app_config()
        if not app_cfg:
            return {"success": False,
                    "message": "Не найден файл bing/app_config.json (данные приложения Bing)"}

        client_id = (app_cfg.get("client_id") or "").strip()
        client_secret = (app_cfg.get("client_secret") or "").strip()
        redirect_uri = (app_cfg.get("redirect_uri") or "").strip()
        missing = [name for name, value in (("client_id", client_id),
                                            ("client_secret", client_secret),
                                            ("redirect_uri", redirect_uri)) if not value]
        if missing:
            return {"success": False,
                    "message": f"В bing/app_config.json не заполнено: {', '.join(missing)}"}

        scope = (app_cfg.get("scope") or "").strip() or BING_DEFAULT_SCOPE
        auth_url = f"{BING_AUTH_URL}?{urllib.parse.urlencode({
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': scope,
        })}"

        try:
            self._open_in_debug_browser("bing", auth_url)
        except Exception as e:
            return {"success": False, "message": str(e)}
        log.append(f"🔑 Открыта вкладка авторизации Bing: {auth_url}")

        kind, value, page_url = self._wait_for_bing_code(redirect_uri)
        if kind == "error":
            return {"success": False, "message": f"Bing отклонил авторизацию: {value}", "log": log}
        if kind != "code":
            return {"success": False,
                    "message": f"Таймаут ({BING_AUTH_TIMEOUT} сек): код не получен. "
                               "Авторизуйтесь в открывшейся вкладке браузера 9225",
                    "log": log}
        log.append(f"✅ Код получен: {page_url}")

        try:
            tokens = self._bing_exchange_code(app_cfg, value, redirect_uri, log)
        except Exception as e:
            return {"success": False, "message": str(e), "log": log}

        access_token = tokens.get("access_token", "") or ""
        refresh_token = tokens.get("refresh_token", "") or ""
        expires_in = int(tokens.get("expires_in") or 3599)
        if not access_token or not refresh_token:
            return {"success": False,
                    "message": "Bing вернул ответ без access_token/refresh_token", "log": log}

        email, error = self._bing_account_email(access_token)
        if not email:
            accounts = self._load_bing_accounts()
            email = f"account-{len(accounts) + 1}"
            log.append(f"ℹ️ Email определить не удалось ({error}), аккаунт сохранён как «{email}»")

        accounts = self._load_bing_accounts()
        accounts[email] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": int(time.time()) + expires_in - 60,
        }
        self._save_bing_accounts(accounts)

        config = self.get_config("bing")
        config["active_account"] = email
        self.save_config("bing", config)

        # Диагностика — в консоль разработчика GUI (result.log печатает bingAuthorize).
        # Значения токенов не пишем: показываем только хвост, сверить с accounts.json
        # по восьми символам хватает, а в логе токен светиться не должен.
        log.append(f"👤 Аккаунт: {email}")
        log.append(f"🔑 access_token: …{_mask_token(access_token)}")
        log.append(f"🔄 refresh_token: …{_mask_token(refresh_token)} (сохранён в bing/accounts.json)")
        log.append(f"⏳ access_token истекает через {expires_in} сек")

        return {"success": True, "account": email, "log": log}

    def get_bing_accounts(self):
        accounts = self._load_bing_accounts()
        config = self.get_config("bing")
        return {"success": True, "accounts": list(accounts.keys()), "active": config.get("active_account", "")}

def main():
    shell32 = ctypes.windll.shell32
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    shell32.SetCurrentProcessExplicitAppUserModelID(u'com.miu-kontent.ywm-and-gsc')

    api = Api()
    html_file = os.path.join(api.gui_dir, "index.html")

    # Режим разработчика: DevTools включаются (F12 открывает консоль), но само
    # окно при старте программы НЕ появляется. Отключать не нужно — дебаг-вывод
    # скриптов (__DEBUG__) живёт только в консоли.
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False

    window = webview.create_window(
        title="YWM-and-GSC",
        url=html_file,
        js_api=api,
        width=980,
        height=800,
        frameless=False,
        on_top=False,
        min_size=(730, 400),
        background_color='#121214'
    )

    webview.start(
        icon=os.path.join(api.gui_dir, "favicon.ico"),
        debug=True,
        private_mode=False,
        http_server=True,
        http_port=_pick_free_port()
    )


def _pick_free_port():
    """Свободный порт для внутреннего HTTP-сервера GUI (http_server=True).

    pywebview при private_mode=False без явного http_port использует фиксированный
    DEFAULT_HTTP_PORT (42001) — это может упасть, если порт занят. Берём свободный
    эфемерный порт на 127.0.0.1, чтобы GUI всегда гарантированно открывался.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    except OSError:
        return 42001


if __name__ == "__main__":
    main()