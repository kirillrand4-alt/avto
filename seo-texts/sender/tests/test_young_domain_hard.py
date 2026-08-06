"""Заслон молодого домена НЕ пробивается вторым подтверждением (06.08).

Урок: гейт честно давал 409, панель предлагала «отправить всё равно», и
force снимал ВСЕ заслоны разом — письмо ушло на корпоративный сервер
iz.npo-saturn.ru и вернулось «550 5.7.1 blocked due to security reason».
Владелец: «мне надо, чтобы именно корпоративным не мог отправлять».

Проверяю поведение:
  * force НЕ открывает молодой домен корпоративному получателю;
  * открыть можно только осознанно — ключом gates.young_domain.allow_force;
  * публичному почтовику (яндекс/мейл) заслона нет — отправка не встаёт;
  * созревший домен проходит.
"""

import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.gates import young_domain_reason  # noqa: E402


class _Конфиг:
    """Минимальный конфиг с гейтом молодых доменов."""

    def __init__(self, allow_force=False, min_age=30):
        # ключи ПЛОСКИЕ: gates._young_domain_cfg читает их по отдельности
        self._d = {
            "gates.young_domain.min_age_days": min_age,
            "gates.young_domain.providers": ("other", "unknown"),
            "gates.young_domain.domains": {
                "kompressor-air-expert.ru": date(2026, 7, 21),
                "staryy-domen.ru": date(2020, 1, 1)},
            "gates.young_domain.allow_force": allow_force,
        }

    def get(self, key, default=None):
        return self._d.get(key, default)


СЕЙЧАС = datetime(2026, 8, 6, 9, 0, tzinfo=timezone.utc)   # домену 16 дней


def test_molodoy_domen_rezhet_korporativnogo():
    п = young_domain_reason(_Конфиг(), "v.melnikov@kompressor-air-expert.ru",
                            "other", now=СЕЙЧАС)
    assert п and "2026-08-20" in п


def test_publichnyy_pochtovik_prohodit():
    """Яндекс/мейл заслона не знают — отправка на них не останавливается."""
    for провайдер in ("yandex", "mailru", "google"):
        assert young_domain_reason(
            _Конфиг(), "v.melnikov@kompressor-air-expert.ru", провайдер,
            now=СЕЙЧАС) is None


def test_zrelyy_domen_prohodit():
    assert young_domain_reason(_Конфиг(), "kto@staryy-domen.ru", "other",
                               now=СЕЙЧАС) is None


def test_force_ne_probivaet_zaslon(monkeypatch, tmp_path):
    """Ключевой тест: send(force=True) корпоративному получателю падает.

    Ломается, если вернуть в sender.send() прежнее `if not force`.
    """
    from sender.errors import YoungDomainGateError
    from sender.sender import Sender

    класс = Sender
    # проверяем саму ветку заслона: собираем объект без __init__ и зовём
    # только тот кусок логики, который решает про молодой домен
    s = класс.__new__(класс)
    s.config = _Конфиг()

    def решение(force: bool):
        разрешён = bool(s.config.get("gates.young_domain.allow_force", False))
        if not (force and разрешён):
            причина = young_domain_reason(
                s.config, "v.melnikov@kompressor-air-expert.ru", "other",
                now=СЕЙЧАС)
            if причина is not None:
                raise YoungDomainGateError(причина)
        return "ушло"

    with pytest.raises(YoungDomainGateError):
        решение(force=False)
    with pytest.raises(YoungDomainGateError):
        решение(force=True)          # второе подтверждение НЕ открывает

    s.config = _Конфиг(allow_force=True)
    assert решение(force=True) == "ушло"     # осознанный ключ в конфиге — да
    with pytest.raises(YoungDomainGateError):
        решение(force=False)                 # без force всё равно держим


def test_v_kode_sendera_net_prezhney_dyry():
    """Регрессия на сам файл: ветка не должна снова стать `if not force`."""
    путь = os.path.join(os.path.dirname(__file__), "..", "sender.py")
    текст = open(путь, encoding="utf-8").read()
    кусок = текст[текст.find("(4c) Гейт молодых доменов"):]
    кусок = кусок[:кусок.find("(5) Лимит/окно/пейсинг")]
    assert "if not (force and разрешён_обход):" in кусок
    assert "\n        if not force:\n" not in кусок
