"""
Подготовка иллюстраций для отчёта о выполнении Работ.

Делает снимки экранов работающего прототипа и сайта стартап-проекта.
Требует запущенного backend'а: uvicorn app.main:app --port 8090

Запуск: python scripts/make_report_figures.py
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"
APP = "http://localhost:8090/"
SITE = (ROOT / "site" / "index.html").as_uri()

QUERY = "разработка информационной системы в Москве до 20 млн по 44-ФЗ"
ASK = "какие требования к участникам и сроки подачи"


async def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 880}, device_scale_factor=2)

        # --- Рисунок 1: экран поиска с распознанными фильтрами ---
        await page.goto(APP, wait_until="networkidle")
        await page.wait_for_timeout(1200)
        await page.fill("#q", QUERY)
        await page.click("#goSearch")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=IMG / "fig-search.png")

        # --- Рисунок 2: ответ RAG-ассистента со ссылками на источники ---
        await page.fill("#askInput", ASK)
        await page.click("#askBtn")
        await page.wait_for_timeout(2200)
        # прокручиваем диалог к вопросу пользователя, чтобы в кадр попали вопрос,
        # начало ответа и ссылки на источники
        await page.evaluate(
            "() => { const u = document.querySelector('#chat .msg.user');"
            " if (u) document.querySelector('#chat').scrollTop = u.offsetTop - 56; }"
        )
        await page.wait_for_timeout(400)
        el = await page.query_selector(".assistant")
        await el.screenshot(path=IMG / "fig-assistant.png")

        # --- Рисунок 3: карточка закупки ---
        await page.click("#results .tender")
        await page.wait_for_timeout(1200)
        # подложка модального окна зафиксирована в области просмотра, из-за чего
        # часть карточки не отрисовывается; на время съёмки переводим её в поток
        await page.evaluate(
            "() => { const o = document.querySelector('.overlay');"
            " o.style.position = 'static'; o.style.background = '#fff'; }"
        )
        await page.wait_for_timeout(400)
        el = await page.query_selector("#modal")
        await el.screenshot(path=IMG / "fig-tender-card.png")
        await page.keyboard.press("Escape")

        # --- Рисунок 4: экран аналитики ---
        await page.click("nav.tabs button[data-tab='dash']")
        await page.wait_for_timeout(1800)
        await page.screenshot(path=IMG / "fig-analytics.png")

        # --- Рисунок 5: пример обращения к API ---
        await page.set_viewport_size({"width": 1060, "height": 900})
        await page.goto((ROOT / "docs" / "img" / "api-example.html").as_uri())
        await page.wait_for_timeout(500)
        el = await page.query_selector(".diagram")
        await el.screenshot(path=IMG / "fig-api.png")

        # --- Рисунок 6: главная страница сайта стартап-проекта ---
        await page.set_viewport_size({"width": 1280, "height": 1000})
        await page.goto(SITE)
        await page.wait_for_timeout(900)
        await page.screenshot(path=IMG / "fig-site-hero.png")

        # --- Рисунок 7: блок партнёров на сайте ---
        await page.locator("#partners").scroll_into_view_if_needed()
        await page.wait_for_timeout(500)
        el = await page.query_selector("#partners .wrap")
        await el.screenshot(path=IMG / "fig-site-partners.png")

        # --- Рисунок 8: схема конвейера обработки запроса ---
        await page.set_viewport_size({"width": 1100, "height": 760})
        await page.goto((ROOT / "docs" / "img" / "pipeline.html").as_uri())
        await page.wait_for_timeout(600)
        el = await page.query_selector(".diagram")
        await el.screenshot(path=IMG / "fig-pipeline.png")

        await browser.close()

    for f in sorted(IMG.glob("*.png")):
        print(f"{f.name:26} {f.stat().st_size / 1024:6.0f} КБ")


if __name__ == "__main__":
    asyncio.run(main())
