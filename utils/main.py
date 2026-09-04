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
        self.yandex_config_path = os.path.join(self.yandex_dir, "config.json")
        self.google_config_path = os.path.join(self.google_dir, "config.json")
        self.google_env_path = os.path.join(self.google_dir, ".env")

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
        default = {"scripts_data": {}}
        if service == "yandex":
            default.update({"oauth_token": "", "user_id": "", "metricCounterId": "", "contactPath": "contacts"})
        else:
            default.update({"client_id": "", "client_secret": "", "access_token": "", "refresh_token": "", "auth_code": "", "redirect_uri": "http://localhost:3000/"})

        if os.path.exists(path):
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
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=4)
            return {"success": True}
        except Exception as e:
            print(f"[API] Ошибка сохранения {service} config: {e}")
            return {"success": False, "message": str(e)}

    def save_script_data(self, service, script_name, data):
        config = self.get_config(service)
        config.setdefault("scripts_data", {})[script_name] = data
        return self.save_config(service, config)

    def get_script_data(self, service, script_name):
        config = self.get_config(service)
        return config.get("scripts_data", {}).get(script_name, {})

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

    def generate_google_env(self):
        config = self.get_config("google")
        lines = [
            f"CLIENT_ID={config.get('client_id', '')}",
            f"CLIENT_SECRET={config.get('client_secret', '')}",
            f"ACCESS_TOKEN={config.get('access_token', '')}",
            f"REFRESH_TOKEN={config.get('refresh_token', '')}",
            f"AUTH_CODE={config.get('auth_code', '')}",
            f"REDIRECT_URI={config.get('redirect_uri', 'http://localhost:3000/')}",
        ]
        try:
            with open(self.google_env_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print(f"[API] Generated {self.google_env_path}")
        except Exception as e:
            print(f"[API] Ошибка генерации .env: {e}")

    def launch_browser(self, service):
        port = 9229 if service == "yandex" else 9227
        profile_name = "chrome-debug-yandex" if service == "yandex" else "chrome-debug-google"
        profile_path = os.path.join(self.base_dir, f".{profile_name}")

        chrome_path = self._find_chrome()
        if not chrome_path:
            return {"success": False, "message": "Chrome не найден"}

        cmd = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_path}",
            "--no-first-run",
            "--no-default-browser-check"
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
        if service == "google":
            self.generate_google_env()

        service_dir = self.yandex_dir if service == "yandex" else self.google_dir
        script_path = os.path.join(service_dir, "scripts", f"{script_name}.js")
        py_script_path = os.path.join(service_dir, "scripts", f"{script_name}.py")

        if os.path.exists(script_path):
            cmd = ["node", script_path]
        elif os.path.exists(py_script_path):
            cmd = [sys.executable, py_script_path]
        else:
            return {"success": False, "message": f"Скрипт {script_name} не найден"}

        process_key = f"{service}:{script_name}"
        if process_key in self.running_processes:
            return {"success": False, "message": "Скрипт уже запущен"}

        def stream_output(proc, key):
            for line in iter(proc.stdout.readline, ''):
                if line:
                    webview.windows[0].evaluate_js(f"appendLog('{key}', `{line.rstrip()}`)")
            proc.stdout.close()
            proc.wait()
            webview.windows[0].evaluate_js(f"scriptFinished('{key}')")
            self.running_processes.pop(key, None)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=service_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1
            )
            self.running_processes[process_key] = proc
            thread = threading.Thread(target=stream_output, args=(proc, process_key), daemon=True)
            thread.start()
            return {"success": True, "message": f"Скрипт {script_name} запущен"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_scripts_list(self, service):
        service_dir = self.yandex_dir if service == "yandex" else self.google_dir
        scripts_dir = os.path.join(service_dir, "scripts")
        scripts = []
        if os.path.exists(scripts_dir):
            for f in os.listdir(scripts_dir):
                if f.endswith(".js") or f.endswith(".py"):
                    scripts.append(f[:-3])
        return {"scripts": scripts}


def main():
    api = Api()
    html_file = os.path.join(api.gui_dir, "index.html")

    window = webview.create_window(
        title="YWM-and-GSC",
        url=html_file,
        js_api=api,
        width=1200,
        height=800,
        frameless=False,    # Убирает стандартную рамку ОС, заголовки и кнопки «закрыть/свернуть» (полезно для создания кастомных уникальных дизайнов).
        on_top=False,       # Фиксирует окно поверх всех остальных окон в системе.
        min_size=(800, 600),
        background_color='#121214'
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()