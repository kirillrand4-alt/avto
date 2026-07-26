"""Регрессия на дефекты ревью 26.07 в генераторе писем (№20/24/26/27/28)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sender.ai_letter import gate, allowed_numbers  # noqa: E402

BASE_OK = ("Здравствуйте! Видел, что вы запускаете новый цех по переработке. "
           "Под такие линии обычно нужен воздух стабильного качества, и мы как раз "
           "поставляем винтовые компрессоры с ресивером и осушителем. Подскажите, "
           "кто у вас отвечает за подготовку сжатого воздуха, чтобы я отправил "
           "конкретный расчёт под вашу мощность и не тратил ваше время впустую. "
           "Если тема не ваша, так и напишите, больше не побеспокою.\n\nС уважением,")


def test_placeholder_in_square_brackets_is_caught():
    """№24: «[Название компании]» — такой шаблон стоит в самих RULES."""
    body = BASE_OK.replace("Здравствуйте!", "Здравствуйте, [Название компании]!")
    fails = gate("тема", body, mode="NEWS", extra={}, facts={})
    assert any("плейсхолдер" in f for f in fails), fails


def test_inn_from_extra_does_not_whitelist_numbers():
    """№27: ИНН из extra не должен открывать дорогу выдуманным числам."""
    nums = allowed_numbers({}, {"inn": "7725104641", "news_sum": "300 млн"})
    assert "7725104641" not in nums      # ИНН не в белом списке
    assert "300" in nums                  # а факт новости — да


def test_digits_in_company_name_are_not_false_reject():
    """№28: «ЭТК № 2» — цифра из названия не должна браковать письмо."""
    body = BASE_OK.replace("Здравствуйте!", "Здравствуйте! Знаю ЭТК № 2.")
    fails = gate("тема", body, mode="NEWS",
                 extra={"company_name": "ЭТК № 2"}, facts={})
    assert not any("непроверенные числа" in f for f in fails), fails


def test_digits_not_in_name_still_rejected():
    """Гейт не должен ослабнуть: выдуманное число по-прежнему брак."""
    body = BASE_OK.replace("Здравствуйте!", "Здравствуйте! У нас 9999 проектов.")
    fails = gate("тема", body, mode="NEWS",
                 extra={"company_name": "ЭТК № 2"}, facts={})
    assert any("непроверенные числа" in f for f in fails), fails
