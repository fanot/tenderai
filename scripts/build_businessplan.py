"""
Двухпроходная сборка бизнес-плана проекта.

Первый проход даёт разбивку на страницы, по ней вычисляются номера страниц
для содержания; второй проход собирает документ с подставленными значениями.

Запуск: python scripts/build_businessplan.py
Результат: dist/Бизнес-план_TenderAI.docx (+ .pdf для проверки)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
JS = ROOT / "scripts" / "build_businessplan.js"
DOCX = DIST / "Бизнес-план_TenderAI.docx"
PDF = DIST / "Бизнес-план_TenderAI.pdf"
TOC_JSON = DIST / ".toc-pages-bp.json"


def build(args: list[str]) -> None:
    subprocess.run(["node", str(JS), *args], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)  # noqa: S603


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
    js = JS.read_text(encoding="utf-8")
    block = js.split("const TOC_ENTRIES = [", 1)[1].split("\n];", 1)[0]
    return re.findall(r'\[\s*\d,\s*"(.+?)"\s*\]', block)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def main() -> None:
    print("Проход 1: предварительная вёрстка…")
    build([])
    to_pdf()
    pages = page_texts()

    entries = toc_entries()
    body_from = next(i for i, t in enumerate(pages) if norm(entries[-1]) in norm(t)) + 1

    mapping: dict[str, int] = {}
    for title in entries:
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
                mapping[title] = i + 1
                break
        else:
            print(f"  ! не найден заголовок: {title}", file=sys.stderr)

    total = len([p for p in pages if p.strip()])
    TOC_JSON.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Проход 2: сборка с номерами страниц (объём — {total} с.)…")
    build(["--pages", str(total), "--toc", str(TOC_JSON)])
    to_pdf()

    after = len([p for p in page_texts() if p.strip()])
    status = "совпал" if after == total else f"ИЗМЕНИЛСЯ: было {total}, стало {after}"
    print(f"Готово: {DOCX}")
    print(f"Объём после второго прохода {status}")


if __name__ == "__main__":
    main()
