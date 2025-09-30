import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading
import sys
import os
import shutil
import json
from urllib.parse import urlparse
from kinescope import KinescopeVideo, KinescopeDownloader

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

        return video_url, referer, video_id

    except Exception as e:
        raise ValueError(f"Ошибка чтения JSON файла: {str(e)}")


class CustomProgressBar:
    """Кастомный прогресс бар в стиле консоли"""

    def __init__(self, parent, label):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="x", pady=2)

        self.label = ctk.CTkLabel(self.frame, text=label, width=60, anchor="w")
        self.label.pack(side="left", padx=(0, 10))

        self.progress_bar = ctk.CTkProgressBar(self.frame, height=12, progress_color="#FF6B35")
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_bar.set(0)

        self.percentage_label = ctk.CTkLabel(self.frame, text="0%", width=40)
        self.percentage_label.pack(side="right", padx=(10, 0))

        self.count_label = ctk.CTkLabel(self.frame, text="[0/0]", width=50)
        self.count_label.pack(side="right")

    def update(self, current, total):
        """Обновляет прогресс бар"""
        progress = current / total if total > 0 else 0
        self.progress_bar.set(progress)
        self.percentage_label.configure(text=f"{int(progress * 100)}%")
        self.count_label.configure(text=f"[{current}/{total}]")


class KinescopeDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DOBRO LOADER")
        self.root.geometry("500x800")
        self.root.resizable(True, True)

        # Установка иконки приложения
        try:
            icon_path = get_resource_path("icon.svg")
            if os.path.exists(icon_path):
                # Для SVG файлов в tkinter нужно использовать специальные библиотеки,
                # но для простоты можно использовать ICO файл или PNG
                # Если у вас есть icon.ico или icon.png, используйте их вместо SVG
                pass
        except Exception as e:
            print(f"Не удалось загрузить иконку: {e}")

        # Цветовая схема
        self.accent_color = "#fb9422"  # Оранжевый акцент
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

        # Прогресс бары
        self.video_progress = None
        self.audio_progress = None

        self.setup_ui()

    def setup_ui(self):
        # Главный контейнер
        main_container = ctk.CTkFrame(self.root, fg_color=self.light_bg)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Заголовок с логотипом
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))


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
                # Fallback на текстовый заголовок
                title_label = ctk.CTkLabel(header_frame,
                                           text="DOBRO LOADER",
                                           font=ctk.CTkFont(size=24, weight="bold"),
                                           text_color="#2C3E50")
                title_label.pack(pady=(0, 10))
        except Exception as e:
            print(f"Не удалось загрузить логотип: {e}")
            # Fallback на текстовый заголовок
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

        # Кнопки управления
        button_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        button_frame.pack(fill="x")

        self.download_button = ctk.CTkButton(button_frame,
                                             text="Начать скачивание",
                                             text_color="#2C3E50",
                                             command=self.start_download,
                                             state="disabled",
                                             height=45,
                                             font=ctk.CTkFont(size=14),
                                             fg_color=self.accent_color,
                                             hover_color="#f48200")
        self.download_button.pack(side="left", fill="x", expand=True, padx=(0, 10))

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
            video_url, referer, video_id = extract_from_json(filename)

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
            self.qualities_status_label.configure(text="Получаем список качеств...", text_color="#3498DB")

            self.fetch_qualities_auto()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при загрузке JSON файла:\n{str(e)}")

    def fetch_qualities_auto(self):
        """Автоматически получает список качеств после загрузки JSON"""
        fetch_thread = threading.Thread(target=self._fetch_qualities_thread)
        fetch_thread.daemon = True
        fetch_thread.start()

    def browse_file(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
        )
        if filename:
            self.output_file.set(filename)

    def _fetch_qualities_thread(self):
        """Поток для получения качеств"""
        try:
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

            if not video_resolutions:
                self.root.after(0, lambda: self.qualities_status_label.configure(
                    text="Не удалось получить качества видео",
                    text_color="#E74C3C"
                ))
                return

            self.root.after(0, lambda: self._update_qualities_ui(video_resolutions))

            downloader.cleanup()

        except Exception as e:
            error_msg = f"Ошибка при получении качеств: {str(e)}"
            self.root.after(0, lambda: self.qualities_status_label.configure(
                text=error_msg,
                text_color="#E74C3C"
            ))

    def _update_qualities_ui(self, resolutions):
        """Обновляет интерфейс с полученными качествами"""
        quality_list = [f"{res[1]}p" for res in resolutions]
        self.quality_combo.configure(values=quality_list)

        if quality_list:
            self.quality_combo.set(quality_list[-1])  # Ставим лучшее качество по умолчанию
            self.qualities_loaded = True

            self.qualities_status_label.configure(
                text=f"✓ Доступно качеств: {len(quality_list)}",
                text_color="#27AE60"
            )

            self.download_button.configure(state="normal")
        else:
            self.qualities_status_label.configure(
                text="Качества не найдены",
                text_color="#E74C3C"
            )

    def start_download(self):
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
        self.download_button.configure(state="disabled")

        # Очищаем предыдущий прогресс
        self.progress_text.configure(state="normal")
        self.progress_text.delete("1.0", "end")
        self.progress_text.configure(state="disabled")

        download_thread = threading.Thread(target=self.download_video)
        download_thread.daemon = True
        download_thread.start()

    def download_video(self):
        try:
            self.add_progress_message("[*] Подготовка к загрузке...")

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

            video_resolutions = downloader.get_resolutions()

            if not video_resolutions:
                self.show_error("Не удалось получить доступные разрешения видео.")
                return

            # Получаем выбранное качество
            selected_quality_str = self.quality_combo.get()
            selected_height = int(selected_quality_str.replace('p', ''))
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

        except Exception as e:
            self.show_error(f"Ошибка при загрузке видео: {str(e)}")
        finally:
            if 'downloader' in locals():
                downloader.cleanup()
            self.download_in_progress = False
            self.download_button.configure(state="normal")

    def show_error(self, message):
        self.add_progress_message(f"[!] {message}")
        messagebox.showerror("Ошибка", message)
        self.download_in_progress = False
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
        self.json_status_label.configure(text="Файл не выбран", text_color="#7F8C8D")
        self.qualities_status_label.configure(text="Загрузите JSON файл", text_color="#7F8C8D")
        self.download_button.configure(state="disabled")
        self.progress_card.pack_forget()


def main():
    root = ctk.CTk()

    # Установка иконки приложения (для Windows)
    try:
        icon_path = get_resource_path("icon.ico")  # Лучше использовать ICO для Windows
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
        else:
            # Попробуем PNG через PhotoImage (для простоты)
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