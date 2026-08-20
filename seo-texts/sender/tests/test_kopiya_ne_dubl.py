"""Копия на второй адрес компании не должна сниматься как дубль.

Утренний заслон 20.08 снимает письмо, если компании УЖЕ писали — по
адресу или по ИНН. Он ловил настоящую беду: два прогона ставили в очередь
два письма одной фирме, и оба уходили.

Но копия — другое. Автоответ компании прямо называет коллегу («обращаться
к моей коллеге, Гадецких Ольге»), мы пишем ему по имени, и по ИНН
отправка у компании, конечно, уже есть. Заслон снял бы такое письмо.

Различаем по пометке в причине карточки, которую ставит человек при
разборе копий. Тому же АДРЕСУ дважды не пишем ни при какой пометке.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from sender.auto_send import AutoSendLoop  # noqa: E402


class ЛожныйStore:
    def __init__(self, флаги):
        self.флаги = флаги
        self.снято = []
        self.спрошено = []

    def sent_flags(self, emails=None, inns=None):
        self.спрошено.append((tuple(emails or ()), tuple(inns or ())))
        из_ = {}
        for к in list(emails or []) + list(inns or []):
            if к in self.флаги:
                из_[к] = self.флаги[к]
        return из_

    def mark_skipped(self, mid, reason):
        self.снято.append((mid, reason))


def _проверка(store, review, инн):
    """Тот же кусок, что в _send_one: спрашиваем флаги и решаем."""
    почта = str(review.get("email") or "").strip().lower()
    _копия = "копия на второй адрес" in str(review.get("reason") or "").lower()
    флаги = store.sent_flags(
        emails=[почта] if почта else None,
        inns=None if _копия else ([инн] if инн else None)) or {}
    след = флаги.get(почта) or ({} if _копия else (флаги.get(инн) or {}))
    return bool(след.get("ever"))


ИНН = "7701234567"


def test_obychnyy_dubl_po_inn_snimaetsya():
    store = ЛожныйStore({ИНН: {"ever": True, "last_ts": "2026-08-19"}})
    review = {"email": "new@firma.ru", "reason": ""}
    assert _проверка(store, review, ИНН) is True


def test_kopiya_po_inn_ne_snimaetsya():
    store = ЛожныйStore({ИНН: {"ever": True, "last_ts": "2026-08-19"}})
    review = {"email": "kollega@firma.ru",
              "reason": "копия на второй адрес (одобрено человеком)"}
    assert _проверка(store, review, ИНН) is False


def test_kopiya_na_tot_zhe_adres_vsyo_ravno_snimaetsya():
    """Пометка не отменяет главного: одному адресу дважды не пишем."""
    store = ЛожныйStore({"kollega@firma.ru": {"ever": True}})
    review = {"email": "kollega@firma.ru",
              "reason": "копия на второй адрес (одобрено человеком)"}
    assert _проверка(store, review, ИНН) is True


def test_u_kopii_inn_voobshche_ne_sprashivaetsya():
    """Лишний вопрос к базе - лишняя цена; проверяем, что его нет."""
    store = ЛожныйStore({})
    review = {"email": "kollega@firma.ru",
              "reason": "копия на второй адрес (одобрено человеком)"}
    _проверка(store, review, ИНН)
    assert store.спрошено == [(("kollega@firma.ru",), ())]


def test_kod_zaslona_na_meste_v_auto_send():
    """Проверка живёт в _send_one, а не только в тесте."""
    import inspect
    исходник = inspect.getsource(AutoSendLoop._send_one)
    assert "копия на второй адрес" in исходник
    assert "auto_send:уже писали" in исходник
