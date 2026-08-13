# -*- coding: utf-8 -*-
"""Тумблер «слать по email вне базы» — одно чтение на всю панель.

Зачем отдельный модуль (13.08, жалоба редактора «стопы всё время загораются»).
Тумблер владельца читался в ДВУХ местах по-разному:

* `confirm._division_flags` знал про него: при ВКЛ компания вне базы обзвона
  давала жёлтое предупреждение, и кнопка «Отправить» работала;
* `Sender.division_block` (последний рубеж перед SMTP) про него не знал вовсе
  и убивал ровно те же письма причиной `company_division_empty`.

Редактор жала «Отправить», письмо помечалось skipped, и на экране загорался
стоп. За два дня так умерло 6 писем, и ещё 52 такие же ждут в очереди
(47 из них — новостные лиды, компании из новостного скана, которых в базе
обзвона нет по определению).

Тумблер относится ТОЛЬКО к случаю «ИНН не из базы обзвона». Настоящее
расхождение направлений (ящик КЦ пишет компании Meyer) он не снимает — это
комплаенс, и там блок остаётся жёстким.
"""
from typing import Optional

КЛЮЧ = "allow_out_of_base"


def razreshena(store=None, config=None) -> bool:
    """Разрешена ли отправка компаниям вне базы обзвона.

    Приоритет владельца: panel_settings (тумблер из UI) → confirm.allow_out_of_base
    (конфиг) → False. Любой сбой чтения — False: по умолчанию не шлём.
    """
    getter = getattr(store, "get_setting", None) if store is not None else None
    if callable(getter):
        try:
            v = getter(КЛЮЧ, None)
            if v is not None:
                return _bool(v)
        except Exception:  # noqa: BLE001 - старый store/мок без настроек
            pass
    get = getattr(config, "get", None) if config is not None else None
    if callable(get):
        try:
            return _bool(get(f"confirm.{КЛЮЧ}", False))
        except Exception:  # noqa: BLE001 - фейк-конфиг
            return False
    return False


def _bool(v: object) -> bool:
    """Настройка приезжает из sqlite строкой: 'false'/'0'/'' — это ВЫКЛ."""
    if isinstance(v, str):
        return v.strip().lower() not in ("", "0", "false", "no", "off", "нет")
    return bool(v)


def prichina_vne_bazy(reason: Optional[str]) -> bool:
    """Причина блока относится к «ИНН не из базы обзвона»?

    Гейт называет этим одну причину — `company_division_empty`. Расхождение
    направлений (`division_mismatch:...`) сюда НЕ входит.
    """
    return str(reason or "") == "company_division_empty"
