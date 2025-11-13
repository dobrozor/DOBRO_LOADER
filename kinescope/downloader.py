import sys
from io import BytesIO
from os import PathLike
from typing import Union, Callable
from pathlib import Path
from requests import Session
from subprocess import Popen, PIPE
from shutil import copyfileobj
from base64 import b64decode, b64encode
from requests.exceptions import ChunkedEncodingError, HTTPError

from tqdm import tqdm
from mpegdash.parser import MPEGDASHParser, MPEGDASH

from kinescope.kinescope import KinescopeVideo
from kinescope.const import KINESCOPE_BASE_URL
from kinescope.exceptions import *

class VideoDownloader:
    def __init__(self, kinescope_video: KinescopeVideo,
                 temp_dir: Union[str, PathLike] = './temp',
                 ffmpeg_path: Union[str, PathLike] = './ffmpeg',
                 mp4decrypt_path: Union[str, PathLike] = './mp4decrypt',
                 token: str = None,
                 cookies: str = None,
                 progress_callback: Callable[[float], None] = None):
        self.kinescope_video: KinescopeVideo = kinescope_video
        self.token = token
        self.cookies = cookies
        self.progress_callback = progress_callback

        self.temp_path: Path = Path(temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            meipass_path = Path(sys._MEIPASS).resolve()
            self.ffmpeg_path = meipass_path / 'ffmpeg.exe'  # Явно указываем .exe
            self.mp4decrypt_path = meipass_path / 'mp4decrypt.exe'  # Явно указываем .exe
        else:
            self.ffmpeg_path = Path(ffmpeg_path).resolve()
            self.mp4decrypt_path = Path(mp4decrypt_path).resolve()

        self.http = Session()
        self.http.headers.update({
            'Referer': self.kinescope_video.referer_url or KINESCOPE_BASE_URL,
            'Origin': self.kinescope_video.referer_url or KINESCOPE_BASE_URL,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        if self.token:
            self.http.headers.update({'Authorization': f'Bearer {self.token}'})
        if self.cookies:
            for cookie in self.cookies.split(';'):
                if '=' in cookie:
                    name, value = cookie.strip().split('=', 1)
                    self.http.cookies.set(name, value)
            print('[*] Applied cookies:', self.http.cookies.get_dict())

        self.mpd_master: MPEGDASH = self._fetch_mpd_master()

    def cleanup_temp(self):
        """Очищает папку temp после успешной загрузки."""
        try:
            import shutil
            shutil.rmtree(self.temp_path, ignore_errors=True)
            print(f"[*] Очищена папка temp: {self.temp_path}")
        except Exception as e:
            print(f"[*] Ошибка очистки папки temp: {e}")

    def _merge_tracks(self, source_video_filepath: str | PathLike,
                      source_audio_filepath: str | PathLike,
                      target_filepath: str | PathLike):
        target_filepath = Path(target_filepath)
        try:
            print(f"[*] Запуск ffmpeg: {self.ffmpeg_path}")
            process = Popen(
                [self.ffmpeg_path, "-i", str(source_video_filepath), "-i", str(source_audio_filepath),
                 "-c", "copy", str(target_filepath), "-y", "-loglevel", "error"],
                stdout=PIPE, stderr=PIPE, text=True, creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise Exception(f"Ошибка ffmpeg: {stderr}")
            if not target_filepath.exists():
                raise Exception(f"Файл {target_filepath} не создан после слияния")
            print(f"[*] Успешно объединены треки в {target_filepath}")
        except FileNotFoundError:
            raise FFmpegNotFoundError(f"ffmpeg не найден по пути {self.ffmpeg_path}")
        except Exception as e:
            raise Exception(f"Ошибка слияния треков: {e}")

    def _decrypt_video(self, source_filepath: str | PathLike,
                       target_filepath: str | PathLike,
                       key: str):
        try:
            print(f"[*] Запуск mp4decrypt: {self.mp4decrypt_path}")
            process = Popen(
                [self.mp4decrypt_path, "--key", f"1:{key}", str(source_filepath), str(target_filepath)],
                stdout=PIPE, stderr=PIPE, text=True, creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise Exception(f"Ошибка mp4decrypt: {stderr}")
            print(f"[*] Успешно расшифровано видео в {target_filepath}")
        except FileNotFoundError:
            raise Mp4DecryptNotFoundError(f"mp4decrypt не найден по пути {self.mp4decrypt_path}")

    def _get_license_key(self):
        if not self.mpd_master.periods[0].adaptation_sets[0].content_protections:
            print("[*] Шифрование не обнаружено, пропускаем получение ключа")
            return None
        
        try:
            kid = self.mpd_master.periods[0].adaptation_sets[0].content_protections[0].cenc_default_kid
            if not kid:
                print("[*] KID не найден в MPD, предполагается отсутствие шифрования")
                return None
            
            license_url = self.kinescope_video.get_clearkey_license_url()
            print("[*] URL лицензии:", license_url)
            
            if '?token=' in license_url and license_url.endswith('?token='):
                if self.token:
                    license_url = f"{license_url}{self.token}"
                    print("[*] Добавлен токен к URL лицензии:", license_url)
                else:
                    print("[*] Предупреждение: URL лицензии содержит пустой токен, возможна ошибка 403")
            
            kid_clean = kid.replace('-', '')
            kid_b64 = b64encode(bytes.fromhex(kid_clean)).decode().replace('=', '')
            
            request_body = {
                'kids': [kid_b64],
                'type': 'temporary'
            }
            print("[*] Тело запроса лицензии:", request_body)
            print("[*] Заголовки запроса:", self.http.headers)
            
            response = self.http.post(
                url=license_url,
                headers={
                    'Origin': self.kinescope_video.referer_url or KINESCOPE_BASE_URL,
                    'Referer': self.kinescope_video.referer_url or KINESCOPE_BASE_URL
                },
                json=request_body
            )
            response.raise_for_status()
            
            response_json = response.json()
            print("[*] Ответ API лицензии:", response_json)
            
            keys = response_json.get('keys', None)
            if not keys:
                print("[*] Поле 'keys' отсутствует в ответе, проверяем тип шифрования")
                raise UnsupportedEncryption(
                    "Ключи шифрования не найдены. Видео может использовать другой DRM или не зашифровано."
                )
            
            key = keys[0].get('k', None)
            if not key:
                raise UnsupportedEncryption(
                    "Поле 'k' отсутствует в ключах. Видео может использовать другой DRM."
                )
            
            decoded_key = b64decode(key + '==').hex()
            print("[*] Ключ лицензии успешно получен")
            return decoded_key
            
        except HTTPError as e:
            print(f"[*] Ошибка HTTP в _get_license_key: {str(e)}")
            raise UnsupportedEncryption(
                f"Не удалось получить ClearKey из-за HTTP ошибки: {str(e)}. "
                "Проверьте токен, реферер, куки или права доступа."
            )
        except Exception as e:
            print(f"[*] Ошибка в _get_license_key: {str(e)}")
            raise UnsupportedEncryption(
                "Не удалось получить ClearKey или обнаружен неподдерживаемый тип шифрования. "
                "Поддерживается только ClearKey."
            )

    def _fetch_segment(self, segment_url: str, file):
        if not segment_url:
            raise SegmentDownloadError("Пустой URL сегмента")
        if not segment_url.startswith('http'):
            base_url = self.mpd_master.periods[0].adaptation_sets[0].representations[0].base_urls[0].base_url_value
            segment_url = base_url + segment_url
        print(f"[*] Загрузка сегмента: {segment_url}")
        for _ in range(5):
            try:
                response = self.http.get(segment_url, stream=True)
                response.raise_for_status()
                content = response.content
                if content is None:
                    raise SegmentDownloadError(f"Пустой ответ от {segment_url}")
                copyfileobj(BytesIO(content), file)
                return
            except (ChunkedEncodingError, HTTPError) as e:
                print(f"[*] Ошибка загрузки сегмента {segment_url}: {e}")
                continue
        raise SegmentDownloadError(f"Не удалось скачать сегмент {segment_url} после 5 попыток")

    def _fetch_segments(self, segments_urls: list[str], filepath: str | PathLike, progress_bar_label: str = ''):
        segments_urls = [seg for i, seg in enumerate(segments_urls) if i == segments_urls.index(seg)]
        total_segments = len(segments_urls)
        if total_segments == 0:
            raise SegmentDownloadError(f"Список сегментов пуст для {progress_bar_label}")
        print(f"[*] Загрузка {progress_bar_label}: {total_segments} сегментов")
        with open(filepath, 'wb') as f:
            for i, segment_url in enumerate(segments_urls):
                self._fetch_segment(segment_url, f)
                if self.progress_callback:
                    progress = ((i + 1) / total_segments) * 50.0
                    total_progress = progress if progress_bar_label == 'Video' else 50.0 + progress
                    self.progress_callback(total_progress)
                print(f"[*] {progress_bar_label}: {i + 1}/{total_segments}")

    def _get_segments_urls(self, resolution: tuple[int, int]) -> dict[str:list[str]]:
        try:
            result = {}
            for adaptation_set in self.mpd_master.periods[0].adaptation_sets:
                # Для видео
                if adaptation_set.content_type == 'video' or adaptation_set.mime_type == 'video/mp4':
                    resolutions = [(r.width, r.height) for r in adaptation_set.representations]
                    idx = resolutions.index(resolution) if adaptation_set.representations[0].height else 0
                    representation = adaptation_set.representations[idx]
                    base_url = representation.base_urls[0].base_url_value
                    result['video/mp4'] = [
                        base_url + (segment_url.media or '')
                        for segment_url in representation.segment_lists[0].segment_urls]
                # Для аудио
                elif adaptation_set.content_type == 'audio' or adaptation_set.mime_type == 'audio/mp4':
                    representation = adaptation_set.representations[0]  # Берем первое аудио представление
                    base_url = representation.base_urls[0].base_url_value
                    result['audio/mp4'] = [
                        base_url + (segment_url.media or '')
                        for segment_url in representation.segment_lists[0].segment_urls]
            return result
        except ValueError:
            raise InvalidResolution('Указано неверное разрешение')
        except Exception as e:
            print(f"[*] Предупреждение при получении сегментов: {e}")
            # Возвращаем хотя бы видео, если есть
            if 'video/mp4' in result:
                return result
            raise

    def _fetch_mpd_master(self) -> MPEGDASH:
        return MPEGDASHParser.parse(self.http.get(
            url=self.kinescope_video.get_mpd_master_playlist_url(),
            headers={'Referer': self.kinescope_video.referer_url or KINESCOPE_BASE_URL}
        ).text)

    def get_resolutions(self) -> list[tuple[int, int]]:
        for adaptation_set in self.mpd_master.periods[0].adaptation_sets:
            if adaptation_set.representations[0].height:
                return [(r.width, r.height) for r in sorted(adaptation_set.representations, key=lambda r: r.height)]

    def download(self, filepath: str, resolution: tuple[int, int] = None):
        if not resolution:
            resolution = self.get_resolutions()[-1]

        key = self._get_license_key()

        # Получаем URL сегментов для проверки наличия аудио
        segments_urls = self._get_segments_urls(resolution)
        has_audio = 'audio/mp4' in segments_urls

        video_path = self.temp_path / f'{self.kinescope_video.video_id}_video.mp4'

        # Скачиваем видео
        self._fetch_segments(
            segments_urls['video/mp4'],
            video_path if not key else video_path.with_suffix('.mp4.enc'),
            'Video'
        )

        # Скачиваем аудио только если оно есть
        audio_path = None
        if has_audio:
            audio_path = self.temp_path / f'{self.kinescope_video.video_id}_audio.mp4'
            self._fetch_segments(
                segments_urls['audio/mp4'],
                audio_path if not key else audio_path.with_suffix('.mp4.enc'),
                'Audio'
            )

        if key:
            print("[*] Расшифровка...", end=' ')
            self._decrypt_video(
                video_path.with_suffix('.mp4.enc'),
                video_path,
                key
            )
            if has_audio:
                self._decrypt_video(
                    audio_path.with_suffix('.mp4.enc'),
                    audio_path,
                    key
                )
            print('Готово')

        filepath = Path(filepath).with_suffix('.mp4')
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if has_audio:
            print("[*] Объединение треков...", end=' ')
            self._merge_tracks(
                video_path,
                audio_path,
                filepath
            )
            print('Готово')
        else:
            # Если аудио нет, просто копируем видео файл
            print("[*] Копирование видео файла...", end=' ')
            import shutil
            shutil.copy2(video_path, filepath)
            print('Готово')

        self.cleanup_temp()