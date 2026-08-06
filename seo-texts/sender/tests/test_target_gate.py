"""Гейт адресата: покупает ли компания то, что мы продаём.

Проверяю поведение, а не наличие кода:

  * режем ТОЛЬКО при обоюдном «не покупатель» — односторонний отказ
    (скептик против, продавец за) компанию не выбрасывает; это цена урока
    06.08, когда критерий «есть ли производство» забраковал дорожников,
    водоканалы и газовиков, живых покупателей;
  * компания без строки деятельности не судится вовсе (провайдер не зовётся)
    и проходит: нет данных — не приговор;
  * вердикт кэшируется по ИНН: повторный суд той же компании не тратит денег;
  * сбой провайдера никого не режет.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.target_gate import TargetGate  # noqa: E402

ЗАВОД = {"inn": "7701234567", "name": "ООО «Завод»", "okved": "25.11",
         "activity": "производство металлоконструкций"}
ОЦЕНЩИК = {"inn": "5050089966", "name": "ООО «Апексгруп»", "okved": "25.61",
           "activity": "независимая оценка недвижимости и экспертиза"}
ДОРОЖНИК = {"inn": "7707070707", "name": "АО «Новые дороги»", "okved": "42.11",
            "activity": "строительство и ремонт автомобильных дорог"}
БЕЗ_ПРОФИЛЯ = {"inn": "7800000000", "name": "ООО «Тайна»", "okved": "25.62",
               "activity": ""}


def _гейт(tmp_path, ответы):
    """Гейт с подменённым провайдером: ответы по очереди вызовов."""
    зовы = []

    def caller(prompt):
        зовы.append(prompt)
        return ответы[min(len(зовы) - 1, len(ответы) - 1)]

    g = TargetGate(str(tmp_path / "t.db"), caller)
    return g, зовы


def _json(пары):
    внутри = ",".join(
        f'{{"inn":"{и}","verdict":"{в}","chem":"x","pochemu":"y"}}'
        for и, в in пары)
    return '{"verdicts":[' + внутри + ']}'


def test_oba_protiv_rezhem(tmp_path):
    """Обе линзы «не покупатель» — компания отсеяна."""
    g, _ = _гейт(tmp_path, [_json([(ОЦЕНЩИК["inn"], "не покупатель")])])
    assert g.not_buyers([ОЦЕНЩИК]) == {ОЦЕНЩИК["inn"]}


def test_odna_protiv_ne_rezhem(tmp_path):
    """Скептик против, продавец за — НЕ режем (дорожники, водоканалы)."""
    ответы = [_json([(ДОРОЖНИК["inn"], "покупатель")]),      # продавец
              _json([(ДОРОЖНИК["inn"], "не покупатель")])]   # скептик
    зовы = []

    def caller(prompt):
        зовы.append(prompt)
        return ответы[len(зовы) - 1] if len(зовы) <= len(ответы) else ответы[-1]

    g = TargetGate(str(tmp_path / "t.db"), caller)
    assert g.not_buyers([ДОРОЖНИК]) == set()


def test_bez_profilya_ne_sudim(tmp_path):
    """Нет строки деятельности — провайдер не зовётся, компания проходит."""
    g, зовы = _гейт(tmp_path, [_json([(БЕЗ_ПРОФИЛЯ["inn"], "не покупатель")])])
    assert g.not_buyers([БЕЗ_ПРОФИЛЯ]) == set()
    assert зовы == []


def test_verdikt_keshiruetsya(tmp_path):
    """Второй суд той же компании не ходит в провайдера."""
    g, зовы = _гейт(tmp_path, [_json([(ОЦЕНЩИК["inn"], "не покупатель")])])
    assert g.not_buyers([ОЦЕНЩИК]) == {ОЦЕНЩИК["inn"]}
    было = len(зовы)
    assert g.not_buyers([ОЦЕНЩИК]) == {ОЦЕНЩИК["inn"]}
    assert len(зовы) == было      # ни одного нового вызова
    assert g.cached([ОЦЕНЩИК["inn"]])[ОЦЕНЩИК["inn"]]["verdict"] == "не покупатель"


def test_sboy_provaydera_nikogo_ne_rezhet(tmp_path):
    def caller(prompt):
        raise RuntimeError("шлюз лёг")

    g = TargetGate(str(tmp_path / "t.db"), caller)
    assert g.not_buyers([ОЦЕНЩИК, ЗАВОД]) == set()


def test_bez_provaydera_gate_spit(tmp_path):
    g = TargetGate(str(tmp_path / "t.db"), None)
    assert g.not_buyers([ОЦЕНЩИК, ЗАВОД, ДОРОЖНИК]) == set()


def test_prompt_nesyot_profil_i_pravila(tmp_path):
    """В промпте есть деятельность компании и напоминание про непрямых
    покупателей — без него линза заворачивает дорожников и водоканалы."""
    g, зовы = _гейт(tmp_path, [_json([(ЗАВОД["inn"], "покупатель")])])
    g.judge([ЗАВОД])
    все = "\n".join(зовы)
    assert "производство металлоконструкций" in все
    assert "водоканал" in все and "фотосепаратор" in все
    assert "JSON" in все
