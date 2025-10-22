import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading
import sys
import os
import shutil
import json
import re
import subprocess
import requests
import httpx
from urllib.parse import urlparse
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
        # НОВОЕ: Извлечение названия видео
        video_title = data.get('meta', {}).get('title', '')

        return video_url, referer, video_id, data, video_title # ОБНОВЛЕНИЕ: добавлено video_title

    except Exception as e:
        raise ValueError(f"Ошибка чтения JSON файла: {str(e)}")

class KinescopeDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DOBRO LOADER")
        self.root.geometry("500x850")
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
        # Главный контейнер
        main_container = ctk.CTkFrame(self.root, fg_color=self.light_bg)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Заголовок с логотипом
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))

        # Логотип (остается как было)
        try:
            logo_path = get_resource_path("logo.png")
            if os.path.exists(logo_path):
                from PIL import Image
                logo_image = ctk.CTkImage(
                    light_image=Image.open(logo_path),
                    dark_image=Image.open(logo_path),
                    size=(375, 160)
                )
                logo_label = ctk.CTkLabel(header_frame, image=logo_image, text="")
                logo_label.pack(pady=(10, 10))
            else:
                title_label = ctk.CTkLabel(header_frame,
                                           text="DOBRO LOADER",
                                           font=ctk.CTkFont(size=24, weight="bold"),
                                           text_color="#2C3E50")
                title_label.pack(pady=(0, 10))
        except Exception as e:
            title_label = ctk.CTkLabel(header_frame,
                                       text="DOBRO LOADER",
                                       font=ctk.CTkFont(size=24, weight="bold"),
                                       text_color="#2C3E50")
            title_label.pack(pady=(0, 10))

        subtitle_label = ctk.CTkLabel(header_frame,
                                      text="Загрузите JSON файл для скачивания видео",
                                      font=ctk.CTkFont(size=12),
                                      text_color="#7F8C8D")
        subtitle_label.pack()

        # Карточка загрузки JSON
        json_card = ctk.CTkFrame(main_container, fg_color=self.card_bg, corner_radius=12)
        json_card.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(json_card,
                     text="Шаг 1: Загрузка данных",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#2C3E50").pack(anchor="w", padx=20, pady=(20, 10))

        json_button = ctk.CTkButton(json_card,
                                    text="📁 Выбрать JSON файл",
                                    text_color="#2C3E50",
                                    command=self.load_json_file,
                                    fg_color=self.accent_color,
                                    hover_color="#f48200",
                                    height=40)
        json_button.pack(fill="x", padx=20, pady=(0, 10))

        self.json_status_label = ctk.CTkLabel(json_card,
                                              text="Файл не выбран",
                                              font=ctk.CTkFont(size=11),
                                              text_color="#7F8C8D")
        self.json_status_label.pack(anchor="w", padx=20, pady=(0, 20))

        # Карточка качества
        self.quality_card = ctk.CTkFrame(main_container, fg_color=self.card_bg, corner_radius=12)
        self.quality_card.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(self.quality_card,
                     text="Шаг 2: Выбор качества",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#2C3E50").pack(anchor="w", padx=20, pady=(20, 10))

        self.quality_combo = ctk.CTkComboBox(self.quality_card,
                                             variable=self.selected_quality,
                                             state="readonly",
                                             height=35,
                                             border_color="#E0E0E0")
        self.quality_combo.pack(fill="x", padx=20, pady=(0, 10))
        self.quality_combo.set("")

        self.qualities_status_label = ctk.CTkLabel(self.quality_card,
                                                   text="Загрузите JSON файл",
                                                   font=ctk.CTkFont(size=11),
                                                   text_color="#7F8C8D")
        self.qualities_status_label.pack(anchor="w", padx=20, pady=(0, 20))

        # Карточка сохранения
        save_card = ctk.CTkFrame(main_container, fg_color=self.card_bg, corner_radius=12)
        save_card.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(save_card,
                     text="Шаг 3: Сохранение",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#2C3E50").pack(anchor="w", padx=20, pady=(20, 10))

        save_frame = ctk.CTkFrame(save_card, fg_color="transparent")
        save_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.file_entry = ctk.CTkEntry(save_frame,
                                       textvariable=self.output_file,
                                       placeholder_text="Выберите путь для сохранения...",
                                       height=35)
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        browse_button = ctk.CTkButton(save_frame,
                                      text="Обзор",
                                      command=self.browse_file,
                                      width=80,
                                      height=35,
                                      fg_color="#34495E",
                                      hover_color="#2C3E50")
        browse_button.pack(side="right")

        # Карточка прогресса
        self.progress_card = ctk.CTkFrame(main_container, fg_color=self.card_bg, corner_radius=12)
        self.progress_card.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(self.progress_card,
                     text="Прогресс загрузки",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#2C3E50").pack(anchor="w", padx=20, pady=(20, 10))

        self.progress_text = ctk.CTkTextbox(self.progress_card, height=120,
                                            font=ctk.CTkFont(family="Consolas", size=11))
        self.progress_text.pack(fill="x", padx=20, pady=(0, 20))
        self.progress_text.configure(state="disabled")

        # Кнопка загрузки (ОБНОВЛЕНИЕ: ОДНА КНОПКА)
        download_buttons_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        download_buttons_frame.pack(fill="x", pady=(0, 10))

        self.download_button = ctk.CTkButton(download_buttons_frame,
                                             text="Скачать",
                                             text_color="#FFFFFF",  # Белый цвет текста для зеленого фона
                                             command=self.start_unified_download,  # ОБНОВЛЕНИЕ
                                             state="disabled",
                                             height=45,
                                             font=ctk.CTkFont(size=16, weight="bold"),
                                             fg_color="#27AE60",
                                             hover_color="#229954")
        self.download_button.pack(fill="x", expand=True)  # ОБНОВЛЕНИЕ

        # Кнопки управления
        button_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        button_frame.pack(fill="x")

        clear_button = ctk.CTkButton(button_frame,
                                     text="Очистить",
                                     command=self.clear_fields,
                                     height=45,
                                     fg_color="#95A5A6",
                                     hover_color="#7F8C8D")
        clear_button.pack(side="right")

        # Скрываем прогресс карточку изначально
        self.progress_card.pack_forget()

    def add_progress_message(self, message):
        """Добавляет сообщение в текстовое поле прогресса"""
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
            # ОБНОВЛЕНИЕ: Получаем video_title
            video_url, referer, video_id, json_data, video_title = extract_from_json(filename)
            self.json_data = json_data

            if not video_url:
                messagebox.showerror("Ошибка", "Не удалось найти URL в JSON файле")
                return

            if not referer:
                messagebox.showerror("Ошибка", "Не удалось найти Referer в JSON файле")
                return

            self.video_url.set(video_url)
            self.referer_url.set(referer)
            self.current_json_file.set(filename)
            self.video_title.set(video_title)  # НОВОЕ: Устанавливаем название

            file_name = os.path.basename(filename)
            self.json_status_label.configure(text=f"✓ {file_name}", text_color="#27AE60")
            self.qualities_status_label.configure(text="Получаем список качеств и ключи...", text_color="#3498DB")

            # НОВОЕ: Сразу предлагаем название в поле сохранения
            self._set_default_output_filename(video_title)

            self.fetch_qualities_and_keys()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при загрузке JSON файла:\n{str(e)}")

    def _set_default_output_filename(self, title):
        """Форматирует название для имени файла и устанавливает его"""
        if title:
            # Очищаем название от недопустимых символов и устанавливаем .mp4
            safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
            default_filename = safe_title + ".mp4"
            # Если путь для сохранения еще не установлен, устанавливаем его в текущую директорию
            if not self.output_file.get() or self.output_file.get().endswith(".mp4"):
                self.output_file.set(os.path.join(os.getcwd(), default_filename))

    def fetch_qualities_and_keys(self):
        """Получает список качеств и DRM ключи"""
        fetch_thread = threading.Thread(target=self._fetch_qualities_and_keys_thread)
        fetch_thread.daemon = True
        fetch_thread.start()

    def _fetch_qualities_and_keys_thread(self):
        """Поток для получения качеств и ключей"""
        try:
            # Получаем качества из JSON
            qualities = self._extract_qualities_from_json()

            if qualities:
                self.root.after(0, lambda: self._update_qualities_ui(qualities))
            else:
                # Если не нашли в JSON, пробуем стандартным способом
                self._fetch_qualities_standard()

            # Получаем DRM ключи
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

        # Убираем дубликаты и сортируем
        qualities = sorted(list(set(qualities)))
        return qualities

    def _fetch_qualities_standard(self):
        """Получает качества стандартным способом"""
        try:
            from kinescope import KinescopeVideo, KinescopeDownloader

            bin_dir = setup_bin_directory()
            ffmpeg_path = os.path.join(bin_dir, "ffmpeg.exe")
            mp4decrypt_path = os.path.join(bin_dir, "mp4decrypt.exe")

            kinescope_video = KinescopeVideo(
                url=self.video_url.get(),
                referer_url=self.referer_url.get()
            )

            downloader = KinescopeDownloader(
                kinescope_video,
                temp_dir='./temp',
                ffmpeg_path=ffmpeg_path,
                mp4decrypt_path=mp4decrypt_path
            )

            video_resolutions = downloader.get_resolutions()
            qualities = [res[1] for res in video_resolutions] if video_resolutions else []

            self.root.after(0, lambda: self._update_qualities_ui(qualities))
            downloader.cleanup()

        except Exception as e:
            self.root.after(0, lambda: self.qualities_status_label.configure(
                text=f"Ошибка получения качеств: {str(e)}",
                text_color="#E74C3C"
            ))

    def _fetch_drm_keys(self):
        """Получает DRM ключи для второго способа скачивания"""
        pssh_list = []
        license_url_list = []

        mpd_url, m3u8_url = self._extract_stream_urls()

        # --- Поиск 1: В MPD (DASH) ---
        if mpd_url:
            try:
                self.add_progress_message("[*] Поиск PSSH и License URL в MPD (DASH)...")
                mpd_content = requests.get(mpd_url, timeout=10).text
                pssh_list = re.findall(r'<cenc:pssh[^>]*>([^<]+)</cenc:pssh>', mpd_content)
                license_url_list = re.findall(r'<dashif:Laurl>([^<]+)</dashif:Laurl>', mpd_content)
            except Exception as e:
                self.root.after(0, lambda: self.add_progress_message(f"[!] Ошибка при чтении MPD: {str(e)}"))

        # --- Поиск 2: В M3U8 (HLS) с помощью новой логики ---
        if not pssh_list and m3u8_url:
            self.add_progress_message("[*] Поиск PSSH и License URL в M3U8 (HLS)...")
            license_url_hls, pssh_hls = self._extract_pssh_from_hls(m3u8_url)

            if pssh_hls:
                pssh_list.append(pssh_hls)
            if license_url_hls:
                license_url_list.append(license_url_hls)

        # --- Получение ключей ---
        try:
            if pssh_list and license_url_list:
                # Берем первый уникальный PSSH и License URL
                final_pssh = list(set(pssh_list))[0]
                final_license_url = list(set(license_url_list))[0]

                self.add_progress_message("[*] Декодирование ключей с помощью pywidevine...")
                keys = self.get_key(final_pssh, final_license_url, self.referer_url.get())
                self.drm_keys = keys
                self.root.after(0, lambda: self.add_progress_message(f"[+] Получено DRM ключей: {len(keys)}"))
                return

            self.root.after(0, lambda: self.add_progress_message(
                "[!] Не удалось найти PSSH и License URL в потоках (MPD/M3U8)."))

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
            self.quality_combo.set(quality_list[-1])  # Лучшее качество по умолчанию
            self.qualities_loaded = True

            self.qualities_status_label.configure(
                text=f"✓ Доступно качеств: {len(quality_list)}",
                text_color="#27AE60"
            )

            # ОБНОВЛЕНИЕ: Только одна кнопка
            self.download_button.configure(state="normal")

    def browse_file(self):
        """Открывает диалог сохранения файла с предложенным названием"""

        default_name = ""
        # НОВОЕ: Используем название видео, если оно есть
        if self.video_title.get():
            default_name = re.sub(r'[\\/:*?"<>|]', '_', self.video_title.get())

        # Используем os.path.split для разделения пути и имени.
        # Если название еще не установлено, os.getcwd() будет путем.
        initial_dir = os.path.dirname(self.output_file.get()) if self.output_file.get() else os.getcwd()
        initial_file = os.path.basename(self.output_file.get()) if self.output_file.get() else default_name + ".mp4"

        filename = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")],
            # НОВОЕ: Передаем предложенное имя файла
            initialfile=initial_file,
            initialdir=initial_dir
        )
        if filename:
            self.output_file.set(filename)

    # ОБНОВЛЕНИЕ: Новая функция для запуска единого процесса
    def start_unified_download(self):
        if self.download_in_progress:
            return

        if not self.output_file.get():
            messagebox.showerror("Ошибка", "Выберите путь для сохранения файла")
            return

        if not self.qualities_loaded:
            messagebox.showerror("Ошибка", "Сначала загрузите JSON файл")
            return

        # Показываем карточку прогресса
        self.progress_card.pack(fill="x", pady=(0, 20))

        self.download_in_progress = True
        self.download_button.configure(state="disabled")  # Только одна кнопка

        # Очищаем предыдущий прогресс
        self.progress_text.configure(state="normal")
        self.progress_text.delete("1.0", "end")
        self.progress_text.configure(state="disabled")

        download_thread = threading.Thread(target=self.download_video_with_fallback)  # Новая функция
        download_thread.daemon = True
        download_thread.start()

    # ОБНОВЛЕНИЕ: Функция с каскадной логикой
    def download_video_with_fallback(self):
        try:
            self.add_progress_message("[*] Запуск скачивания. Сначала пробуем Способ 2 (N_m3u8DL-RE)...")

            # Попытка Способа 2
            success = self._download_method_2()

            if not success:
                self.add_progress_message("[!] Способ 2 не сработал. Пробуем Способ 1 (kinescope)...")
                self._download_method_1()  # Fallback to Method 1

        except Exception as e:
            # Если оба метода не смогли завершить процесс (или произошла критическая ошибка)
            self.show_error(f"Критическая ошибка при загрузке видео: {str(e)}")
        finally:
            self.download_in_progress = False
            self.download_button.configure(state="normal")  # Только одна кнопка

    def _download_method_1(self):
        """Первый способ скачивания (стандартный)"""
        try:
            from kinescope import KinescopeVideo, KinescopeDownloader

            self.add_progress_message("[*] Подготовка к загрузке (Способ 1)...")

            bin_dir = setup_bin_directory()
            ffmpeg_path = os.path.join(bin_dir, "ffmpeg.exe")
            mp4decrypt_path = os.path.join(bin_dir, "mp4decrypt.exe")

            self.add_progress_message("[*] Получение информации о видео...")
            kinescope_video = KinescopeVideo(
                url=self.video_url.get(),
                referer_url=self.referer_url.get()
            )

            # Модифицируем загрузчик для отображения прогресса
            class ProgressDownloader(KinescopeDownloader):
                def __init__(self, *args, **kwargs):
                    self.gui = kwargs.pop('gui')
                    super().__init__(*args, **kwargs)

                def _fetch_segments(self, segments_urls, filepath, progress_bar_label):
                    segments_urls = [seg for i, seg in enumerate(segments_urls) if i == segments_urls.index(seg)]
                    with open(filepath, 'wb') as f:
                        total = len(segments_urls)
                        for i, segment_url in enumerate(segments_urls, 1):
                            self._fetch_segment(segment_url, f)
                            # Обновляем прогресс в GUI
                            self.gui.root.after(0, lambda: self.gui.add_progress_message(
                                f"{progress_bar_label}: {i}/{total} |{'█' * (i * 20 // total):20}| {i * 100 // total}%"
                            ))

            downloader = ProgressDownloader(
                kinescope_video,
                temp_dir='./temp',
                ffmpeg_path=ffmpeg_path,
                mp4decrypt_path=mp4decrypt_path,
                gui=self
            )

            # Получаем выбранное качество
            selected_quality_str = self.quality_combo.get()
            selected_height = int(selected_quality_str.replace('p', ''))
            video_resolutions = downloader.get_resolutions()

            chosen_resolution = None
            for res in video_resolutions:
                if res[1] == selected_height:
                    chosen_resolution = res
                    break

            if not chosen_resolution:
                chosen_resolution = video_resolutions[-1]

            self.add_progress_message(f"[*] Начинаем загрузку в качестве {selected_quality_str}...")

            # Загружаем видео
            downloader.download(self.output_file.get(), chosen_resolution)

            # Успешное завершение
            self.add_progress_message("[+] Видео успешно сохранено (Способ 1)!")
            messagebox.showinfo("Успех", f"Видео успешно скачано!\nФайл: {self.output_file.get()}")
            return True  # ОБНОВЛЕНИЕ: Возврат True

        except Exception as e:
            self.add_progress_message(f"[!] Ошибка в первом способе: {str(e)}")
            return False  # ОБНОВЛЕНИЕ: Возврат False
        finally:
            if 'downloader' in locals():
                # downloader.cleanup() - Оставляем как было, хотя явная очистка тут может быть полезной
                pass

    def _download_method_2(self):
        """Второй способ скачивания (через N_m3u8DL-RE)"""
        try:
            mpd_url, m3u8_url = self._extract_stream_urls()

            if not m3u8_url:
                raise Exception("Не удалось найти URL потока в JSON")

            selected_quality = self.quality_combo.get().replace('p', '')

            # Важно: если DRM ключи не получены, Способ 2, скорее всего, не сработает
            if not self.drm_keys:
                self.add_progress_message("[!] DRM ключи не получены. Способ 2 невозможен.")
                return False

            bin_dir = setup_bin_directory()
            n_m3u8dl_path = os.path.join(bin_dir, "N_m3u8DL-RE.exe")

            key_params = " ".join([f"--key {key}" for key in self.drm_keys])

            # Получаем путь и имя файла для сохранения
            output_path = self.output_file.get()
            save_dir = os.path.dirname(output_path)
            save_name = os.path.splitext(os.path.basename(output_path))[0]

            # Формируем команду с правильными параметрами
            command = f'"{n_m3u8dl_path}" "{m3u8_url}" {key_params} -M format=mp4 -sv res="{selected_quality}" -sa all --log-level INFO --no-log --save-dir "{save_dir}" --save-name "{save_name}"'

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
                return True  # ОБНОВЛЕНИЕ: Возврат True
            else:
                self.add_progress_message(f"[!] N_m3u8DL-RE завершился с ошибкой: {process.returncode}")
                return False  # ОБНОВЛЕНИЕ: Возврат False

        except Exception as e:
            self.add_progress_message(f"[!] Ошибка во втором способе: {str(e)}")
            return False  # ОБНОВЛЕНИЕ: Возврат False

    def _extract_pssh_from_hls(self, master_m3u8_url_full):
        """
        Извлекает Widevine License URL и PSSH-ключ из связанного M3U8-файла.
        Адаптировано из 'get pssh.py'.
        Возвращает: (license_url, pssh_key) или (None, None) в случае ошибки.
        """
        license_url = None
        pssh_key = None

        # --- ШАГ 1: Извлечение Widevine License URL из JSON (повторение логики) ---
        if self.json_data:
            try:
                # 1. Попытка Widevine
                license_url = self.json_data['options']['playlist'][0]['drm']['widevine']['licenseUrl']
            except (KeyError, IndexError):
                # 2. Попытка Clearkey (Clearkey ключи не ищем, только Widevine License URL)
                try:
                    license_url = self.json_data['options']['playlist'][0]['drm']['clearkey']['licenseUrl']
                except (KeyError, IndexError):
                    pass

        if not license_url:
            self.add_progress_message("[!] Ошибка: Не удалось найти widevine/clearkey licenseUrl в JSON.")
            return None, None

        # --- ШАГ 2: Извлечение PSSH-ключа из M3U8-файлов ---
        try:
            # Получаем чистый base_url (без параметров) для запроса master.m3u8
            base_url_match = re.search(r'^(https?://[^?]+?/master\.m3u8)', master_m3u8_url_full)
            if not base_url_match:
                self.add_progress_message("[!] Ошибка: Не удалось извлечь базовую URL для master.m3u8.")
                return license_url, None

            base_url_clean = base_url_match.group(1)
            base_url_prefix = base_url_clean.replace('/master.m3u8', '')

            # Восстанавливаем общие query-параметры
            query_params_match = re.search(r'\?(.*)', master_m3u8_url_full)
            token_params_list = []
            if query_params_match:
                for p in query_params_match.group(1).split('&'):
                    if p.startswith(('expires', 'sign', 'token', 'kinescope_project_id')) and (
                            len(p.split('=')) == 1 or p.split('=')[1]):
                        token_params_list.append(p)
            token_params = "&".join(token_params_list)

            # 1. Запрос master.m3u8
            master_response = requests.get(base_url_clean, timeout=10)
            master_response.raise_for_status()
            master_content = master_response.text

            # 2. Поиск всех ссылок на медиа-потоки (видео или аудио) с максимальным битрейтом
            stream_matches = re.findall(
                r'#EXT-X-STREAM-INF:.*?BANDWIDTH=(\d+).*?\n(media\.m3u8\?.*?)\n',
                master_content,
                re.DOTALL
            )

            # Добавляем поиск аудио потоков, как в 'get pssh.py', для более надежного извлечения PSSH
            audio_matches = re.findall(
                r'#EXT-X-MEDIA:TYPE=AUDIO.*?URI="([^"]+?media\.m3u8[^"]+?)"',
                master_content,
                re.DOTALL
            )

            media_streams = [(int(bandwidth), media_path) for bandwidth, media_path in stream_matches]
            # Аудио потокам даем высокий битрейт, чтобы их тоже проверило
            for audio_path in audio_matches:
                media_streams.append((999999999, audio_path))

            media_streams.sort(key=lambda x: x[0], reverse=True)

            if not media_streams:
                self.add_progress_message("[!] Ошибка: Не найдено потоков media.m3u8 в master.m3u8.")
                return license_url, None

            # 3. Перебор потоков и поиск PSSH
            for _, media_path_relative in media_streams:
                media_path_relative_clean = media_path_relative.split('?')[0]
                media_query_params_match = re.search(r'\?(.*)', media_path_relative)
                media_query_params = media_query_params_match.group(1) if media_query_params_match else ""

                # Формируем полную ссылку для запроса к media.m3u8
                m3u8_url_checked = f"{base_url_prefix}/{media_path_relative_clean}?{media_query_params}&{token_params}"
                m3u8_url_checked = m3u8_url_checked.replace('&&', '&').rstrip('&')
                # Удаляем пустой токен, если есть
                m3u8_url_checked = re.sub(r'&token=(&|$)', r'\1', m3u8_url_checked).rstrip('&')

                try:
                    # Запрос media.m3u8
                    media_response = requests.get(m3u8_url_checked, timeout=10)
                    media_response.raise_for_status()
                    media_content = media_response.text

                    # Поиск PSSH-ключа Widevine в формате base64
                    pssh_match = re.search(
                        r'#EXT-X-KEY.*?KEYFORMAT="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed".*?URI="data:text/plain;base64,([^"]+)"',
                        media_content,
                        re.DOTALL
                    )
                    # Дополнительный поиск для надежности
                    if not pssh_match:
                        pssh_match = re.search(
                            r'#EXT-X-KEY.*?URI="data:text/plain;base64,([^"]+)".*?KEYFORMAT="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"',
                            media_content,
                            re.DOTALL
                        )

                    if pssh_match:
                        pssh_key = pssh_match.group(1)
                        self.add_progress_message("[+] PSSH и License URL найдены в M3U8.")
                        return license_url, pssh_key  # Возвращаем найденные значения

                except requests.exceptions.RequestException:
                    continue  # Пробуем следующий поток

            self.add_progress_message("[!] PSSH-ключ не найден ни в одном потоке media.m3u8.")
            return license_url, None

        except requests.exceptions.RequestException as e:
            self.add_progress_message(f"[!] Ошибка запроса M3U8: {e}")
            return license_url, None
        except Exception as e:
            self.add_progress_message(f"[!] Произошла непредвиденная ошибка при поиске PSSH в HLS: {e}")
            return license_url, None

    def show_error(self, message):
        self.add_progress_message(f"[!] {message}")
        messagebox.showerror("Ошибка", message)
        self.download_in_progress = False
        # ОБНОВЛЕНИЕ: Только одна кнопка
        self.download_button.configure(state="normal")

    def clear_fields(self):
        self.video_url.set("")
        self.referer_url.set("")
        self.output_file.set("")
        self.selected_quality.set("")
        self.quality_combo.set("")
        self.quality_combo.configure(values=[])
        self.qualities_loaded = False
        self.current_json_file.set("")
        self.json_data = None
        self.available_qualities = []
        self.drm_keys = []
        self.json_status_label.configure(text="Файл не выбран", text_color="#7F8C8D")
        self.qualities_status_label.configure(text="Загрузите JSON файл", text_color="#7F8C8D")
        # ОБНОВЛЕНИЕ: Только одна кнопка
        self.download_button.configure(state="disabled")
        self.progress_card.pack_forget()


def main():
    root = ctk.CTk()

    # Установка иконки приложения
    try:
        icon_path = get_resource_path("icon.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
        else:
            icon_path_png = get_resource_path("icon.png")
            if os.path.exists(icon_path_png):
                icon_image = tk.PhotoImage(file=icon_path_png)
                root.iconphoto(True, icon_image)
    except Exception as e:
        print(f"Не удалось установить иконку: {e}")

    app = KinescopeDownloaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
