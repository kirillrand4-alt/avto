"""Композиционный корень движка (P2 №6): единая сборка графа зависимостей.

Раньше DI-вайринг дублировался: `api/app.py::build_deps` (панель) и
`cli._cmd_run` (оркестратор) собирали suppression/gates/sender/leaddesk/...
каждый по-своему — расхождение (например, Bitrix-синк был только у CLI)
накапливалось молча. Теперь ядро собирается здесь; оба вызывают build_deps.

Модуль намеренно БЕЗ fastapi: Deps — обычный dataclass, чтобы CLI-путь
не требовал зависимостей веб-панели.
"""

import os
from dataclasses import dataclass
from typing import Any

from sender.auth import Auth


@dataclass
class Deps:
    """Собранные компоненты движка (общие для панели и оркестратора)."""
    config: Any
    store: Any
    auth: Auth
    leaddesk: Any
    analytics: Any
    gates: Any
    sender: Any
    suppression: Any
    warmup: Any = None
    dns: Any = None
    bitrix: Any = None  # None, если BITRIX_WEBHOOK_URL не задан
    confirm: Any = None  # очередь «подтвердить отправку» (Задача 1/4)


def build_deps(config: Any, store: Any, *, dry_run: bool = True) -> "Deps":
    """Собрать компоненты движка из config+store (единая точка сборки).

    dry_run: панель собирает Sender в dry-run (ничего не шлёт сама),
    оркестратор передаёт боевой флаг из аргументов запуска.
    Bitrix-синк подключается к LeadDesk при наличии BITRIX_WEBHOOK_URL —
    одинаково для обоих потребителей (раньше только у CLI).
    """
    from sender.analytics import Analytics
    from sender.dns import DnsHealth
    from sender.gates import Gates
    from sender.leaddesk import LeadDesk
    from sender.sender import Sender
    from sender.suppression import Suppression
    from sender.warmup import Warmup

    suppression = Suppression(store)
    gates = Gates(config, store)
    sender = Sender(config, store, suppression, gates, dry_run=dry_run)

    bitrix_sink = None
    if os.getenv("BITRIX_WEBHOOK_URL"):
        from sender.bitrix import BitrixSink
        bitrix_sink = BitrixSink(config, store)

    from sender.confirm import ConfirmSend

    # Ручная immediate-send: если confirm.live_send=true, оператор нажатием
    # «Отправить» в панели отправляет письмо НЕМЕДЛЕННО по боевому SMTP.
    # Для этого нужен sender с dry_run=False НЕЗАВИСИМО от dry_run панели/
    # оркестратора (панель собирается dry_run=True). По умолчанию false —
    # approve кладёт в очередь (холд на автоматике сохраняется).
    # ⛔ Холд по автоматике: оркестратор/автоответчик реально НЕ шлют; живьём
    # уходит только то, что оператор одобрил вручную.
    live_send = bool(config.get("confirm.live_send", False))
    confirm_sender = None
    if live_send:
        confirm_sender = Sender(config, store, suppression, gates, dry_run=False)

    return Deps(
        config=config, store=store, auth=Auth(store),
        leaddesk=LeadDesk(config, store, bitrix_sink=bitrix_sink),
        analytics=Analytics(store),
        gates=gates, sender=sender, suppression=suppression,
        warmup=Warmup(config, store, sender), dns=DnsHealth(),
        bitrix=bitrix_sink,
        confirm=ConfirmSend(config, store, suppression, sender=confirm_sender),
    )
