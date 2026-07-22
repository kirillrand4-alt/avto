"""Общий низкоуровневый DNS-резолвинг MX (P2 №3).

dns.py (панельный DNS-чек) и validation.py (валидация базы) держали дословно
параллельные пары «dnspython -> фолбэк nslookup» с разными контрактами ошибок.
Механика теперь одна; семантику ошибок каждый модуль переводит у себя:
validation -> _ResolverError (системный сбой валидации), dns.py -> мягкий [].

Правила общие: MX отсортированы по preference, lowercased, без хвостовой
точки; null-MX RFC 7505 сохраняется литералом "."; [] = записей нет (домен
есть/NXDOMAIN); DnsResolveError = ни один механизм резолвинга не сработал.
"""

import re
import subprocess

from sender.errors import SenderError


class DnsResolveError(SenderError):
    """Системный сбой резолвинга (нет резолвера/таймаут/сломанные NS)."""


_NSLOOKUP_MX_RE = re.compile(
    r"mail exchanger\s*=\s*(?:\d+\s+)?([A-Za-z0-9.\-]+)", re.IGNORECASE)


def resolve_mx_dnspython(domain: str, timeout: float) -> list[str]:
    """MX через dnspython. NXDOMAIN/NoAnswer -> []; прочие сбои -> DnsResolveError."""
    import dns.exception
    import dns.resolver

    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=timeout)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException as exc:
        raise DnsResolveError(str(exc)) from exc

    hosts: list[str] = []
    for r in sorted(answers, key=lambda x: getattr(x, "preference", 0)):
        raw = str(getattr(r, "exchange", r)).lower()
        if raw in (".", ""):  # RFC 7505 null MX — сохранить как sentinel
            hosts.append(".")
            continue
        host = raw.rstrip(".")
        if host:
            hosts.append(host)
    return hosts


def resolve_mx_nslookup(domain: str, timeout: float) -> list[str]:
    """MX через nslookup (фолбэк без dnspython). Сбой утилиты -> DnsResolveError."""
    try:
        proc = subprocess.run(
            ["nslookup", "-query=mx", domain],
            capture_output=True, text=True, timeout=timeout + 5,
        )
    except FileNotFoundError as exc:
        raise DnsResolveError("nslookup not available") from exc
    except subprocess.TimeoutExpired as exc:
        raise DnsResolveError("nslookup timeout") from exc
    except OSError as exc:
        raise DnsResolveError(str(exc)) from exc

    hosts: list[str] = []
    for match in _NSLOOKUP_MX_RE.finditer(proc.stdout or ""):
        raw = match.group(1).lower()
        if raw == ".":
            if "." not in hosts:
                hosts.append(".")
            continue
        host = raw.rstrip(".")
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def resolve_mx(domain: str, timeout: float) -> list[str]:
    """Полный диспетчер: dnspython, при его сбое/отсутствии — nslookup."""
    try:
        return resolve_mx_dnspython(domain, timeout)
    except ImportError:
        return resolve_mx_nslookup(domain, timeout)
    except DnsResolveError:
        return resolve_mx_nslookup(domain, timeout)
