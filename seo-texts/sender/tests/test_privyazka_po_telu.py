# -*- coding: utf-8 -*-
"""Привязка по адресу в ТЕЛЕ письма — когда клиент переслал наше письмо.

Владелец 28.08: «проверь нет ли потерянных писем». Из 182 входящих без
привязки настоящих ответов оказалось три, и все пришли с публичных
почтовиков: клиент переслал наше письмо коллеге или ответил с личного
ящика. Ни отправитель, ни его домен не значат ничего — зато в теле лежит
цитата с адресом нашего получателя: «Кому: phlebolog-ufa@mail.ru».
"""
from sender.imap_watcher import ImapWatcher

ТЕЛО = """Добрый день! Для нас не актуально. Благодарю за предложение!

-------- Пересланное письмо --------
От: Клиника Флебологии phlebolog-ufa@mail.ru
Кому: Гузель Олейник olegraufa@mail.ru
Тема: Fwd: Вопрос по компрессорному оборудованию
> От кого: Игорь Ляпин <i.lyapin@kompressor-air-expert.ru>
> Кому: phlebolog-ufa@mail.ru
"""


class _Store:
    def __init__(self, известные):
        self._известные = известные

    def find_recipient_by_email(self, email):
        rid = self._известные.get((email or "").lower())
        return {"id": rid} if rid else None


class _Cfg:
    def __init__(self, ящики):
        self._я = ящики

    def mailboxes(self):
        return [type("M", (), {"mailbox_id": м})() for м in self._я]


def _вотчер(известные, ящики=("i.lyapin@kompressor-air-expert.ru",)):
    w = ImapWatcher.__new__(ImapWatcher)
    w._store = _Store(известные)
    w._config = _Cfg(ящики)
    return w


def test_nahodit_poluchatelya_v_citate():
    w = _вотчер({"phlebolog-ufa@mail.ru": 4044})
    assert w._recipient_by_telom(ТЕЛО) == 4044


def test_svoy_yashchik_ne_schitaetsya():
    """Наш адрес в цитате не должен привязывать письмо к нам самим."""
    w = _вотчер({"i.lyapin@kompressor-air-expert.ru": 999,
                 "phlebolog-ufa@mail.ru": 4044})
    assert w._recipient_by_telom(ТЕЛО) == 4044


def test_dva_raznyh_poluchatelya_ne_gadaem():
    w = _вотчер({"phlebolog-ufa@mail.ru": 4044,
                 "olegraufa@mail.ru": 5555})
    assert w._recipient_by_telom(ТЕЛО) is None


def test_odin_poluchatel_dvazhdy_v_tele_eto_odin():
    """Адрес встречается дважды — это по-прежнему один получатель."""
    w = _вотчер({"phlebolog-ufa@mail.ru": 4044})
    assert w._recipient_by_telom(ТЕЛО + "\nещё раз phlebolog-ufa@mail.ru") == 4044


def test_net_znakomyh_adresov():
    w = _вотчер({"kto-to@drugoy.ru": 1})
    assert w._recipient_by_telom(ТЕЛО) is None


def test_pustoe_telo():
    w = _вотчер({"phlebolog-ufa@mail.ru": 4044})
    assert w._recipient_by_telom("") is None
    assert w._recipient_by_telom(None) is None


def test_sboy_poiska_ne_ronyaet():
    class _Плохой:
        def find_recipient_by_email(self, email):
            raise RuntimeError("база недоступна")
    w = ImapWatcher.__new__(ImapWatcher)
    w._store = _Плохой()
    w._config = _Cfg(())
    assert w._recipient_by_telom(ТЕЛО) is None
