"""Окно авто-отправки «по времени получателя» (владелец 06.08).

Проверяю не «флаг сохранился», а поведение, ради которого он заведён:

  * выключен — воротник рубит час не по московскому окну, как и раньше;
  * включён  — час отдан расписанию письма (его считает cadence в зоне
    получателя), а воротник держит только ДНИ и праздники. Иначе два механизма
    дерутся: планировщик ставит 09:30 по Владивостоку, а воротник видит 02:30
    по Москве и не пускает — ровно то, ради чего тумблер и нужен;
  * дни недели и праздники продолжают работать в обоих режимах — тумблер не
    должен превращаться в «шли когда угодно».

Тест обязан уметь провалиться: уберите ветку `по_получателю` — падает второй
случай.
"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


class _Хранилище:
    """Минимальный стор: отдаёт только настройку окна."""

    def __init__(self, окно):
        self._окно = окно

    def get_setting(self, key, default=None):
        return self._окно if key == "sending_window" else default


class _Конфиг:
    def sending_window(self):
        from sender.config import WindowCfg
        return WindowCfg(tz="Europe/Moscow", days=(1, 2, 3, 4, 5),
                         start="09:00", end="11:00")

    def holidays(self):
        return set()

    def get(self, key, default=None):
        return {"timezone": "Europe/Moscow"}.get(key, default)


def _воротник(окно):
    """Sender с подменёнными стором и конфигом — берём только _within_window."""
    from sender.sender import Sender
    s = Sender.__new__(Sender)          # без __init__: нужен один метод
    s.store = _Хранилище(окно)
    s.config = _Конфиг()
    return s


ОКНО = {"days": [1, 2, 3, 4, 5], "start": "09:00", "end": "11:00",
        "tz": "Europe/Moscow"}
# среда, 02:30 по Москве = 09:30 по Владивостоку
УТРО_ВЛАДИВОСТОКА = datetime(2026, 8, 5, 23, 30, tzinfo=timezone.utc)
# среда, 10:00 по Москве — внутри окна в любом режиме
УТРО_МОСКВЫ = datetime(2026, 8, 5, 7, 0, tzinfo=timezone.utc)
# воскресенье, 10:00 по Москве — день не разрешён
ВОСКРЕСЕНЬЕ = datetime(2026, 8, 9, 7, 0, tzinfo=timezone.utc)


def test_vyklyuchen_rubit_utro_vladivostoka():
    """Старое поведение: 09:30 по Владивостоку это 02:30 по Москве — не пускаем."""
    s = _воротник(dict(ОКНО, by_recipient_tz=False))
    assert s._within_window(УТРО_ВЛАДИВОСТОКА) is False  # noqa: SLF001


def test_vklyuchen_propuskaet_utro_vladivostoka():
    """Включённый тумблер отдаёт час расписанию письма, которое считано в зоне
    получателя, — иначе дальневосточные письма не уйдут никогда."""
    s = _воротник(dict(ОКНО, by_recipient_tz=True))
    assert s._within_window(УТРО_ВЛАДИВОСТОКА) is True  # noqa: SLF001


def test_dni_nedeli_rabotayut_v_oboih_rezhimah():
    """Тумблер не отменяет дни: воскресенье закрыто и с ним, и без него."""
    for флаг in (False, True):
        s = _воротник(dict(ОКНО, by_recipient_tz=флаг))
        assert s._within_window(ВОСКРЕСЕНЬЕ) is False, флаг  # noqa: SLF001


def test_prazdnik_zakryt_v_oboih_rezhimah(monkeypatch):
    """И праздники: 09:30 по Владивостоку в праздник всё равно нельзя."""
    class _КонфигСПраздником(_Конфиг):
        def holidays(self):
            return {УТРО_ВЛАДИВОСТОКА.date(),
                    datetime(2026, 8, 6).date()}

    for флаг in (False, True):
        s = _воротник(dict(ОКНО, by_recipient_tz=флаг))
        s.config = _КонфигСПраздником()
        assert s._within_window(УТРО_ВЛАДИВОСТОКА) is False, флаг  # noqa: SLF001


def test_moskva_prohodit_v_oboih_rezhimah():
    """Обычное московское утро внутри окна проходит при любом положении."""
    for флаг in (False, True):
        s = _воротник(dict(ОКНО, by_recipient_tz=флаг))
        assert s._within_window(УТРО_МОСКВЫ) is True, флаг  # noqa: SLF001
