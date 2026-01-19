import os
import sys
import json
import re
import subprocess
import requests
import httpx
import shutil
from urllib.parse import urlparse
from base64 import b64decode, b64encode
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH


class KinescopeLogic:
    def __init__(self, log_callback):
        self.log = log_callback
        self.bin_dir = self.setup_bin_directory()
        self.wvd_path = "WVD.wvd"

    def get_resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        return os.path.join(base_path, relative_path)

    def setup_bin_directory(self):
        bin_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "bin")
        os.makedirs(bin_dir, exist_ok=True)

        files = {
            "ffmpeg/bin/ffmpeg.exe": "ffmpeg.exe",
            "mp4decrypt.exe": "mp4decrypt.exe",
            "N_m3u8DL-RE.exe": "N_m3u8DL-RE.exe"
        }

        for src_rel, dst_name in files.items():
            src = self.get_resource_path(src_rel)
            dst = os.path.join(bin_dir, dst_name)
            if not os.path.exists(dst) and os.path.exists(src):
                shutil.copy2(src, dst)
        return bin_dir

    def extract_from_json(self, json_filepath):
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        video_url = data.get('url', '')
        referer = data.get('referrer', '')

        results = []

        # Проверяем наличие плейлиста
        playlist = data.get('options', {}).get('playlist', [])

        if isinstance(playlist, list) and len(playlist) > 0:
            for item in playlist:
                video_title = item.get('title') or data.get('meta', {}).get('title', 'video_download')
                # Создаем отдельный объект для каждого видео, сохраняя общие мета-данные
                results.append({
                    "url": video_url,
                    "referer": referer,
                    "title": video_title,
                    "video_data": item,  # Данные конкретного ролика
                    "full_data": data  # Общие данные (для реферера и т.д.)
                })
        else:
            # Резервный вариант, если плейлиста нет
            results.append({"url": video_url, "referer": referer, "title": "video", "data": data})

        return results

    def get_key(self, pssh, license_url, referer):
        if not os.path.exists(self.wvd_path):
            self.log("[!] Файл WVD.wvd не найден. DRM методы будут недоступны.")
            return []

        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.54 Safari/537.36',
            'origin': referer, 'referer': referer
        }

        device = Device.load(self.wvd_path)
        cdm = Cdm.from_device(device)
        session_id = cdm.open()
        challenge = cdm.get_license_challenge(session_id, PSSH(pssh))
        response = httpx.post(license_url, data=challenge, headers=headers)
        cdm.parse_license(session_id, response.content)
        keys = [f"{key.kid.hex}:{key.key.hex()}" for key in cdm.get_keys(session_id) if key.type == 'CONTENT']
        cdm.close(session_id)
        return keys

    def _extract_stream_urls(self, data):
        mpd_url, m3u8_url = None, None

        # Проверяем наличие sources напрямую в переданном объекте
        sources = data.get('sources', [])
        if isinstance(sources, list):
            # Если sources - это список объектов
            for s in sources:
                src = s.get('src', '')
                if 'master.mpd' in src or 'manifest.mpd' in src:
                    mpd_url = src
                if 'master.m3u8' in src or 'manifest.m3u8' in src:
                    m3u8_url = src
        elif isinstance(sources, dict):
            # Если sources - это словарь (как было в старой версии вашего кода)
            mpd_url = sources.get('shakadash', {}).get('src')
            m3u8_url = sources.get('hls', {}).get('src')

        # Если нашли только m3u8, пробуем угадать mpd (нужен для получения PSSH)
        if not mpd_url and m3u8_url:
            mpd_url = m3u8_url.replace('.m3u8', '.mpd')

        return mpd_url, m3u8_url

    def run_n_m3u8dl(self, url, keys, quality, save_dir, save_name, method_name):
        n_m3u8dl_path = os.path.join(self.bin_dir, "N_m3u8DL-RE.exe")
        key_params = " ".join([f"--key {k}" for k in keys]) if keys else ""
        save_name_clean = re.sub(r'[\s\\/:*?"<>|]', '_', save_name).strip('_')

        # Важно: добавляем --log-level INFO и убираем подавление логов
        command = f'"{n_m3u8dl_path}" "{url}" {key_params} -M format=mp4 -sv res="{quality}" -sa ru --log-level INFO --save-dir "{save_dir}" --save-name "{save_name_clean}"'

        self.log(f"[*] Запуск {method_name}...")

        # Запускаем процесс и перехватываем поток вывода
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Объединяем ошибки и стандартный вывод
            text=True,
            encoding='cp866',
            errors='replace',
            bufsize=1
        )

        # Читаем КАЖДУЮ строку лога консоли
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                self.log(clean_line)  # Передаем строку в main.py -> index.html

        process.wait()
        return process.returncode == 0

    def download_pipeline(self, info, quality, output_path):
        # info теперь содержит video_data (конкретный ролик)
        video_item = info['video_data']
        referer = info['referer']
        save_dir = os.path.dirname(output_path)
        save_name = os.path.splitext(os.path.basename(output_path))[0]

        # Извлекаем ссылки именно для этого видео
        mpd_url, m3u8_url = self._extract_stream_urls(video_item)

        # Способ 2: Widevine
        self.log(f"[*] Пробуем Widevine для: {info['title']}")
        try:
            license_url = video_item['drm']['widevine']['licenseUrl']
            mpd_content = requests.get(mpd_url, timeout=10).text
            pssh_match = re.search(r'<cenc:pssh[^>]*>([^<]+)</cenc:pssh>', mpd_content)
            if pssh_match:
                pssh = pssh_match.group(1)
                keys = self.get_key(pssh, license_url, referer)
                if keys and self.run_n_m3u8dl(m3u8_url, keys, quality, save_dir, save_name, "Widevine"):
                    return True
        except:
            pass

        # Способ 3: Clearkey
        self.log("[!] Способ 2 не сработал. Пробуем Способ 3 (Clearkey)...")
        try:
            # Вместо p = data["options"]["playlist"][0] используем данные текущего видео
            video_item = info['video_data']

            mpd_response = requests.get(mpd_url, timeout=10).text
            kid_match = re.search(r'cenc:default_KID="([^"]+)"', mpd_response)

            if kid_match:
                kid = kid_match.group(1).replace('-', '')
                kid_b64 = b64encode(bytes.fromhex(kid)).decode().replace('=', '')

                # Берем licenseUrl из структуры drm -> clearkey
                lic_url = video_item.get("drm", {}).get("clearkey", {}).get("licenseUrl", "")

                if lic_url:
                    resp = requests.post(lic_url, headers={"Origin": referer, "Referer": referer},
                                         json={"kids": [kid_b64], "type": "temporary"}).json()
                    k = resp['keys'][0]
                    key_param = f"{b64decode(k['kid'] + '==').hex()}:{b64decode(k['k'] + '==').hex()}"

                    if self.run_n_m3u8dl(m3u8_url, [key_param], quality, save_dir, save_name, "Clearkey"):
                        return True
        except:
            pass

        # Способ 4: Keyless
        self.log("[!] Способ 3 не сработал. Пробуем Способ 4 (Без ключей)...")
        if self.run_n_m3u8dl(m3u8_url, [], quality, save_dir, save_name, "Keyless"):
            return True

        self.log("[!] Все методы скачивания исчерпаны.")
        return False