# Публикация сайта стартап-проекта

> **Сайт уже опубликован:** https://fanot.github.io/tenderai/
> Источник — GitHub Actions, workflow `.github/workflows/deploy-pages.yml`.
> Любой push в ветку `main` пересобирает и обновляет сайт автоматически.

Сайт статический — это два HTML-файла без зависимостей, поэтому подходит любой
бесплатный статический хостинг.

```bash
python scripts/build_standalone.py
```

Скрипт создаёт папку `dist/deploy/`:

```
dist/deploy/
  index.html    сайт стартап-проекта (главная страница)
  demo.html     интерактивный прототип сервиса
  .nojekyll     отключает обработку Jekyll на GitHub Pages
  README.md     инструкция по публикации
```

---

## Вариант 1. GitHub Pages — вручную (проще всего)

1. Зарегистрируйтесь на https://github.com
2. **New repository** → имя `tenderai` → **Public** → **Create repository**
3. На странице пустого репозитория: **uploading an existing file** → перетащите
   `index.html`, `demo.html` и `.nojekyll` из `dist/deploy/` → **Commit changes**
4. **Settings → Pages** → *Build and deployment*: Source — **Deploy from a branch**,
   Branch — **main**, папка — **/ (root)** → **Save**
5. Через 1–2 минуты сайт доступен: `https://ВАШ-ЛОГИН.github.io/tenderai/`

## Вариант 2. GitHub Pages — автоматически из репозитория

Если загружаете на GitHub весь проект, в нём уже есть workflow
`.github/workflows/deploy-pages.yml`. Он сам собирает сайт и публикует его.

1. Загрузите проект в репозиторий (`git push`)
2. **Settings → Pages** → Source — **GitHub Actions**
3. Каждый push в `main` обновляет сайт автоматически

```bash
git init
git add .
git commit -m "TenderAI: прототип сервиса и сайт стартап-проекта"
git branch -M main
git remote add origin https://github.com/ВАШ-ЛОГИН/tenderai.git
git push -u origin main
```

## Вариант 3. Netlify Drop — 30 секунд, без git

1. https://app.netlify.com/drop
2. Перетащите папку `dist/deploy` целиком
3. Сайт получает адрес вида `https://random-name.netlify.app`
4. Зарегистрируйтесь, чтобы закрепить сайт, и задайте имя в *Site settings → Change site name*

## Вариант 4. Cloudflare Pages

1. https://dash.cloudflare.com → **Workers & Pages** → **Create** → **Pages** → **Upload assets**
2. Загрузите папку `dist/deploy`, имя проекта — `tenderai`
3. Адрес: `https://tenderai.pages.dev`

---

## Чек-лист перед публикацией

Требования программы «Студенческий стартап» (ФСИ) к сайту стартап-проекта:

- [x] На главной странице размещены логотипы Фонда содействия инновациям и мероприятия
      «Платформа университетского технологического предпринимательства»
- [x] Размещена формулировка: «Проект реализован при поддержке Фонда содействия
      инновациям в рамках программы „Студенческий стартап“ мероприятия „Платформа
      университетского технологического предпринимательства“»
- [x] Размещена информация о продукте — что это за сервис, какую задачу решает,
      как работает
- [ ] Логотипы заменены официальными файлами из брендбуков партнёров
- [ ] Указана реальная электронная почта вместо `hello@tenderai.ru`
- [ ] Ссылка на репозиторий: замените `https://github.com/fanot/tenderai`
- [ ] Раздел «Команда» заполнен реальными именами и ролями участников
- [ ] Проверьте, что сайт открывается на телефоне (адаптивная вёрстка уже настроена)

---

## Развёртывание backend (по желанию)

Сайт и прототип работают полностью без сервера — прототип содержит встроенные данные
и офлайн-версию поискового движка. Backend нужен, только если требуется живое API
(`/docs`, `/api/search`, `/api/assistant/ask`).

Бесплатные варианты для FastAPI: Render (free web service), Amvera, Timeweb Cloud Apps,
Yandex Cloud Serverless Containers. В репозитории есть готовый `Dockerfile`:

```bash
docker build -t tenderai .
docker run -p 8000:8000 tenderai
```
