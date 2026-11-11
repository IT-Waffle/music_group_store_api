# Чек-лист выкладки в production

Порядок: сначала разведка и бэкап, потом конфигурация, потом деплой, потом
проверки. Пока все пункты раздела «Приёмка» не зелёные, frontend не получает
финальный handoff.

Целевая ревизия миграций после деплоя: **`530ac7a03195` (head)**.

Цепочка: `51921ec5c6b0` → `05456137b11c` → `d02c9484a41c` → `334110327a2d` →
`73316b48f694` → `9a7d3c2e1f40` → `5fe558a4ee4f` → `f0160eb8f72a` (is_playable) →
`c8bcf67fec2e` (view_counters) → `b4c10d249214` (comments) → `530ac7a03195`
(comments.notified_at).

## 1. Разведка (ничего не меняя)

- [ ] **Код на сервере.** `git status`, `git log -5`, `git remote -v` в папке
      проекта. Production отвечает на `/api/v1/system/metrics`, которого нет в
      репозитории: найти, откуда он, и сохранить (коммит в отдельную ветку или
      патч), чтобы деплой из `main` его не затёр.
- [ ] **Миграции.** `docker compose exec db psql -U postgres -d music_store -c "SELECT version_num FROM alembic_version;"`
  - `5fe558a4ee4f` или старше — всё штатно, `upgrade head` дойдёт сам;
  - `c83f1a7d4b2e` (ревизии нет в репо) — перед деплоем
    `alembic stamp 5fe558a4ee4f`, иначе контейнер API упадёт на старте
    (миграции выполняются в его `CMD`).
- [ ] **Колонка `is_playable`.** `\d music_tracks` — есть или нет, миграция
      `f0160eb8f72a` безопасна в обоих случаях.
- [ ] **Ресурсы.** `free -m`, `df -h`, `docker stats --no-stream` — сколько
      RAM/диска реально свободно.
- [ ] **Как запущен Nginx**: на хосте или в контейнере, где его конфиг. От этого
      зависят `proxy_pass` и `FORWARDED_ALLOW_IPS`.
- [ ] **IP клиентов сейчас.** `docker compose logs --tail=50 api` — если у всех
      запросов один адрес `172.x.x.x`, реальный IP не доходит (исправляется в
      п. 4).

## 2. Бэкап (обязательно до деплоя)

- [ ] `docker compose exec db pg_dump -U postgres -Fc music_store > backup_$(date +%F).dump`
- [ ] Архив медиа: volume `media_data` (или каталог из `MUSIC_MEDIA_ROOT` /
      `uploads/`).
- [ ] Скопировать бэкап **с сервера** и проверить, что файл не пустой.
- [ ] Записать текущий commit/образ, чтобы было куда откатиться.

## 3. Конфигурация `.env` (на сервере, не в git)

- [ ] `ENVIRONMENT=production` — включает проверку силы `SECRET_KEY` и
      выключает `/docs`.
- [ ] `SECRET_KEY` — случайные ≥ 32 байта
      (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
      Смена ключа разлогинит всех — это нормально.
- [ ] `CORS_ALLOWED_ORIGINS` — пусто, если frontend и API на одном домене;
      иначе только `["https://amorfati.lv"]`.
- [ ] `FORWARDED_ALLOW_IPS` — адрес/подсеть Nginx (например `172.18.0.0/16`
      для Docker-сети или `127.0.0.1`, если Nginx на хосте). Не `*`.
- [ ] `MEDIA_USE_X_ACCEL_REDIRECT=true` и `alias` в Nginx указывает на тот же
      каталог, что `MUSIC_MEDIA_ROOT` внутри контейнера (через volume).
- [ ] `COMMENT_RATE_LIMIT_ATTEMPTS` / `COMMENT_RATE_LIMIT_WINDOW_SECONDS` —
      оставить 5 / 600, если заказчик не просил иначе.
- [ ] Brevo (п. 6): `NOTIFICATIONS_ENABLED=true`, `BREVO_API_KEY`,
      `MAIL_FROM=noreply@amorfati.lv`, `MAIL_FROM_NAME`, `COMMENT_NOTIFY_EMAIL`.
- [ ] `FIRST_ADMIN_PASSWORD` убрать из `.env` после того, как админ создан.
- [ ] Права: `chmod 600 .env`, владелец — пользователь деплоя.

## 4. Сеть и Nginx

- [ ] В `docker-compose.yml` порт API `127.0.0.1:8000:8000` (уже в репо).
      Postgres и Redis наружу не публикуются (в prod не использовать
      `docker-compose.dev.yml`: он открывает 5445 и 6379).
- [ ] Файрвол: открыты только 22, 80, 443. Docker обходит ufw для
      опубликованных портов — поэтому важна привязка к 127.0.0.1.
      По возможности 80/443 только с адресов Cloudflare.
- [ ] Проверка снаружи (с другой машины):
      `curl -m 5 http://<IP сервера>:8000/health/live` — должен **не** отвечать;
      `nc -zv <IP> 5432`, `nc -zv <IP> 6379` — закрыто.
- [ ] Nginx по `deploy/nginx.music.conf.example`:
  - `set_real_ip_from` (все диапазоны Cloudflare) + `real_ip_header CF-Connecting-IP`;
  - `proxy_set_header X-Forwarded-For $remote_addr;` (перезапись, не дописывание);
  - `client_max_body_size 1m` по умолчанию, `520m` только на upload-маршрутах;
  - `/health/ready` только с localhost;
  - `/_protected_music_media/` — `internal`.
- [ ] `nginx -t`, затем `nginx -s reload` (или перезапуск контейнера).
- [ ] Cloudflare: SSL/TLS режим **Full (strict)**, «Always Use HTTPS» включён.

## 5. Деплой

- [ ] На сервере: `git fetch && git checkout main && git pull` (после того как
      сохранён серверный код из п. 1).
- [ ] `docker compose build api && docker compose up -d`
      (миграции применятся при старте контейнера).
- [ ] `docker compose exec api uv run alembic current` → `530ac7a03195 (head)`.
- [ ] `docker compose ps` — все сервисы `healthy`.
- [ ] `docker compose logs --tail=100 api` — нет traceback.

## 6. Brevo

- [ ] В Brevo добавить домен `amorfati.lv` и пройти аутентификацию: записи
      **SPF**, **DKIM** (и **DMARC**, хотя бы `p=none`) в DNS Cloudflare.
      Записи — DNS only (серое облако).
- [ ] Создать API key (SMTP & API → API Keys). В настройках безопасности Brevo
      по возможности ограничить ключ IP-адресом сервера.
- [ ] Ключ — только в `.env` сервера. В git, чатах и тикетах его быть не должно.
- [ ] Отправитель `MAIL_FROM` — адрес на подтверждённом домене.

## 7. Приёмка (smoke-тесты на живом сайте)

Публичное:

- [ ] `https://amorfati.lv/health/live` → `{"status":"alive"}`;
      `/health/ready` снаружи → 403/404 (закрыт в Nginx).
- [ ] `https://amorfati.lv/docs` и `/openapi.json` → 404.
- [ ] `GET /api/v1/catalog/products` — работы на месте, у каждой `view_count`.
- [ ] `GET /api/v1/music/tracks` и `/clips` → 200, у элементов `view_count`.
- [ ] `GET /api/v1/localization/bundle/music_track` → 404;
      `/localization/bundle/ui` → как раньше.

Просмотры:

- [ ] `POST /api/v1/engagement/product/<id>/views` два раза → 1, 2 (или +1 от
      текущего); значение видно в `GET /catalog/products/<id>`.

Комментарии и email:

- [ ] Отправить комментарий с сайта → `202`, публично **не виден**.
- [ ] Он есть в `GET /api/v1/engagement/manage/comments` (админ), `target_title`
      на латышском.
- [ ] Письмо пришло на `COMMENT_NOTIFY_EMAIL` (проверить и «Спам»);
      `notified_at` у комментария заполнен.
- [ ] Approve → комментарий появился в публичном списке с датой.
- [ ] Delete → исчез; повторный delete → 404.
- [ ] 6 комментариев подряд с одного устройства → 6-й `429`; **с другого
      устройства/сети сразу после этого — `202`**. Это доказывает, что лимит
      считается по реальному IP, а не общий на всех.
- [ ] В `docker compose logs api` у запросов видны реальные IP посетителей.

Безопасность:

- [ ] `curl -X POST https://amorfati.lv/api/v1/music/manage/tracks/00000000-0000-0000-0000-000000000000/audio -F file=@big.mp4`
      без токена → `401` сразу.
- [ ] JSON больше 1 МБ на любой публичный POST → `413`.
- [ ] 5 неверных паролей → `429` для этого IP; вход с другого IP работает.

Музыка (регрессия):

- [ ] Загрузить через админку **настоящие** MP3/M4A и MP4 H.264/AAC (в тестах
      ffprobe подменён — проверяем реальный ffprobe в контейнере).
- [ ] Аудио опубликованного трека: `Range: bytes=0-1` → `206`; перемотка в
      браузере работает.
- [ ] `is_playable=false` → аудио `403 TRACK_PLAYBACK_DISABLED`, карточка видна;
      admin-preview работает; обратно `true` → играет.
- [ ] С `MEDIA_USE_X_ACCEL_REDIRECT=true` медиа отдаёт Nginx (в ответе нет
      `X-Accel-Redirect`, файл скачивается, Range работает).

## 8. Эксплуатация

- [ ] Redis: ограничить память, например
      `command: redis-server --maxmemory 64mb --maxmemory-policy volatile-lru`
      (все наши ключи живут с TTL). Наружу Redis не публикуется.
- [ ] Логи Docker не должны съесть диск: в `/etc/docker/daemon.json`
      `"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}`.
- [ ] Регулярный бэкап `pg_dump` + медиа (cron), с копией вне сервера.
- [ ] Внешний мониторинг `https://amorfati.lv/health/live` (UptimeRobot и т. п.).
- [ ] Необязательно, позже: образ API без dev-зависимостей
      (`uv sync --frozen --no-dev`) и запуск не от root.

## 9. Откат

1. `docker compose down api`, вернуть предыдущий commit/образ.
2. Схема: новые миграции только добавляют таблицы/колонки, старый код с ними
   работает. Если всё же нужно откатить схему:
   `alembic downgrade f0160eb8f72a` (удалит view_counters и comments **вместе
   с данными**).
3. Крайний случай — восстановление из `pg_dump` (п. 2).

## 10. Передача frontend

Когда разделы 1–7 зелёные — отдать Кенту `docs/frontend-handoff.md` и
подтвердить, что на production живёт ревизия `530ac7a03195`.
