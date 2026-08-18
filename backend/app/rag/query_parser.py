"""
Разбор естественно-языкового запроса в структурированные фильтры.

Пример: «ищу госзакупки по разработке ПО в Москве до 10 млн по 44-ФЗ для СМП»
  -> категория «ИТ и разработка ПО», регион «г. Москва», nmck_max = 10_000_000,
     law = 44-ФЗ, smp_only = True, очищенный поисковый запрос «разработка ПО».
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from .text import normalize

# Порядок важен: более специфичные варианты проверяются первыми
# («Московская область» раньше, чем «Москва»).
REGION_PATTERNS: list[tuple[str, str]] = [
    ("Московская область", r"\bмосковск\w*\s+обл|\bподмосковь\w*|\bмо\b"),
    ("г. Москва", r"\bмоскв\w*|\bмск\b"),
    ("г. Санкт-Петербург", r"\bсанкт[- ]петербург\w*|\bспб\b|\bпетербург\w*|\bпитер\w*"),
    ("Свердловская область", r"\bсвердловск\w*|\bекатеринбург\w*"),
    ("Республика Татарстан", r"\bтатарстан\w*|\bказан\w*"),
    ("Новосибирская область", r"\bновосибирск\w*"),
    ("Краснодарский край", r"\bкраснодар\w*|\bкубан\w*"),
    ("Нижегородская область", r"\bнижегородск\w*|\bнижн\w*\s+новгород\w*"),
    ("Челябинская область", r"\bчелябинск\w*"),
    ("Воронежская область", r"\bворонеж\w*"),
    ("Красноярский край", r"\bкрасноярск\w*"),
    ("Самарская область", r"\bсамар\w*"),
]

# Каждый паттерн — с границами слова, чтобы «по» не срабатывало внутри «поставка».
CATEGORY_PATTERNS: dict[str, list[str]] = {
    "ИТ и разработка ПО": [
        r"\bит\b", r"\bit\b", r"\bпо\b(?!\s)", r"\bсофт\w*", r"\bпрограммн\w*",
        r"\bразработк\w*", r"\bсайт\w*", r"информационн\w*\s+систем\w*",
        r"мобильн\w*\s+приложен\w*", r"\bцифров\w*", r"\bинтеграц\w*", r"\bвнедрен\w*\s+ис\b",
    ],
    "Поставка вычислительной техники": [
        r"\bкомпьютер\w*", r"\bноутбук\w*", r"\bсервер\w*", r"\bоргтехник\w*",
        r"\bмонитор\w*", r"\bмфу\b", r"вычислительн\w*", r"\bпринтер\w*",
    ],
    "Строительство и ремонт": [
        r"\bстроительств\w*", r"\bремонт\w*", r"\bкапремонт\w*", r"\bблагоустройств\w*",
        r"\bподряд\w*", r"\bсро\b", r"\bстроит\w*",
    ],
    "Медицина и фармацевтика": [
        r"\bмедицин\w*", r"\bмедицинск\w*", r"\bлекарств\w*", r"\bфарм\w*", r"\bбольниц\w*",
        r"\bздравоохранен\w*", r"\bпрепарат\w*", r"расходн\w*\s+материал\w*",
    ],
    "Транспорт и логистика": [
        r"\bтранспорт\w*", r"\bперевозк\w*", r"\bлогистик\w*", r"\bавтобус\w*", r"\bгруз\w*",
    ],
    "Продукты питания": [
        r"\bпитани\w*", r"\bпродукт\w*", r"\bеда\b", r"\bмолочн\w*", r"\bстолов\w*",
    ],
    "Клининг и эксплуатация": [
        r"\bуборк\w*", r"\bклининг\w*", r"\bэксплуатац\w*", r"\bсанитарн\w*", r"\bубор\w*",
    ],
    "Охрана и безопасность": [
        r"\bохран\w*", r"\bбезопасност\w*", r"\bвидеонаблюден\w*", r"\bчоп\b", r"\bсторож\w*",
    ],
    "Образование и обучение": [
        r"\bобразован\w*", r"\bобучен\w*", r"\bквалификац\w*", r"\bучебн\w*", r"\bтренинг\w*",
    ],
    "Энергетика и ЖКХ": [
        r"\bэнерг\w*", r"\bжкх\b", r"\bэлектрич\w*", r"\bтепло\w*", r"инженерн\w*\s+сет\w*",
    ],
}

_MULTIPLIERS = {
    "млрд": 1_000_000_000, "миллиард": 1_000_000_000,
    "млн": 1_000_000, "миллион": 1_000_000,
    "тыс": 1_000, "тысяч": 1_000,
}

# Слова-«шум»: отбрасываются из поискового запроса. Длинные — по префиксу,
# короткие — только точным совпадением (иначе «по» съело бы «поставка»).
_NOISE_PREFIX = [
    "найди", "найти", "ищу", "искать", "покажи", "показать", "нужны", "нужно", "хочу",
    "подбери", "подобрать", "выведи", "госзакупк", "закупк", "тендер", "аукцион",
    "пожалуйста", "какие", "интересу",
]
_NOISE_EXACT = ["все", "есть", "мне", "для", "по", "с", "на", "в", "и", "а", "мы"]


@dataclass
class ParsedQuery:
    text: str
    raw: str
    law: str | None = None
    region: str | None = None
    category: str | None = None
    nmck_min: float | None = None
    nmck_max: float | None = None
    smp_only: bool | None = None
    only_active: bool = False
    matched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_amount(num: str, unit: str | None) -> float:
    value = float(num.replace(" ", "").replace(",", "."))
    if unit:
        for key, mult in _MULTIPLIERS.items():
            if unit.startswith(key):
                return value * mult
    return value


_AMOUNT = r"(\d[\d\s]*(?:[.,]\d+)?)\s*(млрд|млн|тыс[а-я]*|миллион[а-я]*|миллиард[а-я]*)?\s*(?:руб[а-я.]*|₽|р\.)?"


def parse(query: str) -> ParsedQuery:
    raw = query or ""
    q = normalize(raw)
    pq = ParsedQuery(text=raw.strip(), raw=raw)

    # --- закон ---
    if re.search(r"44[\s-]*фз", q):
        pq.law = "44-ФЗ"
        pq.matched.append("закон 44-ФЗ")
    elif re.search(r"223[\s-]*фз", q):
        pq.law = "223-ФЗ"
        pq.matched.append("закон 223-ФЗ")

    # --- СМП ---
    if re.search(r"\bсмп\b|мал[а-я]* предприним|субъект[а-я]* мал", q):
        pq.smp_only = True
        pq.matched.append("только для СМП")

    # --- активные ---
    if re.search(r"актуальн|действующ|открыт|подача заяв|сейчас|принима", q):
        pq.only_active = True
        pq.matched.append("только приём заявок")

    # --- диапазон «от X до Y» ---
    m = re.search(rf"от\s+{_AMOUNT}\s+до\s+{_AMOUNT}", q)
    if m:
        pq.nmck_min = _parse_amount(m.group(1), m.group(2))
        pq.nmck_max = _parse_amount(m.group(3), m.group(4))
        pq.matched.append(f"НМЦК {pq.nmck_min:,.0f}–{pq.nmck_max:,.0f} ₽".replace(",", " "))
    else:
        m_max = re.search(rf"(?:до|не более|дешевле|менее|максимум)\s+{_AMOUNT}", q)
        if m_max and (m_max.group(2) or float(m_max.group(1).replace(" ", "")) >= 1000):
            pq.nmck_max = _parse_amount(m_max.group(1), m_max.group(2))
            pq.matched.append(f"НМЦК до {pq.nmck_max:,.0f} ₽".replace(",", " "))
        m_min = re.search(rf"(?:от|не менее|дороже|более|свыше|больше)\s+{_AMOUNT}", q)
        if m_min and (m_min.group(2) or float(m_min.group(1).replace(" ", "")) >= 1000):
            pq.nmck_min = _parse_amount(m_min.group(1), m_min.group(2))
            pq.matched.append(f"НМЦК от {pq.nmck_min:,.0f} ₽".replace(",", " "))

    # --- регион ---
    for region, pattern in REGION_PATTERNS:
        if re.search(pattern, q):
            pq.region = region
            pq.matched.append(f"регион: {region}")
            break

    # --- категория ---
    best, best_hits = None, 0
    for category, patterns in CATEGORY_PATTERNS.items():
        hits = sum(1 for p in patterns if re.search(p, q))
        if hits > best_hits:
            best, best_hits = category, hits
    if best and best_hits > 0:
        pq.category = best
        pq.matched.append(f"категория: {best}")

    # --- очищенный текст для поиска ---
    cleaned = q
    for pattern in (r"44[\s-]*фз", r"223[\s-]*фз", rf"(?:от|до|не более|не менее|свыше|менее|более)\s+{_AMOUNT}"):
        cleaned = re.sub(pattern, " ", cleaned)
    for noise in _NOISE_PREFIX:
        cleaned = re.sub(rf"\b{noise}\w*", " ", cleaned)
    for noise in _NOISE_EXACT:
        cleaned = re.sub(rf"\b{noise}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    pq.text = cleaned or raw.strip()
    return pq
