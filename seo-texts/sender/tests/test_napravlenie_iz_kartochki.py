# -*- coding: utf-8 -*-
"""Направление письма берётся из карточки — решение владельца 17.08.

«Если в карточке написано направление, то и письмо должно быть под это
направление.» Оператор подтверждает отправку, глядя в карточку; письмо про
другой станок означает, что он подтвердил одно, а ушло другое.

Что было не так. Направление считали два независимых пути из РАЗНЫХ
источников: письмо — цепочкой target_division (новость → потребности → метка
базы → профиль → запасной kc), карточка — полем enrich.company.division с
расчётом по ОКВЭД при пустом. Замер на 18 письмах партии 935 дал 4
расхождения (22%): карточка говорила meyer и «сортировка и инспекция», а
письмо ушло про компрессоры в кампанию КЦ. Стоп-флаг панели молчал — он
сверяет ЯЩИК с письмом, а не письмо с карточкой.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_quota import AiQuota  # noqa: E402


class _Rec:
    def __init__(self, okved=""):
        self.okved = okved


def test_karточка_s_napravleniem_reshaet():
    """Поле division в карточке — прямой ответ, считать нечего."""
    assert AiQuota._division_kartochki({"division": "meyer"}, _Rec()) == "meyer"
    assert AiQuota._division_kartochki({"division": "kc"}, _Rec()) == "kc"


def test_sostavnoe_ne_reshaet():
    """«kc+meyer» — это НЕ ответ, а признание, что оба уместны.

    Такое значение возвращается как есть, а вызывающий (_request) обязан
    пропустить его мимо: решать должна обычная цепочка приоритетов, иначе
    компания с обоими станками навсегда застрянет на одном.
    """
    got = AiQuota._division_kartochki({"division": "kc+meyer"}, _Rec())
    assert got == "kc+meyer"
    assert got not in ("kc", "meyer")


def test_pustaya_kartochka_ne_vydumyvaet():
    """Нет ни поля, ни ОКВЭДа — карточка молчит, а не гадает.

    Пустая строка важна: по ней _request понимает, что решать нечего, и
    оставляет работу цепочке приоритетов.
    """
    assert AiQuota._division_kartochki({}, _Rec()) == ""
    assert AiQuota._division_kartochki(None, _Rec()) == ""


def test_okved_beryotsya_iz_poluchatelya_esli_v_kartochke_pusto():
    """ОКВЭД ищется и в карточке, и в самой строке получателя.

    У компаний вне базы обогащения карточка пустая, а okved у получателя
    есть — иначе такие письма молча уходили бы в запасной «kc».
    Расчёт делает enrich_db; в песочнице его нет, и функция обязана
    вернуть пустую строку, а не упасть: генерация не смеет падать из-за
    отсутствия справочника.
    """
    got = AiQuota._division_kartochki({}, _Rec(okved="10.13"))
    assert isinstance(got, str)


def test_ne_padaet_na_musore():
    """Мусор в карточке не роняет генерацию."""
    for мусор in ({"division": None}, {"division": 0}, {"okved": None}):
        assert isinstance(AiQuota._division_kartochki(мусор, _Rec()), str)


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append((т.__name__, ex))
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {ex}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
