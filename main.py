import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading
import sys
import os
import shutil
import json
import re
import mpegdash
import subprocess
import requests
import httpx
from urllib.parse import urlparse
from base64 import b64decode, b64encode
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
import tqdm

# Настройка темы
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


def get_resource_path(relative_path):
    """Получает путь к ресурсам относительно исполняемого файла"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base_path, relative_path)


def setup_bin_directory():
    """Создаёт папку bin и копирует туда необходимые exe-файлы"""
    bin_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "bin")
    os.makedirs(bin_dir, exist_ok=True)

    ffmpeg_src = get_resource_path("ffmpeg/bin/ffmpeg.exe")
    ffmpeg_dst = os.path.join(bin_dir, "ffmpeg.exe")
    if not os.path.exists(ffmpeg_dst) and os.path.exists(ffmpeg_src):
        shutil.copy2(ffmpeg_src, ffmpeg_dst)

    mp4decrypt_src = get_resource_path("mp4decrypt.exe")
    mp4decrypt_dst = os.path.join(bin_dir, "mp4decrypt.exe")
    if not os.path.exists(mp4decrypt_dst) and os.path.exists(mp4decrypt_src):
        shutil.copy2(mp4decrypt_src, mp4decrypt_dst)

    n_m3u8dl_src = get_resource_path("N_m3u8DL-RE.exe")
    n_m3u8dl_dst = os.path.join(bin_dir, "N_m3u8DL-RE.exe")
    if not os.path.exists(n_m3u8dl_dst) and os.path.exists(n_m3u8dl_src):
        shutil.copy2(n_m3u8dl_src, n_m3u8dl_dst)

    return bin_dir


def validate_url(url):
    """Проверяет, является ли строка валидным URL"""
    try:
        parsed = urlparse(url)
        return all([parsed.scheme, parsed.netloc])
    except:
        return False


def extract_from_json(json_filepath):
    """Извлекает URL, Referer и Title из JSON файла"""
    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        video_url = data.get('url', '')
        referer = data.get('referrer', '')
        video_id = data.get('meta', {}).get('videoId', '')

        # *** ИСПРАВЛЕНИЕ: Ищем title по правильному пути: options -> playlist -> [0] -> title ***
        video_title = ''
        if data.get('options') and isinstance(data['options'].get('playlist'), list) and len(
                data['options']['playlist']) > 0:
            # Пытаемся взять title из первого элемента плейлиста
            video_title = data['options']['playlist'][0].get('title', '')

        # Если не нашли там, пробуем старый путь (хотя он, вероятно, неверный для этого типа JSON)
        if not video_title:
            video_title = data.get('meta', {}).get('title', '')

        return video_url, referer, video_id, data, video_title

    except Exception as e:
        raise ValueError(f"Ошибка чтения JSON файла: {str(e)}")


class KinescopeDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DOBRO LOADER")
        self.root.geometry("500x650")  # Уменьшена высота
        self.root.resizable(True, True)

        # Цветовая схема
        self.accent_color = "#fb9422"
        self.light_bg = "#F8F9FA"
        self.card_bg = "#FFFFFF"

        # Переменные
        self.video_url = tk.StringVar()
        self.referer_url = tk.StringVar()
        self.output_file = tk.StringVar()
        self.selected_quality = tk.StringVar()
        self.download_in_progress = False
        self.qualities_loaded = False
        self.current_json_file = tk.StringVar(value="")
        self.json_data = None
        self.available_qualities = []
        self.drm_keys = []
        self.video_title = tk.StringVar(value="")

        self.setup_ui()

    def setup_ui(self):
        # Главный контейнер с прокруткой
        main_frame = ctk.CTkFrame(self.root, fg_color=self.light_bg)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)  # Уменьшены отступы

        # Canvas для прокрутки
        self.canvas = tk.Canvas(main_frame, bg=self.light_bg, highlightthickness=0)
        scrollbar = ctk.CTkScrollbar(main_frame, orientation="vertical", command=self.canvas.yview)
        self.scrollable_frame = ctk.CTkFrame(self.canvas, fg_color=self.light_bg)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True, padx=(0, 5))
        scrollbar.pack(side="right", fill="y")

        # Заголовок с логотипом (упрощенный)
        header_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent", height=80)
        header_frame.pack(fill="x", pady=(0, 15))

        try:
            logo_path = get_resource_path("logo.png")
            if os.path.exists(logo_path):
                from PIL import Image
                logo_image = ctk.CTkImage(
                    light_image=Image.open(logo_path),
                    dark_image=Image.open(logo_path),
                    size=(300, 120)  # Уменьшен размер логотипа
                )
                logo_label = ctk.CTkLabel(header_frame, image=logo_image, text="")
                logo_label.pack(pady=(5, 5))
            else:
                title_label = ctk.CTkLabel(header_frame,
                                           text="DOBRO LOADER",
                                           font=ctk.CTkFont(size=20, weight="bold"),  # Уменьшен шрифт
                                           text_color="#2C3E50")
                title_label.pack(pady=(5, 5))
        except Exception as e:
            title_label = ctk.CTkLabel(header_frame,
                                       text="DOBRO LOADER",
                                       font=ctk.CTkFont(size=20, weight="bold"),
                                       text_color="#2C3E50")
            title_label.pack(pady=(5, 5))

        subtitle_label = ctk.CTkLabel(header_frame,
                                      text="Загрузите JSON файл для скачивания видео",
                                      font=ctk.CTkFont(size=11),  # Уменьшен шрифт
                                      text_color="#7F8C8D")
        subtitle_label.pack()

        # Карточка загрузки JSON (компактная)
        json_card = ctk.CTkFrame(self.scrollable_frame, fg_color=self.card_bg, corner_radius=10, height=90)
        json_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(json_card,
                     text="1. Загрузка данных",
                     font=ctk.CTkFont(size=12, weight="bold"),  # Уменьшен шрифт
                     text_color="#2C3E50").pack(anchor="w", padx=15, pady=(12, 8))

        json_button_frame = ctk.CTkFrame(json_card, fg_color="transparent")
        json_button_frame.pack(fill="x", padx=15, pady=(0, 8))

        json_button = ctk.CTkButton(json_button_frame,
                                    text="📁 Выбрать JSON",
                                    text_color="#2C3E50",
                                    command=self.load_json_file,
                                    fg_color=self.accent_color,
                                    hover_color="#f48200",
                                    height=32,  # Уменьшена высота
                                    width=120)  # Фиксированная ширина
        json_button.pack(side="left")

        self.json_status_label = ctk.CTkLabel(json_button_frame,
                                              text="Файл не выбран",
                                              font=ctk.CTkFont(size=10),  # Уменьшен шрифт
                                              text_color="#7F8C8D")
        self.json_status_label.pack(side="left", padx=(10, 0))

        # Карточка качества (компактная)
        self.quality_card = ctk.CTkFrame(self.scrollable_frame, fg_color=self.card_bg, corner_radius=10, height=90)
        self.quality_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(self.quality_card,
                     text="2. Выбор качества",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#2C3E50").pack(anchor="w", padx=15, pady=(12, 8))

        quality_frame = ctk.CTkFrame(self.quality_card, fg_color="transparent")
        quality_frame.pack(fill="x", padx=15, pady=(0, 8))

        self.quality_combo = ctk.CTkComboBox(quality_frame,
                                             variable=self.selected_quality,
                                             state="readonly",
                                             height=32,  # Уменьшена высота
                                             width=120,  # Фиксированная ширина
                                             border_color="#E0E0E0")
        self.quality_combo.pack(side="left")
        self.quality_combo.set("")

        self.qualities_status_label = ctk.CTkLabel(quality_frame,
                                                   text="Загрузите JSON файл",
                                                   font=ctk.CTkFont(size=10),
                                                   text_color="#7F8C8D")
        self.qualities_status_label.pack(side="left", padx=(10, 0))

        # Карточка сохранения (компактная)
        save_card = ctk.CTkFrame(self.scrollable_frame, fg_color=self.card_bg, corner_radius=10, height=90)
        save_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(save_card,
                     text="3. Сохранение",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#2C3E50").pack(anchor="w", padx=15, pady=(12, 8))

        save_frame = ctk.CTkFrame(save_card, fg_color="transparent")
        save_frame.pack(fill="x", padx=15, pady=(0, 8))

        self.file_entry = ctk.CTkEntry(save_frame,
                                       textvariable=self.output_file,
                                       placeholder_text="Путь для сохранения...",
                                       height=32)  # Уменьшена высота
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_button = ctk.CTkButton(save_frame,
                                      text="Обзор",
                                      command=self.browse_file,
                                      width=70,  # Уменьшена ширина
                                      height=32,
                                      fg_color="#34495E",
                                      hover_color="#2C3E50")
        browse_button.pack(side="right")

        # Кнопка загрузки (более компактная)
        download_buttons_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent", height=50)
        download_buttons_frame.pack(fill="x", pady=(5, 5))

        self.download_button = ctk.CTkButton(download_buttons_frame,
                                             text="Скачать видео",
                                             text_color="#FFFFFF",
                                             command=self.start_unified_download,
                                             state="disabled",
                                             height=38,  # Уменьшена высота
                                             font=ctk.CTkFont(size=14, weight="bold"),
                                             fg_color="#27AE60",
                                             hover_color="#229954")
        self.download_button.pack(fill="x", expand=True)

        # Кнопки управления (компактные)
        button_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent", height=40)
        button_frame.pack(fill="x", pady=(5, 0))

        clear_button = ctk.CTkButton(button_frame,
                                     text="Очистить",
                                     command=self.clear_fields,
                                     height=32,  # Уменьшена высота
                                     width=80,  # Уменьшена ширина
                                     fg_color="#95A5A6",
                                     hover_color="#7F8C8D")
        clear_button.pack(side="right")

        # Карточка прогресса (появляется только при загрузке)
        self.progress_card = ctk.CTkFrame(self.scrollable_frame, fg_color=self.card_bg, corner_radius=10)

        # Настройка прокрутки колесиком мыши
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def add_progress_message(self, message):
        """Добавляет сообщение в текстовое поле прогресса"""
        if not self.progress_card.winfo_ismapped():
            self.progress_card.pack(fill="x", pady=(10, 0))
            self.root.update_idletasks()

        # Создаем текстовое поле только при первом использовании
        if not hasattr(self, 'progress_text'):
            ctk.CTkLabel(self.progress_card,
                         text="Прогресс загрузки",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#2C3E50").pack(anchor="w", padx=15, pady=(12, 8))

            self.progress_text = ctk.CTkTextbox(self.progress_card, height=80,  # Уменьшена высота
                                                font=ctk.CTkFont(family="Consolas", size=10))  # Уменьшен шрифт
            self.progress_text.pack(fill="x", padx=15, pady=(0, 12))
            self.progress_text.configure(state="disabled")

        self.progress_text.configure(state="normal")
        self.progress_text.insert("end", message + "\n")
        self.progress_text.see("end")
        self.progress_text.configure(state="disabled")
        self.root.update_idletasks()

    def load_json_file(self):
        """Загружает JSON файл и извлекает данные"""
        filename = filedialog.askopenfilename(
            title="Выберите JSON файл",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )

        if not filename:
            return

        try:
            video_url, referer, video_id, json_data, video_title = extract_from_json(filename)
            self.json_data = json_data

            if not video_url:
                messagebox.showerror("Ошибка", "Не удалось найти URL в JSON файле")
                return

            self.video_url.set(video_url)
            self.referer_url.set(referer)
            self.current_json_file.set(filename)
            self.video_title.set(video_title)

            # 2. Получаем директорию, где лежит JSON-файл
            json_dir = os.path.dirname(filename)
            print(f"[LOG] load_json_file: JSON File Dir: {json_dir}")  # <-- ЛОГИРОВАНИЕ

            file_name = os.path.basename(filename)
            self.json_status_label.configure(text=f"✓ {file_name}", text_color="#27AE60")
            self.qualities_status_label.configure(text="Получаем список качеств и ключи...", text_color="#3498DB")

            # 3. Передаем эту директорию в функцию установки имени файла
            self._set_default_output_filename(video_title, json_dir)
            self.fetch_qualities_and_keys()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при загрузке JSON файла:\n{str(e)}")

    def _set_default_output_filename(self, title, save_dir=None):
        """Форматирует название для имени файла и устанавливает его в папку JSON."""
        print(f"[LOG] _set_default_output_filename: Received title='{title}', save_dir='{save_dir}'")  # Оставляем лог

        # Определяем название: если title пустой, используем 'video_download'
        effective_title = title if title else "video_download"

        # 1. Форматируем безопасное имя - заменяем пробелы и спецсимволы на подчеркивания
        safe_title = re.sub(r'[\s\\/:*?"<>|]', '_', effective_title)
        # Убираем двойные подчеркивания
        safe_title = re.sub(r'_+', '_', safe_title)
        # Убираем подчеркивания в начале и конце
        safe_title = safe_title.strip('_')
        default_filename = safe_title + ".mp4"

        # 2. Определяем конечную директорию (папка JSON или текущая)
        final_dir = save_dir if save_dir else os.getcwd()

        # 3. ВСЕГДА устанавливаем полный путь по умолчанию
        full_path = os.path.join(final_dir, default_filename)
        self.output_file.set(full_path)

        print(f"[LOG] _set_default_output_filename: Set Output Path: {full_path}")  # Оставляем лог

    # Для экономии места оставлю сигнатуры остальных методов, но реализация остается прежней
    def fetch_qualities_and_keys(self):
        """Получает список качеств и DRM ключи"""
        fetch_thread = threading.Thread(target=self._fetch_qualities_and_keys_thread)
        fetch_thread.daemon = True
        fetch_thread.start()

    def _fetch_qualities_and_keys_thread(self):
        """Поток для получения качеств и ключей"""
        try:
            qualities = self._extract_qualities_from_json()
            if qualities:
                self.root.after(0, lambda: self._update_qualities_ui(qualities))
            else:
                self._fetch_qualities_standard()
            self._fetch_drm_keys()
        except Exception as e:
            error_msg = f"Ошибка при получении данных: {str(e)}"
            self.root.after(0, lambda: self.qualities_status_label.configure(
                text=error_msg,
                text_color="#E74C3C"
            ))

    def _extract_qualities_from_json(self):
        """Извлекает качества из JSON данных"""
        qualities = []
        if self.json_data and 'options' in self.json_data and 'playlist' in self.json_data['options']:
            for item in self.json_data['options']['playlist']:
                if 'frameRate' in item:
                    for quality in item['frameRate'].keys():
                        if quality.isdigit():
                            qualities.append(int(quality))
        qualities = sorted(list(set(qualities)))
        return qualities


    def _fetch_drm_keys(self):
        """Получает DRM ключи для второго способа скачивания"""
        pssh_list = []
        license_url_list = []
        mpd_url, m3u8_url = self._extract_stream_urls()

        if mpd_url:
            try:
                self.add_progress_message("[*] Поиск PSSH и License URL в MPD...")
                mpd_content = requests.get(mpd_url, timeout=10).text
                pssh_list = re.findall(r'<cenc:pssh[^>]*>([^<]+)</cenc:pssh>', mpd_content)
                license_url_list = re.findall(r'<dashif:Laurl>([^<]+)</dashif:Laurl>', mpd_content)
            except Exception as e:
                self.root.after(0, lambda: self.add_progress_message(f"[!] Ошибка при чтении MPD: {str(e)}"))

        if not pssh_list and m3u8_url:
            self.add_progress_message("[*] Поиск PSSH и License URL в M3U8...")
            license_url_hls, pssh_hls = self._extract_pssh_from_hls(m3u8_url)
            if pssh_hls:
                pssh_list.append(pssh_hls)
            if license_url_hls:
                license_url_list.append(license_url_hls)

        try:
            if pssh_list and license_url_list:
                final_pssh = list(set(pssh_list))[0]
                final_license_url = list(set(license_url_list))[0]
                self.add_progress_message("[*] Декодирование ключей...")
                keys = self.get_key(final_pssh, final_license_url, self.referer_url.get())
                self.drm_keys = keys
                self.root.after(0, lambda: self.add_progress_message(f"[+] Получено DRM ключей: {len(keys)}"))
                return
            self.root.after(0, lambda: self.add_progress_message(
                "[!] Не удалось найти PSSH и License URL"))
        except Exception as e:
            self.root.after(0, lambda: self.add_progress_message(f"[!] Ошибка получения DRM ключей: {str(e)}"))

    def _extract_stream_urls(self):
        """Извлекает URL потоков из JSON"""
        mpd_url, m3u8_url = None, None
        if self.json_data and 'options' in self.json_data and 'playlist' in self.json_data['options']:
            for item in self.json_data['options']['playlist']:
                if 'sources' in item:
                    if 'shakadash' in item['sources']:
                        mpd_url = item['sources']['shakadash'].get('src')
                    if 'hls' in item['sources']:
                        m3u8_url = item['sources']['hls'].get('src')
                if mpd_url and m3u8_url:
                    break

        # *** ДОРАБОТКА: Конвертация M3U8 URL в MPD URL для поиска ключей ***
        # Если MPD не найден напрямую, но есть M3U8, пытаемся создать MPD URL
        if not mpd_url and m3u8_url:
            # Заменяем распространенные расширения m3u8 на mpd
            derived_mpd_url = m3u8_url.replace('/master.m3u8', '/master.mpd').replace('/manifest.m3u8', '/manifest.mpd')
            # Если URL действительно изменился, используем его как mpd_url
            if derived_mpd_url != m3u8_url:
                mpd_url = derived_mpd_url
                self.add_progress_message(f"[*] Сгенерирован MPD URL для поиска ключей: {mpd_url}")
        # *** КОНЕЦ ДОРАБОТКИ ***

        return mpd_url, m3u8_url

    def get_key(self, pssh, license_url, referer):
        """Получает ключи для Widevine"""
        base_headers = {
            'sec-ch-ua': '"Google Chrome";v="95", "Chromium";v="95", ";Not A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.54 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'accept': '*/*',
            'sec-fetch-site': 'same-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'accept-language': 'en-US,en;q=0.9,vi;q=0.8',
        }

        headers = base_headers.copy()
        headers.update({
            'authority': 'license.kinescope.io',
            'origin': referer,
            'referer': referer
        })

        wvd_path = "WVD.wvd"
        if not os.path.exists(wvd_path):
            raise FileNotFoundError("WVD.wvd файл не найден")

        device = Device.load(wvd_path)
        cdm = Cdm.from_device(device)
        session_id = cdm.open()
        challenge = cdm.get_license_challenge(session_id, PSSH(pssh))
        response = httpx.post(license_url, data=challenge, headers=headers)
        cdm.parse_license(session_id, response.content)
        keys = [f"{key.kid.hex}:{key.key.hex()}" for key in cdm.get_keys(session_id) if key.type == 'CONTENT']
        cdm.close(session_id)
        return keys

    def _update_qualities_ui(self, qualities):
        """Обновляет интерфейс с полученными качествами"""
        if not qualities:
            self.qualities_status_label.configure(
                text="Качества не найдены",
                text_color="#E74C3C"
            )
            return

        quality_list = [f"{q}p" for q in qualities]
        self.available_qualities = qualities
        self.quality_combo.configure(values=quality_list)

        if quality_list:
            self.quality_combo.set(quality_list[-1])
            self.qualities_loaded = True
            self.qualities_status_label.configure(
                text=f"✓ Доступно качеств: {len(quality_list)}",
                text_color="#27AE60"
            )
            self.download_button.configure(state="normal")

    def browse_file(self):
        """Открывает диалог сохранения файла с предложенным названием"""

        current_full_path = self.output_file.get()
        print(f"[LOG] browse_file: Current Output Path: {current_full_path}")

        # 1. Определяем начальную директорию
        initial_dir = os.getcwd()
        if current_full_path:
            dir_from_path = os.path.dirname(current_full_path)
            # Проверяем, существует ли директория, чтобы избежать сброса Tkinter'ом
            if os.path.exists(dir_from_path) and os.path.isdir(dir_from_path):
                initial_dir = dir_from_path

        # 2. Определяем начальное имя файла
        initial_file = ""
        if current_full_path and not os.path.isdir(current_full_path):
            initial_file = os.path.basename(current_full_path)
        elif self.video_title.get():
            safe_name = re.sub(r'[\s\\/:*?"<>|]', '_', self.video_title.get())
            # Убираем двойные подчеркивания
            safe_name = re.sub(r'_+', '_', safe_name)
            # Убираем подчеркивания в начале и конце
            safe_name = safe_name.strip('_')
            initial_file = safe_name + ".mp4"

        print(f"[LOG] browse_file: Initial Dir: {initial_dir}")
        print(f"[LOG] browse_file: Initial File: {initial_file}")

        filename = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")],
            initialfile=initial_file,
            initialdir=initial_dir
        )
        if filename:
            self.output_file.set(filename)
            print(f"[LOG] browse_file: New selected path: {filename}")

    def start_unified_download(self):
        if self.download_in_progress:
            return

        if not self.output_file.get():
            messagebox.showerror("Ошибка", "Выберите путь для сохранения файла")
            return

        if not self.qualities_loaded:
            messagebox.showerror("Ошибка", "Сначала загрузите JSON файл")
            return

        self.download_in_progress = True
        self.download_button.configure(state="disabled")

        if hasattr(self, 'progress_text'):
            self.progress_text.configure(state="normal")
            self.progress_text.delete("1.0", "end")
            self.progress_text.configure(state="disabled")

        download_thread = threading.Thread(target=self.download_video_with_fallback)
        download_thread.daemon = True
        download_thread.start()

    def download_video_with_fallback(self):
        try:
            self.add_progress_message("[*] Запуск скачивания. Сначала пробуем Способ 2 (Widevine N_m3u8DL-RE)...")
            success = self._download_method_2()

            if not success:
                self.add_progress_message("[!] Способ 2 не сработал. Пробуем Способ 3 (Clearkey N_m3u8DL-RE)...")
                success = self._download_method_3()

            # --- НОВЫЙ ШАГ (Способ 4) ---
            if not success:
                self.add_progress_message("[!] Способ 3 не сработал. Пробуем Способ 4 (Keyless N_m3u8DL-RE)...")
                success = self._download_method_4()
            # ---------------------------

            if not success:
                self.add_progress_message("[!] Способ 4 не сработал. Пробуем Способ 1 (KinescopeDownloader)...")
                # Убеждаемся, что результат _download_method_1 сохраняется для корректной финальной проверки
                success = self._download_method_1()

            if not success:
                self.add_progress_message("[!] Не удалось скачать видео: все 4 метода не сработали.")
                self.show_error("Не удалось скачать видео: все 4 метода не сработали.")

        except Exception as e:
            self.show_error(f"Критическая ошибка при загрузке видео: {str(e)}")
        finally:
            self.download_in_progress = False
            self.download_button.configure(state="normal")


    def _download_method_2(self):
        """Второй способ скачивания (через N_m3u8DL-RE с Widevine)"""
        try:
            mpd_url, m3u8_url = self._extract_stream_urls()
            if not m3u8_url:
                raise Exception("Не удалось найти URL потока в JSON")

            selected_quality = self.quality_combo.get().replace('p', '')
            if not self.drm_keys:
                self.add_progress_message("[!] DRM ключи не получены. Способ 2 невозможен.")
                return False

            bin_dir = setup_bin_directory()
            n_m3u8dl_path = os.path.join(bin_dir, "N_m3u8DL-RE.exe")
            key_params = " ".join([f"--key {key}" for key in self.drm_keys])

            output_path = self.output_file.get()
            save_dir = os.path.dirname(output_path)
            save_name = os.path.splitext(os.path.basename(output_path))[0]

            # Форматируем имя файла без пробелов и спецсимволов
            save_name_clean = re.sub(r'[\s\\/:*?"<>|]', '_', save_name)
            save_name_clean = re.sub(r'_+', '_', save_name_clean)
            save_name_clean = save_name_clean.strip('_')

            command = f'"{n_m3u8dl_path}" "{m3u8_url}" {key_params} -M format=mp4 -sv res="{selected_quality}" -sa all --log-level INFO --no-log --save-dir "{save_dir}" --save-name "{save_name_clean}"'

            self.add_progress_message(f"[*] Запуск N_m3u8DL-RE...")
            self.add_progress_message(f"[*] Команда: {command}")

            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       bufsize=1)

            vid_progress_pattern = re.compile(r'.*?(\d+/\d+\s+\d+\.\d+%)')
            last_progress = ""

            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    match = vid_progress_pattern.search(output)
                    if match:
                        progress_info = match.group(1)
                        if progress_info != last_progress:
                            self.add_progress_message(f"Прогресс: {progress_info}")
                            last_progress = progress_info

            if process.returncode == 0:
                self.add_progress_message("\n[+] Скачивание завершено (Способ 2)!")
                messagebox.showinfo("Успех", f"Видео успешно скачано!\nФайл: {output_path}")
                return True
            else:
                self.add_progress_message(f"[!] N_m3u8DL-RE завершился с ошибкой: {process.returncode}")
                return False

        except Exception as e:
            self.add_progress_message(f"[!] Ошибка во втором способе: {str(e)}")
            return False

    def _download_method_3(self):
        """Третий способ скачивания (через N_m3u8DL-RE с Clearkey)"""
        try:
            # Получаем данные из JSON
            c = self.json_data
            if not c:
                raise Exception("JSON данные не загружены")

            # Ищем playlist
            if not c.get('options') or not c['options'].get('playlist'):
                raise Exception("Не найден playlist в JSON")

            p = c["options"]["playlist"][0]

            # Ищем MPD URL в разных возможных местах
            mpd_url = None
            sources = p.get("sources", {})

            # Проверяем разные варианты ключей
            for key in ["shakadash", "shaka-dash", "dash", "mpd"]:
                if key in sources and isinstance(sources[key], dict) and "src" in sources[key]:
                    mpd_url = sources[key]["src"]
                    break
                elif key in sources and isinstance(sources[key], str):
                    mpd_url = sources[key]
                    break

            if not mpd_url:
                # Если MPD не найден, пробуем HLS и преобразуем в MPD
                hls_url = None
                for key in ["hls", "m3u8"]:
                    if key in sources and isinstance(sources[key], dict) and "src" in sources[key]:
                        hls_url = sources[key]["src"]
                        break
                    elif key in sources and isinstance(sources[key], str):
                        hls_url = sources[key]
                        break

                if hls_url:
                    # Преобразуем HLS URL в MPD URL
                    mpd_url = hls_url.replace("/master.m3u8", "/master.mpd").replace("/manifest.m3u8", "/manifest.mpd")

            if not mpd_url:
                raise Exception("Ошибка: не найден URL MPD или HLS")

            # Получаем MPD
            self.add_progress_message(f"[*] Получение MPD: {mpd_url}")
            mpd = requests.get(mpd_url, headers={"Referer": c.get("referrer", "")}).text

            # Поиск KID
            kid_match = re.search(r'cenc:default_KID="([^"]+)"', mpd)
            if not kid_match:
                m = re.search(r'<cenc:pssh[^>]*>([^<]+)</cenc:pssh>', mpd)
                if m:
                    try:
                        pssh = b64decode(m.group(1))
                        for i in range(len(pssh) - 32):
                            if pssh[i:i + 4] == b'\x00\x00\x00\x1c' and i + 36 <= len(pssh):
                                k = pssh[i + 20:i + 36].hex().upper()
                                # Создаем объект match с найденным KID
                                kid_match = type('obj', (object,),
                                                 {'group': lambda
                                                     x: f"{k[:8]}-{k[8:12]}-{k[12:16]}-{k[16:20]}-{k[20:32]}"})()
                                break
                    except:
                        pass

            kid = kid_match.group(1) if kid_match else "00000000-0000-0000-0000-000000000000"

            # Преобразуем KID в base64
            kid_clean = kid.replace('-', '')
            kid_b64 = b64encode(bytes.fromhex(kid_clean)).decode().replace('=', '')

            # Запрос лицензии
            license_url = p.get("drm", {}).get("clearkey", {}).get("licenseUrl", "")
            if not license_url:
                # Ищем license URL в других местах
                license_url = c.get("drm", {}).get("clearkey", {}).get("licenseUrl", "")

            if not license_url:
                raise Exception("Не найден license URL для Clearkey")

            self.add_progress_message(f"[*] Получение ключа Clearkey из: {license_url}")
            resp = requests.post(license_url,
                                 headers={"Origin": c.get("referrer", ""), "Referer": c.get("referrer", "")},
                                 json={"kids": [kid_b64], "type": "temporary"})

            result = resp.json()

            # Конвертация и вывод
            if result.get('keys'):
                k = result['keys'][0]
                key_hex = b64decode(k['k'] + '==').hex()
                kid_hex = b64decode(k['kid'] + '==').hex()
                key_param = f"{kid_hex}:{key_hex}"
                self.add_progress_message(f"[+] Получен ключ Clearkey: {key_param}")
            else:
                raise Exception(f"Ключи не получены. Ответ: {result}")

            # Получаем HLS URL для скачивания
            m3u8_url = None
            for key in ["hls", "m3u8"]:
                if key in sources and isinstance(sources[key], dict) and "src" in sources[key]:
                    m3u8_url = sources[key]["src"]
                    break
                elif key in sources and isinstance(sources[key], str):
                    m3u8_url = sources[key]
                    break

            if not m3u8_url:
                raise Exception("Не найден HLS URL для скачивания")

            # Собираем команду для N_m3u8DL-RE
            bin_dir = setup_bin_directory()
            n_m3u8dl_path = os.path.join(bin_dir, "N_m3u8DL-RE.exe")

            selected_quality = self.quality_combo.get().replace('p', '')

            output_path = self.output_file.get()
            save_dir = os.path.dirname(output_path)

            # Получаем чистое имя файла без спецсимволов и пробелов
            video_title = self.video_title.get() or "video_download"
            save_name_clean = re.sub(r'[\s\\/:*?"<>|]', '_', video_title)
            save_name_clean = re.sub(r'_+', '_', save_name_clean)
            save_name_clean = save_name_clean.strip('_')

            command = f'"{n_m3u8dl_path}" "{m3u8_url}" --key {key_param} -M format=mp4 -sv res="{selected_quality}" -sa all --log-level INFO --no-log --save-dir "{save_dir}" --save-name "{save_name_clean}"'

            self.add_progress_message(f"[*] Запуск N_m3u8DL-RE (Clearkey)...")
            self.add_progress_message(f"[*] Команда: {command}")

            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       bufsize=1)

            vid_progress_pattern = re.compile(r'.*?(\d+/\d+\s+\d+\.\d+%)')
            last_progress = ""

            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    match = vid_progress_pattern.search(output)
                    if match:
                        progress_info = match.group(1)
                        if progress_info != last_progress:
                            self.add_progress_message(f"Прогресс: {progress_info}")
                            last_progress = progress_info

            if process.returncode == 0:
                self.add_progress_message("\n[+] Скачивание завершено (Способ 3)!")
                messagebox.showinfo("Успех", f"Видео успешно скачано!\nФайл: {output_path}")
                return True
            else:
                self.add_progress_message(f"[!] N_m3u8DL-RE завершился с ошибкой: {process.returncode}")
                return False

        except Exception as e:
            self.add_progress_message(f"[!] Ошибка в третьем способе (Clearkey): {str(e)}")
            return False

    # --- НОВЫЙ МЕТОД: Способ 4 (N_m3u8DL-RE без ключей) ---
    def _download_method_4(self):
        """Четвертый способ скачивания (через N_m3u8DL-RE без ключей)"""
        try:
            mpd_url, m3u8_url = self._extract_stream_urls()
            if not m3u8_url:
                raise Exception("Не удалось найти URL HLS потока в JSON")

            bin_dir = setup_bin_directory()
            n_m3u8dl_path = os.path.join(bin_dir, "N_m3u8DL-RE.exe")

            selected_quality = self.quality_combo.get().replace('p', '')

            output_path = self.output_file.get()
            save_dir = os.path.dirname(output_path)

            # Получаем чистое имя файла без спецсимволов и пробелов
            video_title = self.video_title.get() or "video_download"
            save_name_clean = re.sub(r'[\s\\/:*?"<>|]', '_', video_title)
            save_name_clean = re.sub(r'_+', '_', save_name_clean)
            save_name_clean = save_name_clean.strip('_')

            # Команда без параметра --key
            command = f'"{n_m3u8dl_path}" "{m3u8_url}" -M format=mp4 -sv res="{selected_quality}" -sa all --log-level INFO --no-log --save-dir "{save_dir}" --save-name "{save_name_clean}"'

            self.add_progress_message(f"[*] Запуск N_m3u8DL-RE (Без ключей)...")
            self.add_progress_message(f"[*] Команда: {command}")

            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       bufsize=1)

            vid_progress_pattern = re.compile(r'.*?(\d+/\d+\s+\d+\.\d+%)')
            last_progress = ""

            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    match = vid_progress_pattern.search(output)
                    if match:
                        progress_info = match.group(1)
                        if progress_info != last_progress:
                            self.add_progress_message(f"Прогресс: {progress_info}")
                            last_progress = progress_info

            if process.returncode == 0:
                self.add_progress_message("\n[+] Скачивание завершено (Способ 4)!")
                messagebox.showinfo("Успех", f"Видео успешно скачано!\nФайл: {output_path}")
                return True
            else:
                self.add_progress_message(f"[!] N_m3u8DL-RE завершился с ошибкой: {process.returncode}")
                return False

        except Exception as e:
            self.add_progress_message(f"[!] Ошибка в четвертом способе (Keyless): {str(e)}")
            return False

    # -----------------------------------------------------------------

    def _extract_pssh_from_hls(self, master_m3u8_url_full):
        """Извлекает Widevine License URL и PSSH-ключ из связанного M3U8-файла"""
        license_url = None
        pssh_key = None

        if self.json_data:
            try:
                license_url = self.json_data['options']['playlist'][0]['drm']['widevine']['licenseUrl']
            except (KeyError, IndexError):
                try:
                    license_url = self.json_data['options']['playlist'][0]['drm']['clearkey']['licenseUrl']
                except (KeyError, IndexError):
                    pass

        if not license_url:
            self.add_progress_message("[!] Ошибка: Не удалось найти licenseUrl в JSON.")
            return None, None

        try:
            base_url_match = re.search(r'^(https?://[^?]+?/master\.m3u8)', master_m3u8_url_full)
            if not base_url_match:
                self.add_progress_message("[!] Ошибка: Не удалось извлечь базовую URL для master.m3u8.")
                return license_url, None

            base_url_clean = base_url_match.group(1)
            base_url_prefix = base_url_clean.replace('/master.m3u8', '')

            query_params_match = re.search(r'\?(.*)', master_m3u8_url_full)
            token_params_list = []
            if query_params_match:
                for p in query_params_match.group(1).split('&'):
                    if p.startswith(('expires', 'sign', 'token', 'kinescope_project_id')) and (
                            len(p.split('=')) == 1 or p.split('=')[1]):
                        token_params_list.append(p)
            token_params = "&".join(token_params_list)

            master_response = requests.get(base_url_clean, timeout=10)
            master_response.raise_for_status()
            master_content = master_response.text

            stream_matches = re.findall(
                r'#EXT-X-STREAM-INF:.*?BANDWIDTH=(\d+).*?\n(.*?\.m3u8.*?)(?:\n#|\n\n|$)',
                master_content,
                re.DOTALL
            )

            if not stream_matches:
                self.add_progress_message("[!] Ошибка: Не найдены ссылки на потоки в master.m3u8.")
                return license_url, None

            target_stream_url = None
            for bandwidth_match, stream_url_match in stream_matches:
                if stream_url_match.startswith('http'):
                    target_stream_url = stream_url_match
                else:
                    target_stream_url = f"{base_url_prefix}/{stream_url_match}"

                if token_params:
                    target_stream_url += f"?{token_params}"

                break

            if not target_stream_url:
                self.add_progress_message("[!] Ошибка: Не удалось собрать ссылку на поток.")
                return license_url, None

            stream_response = requests.get(target_stream_url, timeout=10)
            stream_response.raise_for_status()
            stream_content = stream_response.text

            key_uri_match = re.search(r'#EXT-X-KEY:METHOD=SAMPLE-AES,URI="([^"]+)"', stream_content)
            if key_uri_match:
                key_uri = key_uri_match.group(1)
                if not key_uri.startswith('http'):
                    key_uri = f"{base_url_prefix}/{key_uri}"
                if token_params:
                    key_uri += f"?{token_params}"

                key_response = requests.get(key_uri, timeout=10)
                key_response.raise_for_status()
                key_content = key_response.content

                pssh_match = re.search(rb'pssh(.*?)(\x00\x00\x00|\x00\x00)', key_content)
                if pssh_match:
                    pssh_key = pssh_match.group(1).hex()
                    self.add_progress_message(f"[+] PSSH найден: {pssh_key}")
                else:
                    self.add_progress_message("[!] PSSH не найден в ключевом файле.")
            else:
                self.add_progress_message("[!] Ключевая ссылка не найдена в потоке.")

        except Exception as e:
            self.add_progress_message(f"[!] Ошибка при извлечении PSSH: {str(e)}")

        return license_url, pssh_key

    def show_error(self, message):
        """Показывает сообщение об ошибке"""
        self.root.after(0, lambda: messagebox.showerror("Ошибка", message))
        self.root.after(0, lambda: self.add_progress_message(f"[!] {message}"))

    def clear_fields(self):
        """Очищает все поля"""
        self.video_url.set("")
        self.referer_url.set("")
        self.output_file.set("")
        self.selected_quality.set("")
        self.current_json_file.set("")
        self.video_title.set("")
        self.json_data = None
        self.available_qualities = []
        self.drm_keys = []
        self.qualities_loaded = False
        self.json_status_label.configure(text="Файл не выбран", text_color="#7F8C8D")
        self.qualities_status_label.configure(text="Загрузите JSON файл", text_color="#7F8C8D")
        self.quality_combo.configure(values=[])
        self.download_button.configure(state="disabled")

        if hasattr(self, 'progress_text'):
            self.progress_text.configure(state="normal")
            self.progress_text.delete("1.0", "end")
            self.progress_text.configure(state="disabled")
            self.progress_card.pack_forget()


if __name__ == "__main__":
    root = ctk.CTk()
    app = KinescopeDownloaderGUI(root)
    root.mainloop()
