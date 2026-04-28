# TGFS

TGFS (Telegram File Storage) — это локальный CLI + Telegram-бот, который использует ваш Telegram как хранилище файлов и даёт удобный интерфейс поверх него.

Фактически:
- данные файлов уходят в Telegram (`Saved Messages`) кусками;
- локально хранится только индекс/метаданные в `tgfs.db`;
- файлы можно шифровать мастер-ключом.

---

## Что умеет TGFS

- Загружать большие файлы по частям (chunk upload).
- Скачивать и собирать файл обратно с проверкой целостности.
- Шифровать содержимое перед отправкой (мастер-ключ).
- Искать, удалять и просматривать файлы по ID.
- Управлять Telegram-ботом как сервисом: `tgfs bot start|stop|status`.
- Поднимать бота одной командой: `tgfs up`.

---

## Как это работает

1. Вы выполняете `tgfs upload ...` или отправляете файл в бота.
2. TGFS делит файл на куски (по умолчанию 48MB).
3. Каждый кусок (опционально зашифрованный) загружается сообщением в ваш Telegram.
4. В `tgfs.db` сохраняются:
   - ID файла в системе TGFS,
   - `message_id` каждого куска,
   - hash, размер, флаг шифрования, salt.
5. При `tgfs download <id>` куски скачиваются обратно, расшифровываются и собираются в файл.

---

## Требования

- Python 3.10+ (рекомендуется 3.11+).
- Telegram API credentials с [my.telegram.org](https://my.telegram.org).
- Windows / Linux / macOS.

---

## Быстрый старт

### 1) Клонирование и установка

```bash
git clone https://github.com/zomurb/TGFS.git
cd TGFS
python -m pip install -e .
```

После этого доступна команда `tgfs`.

### 2) Настройка `.env`

Создайте файл `.env` в корне проекта:

```env
TG_API_ID=123456
TG_API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
OWNER_ID=123456789
```

Поддерживаются оба варианта имён:
- `TG_API_ID` / `TG_API_HASH` (рекомендуется),
- `API_ID` / `API_HASH` (совместимость).

### 3) Инициализация базы

```bash
tgfs init-fs
```

### 4) Первая авторизация Telethon

При первом обращении к Telegram CLI запросит телефон/код.  
Это создаст файл сессии `tgfs_session.session` в корне проекта.

---

## Команды CLI

### Файлы

- `tgfs ls` — список файлов в TGFS.
- `tgfs upload "C:\path\file.zip"` — загрузка файла.
- `tgfs download 12 --output "C:\Downloads"` — скачивание по ID.
- `tgfs info 12` — детальная информация по файлу.
- `tgfs search "photo"` — поиск по имени.
- `tgfs rm 12` — удалить файл (и из Telegram, и из БД).

### Бот как сервис

- `tgfs bot start` — запустить бота в фоне.
- `tgfs bot stop` — остановить бота.
- `tgfs bot status` — проверить статус.
- `tgfs up` — поднять бота, если не запущен.

---

## Telegram-бот

Бот поддерживает:
- Slash-команды (`/start`, `/help`, `/list`, `/search`, `/set_password`).
- Загрузку `document`, `photo`, `video`, `audio`, `voice`.
- Ограничение доступа по `OWNER_ID`.
- Использование того же мастер-ключа, что и в CLI.

---

## Шифрование и мастер-пароль

- При первой зашифрованной загрузке задаётся мастер-пароль.
- В БД хранится не пароль, а производный `master_password_hash`.
- Для шифрования чанков используется этот мастер-ключ + случайный salt файла.
- Telegram хранит уже зашифрованный контент.

Важно:
- если забыть мастер-пароль, расшифровать старые зашифрованные файлы не получится.
- храните `tgfs.db` и `tgfs_session.session` безопасно.

---

## Где что хранится

В корне проекта:
- `.env` — настройки и токены;
- `tgfs.db` — индекс файлов и настройки TGFS;
- `tgfs_session.session` — сессия Telethon;
- `.tgfs/bot.pid` — PID фонового бота.

В Telegram:
- сами чанки файлов в `Saved Messages` (`me`).

---

## Скриншоты

Ниже готовые места для скриншотов (замени пути на реальные картинки в репозитории, например `docs/screenshots/...`):

```md
![CLI list](docs/screenshots/cli-ls.png)
![Bot commands](docs/screenshots/bot-commands.png)
![Upload progress](docs/screenshots/upload-progress.png)
```

---

## Частые проблемы

- `ValueError: API ID or Hash cannot be empty`  
  Проверь `.env` и имена переменных (`TG_API_ID`, `TG_API_HASH`).

- `tgfs` не находится в терминале  
  Добавь в `PATH` папку Python Scripts и перезапусти терминал.

- Бот не отвечает  
  Проверь `BOT_TOKEN`, `OWNER_ID` и статус: `tgfs bot status`.

---

## Безопасность

- Не коммитьте `.env`, `tgfs.db`, `tgfs_session.session`.
- Не публикуйте `BOT_TOKEN`, `API_HASH`, session-файлы.
- Используйте проект только для законного контента и с учётом правил Telegram.

---

## Лицензия

Пока не задана отдельно. При желании добавьте `LICENSE` (например, MIT).
