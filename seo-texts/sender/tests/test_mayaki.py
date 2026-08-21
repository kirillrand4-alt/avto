# -*- coding: utf-8 -*-
"""Маяки: разбор конфига, узнавание своих адресов и разворот темы из IMAP.

Маяк - наш собственный ящик у чужого почтовика (mail.ru, Яндекс, Gmail),
куда уходит копия письма, чтобы через час посмотреть по IMAP, в какой оно
папке. По SMTP папку узнать нельзя вовсе: разговор кончается на «250
принял».

Здесь проверяется то, что можно проверить без сети: список, пороги,
узнавание адреса и разбор MIME-кодированной темы. Сама раскладка по папкам
проверяется живым прогоном - для неё нужен настоящий ящик.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.mayaki import (Mayak, _dekod, eto_mayak,  # noqa: E402
                           nastroyki, spisok)


class _Конфиг:
    def __init__(self, д):
        self._д = д

    def get(self, ключ, по_умолчанию=None):
        return self._д.get(ключ, по_умолчанию)


ПРИМЕР = _Конфиг({
    "mayaki.vklyucheny": True,
    "mayaki.v_partiyu": 2,
    "mayaki.zaderzhka_min": 45,
    "mayaki.spisok": [
        {"email": "Proverka@Mail.RU", "provayder": "mail.ru",
         "imap_host": "imap.mail.ru", "parol_env": "MAYAK_1"},
        {"email": "proverka@yandex.ru", "provayder": "yandex",
         "imap_host": "imap.yandex.ru", "parol_env": "MAYAK_2",
         "papka_spam": "Спам"},
    ],
})


def test_nastroyki_po_umolchaniyu_vyklyucheny():
    """Пустой конфиг не должен молча включать отправку самим себе."""
    н = nastroyki(_Конфиг({}))
    assert н["включены"] is False
    assert н["в_партию"] == 1 and н["задержка_мин"] == 60


def test_nastroyki_chitayutsya():
    н = nastroyki(ПРИМЕР)
    assert н == {"включены": True, "в_партию": 2, "задержка_мин": 45}


def test_spisok_i_registr_adresa():
    м = spisok(ПРИМЕР)
    assert [x.email for x in м] == ["proverka@mail.ru", "proverka@yandex.ru"]
    assert м[0].imap_port == 993
    assert м[1].papka_spam == "Спам"


def test_uznayom_svoy_adres_nezavisimo_ot_registra():
    assert eto_mayak("PROVERKA@mail.ru", ПРИМЕР)
    assert eto_mayak(" proverka@yandex.ru ", ПРИМЕР)
    assert not eto_mayak("klient@zavod.ru", ПРИМЕР)
    assert not eto_mayak("", ПРИМЕР)


def test_musor_v_spiske_ne_ronyaet():
    к = _Конфиг({"mayaki.spisok": ["строка", {}, {"email": ""},
                                   {"email": "ok@mail.ru"}]})
    assert [м.email for м in spisok(к)] == ["ok@mail.ru"]


def test_parol_beryotsya_iz_okruzheniya_a_ne_iz_konfiga():
    м = spisok(ПРИМЕР)[0]
    os.environ.pop("MAYAK_1", None)
    assert м.parol() is None, "без переменной окружения пароля нет"
    os.environ["MAYAK_1"] = "секрет"
    try:
        assert м.parol() == "секрет"
    finally:
        os.environ.pop("MAYAK_1", None)


def test_tema_iz_imap_razvorachivaetsya():
    """Тему IMAP отдаёт в MIME-кодировке - без разворота сравнение не выйдет."""
    сырое = b"Subject: =?utf-8?B?0JLQvtC/0YDQvtGBINC/0L4g0LDQt9C+0YLRgw==?="
    assert "Вопрос по азоту" in _dekod(сырое)
    assert _dekod("Обычная тема") == "Обычная тема"
    assert _dekod(None) == ""


def test_polzovatel_dlya_imap():
    """Логин может отличаться от адреса - тогда берём логин."""
    assert Mayak(email="a@b.ru", provayder="", imap_host="h").polzovatel == "a@b.ru"
    assert Mayak(email="a@b.ru", provayder="", imap_host="h",
                 login="ящик1").polzovatel == "ящик1"
