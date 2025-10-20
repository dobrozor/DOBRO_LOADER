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
    """Извлекает URL и Referer из JSON файла"""
    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        video_url = data.get('url', '')
        referer = data.get('referrer', '')
        video_id = data.get('meta', {}).get('videoId', '')

        return video_url, referer, video_id, data

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

        # Кнопки загрузки
        download_buttons_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        download_buttons_frame.pack(fill="x", pady=(0, 10))

        self.download_button_1 = ctk.CTkButton(download_buttons_frame,
                                               text="Скачать (1 способ)",
                                               text_color="#2C3E50",
                                               command=lambda: self.start_download(1),
                                               state="disabled",
                                               height=45,
                                               font=ctk.CTkFont(size=14),
                                               fg_color="#3498DB",
                                               hover_color="#2980B9")
        self.download_button_1.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.download_button_2 = ctk.CTkButton(download_buttons_frame,
                                               text="Скачать (2 способ)",
                                               text_color="#2C3E50",
                                               command=lambda: self.start_download(2),
                                               state="disabled",
                                               height=45,
                                               font=ctk.CTkFont(size=14),
                                               fg_color="#27AE60",
                                               hover_color="#229954")
        self.download_button_2.pack(side="right", fill="x", expand=True, padx=(5, 0))

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
            video_url, referer, video_id, json_data = extract_from_json(filename)
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

            file_name = os.path.basename(filename)
            self.json_status_label.configure(text=f"✓ {file_name}", text_color="#27AE60")
            self.qualities_status_label.configure(text="Получаем список качеств и ключи...", text_color="#3498DB")

            self.fetch_qualities_and_keys()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при загрузке JSON файла:\n{str(e)}")

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
        try:
            mpd_url, m3u8_url = self._extract_stream_urls()

            if mpd_url:
                mpd_content = requests.get(mpd_url).text
                pssh = re.findall(r'<cenc:pssh[^>]*>([^<]+)</cenc:pssh>', mpd_content)
                license_url = re.findall(r'<dashif:Laurl>([^<]+)</dashif:Laurl>', mpd_content)

                if pssh and license_url:
                    keys = self.get_key(list(set(pssh))[0], list(set(license_url))[0], self.referer_url.get())
                    self.drm_keys = keys
                    self.root.after(0, lambda: self.add_progress_message(f"[+] Получено DRM ключей: {len(keys)}"))
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

            self.download_button_1.configure(state="normal")
            self.download_button_2.configure(state="normal")

    def browse_file(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
        )
        if filename:
            self.output_file.set(filename)

    def start_download(self, method):
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
        self.download_button_1.configure(state="disabled")
        self.download_button_2.configure(state="disabled")

        # Очищаем предыдущий прогресс
        self.progress_text.configure(state="normal")
        self.progress_text.delete("1.0", "end")
        self.progress_text.configure(state="disabled")

        download_thread = threading.Thread(target=self.download_video, args=(method,))
        download_thread.daemon = True
        download_thread.start()

    def download_video(self, method):
        try:
            if method == 1:
                self.add_progress_message("[*] Запуск скачивания (1 способ)...")
                success = self._download_method_1()
                if not success:
                    self.add_progress_message("[!] Первый способ не сработал, пробуем второй...")
                    self._download_method_2()
            else:
                self.add_progress_message("[*] Запуск скачивания (2 способ)...")
                self._download_method_2()

        except Exception as e:
            self.show_error(f"Ошибка при загрузке видео: {str(e)}")
        finally:
            self.download_in_progress = False
            self.download_button_1.configure(state="normal")
            self.download_button_2.configure(state="normal")

    def _download_method_1(self):
        """Первый способ скачивания (стандартный)"""
        try:
            from kinescope import KinescopeVideo, KinescopeDownloader

            self.add_progress_message("[*] Подготовка к загрузке (1 способ)...")

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
            self.add_progress_message("[+] Видео успешно сохранено!")
            messagebox.showinfo("Успех", f"Видео успешно скачано!\nФайл: {self.output_file.get()}")
            return True

        except Exception as e:
            self.add_progress_message(f"[!] Ошибка в первом способе: {str(e)}")
            return False
        finally:
            if 'downloader' in locals():
                downloader.cleanup()

    def _download_method_2(self):
        """Второй способ скачивания (через N_m3u8DL-RE)"""
        try:
            mpd_url, m3u8_url = self._extract_stream_urls()

            if not m3u8_url:
                raise Exception("Не удалось найти URL потока в JSON")

            selected_quality = self.quality_combo.get().replace('p', '')

            if not self.drm_keys:
                raise Exception("DRM ключи не получены")

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
                self.add_progress_message("\n[+] Скачивание завершено!")
                messagebox.showinfo("Успех", f"Видео успешно скачано!\nФайл: {output_path}")
            else:
                raise Exception(f"N_m3u8DL-RE завершился с ошибкой: {process.returncode}")

        except Exception as e:
            raise Exception(f"Ошибка во втором способе: {str(e)}")

    def show_error(self, message):
        self.add_progress_message(f"[!] {message}")
        messagebox.showerror("Ошибка", message)
        self.download_in_progress = False
        self.download_button_1.configure(state="normal")
        self.download_button_2.configure(state="normal")

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
        self.download_button_1.configure(state="disabled")
        self.download_button_2.configure(state="disabled")
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