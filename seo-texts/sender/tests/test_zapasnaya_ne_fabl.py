# -*- coding: utf-8 -*-
"""Запасной моделью проверок не должен быть фабл.

Два довода, оба замеренные 19.08. Фабл вдвое дороже опуса ($10/$50 против
$5/$25). И у него рассуждение не выключается: запрет thinking он не
принимает и думает всегда, а выход тарифицируется по $50/M. В журнале
шлюза это видно построчно: фабловские вызовы шли по $0.10-0.16 с выходом
3700-5800 токенов и пометкой «Рассуждение: high», наши обычные проверки —
$0.02-0.05 и «отключено».

Читаем исходник: gen_provider тянет anthropic, которого в песочнице нет.
"""
import re
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parents[1]
ЛИНЗЫ = (КОРЕНЬ / "review_lenses.py").read_text(encoding="utf-8")


def test_zapasnaya_ne_fabl():
    м = re.search(r"^\s*fallback = (.+)$", ЛИНЗЫ, re.M)
    assert м, "строка запасной модели пропала"
    assert "fable" not in м.group(1).lower(), (
        "запасная снова фабл: он вдвое дороже и рассуждение не выключает")


def test_zapasnaya_perenastraivaetsya():
    """Модель шлюза может отвалиться — запасную надо уметь сменить без
    выкатки кода."""
    м = re.search(r"^\s*fallback = (.+)$", ЛИНЗЫ, re.M)
    assert "environ" in м.group(1), "запасная прибита константой"


def test_proverki_bez_rassuzhdeniya():
    """Сам вызов проверок обязан гасить рассуждение явно."""
    i = ЛИНЗЫ.index("gen_provider._raw_stream(")
    assert "thinking=False" in ЛИНЗЫ[i:i + 300]
