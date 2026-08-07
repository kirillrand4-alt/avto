"""Метка направления обязана доезжать от базы обзвона до генератора.

Инцидент 07.08: «ТОКК Металлпак» (жестяная банка, метка kc, партия
металлообработки) получил письмо про рентген-инспекцию Meyer. Разбор показал
дыру в проводке: ai_quota._request возвращал company_name/okved/activity/extra
и НЕ клал метку направления, поэтому правило base_label в target_division не
могло сработать в принципе. Решал профиль — а в описании компании стоит
«консервная промышленность», пищевой маркер Meyer.

Проверяю оба конца: что _request кладёт метку и что с ней выбор направления
меняется на правильный.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.ai_letter import target_division  # noqa: E402

# Реальный вход «ТОКК Металлпак»: в категориях И компрессоры, И фотосепараторы,
# поэтому правило «по потребностям» молчит (направлений два).
ТОКК = {
    "company_name": 'ООО "ТОКК МЕТАЛЛПАК"',
    "okved": "25.92",
    "activity": "производство металлической упаковки для консервной промышленности",
    "mode": "GENERIC",
    "extra": {"equipment": ("Промышленные компрессоры от 200 000 ₽ | "
                            "Фотосепараторы | Генераторы азота | "
                            "МКС — мобильные компрессорные станции")},
}


def test_bez_metki_vybor_uezzhaet_v_meyer():
    """Так было: метки нет -> решает профиль -> «консервная» тянет в Meyer."""
    d, почему = target_division(ТОКК, default="kc")
    assert (d, почему) == ("meyer", "profile")


def test_s_metkoy_vybor_pravilnyy():
    d, почему = target_division(dict(ТОКК, division="kc"), default="kc")
    assert (d, почему) == ("kc", "base_label")


def test_metka_ne_bet_novost_i_potrebnost():
    """Метка стоит НИЖЕ новости и однозначной потребности — так и остаётся."""
    новостное = dict(ТОКК, division="kc", mode="NEWS",
                     extra={"news_object": "линия оптической сортировки зерна",
                            "city": "Курск"})
    d, почему = target_division(новостное, default="kc")
    assert d == "meyer" and почему in ("news", "news_over_needs")

    одна_потребность = dict(ТОКК, division="meyer",
                            extra={"equipment": "Промышленные компрессоры от 200 000 ₽"})
    d2, почему2 = target_division(одна_потребность, default="kc")
    assert (d2, почему2) == ("kc", "needs")


def _quota(segment: str, категории: str, *, настройка=None):
    """AiQuota без БД и провайдера: подменены карточка и настройки."""
    from sender.ai_quota import AiQuota

    q = AiQuota.__new__(AiQuota)
    q._digest = lambda inn: {}
    q._card_for = lambda inn: {
        "obzvon": {"division": "kc", "equip_categories": категории},
        "enrich": {"company": {
            "activity": "производство металлической упаковки для консервной "
                        "промышленности"}}}
    q._cards = lambda: None

    class _Store:
        def get_setting(self, key, default=None):
            return настройка if key == "segment_division" else default

    q._store = _Store()

    class _R:
        inn = "5040192940"
        email = "info@tokkmetallpack.ru"
        company_name = 'ООО "ТОКК МЕТАЛЛПАК"'
        okved = "25.92"
        contact_name = ""
        extra = {}

    _R.segment = segment
    return q, _R()


ОБА = "Промышленные компрессоры от 200 000 ₽ | Фотосепараторы"


def test_request_kladyot_metku_i_partiyu():
    q, r = _quota("металлообработка", ОБА)
    req = q._request(r)
    assert req["division"] == "kc"
    assert req["segment"] == "металлообработка"
    assert req["target_division"] == "kc"          # партия решает явно
    d, почему = target_division(dict(req, mode="GENERIC"), default="kc")
    assert (d, почему) == ("kc", "explicit")


def test_partiya_bet_dazhe_odnoznachnuyu_potrebnost():
    """Только фотосепараторы в категориях, но партия компрессорная — kc.

    Без этого правила метки мало: «однозначная потребность» стоит выше неё,
    и письмо всё равно уехало бы в Meyer."""
    q, r = _quota("металлообработка", "Фотосепараторы")
    req = q._request(r)
    d, почему = target_division(dict(req, mode="GENERIC"), default="kc")
    assert (d, почему) == ("kc", "explicit")


def test_novostnaya_partiya_ne_forsiruetsya():
    """У новостных направление обязан выбирать повод, а не партия."""
    q, r = _quota("новостные", "Фотосепараторы")
    req = q._request(r)
    assert req["target_division"] is None
    d, _ = target_division(dict(req, mode="GENERIC"), default="kc")
    assert d == "meyer"                            # потребность решает сама


def test_kartu_mozhno_pravit_nastroykoy():
    q, r = _quota("пищёвка", ОБА, настройка={"пищёвка": "meyer"})
    assert q._request(r)["target_division"] == "meyer"
    # пустое значение снимает правило
    q2, r2 = _quota("металлообработка", ОБА,
                    настройка={"металлообработка": ""})
    assert q2._request(r2)["target_division"] is None
