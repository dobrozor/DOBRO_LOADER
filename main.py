import re
import webview
import uuid
import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from downloader_logic import KinescopeLogic


class Api:
    def __init__(self):
        self.logic = None
        self.tasks = {}  # Храним инфо о задачах: {id: {info, progress_states}}
        # Процессор очереди скачиваний (максимум 3 одновременно)
        self.executor = ThreadPoolExecutor(max_workers=3)

    def _get_window(self):
        return webview.windows[0] if webview.windows else None

    def send_log(self, task_id, message):
        window = self._get_window()
        if not window: return

        # Лог в интерфейс
        safe_msg = message.replace("'", "\\'").replace("\n", "").replace("\r", "")
        window.evaluate_js(f"addTaskLog('{task_id}', '{safe_msg}')")

        # Прогресс
        progress_match = re.search(r'(\d+\.?\d*)%', message)
        if progress_match:
            percent = float(progress_match.group(1))
            task = self.tasks.get(task_id)
            if task:
                if "Vid" in message:
                    task['progress']['video'] = percent
                elif "Aud" in message:
                    task['progress']['audio'] = percent

                avg = (task['progress'].get('video', 0) + task['progress'].get('audio', 0)) / 2
                window.evaluate_js(f"updateTaskProgress('{task_id}', {avg}, 'Загрузка...')")

        if "Merging" in message or "Muxing" in message:
            window.evaluate_js(f"updateTaskProgress('{task_id}', 100, 'Склейка...')")

    def select_folder(self):
        window = self._get_window()
        result = window.create_file_dialog(
            webview.FOLDER_DIALOG
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def select_json(self):
        window = self._get_window()
        results = window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=('JSON (*.json)',),
            allow_multiple=True
        )

        if not results: return None

        new_tasks = []
        for path in results:
            try:
                if not self.logic: self.logic = KinescopeLogic(lambda x: None)

                # Теперь extract_from_json возвращает СПИСОК
                video_list = self.logic.extract_from_json(path)

                for video_info in video_list:
                    task_id = str(uuid.uuid4())[:8]

                    # Получаем качества для конкретного видео
                    qualities = []
                    item = video_info['video_data']
                    if 'frameRate' in item:
                        qualities = sorted([int(q) for q in item['frameRate'].keys() if q.isdigit()], reverse=True)

                    self.tasks[task_id] = {
                        'info': video_info,
                        'progress': {'video': 0, 'audio': 0},
                        'path': path
                    }

                    new_tasks.append({
                        "id": task_id,
                        "filename": video_info['title'],
                        "qualities": qualities or [1080, 720, 480, 360]
                    })
            except Exception as e:
                print(f"Ошибка при чтении {path}: {e}")
                continue

        return new_tasks

    def delete_task(self, task_id):
        if task_id in self.tasks:
            del self.tasks[task_id]
            # Можно добавить принудительную очистку логов, если нужно
            return True
        return False

    def start_download(self, task_id, quality, custom_folder=None):
        task = self.tasks.get(task_id)
        if not task: return

        def run():
            try:
                # Создаем экземпляр логики специально для этой задачи, чтобы лог шел правильно
                task_logic = KinescopeLogic(lambda msg: self.send_log(task_id, msg))

                base_dir = custom_folder if custom_folder else os.path.dirname(task['path'])

                save_path = os.path.join(
                    base_dir,
                    re.sub(r'[\s\\/:*?"<>|]', '_', task['info']['title'].strip()) + f"_{quality}p.mp4"
                )

                if os.path.exists(save_path):
                    self.send_log(task_id, f"✅ Файл уже существует: {save_path}. Пропуск.")
                    self._get_window().evaluate_js(f"updateTaskProgress('{task_id}', 100, 'Уже скачано')")
                    return

                self.send_log(task_id, f"🚀 Очередь дошла, старт: {quality}p в {base_dir}")
                
                try:
                    success = task_logic.download_pipeline(task['info'], quality, save_path)
                except Exception as e:
                    self.send_log(task_id, f"❌ Системная ошибка скачивания: {str(e)}\n{traceback.format_exc()}")
                    success = False

                if success:
                    self.send_log(task_id, "✅ ГОТОВО")
                    self._get_window().evaluate_js(f"updateTaskProgress('{task_id}', 100, 'Завершено')")
                else:
                    self.send_log(task_id, "❌ ОШИБКА")
                    self._get_window().evaluate_js(f"updateTaskProgress('{task_id}', 0, 'Ошибка')")
                    
            except Exception as e:
                self.send_log(task_id, f"❌ КРИТИЧЕСКАЯ ОШИБКА ПОТОКА: {str(e)}\n{traceback.format_exc()}")
                self._get_window().evaluate_js(f"updateTaskProgress('{task_id}', 0, 'Критическая ошибка')")

        self.send_log(task_id, "⏳ Ожидание в очереди...")
        self._get_window().evaluate_js(f"updateTaskProgress('{task_id}', 0, 'В очереди...')")
        self.executor.submit(run)


def main():
    api = Api()
    webview.create_window(
        'DOBRO LOADER PRO', 'index.html', js_api=api,
        width=900, height=500, resizable=True
    )
    webview.start()


if __name__ == '__main__':
    main()