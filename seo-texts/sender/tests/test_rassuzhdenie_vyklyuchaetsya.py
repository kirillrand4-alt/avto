# -*- coding: utf-8 -*-
"""Рассуждение должно выключаться, а не включаться само.

В gen_provider.call стояло жёсткое thinking=True, и всё, что шло через него,
рассуждало без спроса — по журналу шлюза это $0.09-0.21 за вызов против
$0.02-0.05 с выключенным. Владелец заметил по своей панели: «раньше было
без рассуждения».

Читаем ИСХОДНИК, а не импортируем: gen_provider тянет anthropic, которого в
песочнице тестов нет, и из-за этого сторож бы просто не запускался.
"""
import re
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parents[2]
ПРОВАЙДЕР = (КОРЕНЬ / "gen_provider.py").read_text(encoding="utf-8")
КВОТА = (КОРЕНЬ / "sender" / "ai_quota.py").read_text(encoding="utf-8")


def test_call_prinimaet_thinking():
    сигнатура = re.search(r"def call\((.*?)\):", ПРОВАЙДЕР, re.S).group(1)
    assert "thinking" in сигнатура, "call() должен уметь выключать рассуждение"
    assert "thinking=True" in сигнатура.replace(" ", ""), (
        "умолчание не меняем: через call() ходят чужие задачи "
        "(разбор тендеров, классификация hh)")


def test_v_tele_call_net_zhyostkogo_thinking():
    """Именно эта строка и включала рассуждение всем подряд."""
    тело = ПРОВАЙДЕР[ПРОВАЙДЕР.index("def call("):]
    тело = тело[:тело.index("\ndef ", 10)] if "\ndef " in тело[10:] else тело
    assert not re.search(r"^\s{4}thinking = True\s*$", тело, re.M), (
        "thinking снова прибит константой внутри call()")


def test_raw_stream_pishet_disabled():
    """Ровно та строка тела запроса, которую читает шлюз."""
    assert "{'type': 'adaptive'} if thinking" in ПРОВАЙДЕР
    assert "{'type': 'disabled'}" in ПРОВАЙДЕР


def test_thinking_prokidyvaetsya_v_raw_stream():
    тело = ПРОВАЙДЕР[ПРОВАЙДЕР.index("def call("):]
    assert "thinking=thinking" in тело, (
        "параметр есть, но до запроса не доходит")


def test_linza_idey_ne_rassuzhdaet():
    i = КВОТА.index('model="claude-haiku-4-5"')
    assert "thinking=False" in КВОТА[i:i + 200], (
        "линза идей обязана звать модель без рассуждения")


def test_konveyer_pisem_ne_rassuzhdaet():
    """Проверки и генерация писем ходят мимо call() — с явным запретом."""
    линзы = (КОРЕНЬ / "sender" / "review_lenses.py").read_text(
        encoding="utf-8")
    i = линзы.index("gen_provider._raw_stream(")
    assert "thinking=False" in линзы[i:i + 300]
