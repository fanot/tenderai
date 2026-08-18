"""Тесты разбора естественно-языкового запроса в структурные фильтры."""
import pytest

from app.rag import query_parser as qp


@pytest.mark.parametrize(
    "query,field,expected",
    [
        ("закупки по 44-ФЗ", "law", "44-ФЗ"),
        ("тендеры 223 ФЗ", "law", "223-ФЗ"),
        ("ремонт школы в Москве", "region", "г. Москва"),
        ("ремонт школы в Подмосковье", "region", "Московская область"),
        ("поставка в Питере", "region", "г. Санкт-Петербург"),
        ("закупки в Казани", "region", "Республика Татарстан"),
        ("разработка мобильного приложения", "category", "ИТ и разработка ПО"),
        ("поставка ноутбуков", "category", "Поставка вычислительной техники"),
        ("уборка помещений", "category", "Клининг и эксплуатация"),
        ("поставка лекарственных препаратов", "category", "Медицина и фармацевтика"),
        ("капитальный ремонт здания", "category", "Строительство и ремонт"),
    ],
)
def test_extract_scalar_filters(query, field, expected):
    assert getattr(qp.parse(query), field) == expected


@pytest.mark.parametrize(
    "query,nmck_min,nmck_max",
    [
        ("закупки до 20 млн", None, 20_000_000),
        ("тендеры от 5 млн", 5_000_000, None),
        ("контракты от 10 млн до 100 млн", 10_000_000, 100_000_000),
        ("закупки до 500 тыс рублей", None, 500_000),
        ("закупки до 1 млрд", None, 1_000_000_000),
    ],
)
def test_extract_budget(query, nmck_min, nmck_max):
    p = qp.parse(query)
    assert p.nmck_min == nmck_min
    assert p.nmck_max == nmck_max


def test_smp_and_active_flags():
    p = qp.parse("актуальные закупки для СМП")
    assert p.smp_only is True
    assert p.only_active is True


def test_noise_words_do_not_break_category():
    """«по» как предлог не должно превращать «поставку» в ИТ-категорию."""
    p = qp.parse("поставка продуктов питания по 44-ФЗ")
    assert p.category == "Продукты питания"


def test_cleaned_text_keeps_subject_terms():
    p = qp.parse("найди тендеры на разработку информационной системы до 20 млн")
    assert "разработ" in p.text
    assert "20" not in p.text
    assert "тендер" not in p.text


def test_empty_query_is_safe():
    p = qp.parse("")
    assert p.law is None and p.region is None and p.matched == []
