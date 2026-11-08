# Paragraph AI 📚🤖

Paragraph AI — бот для платформы MAX, который помогает работать с учебниками в формате PDF. Бот распознаёт структуру книги, находит параграф по запросу и готовит по нему структурированный конспект с помощью модели, совместимой с API OpenAI.

[Открыть бота в MAX](https://max.ru/se14377957_1_bot) · [Готовый Docker-образ в GitHub Packages](https://github.com/sasha4ka/paragraph-ai/pkgs/container/paragraph-ai)

## Возможности

- Загрузка PDF-файлов учебников размером до 20 MB по умолчанию (настраивается через `MAX_FILE_SIZE_MB`), просмотр списка книг и удаление книг.
- Извлечение оглавления и параграфов из PDF. Для некоторых книг с текстовыми заголовками вида `§ 1` структура извлекается локально; в остальных случаях для разбора используется языковая модель.
- Текстовый устный доклад, доклад в виде карточек и проверка знаний из девяти вопросов с разбором ответов.
- Выбор книги и одного параграфа по номеру или названию.
- Генерация и отправка конспекта по этапам, включая очистку текста, планирование и выделение информации.
- Приём отзывов и пересылка их в чат администратора, если настроен `ADMIN_CHAT_ID`.

В основном меню доступны «Мои книги», «Конспект» и «Отзыв». Кнопка «Конспект» открывает экран режимов работы; после готового текстового доклада можно вернуться к этому экрану.

## Как пользоваться ботом

1. Откройте «Мои книги», добавьте название учебника и отправьте PDF-файл.
2. Дождитесь обработки файла. Книги с нераспознанным оглавлением не будут добавлены.
3. Откройте «Конспект», выберите режим, книгу и один параграф. В проверке знаний укажите номер варианта для вопросов A и B и напишите ответ на вопросы C. После проверки можно попросить объяснить ошибки. Кнопка «Выйти» возвращает к выбору режима.
4. Чтобы отправить отзыв, выберите «Отзыв»; имя указывать необязательно.

Книги хранятся в каталоге `books/` вместе с JSON-метаданными. В Docker Compose этот каталог подключён к постоянному тому. Каталог книг общий для экземпляра бота, а не отдельное хранилище библиотек пользователей.

## Стек технологий

- Python 3.12+ и `uv` для управления зависимостями.
- `maxapi` для бота MAX; FastAPI и Uvicorn для webhook-сервера.
- `pypdf` для чтения PDF и OpenAI-совместимый API для извлечения структуры и генерации конспектов.
- Pydantic Settings для конфигурации через переменные окружения.
- Docker Compose и Caddy для контейнерного развёртывания с HTTPS.

## Структура проекта

```text
.
├── app/
│   ├── handlers/
│   │   ├── feedback/       # Приём отзывов
│   │   ├── manage_books/   # Загрузка, список и удаление книг
│   │   ├── start/          # Стартовое меню
│   │   ├── navigation.py   # Выбор режима работы с материалом
│   │   └── summarize/      # Выбор книги/параграфа и отправка конспекта
│   ├── logics/
│   │   ├── summary/        # Очистка, планирование и сборка конспекта
│   │   ├── parser.py       # Извлечение структуры книги из PDF
│   │   └── select_paragraph.py
│   ├── app.py              # FastAPI, webhook и polling
│   ├── books.py            # Каталог книг и JSON-метаданные
│   ├── settings.py         # Настройки приложения
│   └── states.py           # Состояния диалогов бота
├── books/                  # PDF-файлы и метаданные (metadata/)
├── tests/                  # Автоматические тесты
├── main.py                 # Точка входа
├── compose.yaml            # Приложение и Caddy
├── Dockerfile
├── pyproject.toml
├── requirements.txt       # Версии Python-зависимостей для pip
└── uv.lock
```

## Установка и запуск

Требуются Python 3.12+ и [uv](https://docs.astral.sh/uv/). Для режима карточек также нужен Node.js 22.12+ с npm.

```bash
git clone https://github.com/sasha4ka/paragraph-ai.git
cd paragraph-ai
uv sync --locked
```

Создайте `.env` в корне проекта. Для локальной разработки с long polling используйте токен отдельного тестового бота:

```env
API_TOKEN=your_maxapi_token_here
OPENAI_API_TOKEN=your_openai_compatible_api_key
DEBUG=True
```

Из корня репозитория установите компоненты для карточек и запустите бота.

```bash
npm ci --prefix renderer
uv run playwright install chromium
uv run python main.py
```

Для установки через pip вместо uv используйте `requirements.txt` и команды ниже. Файл содержит закреплённые в `uv.lock` версии всех Python-зависимостей приложения, включая транзитивные.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci --prefix renderer
python -m playwright install chromium
python main.py
```

### Рендеринг карточки из stdin

Рендерер карточек находится отдельно от основного приложения. Команда `render-card` читает HTML карточки из stdin, преобразует содержимое `<formula>` и `<inline-formula>` в HTML KaTeX и сохраняет изображение PNG или JPEG. Для блочной формулы используется display-режим; CSS KaTeX и шрифты подключаются локально.

После установки зависимостей из корня проекта передайте HTML-карточку с `<card-title>` и `<card-body>` через stdin. Путь к изображению укажите аргументом.

```bash
uv run render-card /tmp/card.png < card.html
```

Скрипт ограничивает входной HTML размером 1 MB. При ошибке валидации карточки или LaTeX-команде сообщение выводится в stderr, а команда завершается с ненулевым кодом. В Docker Node.js и зависимости KaTeX устанавливаются при сборке образа.

При `DEBUG=True` приложение использует polling и удаляет существующие webhook-подписки этого бота. Не запускайте этот режим одновременно с production-инстансом, использующим тот же токен.

## Конфигурация

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `API_TOKEN` | — | Токен бота MAX. |
| `OPENAI_API_TOKEN` | — | Ключ OpenAI-совместимого API для обработки текста. |
| `OPENAI_BASE_URL` | `https://routerai.ru/api/v1` | Базовый URL API модели. |
| `DEFAULT_MODEL` | `openai/gpt-6-luna` | Модель для выбора параграфа и генерации конспекта. |
| `PARSING_MODEL` | `deepseek/deepseek-v4.1-flash` | Модель для разбора оглавления PDF. |
| `MAX_FILE_SIZE_MB` | `20` | Максимальный размер загружаемого файла в мегабайтах. |
| `ADMIN_CHAT_ID` | — | Необязательный ID чата, куда пересылаются отзывы. |
| `DEBUG` | `False` | `True` включает polling; `False` включает FastAPI webhook. |
| `WEBHOOK_URL` | — | Обязательный абсолютный HTTPS URL с путём `/webhook`, если `DEBUG=False`. |
| `WEBHOOK_SECRET` | — | Необязательный секрет webhook MAX. |

Имена переменных окружения сопоставляются с настройками без учёта регистра. Параметры модели, URL и максимального размера можно переопределить в `.env`.

## Развёртывание через Docker Compose

Для production задайте в `.env` как минимум `API_TOKEN`, `OPENAI_API_TOKEN`, `WEBHOOK_URL` и публичный домен `DOMAIN`:

```env
API_TOKEN=your_maxapi_token_here
OPENAI_API_TOKEN=your_openai_compatible_api_key
DEBUG=False
WEBHOOK_URL=https://bot.example.com/webhook
DOMAIN=bot.example.com
# Необязательно:
WEBHOOK_SECRET=your_webhook_secret
ADMIN_CHAT_ID=123456789
```

Укажите DNS-запись домена на сервер и откройте порты 80 и 443. Caddy получает HTTPS-сертификат и проксирует запросы на приложение. Без домена Caddy использует `localhost` (для публичного webhook MAX нужен доступный извне HTTPS URL).

```bash
docker compose pull
docker compose up -d
docker compose logs -f app
```

По умолчанию Compose загружает образ `ghcr.io/sasha4ka/paragraph-ai:latest`. Чтобы выбрать другой тег, задайте `IMAGE_TAG`, например `IMAGE_TAG=release`. Образ также можно скачать командой `docker pull ghcr.io/sasha4ka/paragraph-ai:release`.

### Сборка образа из исходников

Из корня репозитория соберите образ и запустите его через Compose с production-настройками из `.env`.

```bash
docker build -t ghcr.io/sasha4ka/paragraph-ai:local .
docker compose pull caddy
IMAGE_TAG=local docker compose up -d --pull never
IMAGE_TAG=local docker compose logs -f app
```

Для локального запуска контейнера из командной строки используйте `.env` с токеном тестового бота и `DEBUG=True`.

```bash
docker run --rm --env-file .env \
  --mount source=paragraph_ai_local_books,target=/app/books \
  ghcr.io/sasha4ka/paragraph-ai:local
```

При `DEBUG=False` приложение запускает FastAPI на порту 8000 и регистрирует `WEBHOOK_URL` в MAX. URL должен быть абсолютным HTTPS-адресом с путём `/webhook`. Если настроен `WEBHOOK_SECRET`, он используется при регистрации и проверке входящих запросов. Проверить состояние сервера можно запросом `GET /healthcheck`.

Каталог `books/` не включён в образ. Загруженные через бота книги сохраняются в Docker volume `books_data` и переживают пересоздание контейнера. Отзывы пересылаются в `ADMIN_CHAT_ID`, если этот параметр задан.
