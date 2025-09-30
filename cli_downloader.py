import os
import sys
import shutil
from urllib.parse import urlparse
from kinescope import KinescopeVideo, KinescopeDownloader


def get_resource_path(relative_path):
    """Получает путь к ресурсам относительно исполняемого файла"""
    try:
        base_path = sys._MEIPASS  # Для PyInstaller
    except Exception:
        base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base_path, relative_path)


def setup_bin_directory():
    """Создаёт папку bin и копирует туда необходимые exe-файлы"""
    bin_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "bin")
    os.makedirs(bin_dir, exist_ok=True)

    # Копируем ffmpeg
    ffmpeg_src = get_resource_path("ffmpeg/bin/ffmpeg.exe")
    ffmpeg_dst = os.path.join(bin_dir, "ffmpeg.exe")
    if not os.path.exists(ffmpeg_dst) and os.path.exists(ffmpeg_src):
        shutil.copy2(ffmpeg_src, ffmpeg_dst)

    # Копируем mp4decrypt
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


def download_video():
    """Основная функция для скачивания видео в интерактивном режиме"""
    print("\n██████╗░░█████╗░██████╗░██████╗░░█████╗░    ██╗░░░░░░█████╗░░█████╗░██████╗░███████╗██████╗░"
          "\n██╔══██╗██╔══██╗██╔══██╗██╔══██╗██╔══██╗    ██║░░░░░██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗"
          "\n██║░░██║██║░░██║██████╦╝██████╔╝██║░░██║    ██║░░░░░██║░░██║███████║██║░░██║█████╗░░██████╔╝"
          "\n██║░░██║██║░░██║██╔══██╗██╔══██╗██║░░██║    ██║░░░░░██║░░██║██╔══██║██║░░██║██╔══╝░░██╔══██╗"
          "\n██████╔╝╚█████╔╝██████╦╝██║░░██║╚█████╔╝    ███████╗╚█████╔╝██║░░██║██████╔╝███████╗██║░░██║"
          "\n╚═════╝░░╚════╝░╚═════╝░╚═╝░░╚═╝░╚════╝░    ╚══════╝░╚════╝░╚═╝░░╚═╝╚═════╝░╚══════╝╚═╝░░╚═╝\n")

    # Получаем URL видео
    while True:
        video_url = input("\nВведите URL видео: ").strip()
        if validate_url(video_url):
            break
        print("Ошибка: введите корректный URL (например: https://kinescope.io/video/123)")

    # Получаем Referer URL
    referer = input("Введите Referer URL [по умолчанию https://kinescope.io/]: ").strip()
    referer = referer if referer else "https://kinescope.io/"

    # Получаем имя выходного файла
    while True:
        output_file = input("Введите имя выходного файла [например video.mp4]: ").strip()
        if output_file:
            if not output_file.lower().endswith('.mp4'):
                output_file += '.mp4'
            break
        print("Ошибка: имя файла не может быть пустым")

    # Выбор качества
    while True:
        best_quality = input("Автоматически выбрать лучшее качество? (y/n): ").strip().lower()
        if best_quality in ['y', 'n', 'д', 'н']:
            break
        print("Пожалуйста, введите 'y' или 'n'")

    # Настраиваем bin-директорию
    bin_dir = setup_bin_directory()
    ffmpeg_path = os.path.join(bin_dir, "ffmpeg.exe")
    mp4decrypt_path = os.path.join(bin_dir, "mp4decrypt.exe")

    # Создаем объект видео
    kinescope_video = KinescopeVideo(
        url=video_url,
        referer_url=referer
    )

    # Инициализируем загрузчик
    downloader = KinescopeDownloader(
        kinescope_video,
        temp_dir='./temp',
        ffmpeg_path=ffmpeg_path,
        mp4decrypt_path=mp4decrypt_path
    )

    # Получаем доступные разрешения
    print('= ВЫБЕРИТЕ КАЧЕСТВО ====================')
    video_resolutions = downloader.get_resolutions()

    if not video_resolutions:
        print("Ошибка: не удалось получить доступные разрешения видео.")
        sys.exit(1)

    # Выбираем качество
    if best_quality in ['y', 'д']:
        chosen_resolution = video_resolutions[-1]
        print(f'[+] Автоматически выбрано лучшее качество: {chosen_resolution[1]}p')
    else:
        print("Доступные варианты качества:")
        for i, res in enumerate(video_resolutions):
            print(f"{i + 1}) {res[1]}p")

        while True:
            try:
                choice = int(input("Введите номер качества: ")) - 1
                if 0 <= choice < len(video_resolutions):
                    chosen_resolution = video_resolutions[choice]
                    break
                print(f"Ошибка: введите число от 1 до {len(video_resolutions)}")
            except ValueError:
                print("Ошибка: введите число")

        # Загружаем видео
        print('= НАЧИНАЕМ ЗАГРУЗКУ ===============')
        try:
            downloader.download(output_file, chosen_resolution)
            print(f"\n[+] Видео успешно сохранено как: {output_file}")
        except Exception as e:
            print(f"\n[!] Ошибка при загрузке видео: {e}")
            sys.exit(1)
        finally:
            # Добавляем очистку
            if 'downloader' in locals():
                downloader.cleanup()




if __name__ == "__main__":
    main()