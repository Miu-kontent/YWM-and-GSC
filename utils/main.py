import os
import sys
import json
import time
import threading
import subprocess
import webview
import requests
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
        self.yandex_scripts_data_path = os.path.join(self.yandex_dir, "scripts_data.json")
        self.yandex_scripts_dir = os.path.join(self.yandex_dir, "scripts")
        self.google_config_path = os.path.join(self.google_dir, "config.json")
        self.google_scripts_data_path = os.path.join(self.google_dir, "scripts_data.json")
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
                for member in z.namelist():
                    if member == root_prefix:
                        continue
                    rel_path = member[len(root_prefix):]
                    if rel_path.startswith((".git/", ".venv")) or rel_path.endswith("config.json"):
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
                "oauth_token": "", 
                "user_id": "", 
                "metric_id": "", 
                "contact_path": "", 
                "sitemap_path": ""
            })
        else:
            default.update({
                "client_id": "", 
                "client_secret": "", 
                "access_token": "", 
                "auth_code": "", 
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

    def _get_scripts_data_path(self, service):
        return self.yandex_scripts_data_path if service == "yandex" else self.google_scripts_data_path

    def _load_scripts_data(self, service):
        path = self._get_scripts_data_path(service)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_scripts_data(self, service, data):
        path = self._get_scripts_data_path(service)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def save_script_data(self, service, script_name, data):
        try:
            all_data = self._load_scripts_data(service)
            all_data[script_name] = data
            self._save_scripts_data(service, all_data)
            return {"success": True}
        except Exception as e:
            print(f"[API] Ошибка сохранения данных скрипта {script_name}: {e}")
            return {"success": False}

    def get_script_data(self, service, script_name):
        all_data = self._load_scripts_data(service)
        return all_data.get(script_name, {})

    def get_scripts_data(self, service):
        return self._load_scripts_data(service)

    def generate_arr_js(self, service, script_name):
        data = self.get_script_data(service, script_name)
        service_dir = self.yandex_dir if service == "yandex" else self.google_dir
        output_path = os.path.join(service_dir, f"array_{script_name}.js")

        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"const {key} = {json.dumps(value, ensure_ascii=False)};")
            elif isinstance(value, dict):
                lines.append(f"const {key} = {json.dumps(value, ensure_ascii=False)};")
            elif isinstance(value, str):
                lines.append(f"const {key} = \"{value}\";")
            else:
                lines.append(f"const {key} = {json.dumps(value)};")
        lines.append(f"\nmodule.exports = {{{', '.join(data.keys())}}};")

        try:
            os.makedirs(service_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print(f"[API] Generated {output_path}")
        except Exception as e:
            print(f"[API] Ошибка генерации arr.js: {e}")

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
            # "--no-first-run",
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
        self.generate_arr_js(service, script_name)

        service_dir = self.yandex_dir if service == "yandex" else self.google_dir
        script_path = os.path.join(service_dir, "scripts", f"{script_name}.js")
        py_script_path = os.path.join(service_dir, "scripts", f"{script_name}.py")

        if os.path.exists(script_path):
            cmd = ["node", script_path]
        elif os.path.exists(py_script_path):
            cmd = [sys.executable, "-u", py_script_path]
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
            webview.windows[0].evaluate_js(f"scriptFinished('{key}')")
            self.running_processes.pop(key, None)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=service_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
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
            proc = subprocess.run(
                [sys.executable, script_path],
                cwd=self.yandex_dir,
                capture_output=True, text=True, timeout=180, encoding="utf-8"
            )
            log_lines = proc.stdout.splitlines()
            return {"success": proc.returncode == 0, "log": log_lines, "stdout": proc.stdout}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Таймаут (180 сек)", "log": ["❌ Таймаут: скрипт не завершился"]}
        except Exception as e:
            return {"success": False, "message": str(e), "log": [f"❌ {e}"]}

    def start_yandex_get_token(self):
        result = self._run_yandex_script("yandex_get_token")
        token = None
        for line in result.get("log", []):
            if line.startswith("OAUTH_TOKEN:"):
                token = line.split(":", 1)[1]
        if token:
            config = self.get_config("yandex")
            config["oauth_token"] = token
            self.save_config("yandex", config)
        return {"success": bool(token), "oauth_token": token or "", "log": result.get("log", [])}

    def start_yandex_get_userid(self):
        result = self._run_yandex_script("yandex_get_userid")
        user_id = None
        for line in result.get("log", []):
            if line.startswith("USER_ID:"):
                user_id = line.split(":", 1)[1]
        if user_id:
            config = self.get_config("yandex")
            config["user_id"] = user_id
            self.save_config("yandex", config)
        return {"success": bool(user_id), "user_id": user_id or "", "log": result.get("log", [])}

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
        width=1000,
        height=800,
        frameless=False,
        on_top=False,
        min_size=(600, 400),
        background_color='#121214'
    )

    webview.start(icon=os.path.join(api.gui_dir, "favicon.ico"), debug=True)


if __name__ == "__main__":
    main()