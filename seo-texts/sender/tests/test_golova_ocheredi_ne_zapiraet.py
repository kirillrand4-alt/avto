# -*- coding: utf-8 -*-
"""Непроходимое письмо в голове очереди не должно запирать всю отправку.

18.08, полтора часа простоя при свободных ящиках. Цикл берёт партию из
десяти писем по возрасту (ORDER BY scheduled_at, id LIMIT batch). Первые
десять оказались адресованы получателям на mail.ru, а весь наш mail.ru-пул
был закрыт: четыре ящика под гейтом репутации, два выбрали дневной лимит.
Проход возвращал эту десятку в очередь и заканчивался — и так каждую
минуту. Письмо №11, у которого и окно открыто, и ящик свободен, не уходило
никогда.

Замер после расшивки затора: письма пошли в ту же секунду, шестью ящиками
сразу.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.auto_send import AutoSendLoop  # noqa: E402

СЕЙЧАС = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


class _Письмо:
    def __init__(self, mid, пул):
        self.id = mid
        self.пул = пул
        self.recipient_id = mid
        self.campaign_id = 10


class _Store:
    """Очередь: сначала десять непроходимых, потом отправимые."""

    def __init__(self, письма):
        self.письма = list(письма)
        self.отдано: list = []
        self.освобождено: list = []

    def get_setting(self, key, default=None):
        return True if key == "auto_send_enabled" else default

    def claim_approved_due(self, *, now, limit, skip_ids=None):
        пропуск = set(skip_ids or ())
        взято = [m for m in self.письма if m.id not in пропуск][:limit]
        self.отдано.extend(m.id for m in взято)
        return взято

    def release_message(self, mid):
        self.освобождено.append(mid)

    def reschedule_message(self, mid, когда):
        pass

    def mark_failed(self, mid, причина, retryable=False):
        pass

    def mark_skipped(self, mid, причина):
        pass


class _Sender:
    """Ящик даёт только письмам «яндексового» пула."""

    def __init__(self):
        self.отправлено: list = []

    def pick_mailbox(self, recipient, campaign, *, now=None, message=None):
        return "box@ya.ru" if getattr(message, "пул", "") == "yandex" else None

    def send(self, m, rendered, mailbox_id, *, now=None, to_email=None):
        self.отправлено.append(m.id)
        return type("Res", (), {"ok": True, "error": None})()


def _цикл(письма, batch=10):
    store = _Store(письма)
    цикл = AutoSendLoop(store=store, config=_Config(), live_sender=_Sender(),
                        batch=batch)
    # заглушки того, что цикл спрашивает у стора по каждому письму
    store.confirm_review_for_message = lambda mid: {
        "subject": "Тема", "body": "Текст", "email": "a@b.ru"}
    store.get_recipient = lambda rid: type("R", (), {"email": "a@b.ru",
                                                     "tz": "Europe/Moscow"})()
    store.get_campaign = lambda cid: type("C", (), {"id": cid,
                                                    "provider_pool": None})()
    return цикл, store


class _Config:
    def get(self, key, default=None):
        return default

    def sending_window(self):
        return type("W", (), {"days": (1, 2, 3, 4, 5), "start": "00:00",
                              "end": "23:59", "tz": "Europe/Moscow"})()

    def holidays(self):
        return set()


ЗАПЕРТЫЕ = [_Письмо(i, "mailru") for i in range(1, 11)]
ОТПРАВИМЫЕ = [_Письмо(i, "yandex") for i in range(11, 16)]


def test_prohod_idyot_dalshe_zapertoy_golovy():
    цикл, store = _цикл(ЗАПЕРТЫЕ + ОТПРАВИМЫЕ)
    итог = цикл.tick(now=СЕЙЧАС)
    assert итог["sent"] == 5, итог
    assert sorted(цикл.sender.отправлено) == [11, 12, 13, 14, 15]
    assert итог["released"] == 10


def test_zapertye_vozvrashcheny_a_ne_poteryany():
    цикл, store = _цикл(ЗАПЕРТЫЕ + ОТПРАВИМЫЕ)
    цикл.tick(now=СЕЙЧАС)
    assert sorted(store.освобождено) == list(range(1, 11))


def test_odno_pismo_ne_beryotsya_dvazhdy_za_prohod():
    цикл, store = _цикл(ЗАПЕРТЫЕ + ОТПРАВИМЫЕ)
    цикл.tick(now=СЕЙЧАС)
    assert len(store.отдано) == len(set(store.отдано)), store.отдано


def test_vsya_ochered_neprohodima_prohod_konechen():
    """Если слать некуда вообще — проход обязан закончиться, а не крутиться."""
    цикл, store = _цикл(list(ЗАПЕРТЫЕ))
    итог = цикл.tick(now=СЕЙЧАС)
    assert итог["sent"] == 0 and итог["released"] == 10


def test_partiya_ogranichivaet_otpravku():
    """batch — это потолок ОТПРАВЛЕННЫХ за проход, а не просмотренных."""
    цикл, store = _цикл(ЗАПЕРТЫЕ + [_Письмо(i, "yandex")
                                    for i in range(11, 30)], batch=3)
    итог = цикл.tick(now=СЕЙЧАС)
    assert итог["sent"] == 3, итог


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:200]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
