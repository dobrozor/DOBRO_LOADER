Присоединяйтесь к нашему [чату сообщества](https://t.me/KinescopeDL) в Telegram, чтобы обсудить возникшие проблемы или если вам нужна помощь.

## ⬇️ Установка
Просто скачайте релиз и запустите его, все остальные файлы подтянуться сами



## 🔨 Сборка на основе исходных текстов
### Требования
Требуются [FFmpeg](https://ffmpeg.org/download.html) и [mp4decrypt](https://www.bento4.com/downloads/).

### Сборка
1. Загрузите и установите последнюю версию [Python 3](https://www.python.org/downloads/)
2. Убедитесь, что у вас установлен pip:
    ``оболочка
    python -m ensurepip -обновление
    ```
3. Клонируем проект с помощью [git](https://git-scm.com/downloads):
    ``оболочки
    git clone https://github.com/anijackich/kinescope-dl.git
    ```
    или напрямую скачайте и распакуйте [исходный код](https://github.com/anijackich/kinescope-dl/archive/refs/heads/master.zip).
4. Откройте консоль в каталоге проекта
5. Установите и используйте virtualenv (необязательно):
    оболочка ``
    pip install virtualenv
    python3 -m venv venv
    ```
    В Windows запустите:
    ``shell
    .\venv\Scripts\activate.bat
    ```
    В Unix или macOS запустите:
    ``
исходный код оболочки venv/bin/activate
    ```
6. Требования к установке:
    ``оболочка
    установка pip -r requirements.txt
    ```
7. Установите PyInstaller:
    ``оболочка
    pip установить pyinstaller
    ```
8. Задайте переменные среды с путями к двоичным файлам FFmpeg и mp4decrypt:

   В Windows запустите: 
   ``shell
   установите FFMPEG_PATH=C:\path\to\ffmpeg.exe
   установите MP4DECRYPT_PATH=C:\path\to\mp4decrypt.exe
   ```
   В Unix или macOS запустите:
   ``оболочка
   экспортировать FFMPEG_PATH=/путь/к/ffmpeg
   экспортировать MP4DECRYPT_PATH=/путь/к/mp4decrypt
   ```
9. Создайте проект:
    ``оболочка
    кинескоп pyinstaller-dl.spec
    ```
10. Готовый скрипт должен быть доступен в папке _dist_
