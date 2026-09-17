import os
import sys
import json
import time
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

        self.running_processes = {}

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
        path = self.yandex_config_path if service == "yandex" else self.google_config_path
        default = {}
        if service == "yandex":
            default.update({
                "active_account": "", 
                "metric_id": "", 
                "contact_path": "", 
                "sitemap_path": ""
            })
        else:
            default.update({
                "active_account": "", 
                "sitemap_path": ""
            })

        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                default.update(data)
        except Exception as e:
            print(f"[API] Ошибка чтения {service} config: {e}")
        return default

    def save_config(self, service, data):
        path = self.yandex_config_path if service == "yandex" else self.google_config_path
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
        registry_dir = self.yandex_dir if service == "yandex" else self.google_dir
        registry_path = os.path.join(registry_dir, "registry.json")
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
        scripts_dir = self.yandex_scripts_dir if service == "yandex" else self.google_scripts_dir
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
        return self.yandex_arrays_dir if service == "yandex" else self.google_arrays_dir

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
        port = 9229 if service == "yandex" else 9227
        try:
            import requests as req
            r = req.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
            return {"success": True, "running": r.status_code == 200}
        except Exception:
            return {"success": True, "running": False}

    def launch_browser(self, service):
        port = 9229 if service == "yandex" else 9227
        profiles_dir = os.path.join(self.base_dir, "debug_profiles")
        os.makedirs(profiles_dir, exist_ok=True)
        profile_name = "chrome-debug-yandex" if service == "yandex" else "chrome-debug-google"
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

        service_dir = self.yandex_dir if service == "yandex" else self.google_dir
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
            webview.windows[0].evaluate_js(f"scriptFinished('{key}', {proc.returncode})")
            self.running_processes.pop(key, None)

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

    def _open_in_yandex_debug_browser(self, url):
        """Открывает URL новой вкладкой в отладочном Chrome (порт 9229) через CDP /json/new."""
        try:
            import urllib.parse
            resp = requests.put(
                f"http://127.0.0.1:9229/json/new?{urllib.parse.quote(url, safe='')}",
                timeout=5,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"CDP ответил HTTP {resp.status_code}")
            return resp.json().get("webSocketDebuggerUrl", "")
        except Exception as e:
            print(f"[API] Ошибка открытия вкладки в браузере 9229: {e}")
            raise RuntimeError(f"Не удалось открыть вкладку в браузере 9229: {e}")

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
        try:
            import urllib.parse
            resp = requests.put(
                f"http://127.0.0.1:9227/json/new?{urllib.parse.quote(url, safe='')}",
                timeout=5,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"CDP ответил HTTP {resp.status_code}")
            return True
        except Exception as e:
            print(f"[API] Ошибка открытия вкладки в браузере 9227: {e}")
            raise RuntimeError(f"Не удалось открыть вкладку в браузере 9227: {e}")

def main():
    shell32 = ctypes.windll.shell32
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    shell32.SetCurrentProcessExplicitAppUserModelID(u'com.miu-kontent.ywm-and-gsc')

    api = Api()
    html_file = os.path.join(api.gui_dir, "index.html")

    window = webview.create_window(
        title="YWM-and-GSC",
        url=html_file,
        js_api=api,
        width=970,
        height=800,
        frameless=False,
        on_top=False,
        min_size=(730, 400),
        background_color='#121214'
    )

    webview.start(icon=os.path.join(api.gui_dir, "favicon.ico"), debug=False, private_mode=False)


if __name__ == "__main__":
    main()