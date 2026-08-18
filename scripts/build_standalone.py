"""
Сборка автономного HTML-прототипа: один файл, который открывается двойным
кликом и работает без backend'а (данные и офлайн-движок инлайнятся внутрь).

Запуск:  python scripts/build_standalone.py
Результат: dist/tenderai-prototype.html
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "index.html"
ENGINE = ROOT / "frontend" / "offline-engine.js"
DATA = ROOT / "backend" / "app" / "data" / "tenders.json"
DIST = ROOT / "dist"

DEPLOY_README = """# Сайт стартап-проекта TenderAI — публикация

В этой папке два файла, больше ничего не нужно:

* `index.html` — сайт стартап-проекта (главная страница)
* `demo.html` — интерактивный прототип сервиса

## Вариант 1. GitHub Pages (бесплатно, постоянный адрес)

1. Зарегистрируйтесь на https://github.com (если аккаунта ещё нет).
2. Создайте репозиторий: **New repository** → имя `tenderai` → **Public** → **Create**.
3. На странице пустого репозитория нажмите **uploading an existing file** и перетащите
   туда `index.html`, `demo.html` и `.nojekyll` из этой папки → **Commit changes**.
4. Откройте **Settings → Pages**. В блоке *Build and deployment*:
   Source — **Deploy from a branch**, Branch — **main**, папка — **/ (root)** → **Save**.
5. Через 1–2 минуты сайт будет доступен по адресу
   `https://ВАШ-ЛОГИН.github.io/tenderai/`

Чтобы обновить сайт — загрузите изменённый `index.html` в репозиторий, публикация
произойдёт автоматически.

## Вариант 2. Netlify Drop (быстрее всего, 30 секунд)

1. Откройте https://app.netlify.com/drop
2. Перетащите на страницу **всю эту папку** целиком.
3. Сайт сразу получит адрес вида `https://random-name.netlify.app`.
4. Зарегистрируйтесь, чтобы адрес закрепился за вами, и в *Site settings → Change site name*
   задайте понятное имя.

## Вариант 3. Cloudflare Pages

1. https://dash.cloudflare.com → **Workers & Pages** → **Create** → **Pages** →
   **Upload assets**.
2. Загрузите эту папку, укажите имя проекта `tenderai`.
3. Адрес: `https://tenderai.pages.dev`

## После публикации

* Замените `https://github.com/fanot/tenderai` в блоке «Контакты» на адрес
  вашего репозитория.
* Замените адрес электронной почты `hello@tenderai.ru` на рабочий.
* Замените векторные логотипы партнёров официальными файлами из брендбуков
  Фонда содействия инновациям и Платформы университетского технологического
  предпринимательства.
* Заполните раздел «Команда» реальными именами участников.
"""


def main() -> None:
    html = SRC.read_text(encoding="utf-8")
    tenders = json.loads(DATA.read_text(encoding="utf-8"))

    data_block = (
        "<script>window.__EMBEDDED_TENDERS__ = "
        + json.dumps(tenders, ensure_ascii=False, separators=(",", ":"))
        + ";</script>"
    )
    html = html.replace("<!--EMBEDDED_DATA-->", data_block)
    html = html.replace(
        '<script src="/static/offline-engine.js"></script>',
        "<script>\n" + ENGINE.read_text(encoding="utf-8") + "\n</script>",
    )

    DIST.mkdir(exist_ok=True)
    out = DIST / "tenderai-prototype.html"
    out.write_text(html, encoding="utf-8")
    print(f"Собрано: {out}  ({out.stat().st_size / 1024:.0f} КБ, {len(tenders)} тендеров)")

    # Автономная копия сайта стартап-проекта: ссылки на прототип переписываются
    # на соседний файл, чтобы сайт открывался с диска без сервера.
    site = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    site_out = DIST / "tenderai-startup-site.html"
    site_out.write_text(site.replace('href="/"', 'href="tenderai-prototype.html"'), encoding="utf-8")
    print(f"Собрано: {site_out}  ({site_out.stat().st_size / 1024:.0f} КБ)")

    # Папка для публикации на статическом хостинге (GitHub Pages / Netlify / Cloudflare Pages).
    deploy = DIST / "deploy"
    deploy.mkdir(exist_ok=True)
    (deploy / "index.html").write_text(site.replace('href="/"', 'href="demo.html"'), encoding="utf-8")
    (deploy / "demo.html").write_text(html, encoding="utf-8")
    # .nojekyll отключает обработку Jekyll на GitHub Pages
    (deploy / ".nojekyll").write_text("", encoding="utf-8")
    (deploy / "README.md").write_text(DEPLOY_README, encoding="utf-8")
    print(f"Собрано: {deploy}/ — папка для публикации (index.html + demo.html)")


if __name__ == "__main__":
    main()
