# Adrobot

Веб-интерфейс для работы с кампаниями Keitaro. В форме создания укажите название, двухбуквенный код страны и ID оффера, затем выберите домен, группу и источник трафика. Keitaro направит посетителей из указанной страны в Google, а остальных — на оффер.

В разделе «Офферы» загрузите кампанию по ID. Добавление, удаление и восстановление офферов пересчитывает доли в черновике. Закреплённые доли сохраняются, остальной трафик делится между активными незакреплёнными офферами. «Отправить в Keitaro» применяет черновик, «Отмена» возвращает текущие доли. PostgreSQL хранит закрепления и список ранее видимых офферов для восстановления.

## Запуск через Docker Compose

Нужен Docker с плагином Compose. Скопируйте `.env.example` в `.env`. Если `.env` уже есть, добавьте в него `POSTGRES_PASSWORD`. Задайте собственный пароль PostgreSQL. Значение с символом `$` заключите в одинарные кавычки, чтобы Compose прочитал его буквально. Для подключения к Keitaro укажите `KEITARO_BASE_URL` без пути `/admin` и заполните `KEITARO_API_KEY`.

Из корня проекта запустите сборку и контейнеры.

```bash
docker compose up --build -d
```

Откройте `http://127.0.0.1:8080`. nginx раздаёт React и передаёт запросы `/api/` в FastAPI. Документация API доступна на `http://127.0.0.1:8080/docs`. Порт можно изменить через `ADROBOT_PORT` в `.env`. PostgreSQL и FastAPI доступны внутри сети Compose.

Compose ждёт готовности PostgreSQL и применяет миграции Alembic перед запуском API. Данные PostgreSQL лежат в именованном томе и сохраняются после `docker compose down`.

## Разработка без Docker

Нужны Python 3.11+, Node.js 22.12+ и доступная база PostgreSQL.

В корне проекта скопируйте `.env.example` в `.env`. Укажите базовый адрес Keitaro без пути `/admin` и заполните `KEITARO_API_KEY`. API-ключ используется только сервером. В `DATABASE_URL` укажите адрес уже созданной базы и пользователя с правом менять её схему. Спецсимволы в логине и пароле кодируйте по правилам URL, например `@` как `%40`.

Бэкенд запускается из корня проекта.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m alembic -c backend/alembic.ini upgrade head
python -m uvicorn app.main:app --app-dir backend --reload
```

В другом терминале запустите фронтенд.

```bash
cd frontend
npm ci
npm run dev
```

Интерфейс доступен на `http://localhost:5173`, документация API — на `http://127.0.0.1:8000/docs`.

## Миграции

Миграции хранятся в `backend/alembic/versions`. При обновлении через Compose запустите `docker compose up --build -d`, чтобы применить новые миграции. Текущую ревизию можно посмотреть командой `docker compose exec api python -m alembic -c alembic.ini current`.

При запуске без Docker примените миграции командой `python -m alembic -c backend/alembic.ini upgrade head` из корня репозитория. Текущую ревизию можно посмотреть командой `python -m alembic -c backend/alembic.ini current`.
