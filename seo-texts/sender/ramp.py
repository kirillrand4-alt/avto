"""Единый резолвер рамп-кривой (P2 №1): «писем/день по (кривая, рамп-день)».

Раньше clamp-в-кривую был размазан по sender._daily_limit, warmup._curve_value
и orchestrator._seed_mailbox_states (последний падал бы на пустой кривой —
голый [0]). Семантика одна: индекс зажимается в границы, после конца кривой —
плато на последнем элементе, пустая кривая -> 0.
"""

from typing import Any, Sequence


def curve_value(curve: Sequence[int], ramp_day: int) -> int:
    """Значение кривой на рамп-день: clamp в границы, пусто -> 0.

    Ревью (подтверждено): мусор в конфиге (None/строка в ramp_day или в
    элементе кривой) не должен ронять тик — деградируем в 0 (не шлём).
    """
    if not curve:
        return 0
    try:
        day = int(ramp_day)
    except (TypeError, ValueError):
        return 0
    idx = min(max(day, 0), len(curve) - 1)
    try:
        return int(curve[idx])
    except (TypeError, ValueError):
        return 0


def daily_send_limit(config: Any, provider: str, ramp_day: int) -> int:
    """Дневной лимит отправки по send-кривой провайдера из конфига."""
    try:
        curve = config.ramp_curve(provider) or []
    except Exception:  # noqa: BLE001 - нет кривой у провайдера -> лимит 0
        curve = []
    return curve_value(curve, ramp_day)
