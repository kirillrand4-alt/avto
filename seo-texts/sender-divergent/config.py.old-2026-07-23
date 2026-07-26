# FILE: sender/config.py
"""Загрузка и валидация конфигурации сервиса «Руспром» (модуль `config`).

Только stdlib. Никаких сетевых вызовов. Парсинг YAML выполняется встроенным
минимальным парсером (подмножество YAML, достаточное для конфига из контракта),
поэтому внешних зависимостей нет.

`Config` иммутабелен после `load()`. Все инварианты безопасности из §5,
относящиеся к конфигу, проверяются на этапе загрузки:

* рамп-кривые — непустые, положительные, неубывающие; каждый провайдер ящика
  обязан иметь кривую;
* окно отправки — корректные дни (ISO 1..7) и `start < end`;
* провайдер-сплит — пулы ссылаются только на объявленные ящики, роутинг — только
  на существующие пулы;
* атрибуция Руспром — юрлицо задано, ИНН имеет валидный формат (10/12 цифр),
  секрет подписи one-click присутствует в окружении;
* секреты (`password_env`, `unsub_secret_env`) обязаны присутствовать в env.

Безопасные дефолты: при отсутствии значений выбирается более консервативный
вариант (`dry_run=True`, `fail_on_unfilled=True`, авто-suppress включён и т.д.).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Optional
from sender.errors import ConfigError, SenderError  # noqa: E402


# --------------------------------------------------------------------------- #
# Исключения (config-часть общей иерархии §2)
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Конфиг-структуры (§3)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MailboxCfg:
    mailbox_id: str
    provider: str
    smtp_host: str
    smtp_port: int
    imap_host: str
    imap_port: int
    login: str
    password_env: str
    from_name: str
    signature: Optional[str]
    pool: Optional[str]
    is_warmup_node: bool = False


@dataclass(frozen=True)
class WindowCfg:
    tz: str
    days: tuple[int, ...]
    start: str  # "09:30"
    end: str    # "18:30"


@dataclass(frozen=True)
class GatesCfg:
    domain_bounce_pct: float
    domain_complaint_pct: float
    mailbox_bounce_pct: float
    global_complaint_pct: float
    min_volume: int
    provider_bounce_pct: float = 2.5  # bounce × провайдер получателя (mx_provider)
    window_days: int = 14             # окно метрик гейтов (ревью); 0 = вся история


@dataclass(frozen=True)
class LegalCfg:
    entity: str
    inn: str
    unsub_base_url: str
    unsub_secret_env: str
    refusal_log_max_lag_hours: int


# --------------------------------------------------------------------------- #
# Константы валидации
# --------------------------------------------------------------------------- #
_VALID_MAILBOX_PROVIDERS = frozenset({"yandex", "mailru", "google", "outlook"})
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_INN_RE = re.compile(r"^\d{10}$|^\d{12}$")


# --------------------------------------------------------------------------- #
# Минимальный YAML-парсер (подмножество, только stdlib)
# --------------------------------------------------------------------------- #
_MAP_ENTRY_RE = re.compile(r"^[^\s:#][^:]*:(\s.*)?$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+)$")


def _strip_comment(line: str) -> str:
    """Удаляет комментарий `#`, уважая кавычки (YAML: `#` только после пробела)."""
    out: list[str] = []
    quote: str | None = None
    prev = " "
    for ch in line:
        if quote is not None:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#" and prev in (" ", "\t"):
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def _split_flow(inner: str) -> list[str]:
    """Разбивает содержимое flow-списка `[a, b, c]` по запятым (без вложенности)."""
    return [p for p in (x.strip() for x in inner.split(",")) if p != ""]


def _parse_scalar(raw: str) -> Any:
    """Приводит скалярную строку к bool/int/float/None/str или flow-списку."""
    s = raw.strip()
    if s == "":
        return None
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [] if inner == "" else [_parse_scalar(p) for p in _split_flow(inner)]
    low = s.lower()
    if low in ("null", "~", "none"):
        return None
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)
    return s


class _MiniYaml:
    """Рекурсивный парсер по отступам для подмножества YAML."""

    def __init__(self, lines: list[list[Any]]):
        # lines: изменяемый список [indent, content]
        self.lines = lines
        self.i = 0

    def parse(self) -> Any:
        if not self.lines:
            return {}
        indent, content = self.lines[0]
        if content.startswith("- ") or content == "-":
            return self._parse_list(indent)
        return self._parse_map(indent)

    def _parse_map(self, indent: int) -> dict:
        result: dict[str, Any] = {}
        while self.i < len(self.lines):
            cur_indent, content = self.lines[self.i]
            if cur_indent != indent or content.startswith("- ") or content == "-":
                break
            key, sep, val = content.partition(":")
            if sep == "":
                # строка без ':' на уровне карты — некорректно для нашего конфига
                raise ConfigError(f"invalid config line: {content!r}")
            key = key.strip()
            val = val.strip()
            self.i += 1
            if val == "":
                result[key] = self._parse_child(indent)
            else:
                result[key] = _parse_scalar(val)
        return result

    def _parse_child(self, parent_indent: int) -> Any:
        if self.i >= len(self.lines):
            return None
        cur_indent, content = self.lines[self.i]
        if cur_indent <= parent_indent:
            return None
        if content.startswith("- ") or content == "-":
            return self._parse_list(cur_indent)
        return self._parse_map(cur_indent)

    def _parse_list(self, indent: int) -> list:
        result: list[Any] = []
        while self.i < len(self.lines):
            cur_indent, content = self.lines[self.i]
            if cur_indent != indent or not (content == "-" or content.startswith("- ")):
                break
            if content == "-":
                self.i += 1
                result.append(self._parse_child(indent))
                continue
            after = content[1:]
            stripped = after.lstrip()
            inner_indent = indent + 1 + (len(after) - len(stripped))
            if _MAP_ENTRY_RE.match(stripped):
                # элемент списка — карта; первый ключ inline
                self.lines[self.i] = [inner_indent, stripped]
                result.append(self._parse_map(inner_indent))
            else:
                self.i += 1
                result.append(_parse_scalar(stripped))
        return result


def _load_yaml(text: str) -> Any:
    lines: list[list[Any]] = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip(" "))
        lines.append([indent, line.strip()])
    return _MiniYaml(lines).parse()


# --------------------------------------------------------------------------- #
# Утилиты доступа/приведения
# --------------------------------------------------------------------------- #
def _require(node: dict, key: str, ctx: str) -> Any:
    if not isinstance(node, dict) or key not in node or node[key] is None:
        raise ConfigError(f"{ctx}: missing required key '{key}'")
    return node[key]


def _as_str(value: Any, ctx: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ConfigError(f"{ctx}: expected non-empty string, got {value!r}")
    return value


def _as_int(value: Any, ctx: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{ctx}: expected int, got {value!r}")
    return value


def _as_float(value: Any, ctx: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{ctx}: expected number, got {value!r}")
    return float(value)


def _freeze(value: Any) -> Any:
    """Возвращает иммутабельное представление (для `get`)."""
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _validate_curve(curve: Any, ctx: str) -> list[int]:
    if not isinstance(curve, list) or not curve:
        raise ConfigError(f"{ctx}: ramp curve must be a non-empty list")
    out: list[int] = []
    prev = None
    for i, v in enumerate(curve):
        iv = _as_int(v, f"{ctx}[{i}]")
        if iv <= 0:
            raise ConfigError(f"{ctx}[{i}]: ramp value must be positive")
        if prev is not None and iv < prev:
            raise ConfigError(f"{ctx}: ramp curve must be non-decreasing")
        prev = iv
        out.append(iv)
    return out


def _hhmm_to_minutes(value: str, ctx: str) -> int:
    m = _HHMM_RE.match(value)
    if not m:
        raise ConfigError(f"{ctx}: invalid HH:MM value {value!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def _validate_inn(value: str, ctx: str) -> str:
    if not isinstance(value, str) or not _INN_RE.match(value):
        raise ConfigError(f"{ctx}: INN must be 10 or 12 digits, got {value!r}")
    return value


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
class Config:
    """Загружает и валидирует YAML/env. Иммутабелен после `load()`."""

    def __init__(self, data: dict, env: Mapping[str, str]):
        self._frozen = False
        self._env = dict(env)
        self._data = self._apply_safe_defaults(data)

        # Построение и валидация типизированных структур (порядок важен).
        self._mailboxes = self._build_mailboxes()
        self._pools = self._build_pools()
        self._validate_ramp_curves()
        self._window = self._build_window()
        self._holidays = self._build_holidays()
        self._gates = self._build_gates()
        self._legal = self._build_legal()
        self._validate_attribution()

        self._frozen = True

    # -- иммутабельность --------------------------------------------------- #
    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_frozen", False):
            raise ConfigError("Config is immutable after load()")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        raise ConfigError("Config is immutable after load()")

    # -- загрузка ---------------------------------------------------------- #
    @classmethod
    def load(cls, path: str | Path, env: Mapping[str, str] | None = None) -> "Config":
        """Читает YAML-файл, валидирует и возвращает иммутабельный Config."""
        env = dict(env) if env is not None else dict(os.environ)
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read config file {path}: {exc}") from exc
        data = _load_yaml(text)
        if not isinstance(data, dict):
            raise ConfigError("config root must be a mapping")
        return cls(data, env)

    # -- нормализация безопасных дефолтов ---------------------------------- #
    @staticmethod
    def _apply_safe_defaults(data: dict) -> dict:
        # неглубокая копия по секциям, чтобы не мутировать вход
        out = {k: v for k, v in data.items()}

        def section(name: str) -> dict:
            cur = out.get(name)
            cur = dict(cur) if isinstance(cur, dict) else {}
            out[name] = cur
            return cur

        service = section("service")
        service.setdefault("dry_run", True)          # безопасно: не слать по умолчанию
        service.setdefault("tick_interval_sec", 60)

        validation = section("validation")
        validation.setdefault("check_mx", True)

        personalization = section("personalization")
        personalization.setdefault("fail_on_unfilled", True)  # гейт незаполненных {}

        imap = section("imap")
        imap.setdefault("auto_suppress_on_bounce", True)
        imap.setdefault("auto_suppress_on_complaint", True)

        return out

    # -- построители секций ------------------------------------------------ #
    def _build_mailboxes(self) -> list[MailboxCfg]:
        raw = self._data.get("mailboxes")
        if not isinstance(raw, list) or not raw:
            raise ConfigError("mailboxes: must be a non-empty list")
        result: list[MailboxCfg] = []
        seen: set[str] = set()
        for i, m in enumerate(raw):
            ctx = f"mailboxes[{i}]"
            if not isinstance(m, dict):
                raise ConfigError(f"{ctx}: must be a mapping")
            mid = _as_str(_require(m, "mailbox_id", ctx), f"{ctx}.mailbox_id")
            if mid in seen:
                raise ConfigError(f"{ctx}: duplicate mailbox_id {mid!r}")
            seen.add(mid)

            provider = _as_str(_require(m, "provider", ctx), f"{ctx}.provider")
            if provider not in _VALID_MAILBOX_PROVIDERS:
                raise ConfigError(
                    f"{ctx}.provider: {provider!r} not in {sorted(_VALID_MAILBOX_PROVIDERS)}"
                )

            pw_env = _as_str(_require(m, "password_env", ctx), f"{ctx}.password_env")
            if pw_env not in self._env:
                raise ConfigError(
                    f"{ctx}: secret env var {pw_env!r} is not present in environment"
                )

            signature = m.get("signature_ref")
            if signature is None:
                signature = m.get("signature")

            result.append(
                MailboxCfg(
                    mailbox_id=mid,
                    provider=provider,
                    smtp_host=_as_str(_require(m, "smtp_host", ctx), f"{ctx}.smtp_host"),
                    smtp_port=_as_int(_require(m, "smtp_port", ctx), f"{ctx}.smtp_port"),
                    imap_host=_as_str(_require(m, "imap_host", ctx), f"{ctx}.imap_host"),
                    imap_port=_as_int(_require(m, "imap_port", ctx), f"{ctx}.imap_port"),
                    login=_as_str(_require(m, "login", ctx), f"{ctx}.login"),
                    password_env=pw_env,
                    from_name=_as_str(_require(m, "from_name", ctx), f"{ctx}.from_name"),
                    signature=signature if signature is not None else None,
                    pool=m.get("pool"),
                    is_warmup_node=bool(m.get("is_warmup_node", False)),
                )
            )
        return result

    def _build_pools(self) -> dict[str, list[str]]:
        mailbox_ids = {mb.mailbox_id for mb in self._mailboxes}
        ps = self._data.get("provider_split", {})
        if not isinstance(ps, dict):
            raise ConfigError("provider_split: must be a mapping")

        pools_raw = ps.get("pools", {})
        if not isinstance(pools_raw, dict) or not pools_raw:
            raise ConfigError("provider_split.pools: must be a non-empty mapping")

        pools: dict[str, list[str]] = {}
        for name, members in pools_raw.items():
            if not isinstance(members, list) or not members:
                raise ConfigError(f"provider_split.pools.{name}: must be a non-empty list")
            for mb in members:
                if mb not in mailbox_ids:
                    raise ConfigError(
                        f"provider_split.pools.{name}: references undefined mailbox {mb!r}"
                    )
            pools[name] = list(members)

        # routing → существующие пулы
        routing = ps.get("routing", {})
        if routing is not None:
            if not isinstance(routing, dict):
                raise ConfigError("provider_split.routing: must be a mapping")
            for prov, pool_name in routing.items():
                if pool_name not in pools:
                    raise ConfigError(
                        f"provider_split.routing.{prov}: references undefined pool {pool_name!r}"
                    )

        # mailbox.pool → существующие пулы
        for mb in self._mailboxes:
            if mb.pool is not None and mb.pool not in pools:
                raise ConfigError(
                    f"mailbox {mb.mailbox_id}: pool {mb.pool!r} is not defined in provider_split.pools"
                )
        return pools

    def _validate_ramp_curves(self) -> None:
        rc = self._data.get("ramp_curves")
        if not isinstance(rc, dict) or not rc:
            raise ConfigError("ramp_curves: required non-empty mapping")
        for prov, curve in rc.items():
            _validate_curve(curve, f"ramp_curves.{prov}")
        # каждый провайдер ящика обязан иметь кривую рампа
        for mb in self._mailboxes:
            if mb.provider not in rc:
                raise ConfigError(
                    f"ramp_curves: missing curve for mailbox provider {mb.provider!r}"
                )
        # прогрев (если задан) — валидная кривая
        warmup = self._data.get("warmup", {})
        if isinstance(warmup, dict) and "ramp_curve" in warmup:
            _validate_curve(warmup["ramp_curve"], "warmup.ramp_curve")

    def _build_window(self) -> WindowCfg:
        w = self._data.get("window")
        if not isinstance(w, dict):
            raise ConfigError("window: required mapping")
        days_raw = _require(w, "days", "window")
        if not isinstance(days_raw, list) or not days_raw:
            raise ConfigError("window.days: must be a non-empty list")
        days: list[int] = []
        for d in days_raw:
            iv = _as_int(d, "window.days")
            if not 1 <= iv <= 7:
                raise ConfigError(f"window.days: ISO day out of range: {iv}")
            days.append(iv)

        start = _as_str(_require(w, "start", "window"), "window.start")
        end = _as_str(_require(w, "end", "window"), "window.end")
        start_m = _hhmm_to_minutes(start, "window.start")
        end_m = _hhmm_to_minutes(end, "window.end")
        if start_m >= end_m:
            raise ConfigError(f"window: start {start!r} must be before end {end!r}")

        tz = _as_str(self._data.get("timezone", "UTC"), "timezone")
        self._validate_tz(tz)
        return WindowCfg(tz=tz, days=tuple(days), start=start, end=end)

    @staticmethod
    def _validate_tz(tz: str) -> None:
        try:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        except ImportError:
            return
        try:
            ZoneInfo(tz)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"timezone: unknown zone {tz!r}") from exc
        except Exception:
            # прочие сбои (например, отсутствие tzdata) — не блокируем загрузку
            return

    def _build_holidays(self) -> set[date]:
        raw = self._data.get("holidays", [])
        if raw is None:
            return set()
        if not isinstance(raw, list):
            raise ConfigError("holidays: must be a list")
        out: set[date] = set()
        for item in raw:
            if not isinstance(item, str):
                raise ConfigError(f"holidays: expected ISO date string, got {item!r}")
            try:
                out.add(date.fromisoformat(item))
            except ValueError as exc:
                raise ConfigError(f"holidays: invalid date {item!r}") from exc
        return out

    def _build_gates(self) -> GatesCfg:
        g = self._data.get("gates")
        if not isinstance(g, dict):
            raise ConfigError("gates: required mapping")
        cfg = GatesCfg(
            domain_bounce_pct=_as_float(_require(g, "domain_bounce_pct", "gates"), "gates.domain_bounce_pct"),
            domain_complaint_pct=_as_float(_require(g, "domain_complaint_pct", "gates"), "gates.domain_complaint_pct"),
            mailbox_bounce_pct=_as_float(_require(g, "mailbox_bounce_pct", "gates"), "gates.mailbox_bounce_pct"),
            global_complaint_pct=_as_float(_require(g, "global_complaint_pct", "gates"), "gates.global_complaint_pct"),
            min_volume=_as_int(_require(g, "min_volume", "gates"), "gates.min_volume"),
            # опционален: старые конфиги без ключа работают с дефолтом
            provider_bounce_pct=_as_float(g.get("provider_bounce_pct", 2.5), "gates.provider_bounce_pct"),
            # окно метрик (ревью): 14 дн по умолчанию; 0 = вся история
            window_days=_as_int(g.get("window_days", 14), "gates.window_days"),
        )
        for name, val in (
            ("domain_bounce_pct", cfg.domain_bounce_pct),
            ("domain_complaint_pct", cfg.domain_complaint_pct),
            ("mailbox_bounce_pct", cfg.mailbox_bounce_pct),
            ("global_complaint_pct", cfg.global_complaint_pct),
            ("provider_bounce_pct", cfg.provider_bounce_pct),
        ):
            if not 0.0 <= val <= 100.0:
                raise ConfigError(f"gates.{name}: percentage out of range [0..100]: {val}")
        if cfg.min_volume < 0:
            raise ConfigError("gates.min_volume: must be >= 0")
        if cfg.window_days < 0:
            raise ConfigError("gates.window_days: must be >= 0")
        return cfg

    def _build_legal(self) -> LegalCfg:
        l = self._data.get("legal")
        if not isinstance(l, dict):
            raise ConfigError("legal: required mapping")
        entity = _as_str(_require(l, "entity", "legal"), "legal.entity")
        inn = _validate_inn(_as_str(_require(l, "inn", "legal"), "legal.inn"), "legal.inn")
        base_url = _as_str(_require(l, "unsub_base_url", "legal"), "legal.unsub_base_url")
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError(f"legal.unsub_base_url: must be http(s) URL, got {base_url!r}")
        secret_env = _as_str(_require(l, "unsub_secret_env", "legal"), "legal.unsub_secret_env")
        if secret_env not in self._env:
            raise ConfigError(
                f"legal.unsub_secret_env: secret env var {secret_env!r} is not present in environment"
            )
        lag = _as_int(_require(l, "refusal_log_max_lag_hours", "legal"), "legal.refusal_log_max_lag_hours")
        if lag <= 0:
            raise ConfigError("legal.refusal_log_max_lag_hours: must be > 0")
        return LegalCfg(
            entity=entity,
            inn=inn,
            unsub_base_url=base_url,
            unsub_secret_env=secret_env,
            refusal_log_max_lag_hours=lag,
        )

    def _validate_attribution(self) -> None:
        attr = self._data.get("attribution")
        if attr is None:
            return
        if not isinstance(attr, dict):
            raise ConfigError("attribution: must be a mapping")
        _as_str(_require(attr, "entity", "attribution"), "attribution.entity")
        _validate_inn(
            _as_str(_require(attr, "entity_inn", "attribution"), "attribution.entity_inn"),
            "attribution.entity_inn",
        )

    # -- публичный API ----------------------------------------------------- #
    def mailboxes(self) -> list[MailboxCfg]:
        """Список ящиков (валидированные MailboxCfg)."""
        return list(self._mailboxes)

    def add_mailbox(self, mb: "MailboxCfg") -> bool:
        """Добавить ящик в память на лету (Задача 2: POST /mailboxes). Дедуп по
        mailbox_id. Если ящик указывает pool — добавляем его в пул. Возвращает
        True если добавлен (False если уже был)."""
        if any(m.mailbox_id == mb.mailbox_id for m in self._mailboxes):
            return False
        self._mailboxes.append(mb)
        if mb.pool:
            self._pools.setdefault(mb.pool, [])
            if mb.mailbox_id not in self._pools[mb.pool]:
                self._pools[mb.pool].append(mb.mailbox_id)
        return True

    def load_mailbox_overrides(self, store: Any) -> int:
        """Подхватить ящики, добавленные из панели (mailbox_overrides), в память.
        Вызывается на старте (wiring.build_deps) и после POST /mailboxes. Идемпотентно."""
        added = 0
        try:
            rows = store.list_mailbox_overrides()
        except Exception:  # noqa: BLE001 - у мок-store метода может не быть
            return 0
        for r in rows:
            try:
                mb = MailboxCfg(
                    mailbox_id=r["mailbox_id"], provider=r["provider"],
                    smtp_host=r["smtp_host"], smtp_port=int(r["smtp_port"]),
                    imap_host=r["imap_host"], imap_port=int(r["imap_port"]),
                    login=r["login"], password_env=r["password_env"],
                    from_name=r.get("from_name") or "", signature=r.get("signature"),
                    pool=r.get("pool"), is_warmup_node=bool(r.get("is_warmup_node")))
                if self.add_mailbox(mb):
                    added += 1
            except Exception:  # noqa: BLE001 - битую override-строку пропускаем
                continue
        return added

    def provider_pools(self) -> dict[str, list[str]]:
        """pool_name -> [mailbox_id]."""
        return {name: list(members) for name, members in self._pools.items()}

    def ramp_curve(self, provider: str) -> list[int]:
        """Рамп-кривая провайдера; индекс = ramp_day."""
        rc = self._data.get("ramp_curves", {})
        if provider not in rc:
            raise ConfigError(f"ramp_curves: no curve for provider {provider!r}")
        return [int(v) for v in rc[provider]]

    def sending_window(self) -> WindowCfg:
        """Окно отправки (tz/дни/начало/конец)."""
        return self._window

    def holidays(self) -> set[date]:
        """Множество праздничных дат (переносим отправку)."""
        return set(self._holidays)

    def gates(self) -> GatesCfg:
        """Пороги kill-switch."""
        return self._gates

    def legal(self) -> LegalCfg:
        """Юр-атрибуция Руспром + ИНН + база unsub."""
        return self._legal

    def get(self, dotted_key: str, default: Any = ...) -> Any:
        """Доступ по точечному ключу. Если ключа нет и default не задан — ConfigError."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                if default is ...:
                    raise ConfigError(f"missing config key: {dotted_key!r}")
                return default
        return _freeze(node)
