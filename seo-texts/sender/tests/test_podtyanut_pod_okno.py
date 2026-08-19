# -*- coding: utf-8 -*-
"""Расширили окно — очередь подтянулась.

19.08: 107 одобренных писем отложили на завтра 09:00, потому что в момент
прохода окно кончалось в 11:00. Через час владелец продлил окно до 15:00, а
письма всё равно остались стоять до утра: claim_approved_due смотрит только
scheduled_at. Подтяжка чинит именно это — и только в сторону «раньше».
"""
from datetime import datetime, timezone

from sender.auto_send import podtyanut_pod_okno

ОКНО_УЗКОЕ = {"days": [1, 2, 3, 4, 5], "start": "09:00", "end": "11:00",
              "tz": "Europe/Moscow", "by_recipient_tz": True}
ОКНО_ШИРОКОЕ = dict(ОКНО_УЗКОЕ, end="15:00")
# среда, 12:30 МСК = 09:30 UTC: узкое окно закрыто, широкое открыто
СЕЙЧАС = datetime(2026, 8, 19, 9, 30, tzinfo=timezone.utc)


class _Получатель:
    def __init__(self, rid, tz):
        self.id = rid
        self.tz = tz


class _Хранилище:
    """Минимальный store: только то, чем пользуется подтяжка."""

    def __init__(self, письма, зоны=None):
        # письма: {mid: (rid, scheduled_at)}
        self.письма = dict(письма)
        self.зоны = зоны or {}
        self.переносы: list = []

    def approved_scheduled_after(self, porog):
        return [(mid, rid, sched)
                for mid, (rid, sched) in sorted(self.письма.items())
                if sched > porog]

    def get_recipient(self, rid):
        return _Получатель(rid, self.зоны.get(rid))

    def reschedule_message(self, mid, when):
        стало = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        rid, _ = self.письма[mid]
        self.письма[mid] = (rid, стало)
        self.переносы.append((mid, стало))
        return True


def test_рассширенное_окно_подтягивает_отложенные():
    st = _Хранилище({1: (11, "2026-08-20T06:00:00"),
                     2: (12, "2026-08-20T06:00:00")})
    n = podtyanut_pod_okno(st, ОКНО_ШИРОКОЕ, СЕЙЧАС)
    assert n == 2
    assert all(с == "2026-08-19T09:30:00" for _m, с in st.переносы)


def test_узкое_окно_ничего_не_тянет():
    """Окно закрыто — next_slot даёт завтра, раньше не станет."""
    st = _Хранилище({1: (11, "2026-08-20T06:00:00")})
    assert podtyanut_pod_okno(st, ОКНО_УЗКОЕ, СЕЙЧАС) == 0
    assert st.переносы == []


def test_назначенное_на_сегодня_не_трогаем():
    """Разгон внутри дня — осознанный: письмо на 09:31 и на 14:00 сегодня
    остаётся как назначено, подтяжка спасает только застрявших на завтра."""
    st = _Хранилище({1: (11, "2026-08-19T09:31:00"),
                     2: (12, "2026-08-19T11:00:00")})
    assert podtyanut_pod_okno(st, ОКНО_ШИРОКОЕ, СЕЙЧАС) == 0
    assert st.переносы == []


def test_зона_получателя_учитывается():
    """Сахалин (UTC+11): 09:30 UTC = 20:30 у получателя — его час закрыт,
    письмо остаётся на завтра, московское — подтягивается."""
    st = _Хранилище({1: (11, "2026-08-20T06:00:00"),
                     2: (12, "2026-08-19T22:00:00")},
                    зоны={11: "Europe/Moscow", 12: "Asia/Sakhalin"})
    assert podtyanut_pod_okno(st, ОКНО_ШИРОКОЕ, СЕЙЧАС) == 1
    assert [m for m, _ in st.переносы] == [1]


def test_store_без_метода_не_роняет():
    class _Старый:
        pass
    assert podtyanut_pod_okno(_Старый(), ОКНО_ШИРОКОЕ, СЕЙЧАС) == 0


def test_сбой_одного_письма_не_рвёт_подтяжку():
    class _Кривой(_Хранилище):
        def get_recipient(self, rid):
            if rid == 11:
                raise RuntimeError("получатель не читается")
            return super().get_recipient(rid)

    st = _Кривой({1: (11, "2026-08-20T06:00:00"),
                  2: (12, "2026-08-20T06:00:00")})
    assert podtyanut_pod_okno(st, ОКНО_ШИРОКОЕ, СЕЙЧАС) == 1


def test_cikl_podtyagivaet_sam():
    """Цикл автоотправки лечит очередь сам, без сохранения окна в панели:
    окно могли расширить и правкой конфига, и рестартом."""
    from sender.auto_send import AutoSendLoop

    класс = _Хранилище({1: (11, "2026-08-20T06:00:00")})

    class _Полный(type(класс)):
        def get_setting(self, key, default=None):
            return ОКНО_ШИРОКОЕ if key == "sending_window" else default

        def claim_approved_due(self, **kw):
            return []

    st = _Полный({1: (11, "2026-08-20T06:00:00")})
    st.get_setting = lambda key, default=None: (               # noqa: E731
        ОКНО_ШИРОКОЕ if key == "sending_window" else
        (True if key == "auto_send_enabled" else default))
    цикл = AutoSendLoop(store=st, config=object(), live_sender=object())
    цикл.tick(now=СЕЙЧАС)
    assert st.переносы == [(1, "2026-08-19T09:30:00")]


def test_ne_shlyom_dvazhdy_odnomu_adresu():
    """Два письма одной компании из разных прогонов — не повод писать дважды.

    Заслон свежего контакта живёт на ВХОДЕ в очередь и срабатывает в момент
    постановки: два письма, поставленные разными прогонами, оба проходят его
    законно — на тот момент ни одно ещё не отправлено. 19.08 так
    zakupka@syrodelovo.ru получил два мейеровских письма, в 03:57 и в 06:01.
    Теперь цикл перепроверяет след перед самой отправкой.
    """
    from datetime import datetime, timezone

    from sender.auto_send import AutoSendLoop

    ОКНО = {"days": [1, 2, 3, 4, 5], "start": "09:00", "end": "18:00",
            "tz": "Europe/Moscow", "by_recipient_tz": False}
    СЕЙЧАС = datetime(2026, 8, 19, 9, 30, tzinfo=timezone.utc)

    class _Письмо:
        id, recipient_id, campaign_id = 7, 11, 10

    class _Ст:
        def __init__(self):
            self.снято = []
            self.отдал = False

        def get_setting(self, key, default=None):
            return (ОКНО if key == "sending_window"
                    else True if key == "auto_send_enabled" else default)

        def claim_approved_due(self, **kw):
            if self.отдал:
                return []
            self.отдал = True
            return [_Письмо()]

        def confirm_review_for_message(self, mid):
            return {"subject": "т", "body": "б", "email": "a@b.ru"}

        def get_recipient(self, rid):
            return type("R", (), {"id": rid, "email": "a@b.ru",
                                  "inn": "7810526387", "tz": None})()

        def get_campaign(self, cid):
            return type("C", (), {"id": cid})()

        def sent_flags(self, emails=None, inns=None):
            return {"a@b.ru": {"ever": True, "last_ts": "2026-08-19T03:57",
                               "replied": False, "within_90d": True}}

        def mark_skipped(self, mid, reason):
            self.снято.append((mid, reason))

        def approved_scheduled_after(self, porog):
            return []

    st = _Ст()
    цикл = AutoSendLoop(store=st, config=object(), live_sender=object())
    из = цикл.tick(now=СЕЙЧАС)
    assert из["skipped"] == 1, из
    assert st.снято and "уже писали" in st.снято[0][1]
