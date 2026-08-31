# Telegram Media Publisher

Локальное Windows-приложение для подготовки публикаций из папки с видео. Приложение работает только через исходящие запросы Bot API: `getMe`, `sendMessage`, `sendPhoto` и `sendMediaGroup`; polling, `getUpdates` и webhook не используются.

## Запуск MVP

```powershell
.\.venv\Scripts\python.exe -m pip install -r media_publisher_requirements.txt
.\.venv\Scripts\python.exe -m media_publisher.main
```

В окне выберите папку, укажите токен и Chat ID, затем нажмите «Сканировать». Настройки сохраняются в профиле Windows (`%APPDATA%/TelegramMediaPublisher/settings.json`), токен не попадает в репозиторий и не выводится в логи. Кнопки проверки подключения и тестовой отправки используют только введённые локально значения.

MVP включает рекурсивное сканирование, разбор имён файлов (`S02E03`, «2 сезон 3 серия», качество, озвучка), группировку по сериалам/сезонам, предупреждения о пропусках и отправку медиагрупп до 10 файлов. Провайдеры TMDB/OMDb/Rezka и кэш публикаций подключены как расширяемые модули для следующих этапов.
