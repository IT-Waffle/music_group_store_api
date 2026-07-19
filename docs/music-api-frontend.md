# Music API: инструкция для frontend

Все маршруты начинаются с `/api/v1/music`. Актуальные типы также доступны в
`/docs` и `/openapi.json`.

Полная инструкция по остальным доменам backend находится в
[`api-usage.md`](api-usage.md).

## Основные правила

- Публичные запросы не требуют токена и возвращают только опубликованный контент.
- Административные запросы требуют `Authorization: Bearer <token>`.
- Язык публичного ответа задаётся заголовком `Accept-Language: en|lv|ru`.
- Если язык не поддерживается, backend использует `en`.
- Все URL медиа относительные. Frontend должен добавлять origin API, если API и
  frontend находятся на разных доменах.
- Не формируйте URL аудио, видео, cover или poster вручную: используйте поле
  `url` из ответа.
- YouTube/Vimeo — только необязательные внешние ссылки. Основное видео клипа
  всегда находится в `video.url` и загружается на наш backend.

## Авторизация админки

```http
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

username=admin@example.com&password=...
```

Ответ:

```json
{
  "access_token": "jwt",
  "token_type": "bearer"
}
```

После пяти неудачных попыток backend временно возвращает `429 RATE_LIMITED`.

## Публичные списки

```http
GET /api/v1/music/tracks?limit=20&offset=0
Accept-Language: ru
```

```http
GET /api/v1/music/clips?limit=20&offset=0
Accept-Language: ru
```

Оба списка имеют одинаковую оболочку:

```json
{
  "items": [],
  "total": 0,
  "limit": 20,
  "offset": 0
}
```

Список треков сортируется по `sort_order`, затем по `release_date` и дате
создания. Список клипов — по `sort_order`, затем по дате создания.

## Публичный трек

```http
GET /api/v1/music/tracks/{slug}
Accept-Language: lv
```

Сокращённый пример:

```json
{
  "id": "uuid",
  "slug": "amor-fati-one",
  "title": "...",
  "description": "...",
  "sort_order": 10,
  "release_date": "2026-09-07",
  "audio": {
    "id": "uuid",
    "kind": "audio",
    "url": "/api/v1/music/tracks/amor-fati-one/audio",
    "content_type": "audio/mpeg",
    "size_bytes": 123456,
    "duration_ms": 218000,
    "width": null,
    "height": null,
    "codec": "mp3"
  },
  "cover": {
    "url": "/api/v1/music/tracks/amor-fati-one/cover",
    "content_type": "image/webp",
    "width": 1600,
    "height": 1600
  },
  "clips": [],
  "created_at": "2026-07-19T12:00:00",
  "updated_at": "2026-07-19T12:00:00"
}
```

`cover` может быть `null`. У опубликованного трека `audio` всегда существует.
Draft, archived и неизвестный slug одинаково возвращают `404 TRACK_NOT_FOUND`.

## Публичный клип

```http
GET /api/v1/music/clips/{clip_id}
Accept-Language: en
```

```json
{
  "id": "uuid",
  "track_id": "uuid",
  "track_slug": "amor-fati-one",
  "title": "...",
  "description": "...",
  "sort_order": 1,
  "video": {
    "url": "/api/v1/music/clips/{clip_id}/video",
    "content_type": "video/mp4",
    "size_bytes": 123456789,
    "duration_ms": 180000,
    "width": 1920,
    "height": 1080,
    "codec": "h264/aac"
  },
  "poster": null,
  "youtube_url": "https://www.youtube.com/watch?v=...",
  "vimeo_url": null,
  "created_at": "2026-07-19T12:00:00",
  "updated_at": "2026-07-19T12:00:00"
}
```

`poster`, `youtube_url` и `vimeo_url` могут быть `null`. `video` у публичного
клипа всегда существует. Клип скрыт, если не опубликован он сам или его трек.

## Проигрывание медиа

Передавайте URL из ответа прямо в `<audio>`, `<video>` или `<img>`:

```html
<audio controls src="/api/v1/music/tracks/amor-fati-one/audio"></audio>
<video controls poster="/api/v1/music/clips/CLIP_ID/poster">
  <source src="/api/v1/music/clips/CLIP_ID/video" type="video/mp4" />
</video>
```

Audio/video routes поддерживают `HEAD`, `Range`, `206` и `416`. Браузер сам
отправляет Range-запросы для перемотки. После unpublish/archive публичные media
routes начинают возвращать 404.

## Рабочий порядок в админке

### 1. Создать draft-трек

```http
POST /api/v1/music/manage/tracks
Authorization: Bearer TOKEN
Content-Type: application/json
```

```json
{
  "slug": "amor-fati-one",
  "sort_order": 10,
  "release_date": "2026-09-07",
  "translations": {
    "en": {"title": "...", "description": "..."},
    "lv": {"title": "...", "description": "..."},
    "ru": {"title": "...", "description": "..."}
  }
}
```

Draft можно сохранять с неполными текстами, но публикация требует `title` и
`description` на всех трёх языках.

### 2. Загрузить audio и необязательный cover

```http
POST /api/v1/music/manage/tracks/{track_id}/audio
POST /api/v1/music/manage/tracks/{track_id}/cover
Authorization: Bearer TOKEN
Content-Type: multipart/form-data
```

Поле файла называется `file`. При использовании `FormData` не задавайте
`Content-Type` вручную — браузер должен добавить boundary.

```js
const form = new FormData();
form.append("file", selectedFile);

await fetch(`${api}/api/v1/music/manage/tracks/${trackId}/audio`, {
  method: "POST",
  headers: { Authorization: `Bearer ${token}` },
  body: form,
});
```

Повторная загрузка заменяет старый файл только после успешной проверки нового.

### 3. Создать карточку клипа

```http
POST /api/v1/music/manage/tracks/{track_id}/clips
Authorization: Bearer TOKEN
Content-Type: application/json
```

```json
{
  "sort_order": 1,
  "youtube_url": "https://www.youtube.com/watch?v=...",
  "vimeo_url": null,
  "translations": {
    "en": {"title": "...", "description": "..."},
    "lv": {"title": "...", "description": "..."},
    "ru": {"title": "...", "description": "..."}
  }
}
```

Обе внешние ссылки необязательны. Можно передать одну, обе или ни одной.

### 4. Загрузить обязательный MP4 и необязательный poster

```http
POST /api/v1/music/manage/clips/{clip_id}/video
POST /api/v1/music/manage/clips/{clip_id}/poster
Authorization: Bearer TOKEN
Content-Type: multipart/form-data
```

### 5. Опубликовать клип

```http
PATCH /api/v1/music/manage/tracks/{track_id}/clips/{clip_id}
Authorization: Bearer TOKEN
Content-Type: application/json

{"is_published": true}
```

Без MP4 и трёх полных переводов backend вернёт 409.

### 6. Опубликовать трек

```http
POST /api/v1/music/manage/tracks/{track_id}/publish
Authorization: Bearer TOKEN
```

Трек требует полного `en/lv/ru` и аудио. Все клипы, уже отмеченные как
published, также должны быть полностью готовы.

## Редактирование и lifecycle

```text
GET    /manage/tracks?status=draft|published|archived
GET    /manage/tracks/{track_id}
PATCH  /manage/tracks/{track_id}
POST   /manage/tracks/{track_id}/publish
POST   /manage/tracks/{track_id}/unpublish
POST   /manage/tracks/{track_id}/archive
POST   /manage/tracks/{track_id}/restore
DELETE /manage/tracks/{track_id}
PATCH  /manage/tracks/{track_id}/clips/{clip_id}
DELETE /manage/tracks/{track_id}/clips/{clip_id}
```

- `moderator` работает с draft, загружает файлы и может сделать unpublish.
- `admin` дополнительно публикует, архивирует, восстанавливает, удаляет и может
  изменять опубликованный трек.
- Published-трек нельзя удалить напрямую: сначала unpublish или archive.

## Preview медиа в админке

Admin-ответ возвращает для каждого asset авторизованный URL вида:

```text
/api/v1/music/manage/assets/{asset_id}/content
```

Обычный `<video src>` не умеет добавить Bearer header. Получите Blob через
`fetch`, затем создайте временный object URL:

```js
const response = await fetch(`${api}${asset.url}`, {
  headers: { Authorization: `Bearer ${token}` },
});
if (!response.ok) throw new Error("Preview loading failed");
const objectUrl = URL.createObjectURL(await response.blob());
video.src = objectUrl;

// При размонтировании компонента:
URL.revokeObjectURL(objectUrl);
```

Для больших draft-видео этот подход загружает Blob целиком. Если админке нужен
полноценный streaming-preview с перемоткой до публикации, это следует отдельно
согласовать: потребуется краткоживущий preview token или cookie-auth.

## Ошибки

Контролируемая ошибка music API:

```json
{
  "detail": {
    "code": "TRACK_AUDIO_REQUIRED",
    "message": "Upload a valid audio file before publishing the track.",
    "field": "audio"
  }
}
```

Frontend должен принимать решения по `detail.code`, а `message` показывать как
fallback. Основные коды:

- `TRACK_NOT_FOUND`, `CLIP_NOT_FOUND`, `ASSET_NOT_FOUND`;
- `TRACK_SLUG_CONFLICT`;
- `TRACK_AUDIO_REQUIRED`, `CLIP_VIDEO_REQUIRED`, `TRANSLATIONS_REQUIRED`;
- `INVALID_STATE_TRANSITION`, `INSUFFICIENT_ROLE`;
- `INVALID_EXTERNAL_VIDEO_URL`;
- `MEDIA_TOO_LARGE`, `MEDIA_TYPE_UNSUPPORTED`, `MEDIA_CODEC_UNSUPPORTED`,
  `MEDIA_INVALID`;
- `RATE_LIMITED` для login.

Обычные ошибки Pydantic (неверный UUID, отсутствующее поле и т. п.) используют
стандартный FastAPI 422 response.

## Форматы и лимиты

| Назначение | Форматы | Лимит |
| --- | --- | ---: |
| cover/poster | JPEG, PNG, WebP | 10 MB |
| audio | MP3, M4A/AAC | 100 MB |
| video | MP4, H.264 + AAC | 500 MB |

Frontend может проверять размер до отправки для быстрого UX, но backend всё
равно выполняет окончательную проверку содержимого и codec.
