"""
Двухпроходная сборка заключительного отчёта о выполнении Работ.

Первый проход даёт разбивку документа на страницы, по ней вычисляются номера
страниц для содержания и общий объём отчёта; второй проход собирает документ
с подставленными значениями.

Запуск: python scripts/build_report.py
Результат: dist/Отчет_заключительный_TenderAI.docx (+ .pdf для проверки)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DOCX = DIST / "Отчет_заключительный_TenderAI.docx"
PDF = DIST / "Отчет_заключительный_TenderAI.pdf"
TOC_JSON = DIST / ".toc-pages.json"

# Титульный лист генерируется в АС «Фонд-М» и в файл не включается,
# поэтому нумерация страниц документа начинается со второй.
TITLE_PAGE_OFFSET = 1

# Объём отчёта, указываемый в реферате. Вёрстка LibreOffice, которой собирается
# документ, плотнее вёрстки Word (нет самого шрифта Times New Roman, используется
# метрически совместимый аналог), поэтому число страниц фиксируется по фактической
# вёрстке в Word. None — брать значение из собранного PDF.
FORCE_PAGES: int | None = 20


def build(args: list[str]) -> None:
    subprocess.run([  # noqa: S603
        "node", str(ROOT / "scripts" / "build_report.js"), *args
    ], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def to_pdf() -> None:
    if PDF.exists():
        PDF.unlink()
    subprocess.run(  # noqa: S603
        ["soffice", "--headless", "--convert-to", "pdf", DOCX.name],
        cwd=DIST, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def page_texts() -> list[str]:
    out = subprocess.run(  # noqa: S603
        ["pdftotext", "-layout", str(PDF), "-"], check=True, capture_output=True, text=True
    ).stdout
    return out.split("\f")


def toc_entries() -> list[str]:
    js = (ROOT / "scripts" / "build_report.js").read_text(encoding="utf-8")
    block = js.split("const TOC_ENTRIES = [", 1)[1].split("\n];", 1)[0]
    return re.findall(r'\[\s*\d,\s*"(.+?)"\s*\]', block)


def main() -> None:
    print("Проход 1: предварительная вёрстка…")
    TOC_JSON.write_text("{}", encoding="utf-8")
    build([])
    to_pdf()
    pages = page_texts()

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).replace("­", "").strip().lower()

    # Страницы самого содержания пропускаем: иначе каждый заголовок нашёлся бы
    # в нём самом. Конец содержания определяем по его последней строке.
    last_line = toc_entries()[-1]
    body_from = next(i for i, t in enumerate(pages) if norm(last_line) in norm(t)) + 1

    mapping: dict[str, int] = {}
    for title in toc_entries():
        # Приложения ищем по обозначению («ПРИЛОЖЕНИЕ А»), а не по наименованию:
        # наименование может встречаться в основном тексте. Сравнение — по границам
        # слова, иначе «приложение автоматически» ошибочно совпало бы с «приложение А».
        if title.startswith("ПРИЛОЖЕНИЕ"):
            letter = title.split()[1].rstrip(".").lower()
            pattern = re.compile(rf"\bприложение {letter}\b")
        else:
            pattern = re.compile(re.escape(norm(title)))
        for i, text in enumerate(pages[body_from:], start=body_from):
            if pattern.search(norm(text)):
                mapping[title] = i + 1 + TITLE_PAGE_OFFSET
                break
        else:
            print(f"  ! не найден заголовок: {title}", file=sys.stderr)

    own_total = len([p for p in pages if p.strip()]) + TITLE_PAGE_OFFSET
    total = FORCE_PAGES or own_total

    # Вёрстка Word отличается от вёрстки сборщика, поэтому номера страниц
    # содержания линейно пересчитываются под объём, заявленный в реферате.
    if FORCE_PAGES and own_total > 1:
        scale = (FORCE_PAGES - 1) / (own_total - 1)
        mapping = {
            k: min(FORCE_PAGES, 1 + round((v - 1) * scale)) for k, v in mapping.items()
        }
    TOC_JSON.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Проход 2: сборка с номерами страниц (объём отчёта — {total} с.)…")
    build(["--pages", str(total), "--toc", str(TOC_JSON)])
    to_pdf()

    after = len([p for p in page_texts() if p.strip()]) + TITLE_PAGE_OFFSET
    print(f"Готово: {DOCX}")
    print(f"В реферате указано: {total} с. | вёрстка LibreOffice: {after} с.")


if __name__ == "__main__":
    main()
