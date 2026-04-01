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
        self.log("[INIT] Инициализация KinescopeLogic...")
        self.bin_dir = self.setup_bin_directory()
        self.wvd_path = "WVD.wvd"
        self.log(f"[INIT] Путь к бинарникам: {self.bin_dir}")
        self.log(f"[INIT] Путь к WVD файлу: {self.wvd_path}")

    def get_resource_path(self, relative_path):
        """Получает абсолютный путь к ресурсу (для PyInstaller)"""
        try:
            base_path = sys._MEIPASS
            self.log(f"[RESOURCE] Режим PyInstaller, базовый путь: {base_path}")
        except Exception:
            base_path = os.path.dirname(os.path.abspath(__file__))
            self.log(f"[RESOURCE] Обычный режим, базовый путь: {base_path}")
        full_path = os.path.join(base_path, relative_path)

        # Исправляем логирование, чтобы Python не воспринимал слеши \b, \n как спецсимволы
        safe_full = full_path.replace('\\', '/')
        self.log(f"[RESOURCE] Полный путь к ресурсу '{relative_path}': {safe_full}")
        return full_path

    def setup_bin_directory(self):
        """Настраивает директорию с бинарными файлами"""
        # Исправляем путь, чтобы слеши не терялись.
        # Используем os.path.dirname(__file__) для надежности
        base_dir = os.path.dirname(os.path.abspath(__file__))
        bin_dir = os.path.join(base_dir, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        self.log(f"[SETUP] Создана/проверена директория бинарников: {bin_dir}")

        files = {
            os.path.join("ffmpeg", "bin", "ffmpeg.exe"): "ffmpeg.exe",
            "mp4decrypt.exe": "mp4decrypt.exe",
            "N_m3u8DL-RE.exe": "N_m3u8DL-RE.exe"
        }

        for src_rel, dst_name in files.items():
            src = self.get_resource_path(src_rel)
            dst = os.path.join(bin_dir, dst_name)
            if os.path.exists(src):
                if not os.path.exists(dst):
                    try:
                        shutil.copy2(src, dst)
                        self.log(f"[SETUP] Скопирован бинарник: {src} -> {dst}")
                    except Exception as e:
                        self.log(f"[SETUP] ⚠️ Ошибка копирования {src}: {e}")
                else:
                    self.log(f"[SETUP] Бинарник уже существует: {dst}")
            else:
                self.log(f"[SETUP] ⚠️ Бинарник не найден: {src}")

        return bin_dir

    def extract_from_json(self, json_filepath):
        """Извлекает данные видео из JSON файла"""
        self.log(f"[JSON] Чтение JSON файла: {json_filepath}")
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        video_url = data.get('url', '')
        referer = data.get('referrer', '')
        self.log(f"[JSON] URL видео: {video_url[:50]}...")
        self.log(f"[JSON] Referer: {referer}")

        results = []
        playlist = data.get('options', {}).get('playlist', [])

        if isinstance(playlist, list) and len(playlist) > 0:
            self.log(f"[JSON] Найден плейлист с {len(playlist)} видео")
            for idx, item in enumerate(playlist):
                video_title = item.get('title') or data.get('meta', {}).get('title', f'video_{idx + 1}')
                self.log(f"[JSON] [{idx + 1}/{len(playlist)}] Видео: {video_title}")
                results.append({
                    "url": video_url,
                    "referer": referer,
                    "title": video_title,
                    "video_data": item,
                    "full_data": data
                })
        else:
            self.log("[JSON] Плейлист не найден, используем основные данные")
            results.append({
                "url": video_url,
                "referer": referer,
                "title": "video",
                "video_data": data,
                "full_data": data
            })

        self.log(f"[JSON] Извлечено {len(results)} элементов для скачивания")
        return results

    def get_key(self, pssh, license_url, referer):
        """Получает ключ дешифрования через Widevine CDM"""
        self.log("[WIDEVINE] === НАЧАЛО ПОЛУЧЕНИЯ КЛЮЧА ===")

        # Шаг 1: Проверка WVD файла
        self.log(f"[WIDEVINE] Шаг 1: Проверка наличия WVD файла: {self.wvd_path}")
        if not os.path.exists(self.wvd_path):
            self.log(f"[WIDEVINE] ❌ Файл {self.wvd_path} не найден. DRM методы недоступны.")
            return []
        self.log(f"[WIDEVINE] ✓ WVD файл найден: {os.path.abspath(self.wvd_path)}")

        # Шаг 2: Настройка заголовков
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.54 Safari/537.36',
            'origin': referer,
            'referer': referer
        }
        self.log(f"[WIDEVINE] Шаг 2: Заголовки запроса:")
        self.log(f"[WIDEVINE]   User-Agent: {headers['user-agent']}")
        self.log(f"[WIDEVINE]   Origin: {headers['origin']}")
        self.log(f"[WIDEVINE]   Referer: {headers['referer']}")

        try:
            # Шаг 3: Загрузка устройства
            self.log("[WIDEVINE] Шаг 3: Загрузка устройства из WVD файла...")
            device = Device.load(self.wvd_path)
            self.log(f"[WIDEVINE] ✓ Устройство загружено: {device.system_id} (Security Level: {device.security_level})")

            # Шаг 4: Инициализация CDM
            self.log("[WIDEVINE] Шаг 4: Инициализация Content Decryption Module (CDM)...")
            cdm = Cdm.from_device(device)
            self.log(f"[WIDEVINE] ✓ CDM инициализирован: {cdm}")

            # Шаг 5: Открытие сессии
            self.log("[WIDEVINE] Шаг 5: Открытие сессии CDM...")
            session_id = cdm.open()
            self.log(f"[WIDEVINE] ✓ Сессия открыта, ID: {session_id.hex()}")

            # Шаг 6: Парсинг PSSH
            self.log(f"[WIDEVINE] Шаг 6: Парсинг PSSH (первые 30 символов): {pssh[:30]}...")
            pssh_obj = PSSH(pssh)
            self.log(f"[WIDEVINE] ✓ PSSH распознан: {pssh_obj}")

            # Шаг 7: Генерация лицензионного челленджа
            self.log("[WIDEVINE] Шаг 7: Генерация лицензионного челленджа...")
            challenge = cdm.get_license_challenge(session_id, pssh_obj)
            self.log(f"[WIDEVINE] ✓ Челлендж сгенерирован ({len(challenge)} байт)")

            # Шаг 8: Отправка запроса на лицензионный сервер
            self.log(f"[WIDEVINE] Шаг 8: Отправка запроса на лицензионный сервер: {license_url}")
            response = httpx.post(license_url, data=challenge, headers=headers, timeout=15)
            self.log(f"[WIDEVINE] ✓ Ответ получен: статус {response.status_code}, размер {len(response.content)} байт")

            if response.status_code != 200:
                self.log(f"[WIDEVINE] ❌ Сервер вернул ошибку: {response.status_code}")
                cdm.close(session_id)
                return []

            # Шаг 9: Парсинг лицензии
            self.log("[WIDEVINE] Шаг 9: Парсинг лицензии и извлечение ключей...")
            cdm.parse_license(session_id, response.content)
            self.log("[WIDEVINE] ✓ Лицензия успешно распарсена")

            # Шаг 10: Извлечение ключей CONTENT
            keys = [f"{key.kid.hex}:{key.key.hex()}" for key in cdm.get_keys(session_id) if key.type == 'CONTENT']
            self.log(f"[WIDEVINE] Шаг 10: Найдено ключей CONTENT: {len(keys)}")

            if keys:
                for i, key_str in enumerate(keys, 1):
                    kid, key = key_str.split(':')
                    self.log(f"[WIDEVINE]   Ключ #{i}: KID={kid} | KEY={key}")
            else:
                self.log("[WIDEVINE] ⚠️ Ключи CONTENT не найдены (возможно, только ключи для подписи)")

            # Шаг 11: Закрытие сессии
            cdm.close(session_id)
            self.log("[WIDEVINE] Шаг 11: Сессия закрыта")

            self.log("[WIDEVINE] === КЛЮЧИ УСПЕШНО ПОЛУЧЕНЫ ===")
            return keys

        except Exception as e:
            self.log(f"[WIDEVINE] ❌ Ошибка при получении ключа: {type(e).__name__}: {str(e)}")
            import traceback
            self.log(f"[WIDEVINE] Трассировка: {traceback.format_exc()}")
            return []

    def _extract_stream_urls(self, data):
        """Извлекает URL потоков (MPD и M3U8) из данных видео"""
        self.log("[STREAM] Извлечение URL потоков из данных видео...")
        mpd_url, m3u8_url = None, None

        sources = data.get('sources', [])
        self.log(f"[STREAM] Тип sources: {type(sources)}")

        if isinstance(sources, list):
            self.log(f"[STREAM] Найдено {len(sources)} источников в списке")
            for idx, s in enumerate(sources):
                src = s.get('src', '')
                mime = s.get('type', '')
                self.log(f"[STREAM]   Источник #{idx}: type={mime}, src={src[:50]}...")
                if 'master.mpd' in src or 'manifest.mpd' in src or mime == 'application/dash+xml':
                    mpd_url = src
                    self.log(f"[STREAM]   ✓ Найден MPD: {mpd_url[:50]}...")
                if 'master.m3u8' in src or 'manifest.m3u8' in src or mime == 'application/x-mpegURL':
                    m3u8_url = src
                    self.log(f"[STREAM]   ✓ Найден M3U8: {m3u8_url[:50]}...")

        elif isinstance(sources, dict):
            self.log("[STREAM] Sources в формате словаря")
            mpd_url = sources.get('shakadash', {}).get('src')
            m3u8_url = sources.get('hls', {}).get('src')
            if mpd_url:
                self.log(f"[STREAM]   ✓ Найден MPD (shakadash): {mpd_url[:50]}...")
            if m3u8_url:
                self.log(f"[STREAM]   ✓ Найден M3U8 (hls): {m3u8_url[:50]}...")

        # Попытка угадать MPD если есть только M3U8
        if not mpd_url and m3u8_url:
            mpd_url = m3u8_url.replace('.m3u8', '.mpd')
            self.log(f"[STREAM] ⚠️ MPD не найден напрямую, угадан по M3U8: {mpd_url[:50]}...")

        self.log(f"[STREAM] Итог: MPD={bool(mpd_url)}, M3U8={bool(m3u8_url)}")
        return mpd_url, m3u8_url

    def run_n_m3u8dl(self, url, keys, quality, save_dir, save_name, method_name):
        """Запускает N_m3u8DL-RE для скачивания видео"""
        self.log(f"[DOWNLOAD] === ЗАПУСК СКАЧИВАНИЯ ({method_name}) ===")
        self.log(f"[DOWNLOAD] URL потока: {url[:60]}...")
        self.log(f"[DOWNLOAD] Качество: {quality}")
        self.log(f"[DOWNLOAD] Директория сохранения: {save_dir}")
        self.log(f"[DOWNLOAD] Имя файла: {save_name}")

        n_m3u8dl_path = os.path.join(self.bin_dir, "N_m3u8DL-RE.exe")
        safe_path = n_m3u8dl_path.replace('\\', '/')

        if not os.path.exists(n_m3u8dl_path):
            self.log(f"[DOWNLOAD] ❌ N_m3u8DL-RE не найден по пути: {safe_path}")
            return False

        # Формирование параметров ключей
        if keys:
            self.log(f"[DOWNLOAD] Передано ключей: {len(keys)}")
            for i, k in enumerate(keys, 1):
                kid, key = k.split(':')
                self.log(f"[DOWNLOAD]   Ключ #{i}: KID={kid[:8]}... | KEY={key[:8]}...")
            key_params = " ".join([f"--key {k}" for k in keys])
        else:
            self.log("[DOWNLOAD] Ключи не переданы (режим без DRM)")
            key_params = ""

        # Очистка имени файла от недопустимых символов
        save_name_clean = re.sub(r'[\s\\/:*?"<>|]', '_', save_name).strip('_')
        if save_name_clean != save_name:
            self.log(f"[DOWNLOAD] Имя файла очищено: '{save_name}' -> '{save_name_clean}'")

        # Формирование команды
        # Обернул пути в экранированные кавычки для надежности в Windows
        command = f'"{safe_path}" "{url}" {key_params} -M format=mp4 -sv res="{quality}" -sa ru --log-level INFO --save-dir "{save_dir}" --save-name "{save_name_clean}"'
        self.log(f"[DOWNLOAD] Команда: {command}...")

        # Настройка переменных окружения для передачи пути к ffmpeg
        env = os.environ.copy()
        ffmpeg_bin_dir = os.path.join(self.bin_dir, "ffmpeg", "bin")
        env["PATH"] = f"{self.bin_dir};{ffmpeg_bin_dir};" + env.get("PATH", "")

        # Запуск процесса
        self.log(f"[DOWNLOAD] Запуск N_m3u8DL-RE ({method_name})...")
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                env=env  # Передаем обновленные пути!
            )

            download_progress = []
            for line in process.stdout:
                clean_line = line.strip()
                if clean_line:
                    # Фильтрация для отображения прогресса
                    if any(x in clean_line.lower() for x in ['download', 'merge', 'complete', 'error', 'fail', '%']):
                        self.log(f"[N_m3u8DL] {clean_line}")
                        download_progress.append(clean_line)
                    elif 'key' not in clean_line.lower() and len(clean_line) < 150:
                        self.log(f"[N_m3u8DL] {clean_line}")

            process.wait()
            success = process.returncode == 0

            if success:
                self.log(f"[DOWNLOAD] ✓ Скачивание успешно завершено ({method_name})")
                output_file = os.path.join(save_dir, f"{save_name_clean}.mp4")
                if os.path.exists(output_file):
                    size_mb = os.path.getsize(output_file) / (1024 * 1024)
                    self.log(f"[DOWNLOAD] Размер итогового файла: {size_mb:.2f} MB")
            else:
                self.log(f"[DOWNLOAD] ❌ Скачивание завершилось с ошибкой (код {process.returncode})")

            return success

        except Exception as e:
            self.log(f"[DOWNLOAD] ❌ Исключение при запуске N_m3u8DL-RE: {type(e).__name__}: {str(e)}")
            return False

    def download_pipeline(self, info, quality, output_path):
        """Основной конвейер скачивания видео"""
        video_title = info['title']
        self.log(f"\n{'=' * 60}")
        self.log(f"[PIPELINE] НАЧАЛО СКАЧИВАНИЯ: {video_title}")
        self.log(f"{'=' * 60}")

        video_item = info['video_data']
        referer = info['referer']
        save_dir = os.path.dirname(output_path)
        save_name = os.path.splitext(os.path.basename(output_path))[0]

        os.makedirs(save_dir, exist_ok=True)
        self.log(f"[PIPELINE] Директория сохранения: {save_dir}")
        self.log(f"[PIPELINE] Запрошенное качество: {quality}")

        # Извлечение потоков
        mpd_url, m3u8_url = self._extract_stream_urls(video_item)
        if not m3u8_url:
            self.log("[PIPELINE] ❌ M3U8 URL не найден. Скачивание невозможно.")
            return False
        self.log(f"[PIPELINE] M3U8 URL: {m3u8_url[:60]}...")

        # === СПОСОБ 2: WIDEVINE ===
        self.log("\n[PIPELINE] === СПОСОБ 2: WIDEVINE DRM ===")
        try:
            # Шаг 1: Получение лицензионного URL
            license_url = video_item.get('drm', {}).get('widevine', {}).get('licenseUrl')
            if not license_url:
                self.log("[WIDEVINE] ❌ licenseUrl не найден в структуре DRM")
                raise KeyError("licenseUrl отсутствует")

            self.log(f"[WIDEVINE] Найден licenseUrl: {license_url[:60]}...")

            # Шаг 2: Загрузка MPD манифеста
            self.log(f"[WIDEVINE] Загрузка MPD манифеста: {mpd_url[:60]}...")
            mpd_response = requests.get(mpd_url, timeout=15)
            mpd_response.raise_for_status()
            self.log(f"[WIDEVINE] ✓ MPD загружен ({len(mpd_response.text)} символов)")

            # Шаг 3: Извлечение PSSH из манифеста
            self.log("[WIDEVINE] Поиск PSSH в MPD манифесте...")
            pssh_match = re.search(r'<cenc:pssh[^>]*>([^<]+)</cenc:pssh>', mpd_response.text)
            if not pssh_match:
                self.log("[WIDEVINE] ❌ PSSH не найден в манифесте")
                raise ValueError("PSSH не найден")

            pssh = pssh_match.group(1).strip()
            self.log(f"[WIDEVINE] ✓ PSSH найден: {pssh[:40]}...")

            # Шаг 4: Получение ключей
            keys = self.get_key(pssh, license_url, referer)
            if not keys:
                self.log("[WIDEVINE] ❌ Ключи не получены")
                raise ValueError("Ключи не получены")

            # Шаг 5: Скачивание с ключами
            self.log("[WIDEVINE] Запуск скачивания с полученными ключами...")
            if self.run_n_m3u8dl(m3u8_url, keys, quality, save_dir, save_name, "Widevine"):
                self.log(f"\n{'=' * 60}")
                self.log(f"[PIPELINE] ✓ УСПЕХ: Видео скачано через Widevine DRM")
                self.log(f"{'=' * 60}\n")
                return True
            else:
                self.log("[WIDEVINE] Скачивание с ключами не удалось")

        except Exception as e:
            self.log(f"[WIDEVINE] ⚠️ Способ 2 (Widevine) завершился с ошибкой: {type(e).__name__}: {str(e)}")

        # === СПОСОБ 3: CLEARKEY ===
        self.log("\n[PIPELINE] === СПОСОБ 3: CLEARKEY DRM ===")
        try:
            self.log("[CLEARKEY] Загрузка MPD для извлечения KID...")
            mpd_response = requests.get(mpd_url, timeout=15)
            mpd_response.raise_for_status()

            # Извлекаем default_KID из манифеста
            self.log("[CLEARKEY] Поиск default_KID в манифесте...")
            kid_match = re.search(r'cenc:default_KID="([^"]+)"', mpd_response.text)
            if not kid_match:
                self.log("[CLEARKEY] ❌ default_KID не найден")
                raise ValueError("KID не найден")

            kid_hex = kid_match.group(1).replace('-', '')
            self.log(f"[CLEARKEY] ✓ Найден KID: {kid_hex}")

            # Получаем licenseUrl для Clearkey
            lic_url = video_item.get('drm', {}).get('clearkey', {}).get('licenseUrl')
            if not lic_url:
                self.log("[CLEARKEY] ❌ licenseUrl для Clearkey не найден")
                raise KeyError("Clearkey licenseUrl отсутствует")

            self.log(f"[CLEARKEY] Отправка запроса на лицензионный сервер: {lic_url[:60]}...")

            # Формируем KID в base64 без padding
            kid_b64 = b64encode(bytes.fromhex(kid_hex)).decode().rstrip('=')

            # Отправляем запрос к Clearkey серверу
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': referer,
                'Origin': referer.split('/')[0] + '//' + referer.split('/')[2] if referer else '',
                'Content-Type': 'application/json'
            }

            payload = {
                "kids": [kid_b64],
                "type": "temporary"
            }

            resp = requests.post(lic_url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            license_data = resp.json()
            self.log(f"[CLEARKEY] ✓ Ответ сервера получен")

            if 'keys' not in license_data or not license_data['keys']:
                self.log("[CLEARKEY] ❌ Ключи не найдены в ответе сервера")
                raise ValueError("Ключи отсутствуют в ответе")

            # Извлекаем ключ - правильно формируем KID:KEY
            key_data = license_data['keys'][0]
            key_hex = b64decode(key_data['k'] + '==').hex()
            key_param = f"{kid_hex}:{key_hex}"

            self.log(
                f"[CLEARKEY] Извлечён ключ: KID={key_param.split(':')[0][:8]}... | KEY={key_param.split(':')[1][:8]}...")

            # Запускаем скачивание с правильным ключом
            if self.run_n_m3u8dl(m3u8_url, [key_param], quality, save_dir, save_name, "Clearkey"):
                self.log(f"\n{'=' * 60}")
                self.log(f"[PIPELINE] ✓ УСПЕХ: Видео скачано через Clearkey DRM")
                self.log(f"{'=' * 60}\n")
                return True


        except Exception as e:
            self.log(f"[CLEARKEY] ⚠️ Способ 3 (Clearkey) завершился с ошибкой: {type(e).__name__}: {str(e)}")

        # === СПОСОБ 4: KEYLESS ===
        self.log("\n[PIPELINE] === СПОСОБ 4: БЕЗ КЛЮЧЕЙ (открытый поток) ===")
        self.log("[KEYLESS] Попытка скачать видео без дешифрования...")
        if self.run_n_m3u8dl(m3u8_url, [], quality, save_dir, save_name, "Keyless"):
            self.log(f"\n{'=' * 60}")
            self.log(f"[PIPELINE] ✓ УСПЕХ: Видео скачано без DRM")
            self.log(f"{'=' * 60}\n")
            return True

        # === ВСЕ СПОСОБЫ ИСЧЕРПАНЫ ===
        self.log(f"\n{'=' * 60}")
        self.log(f"[PIPELINE] ❌ ОШИБКА: Все методы скачивания исчерпаны")
        self.log(f"{'=' * 60}\n")
        return False

    def get_keys_from_log_json(self, json_path):
        """
        Способ 5: Получение ключей на основе загруженного JSON-лога плеера
        """
        # Исправлено: заменено self.logger на self.log
        self.log(f"--- Попытка получить ключи из лога: {json_path} ---")

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)

            # Извлекаем ID видео и реферер
            video_id = log_data.get('state', {}).get('videoId') or log_data.get('videoId')
            if not video_id and 'playerId' in log_data:
                video_id = log_data['playerId'].replace('player_', '')

            referer = log_data.get('referrer') or log_data.get('options', {}).get('metrics', {}).get('urlParams',
                                                                                                     {}).get('referrer')

            # Извлекаем токен из URL
            url_with_token = log_data.get('url', '')
            token_match = re.search(r'drmauthtoken=([^&]+)', url_with_token)
            token = token_match.group(1) if token_match else None

            if not video_id or not token:
                # Исправлено: заменено self.logger на self.log
                self.log("❌ Не удалось найти VideoID или DRM Token в JSON.")
                return None

            # Формируем URL лицензии и манифеста
            license_url = f"https://license.kinescope.io/v1/vod/{video_id}/acquire/widevine?token={token}"
            mpd_url = f"https://kinescope.io/{video_id}/master.mpd"

            # Исправлено: заменено self.logger на self.log
            self.log(f"ID видео: {video_id}")

            # Получаем PSSH из манифеста
            response = requests.get(mpd_url, headers={'Referer': referer}, timeout=10)
            pssh_match = re.search(r'<cenc:pssh[^>]*>([^<]+)</cenc:pssh>', response.text)

            if not pssh_match:
                # Исправлено: заменено self.logger на self.log
                self.log("❌ PSSH не найден в манифесте.")
                return None

            pssh = pssh_match.group(1).strip()

            # Используем существующий метод get_key (Способ 2) для получения ключей
            keys = self.get_key(pssh, license_url, referer)
            return keys, mpd_url, referer

        except Exception as e:
            # Исправлено: заменено self.logger на self.log
            self.log(f"❌ Ошибка при разборе JSON-лога: {e}")
            return None
