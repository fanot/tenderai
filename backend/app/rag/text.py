"""Нормализация и токенизация русского текста без внешних зависимостей."""
from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)

STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все",
    "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по",
    "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему",
    "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть",
    "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом",
    "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней", "для",
    "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз",
    "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "им", "более", "всегда", "конечно", "всю", "между",
    "the", "a", "an", "of", "for", "and", "to", "in", "on", "is", "are",
}

# Лёгкий стеммер для русского: отсечение частотных окончаний.
_SUFFIXES = (
    "иями", "ями", "ами", "иях", "ах", "ях", "ов", "ев", "ий", "ый", "ой", "ая", "ое",
    "ые", "ий", "ем", "ом", "ам", "ум", "ах", "ую", "юю", "ее", "ие", "ия", "ью", "ья",
    "ов", "ей", "ий", "ые", "ых", "ым", "ми", "ть", "ся", "ет", "ут", "ют", "ат", "ят",
    "ал", "ил", "ла", "ло", "ли", "на", "ны", "ное", "ных", "ном", "ной", "у", "ю", "а",
    "я", "о", "е", "и", "ы", "ь", "й",
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return text.replace("ё", "е").lower()


def stem(token: str) -> str:
    """Грубый, но устойчивый стеммер: обрезает окончание, сохраняя основу >= 4 символов."""
    if len(token) <= 4 or token.isdigit():
        return token
    for suf in _SUFFIXES:
        if token.endswith(suf) and len(token) - len(suf) >= 4:
            return token[: -len(suf)]
    return token


def tokenize(text: str, *, use_stemming: bool = True, drop_stopwords: bool = True) -> list[str]:
    tokens = _WORD_RE.findall(normalize(text))
    if drop_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    if use_stemming:
        tokens = [stem(t) for t in tokens]
    return tokens


def char_ngrams(text: str, n: int = 4) -> list[str]:
    """Символьные n-граммы — устойчивы к опечаткам и словоформам."""
    s = f" {normalize(text)} "
    s = re.sub(r"[^а-яa-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    if len(s) < n:
        return [s.strip()] if s.strip() else []
    return [s[i : i + n] for i in range(len(s) - n + 1)]
