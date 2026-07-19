"""Гигиена почтового домена: DKIM / SPF / DMARC / MX (preflight).

NEW-BACKEND для Фазы 2.1 (экраны ящиков/доменов, конструктор): перед боем
проверить, что отправляющий домен-двойник настроен правильно, и подсветить
слепую зону протухших DKIM-ключей (тихий спам). Резолв — по тому же паттерну,
что и validation.py: dnspython при наличии, иначе фолбэк на nslookup. Ошибки
резолвера дают None-поля (не удалось проверить), а не исключение.

Только stdlib. Никаких сетевых вызовов при импорте.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Optional

__all__ = ["DnsReport", "DnsHealth"]

_DEFAULT_DKIM_SELECTORS = ["mail", "default", "dkim", "mx"]


@dataclass(frozen=True)
class DnsReport:
    """Итог проверки домена. None-поле = проверить не удалось (нет резолвера)."""
    domain: str
    spf: Optional[bool]
    dkim: Optional[bool]
    dmarc: Optional[bool]
    mx_ok: bool
    spf_record: Optional[str]
    dmarc_policy: Optional[str]
    issues: tuple[str, ...]


class DnsHealth:
    """Проверка SPF/DKIM/DMARC/MX домена. Резолв TXT/MX — dnspython или nslookup."""

    def __init__(self, *, timeout: float = 5.0, dkim_selectors: Optional[list] = None):
        self._timeout = float(timeout)
        self._selectors = list(dkim_selectors) if dkim_selectors else list(_DEFAULT_DKIM_SELECTORS)

    def check(self, domain: str) -> DnsReport:
        domain = (domain or "").strip().lower().rstrip(".")
        issues: list[str] = []

        # --- SPF ---
        spf: Optional[bool] = None
        spf_record: Optional[str] = None
        txt = self._txt(domain)
        if txt is None:
            spf = None
        else:
            for rec in txt:
                if "v=spf1" in rec.lower():
                    spf, spf_record = True, rec
                    break
            else:
                spf = False
        if spf is False:
            issues.append("no_spf")

        # --- DMARC ---
        dmarc: Optional[bool] = None
        dmarc_policy: Optional[str] = None
        dtxt = self._txt("_dmarc." + domain)
        if dtxt is None:
            dmarc = None
        else:
            for rec in dtxt:
                if "v=dmarc1" in rec.lower():
                    dmarc = True
                    m = re.search(r"\bp\s*=\s*([a-zA-Z]+)", rec)
                    if m:
                        dmarc_policy = m.group(1).lower()
                    break
            else:
                dmarc = False
        if dmarc is False:
            issues.append("no_dmarc")
        elif dmarc is True and dmarc_policy == "none":
            issues.append("dmarc_policy_none")

        # --- DKIM (по селекторам) ---
        dkim: Optional[bool] = None
        any_resolver_ok = False
        found = False
        for sel in self._selectors:
            rec = self._txt(f"{sel}._domainkey.{domain}")
            if rec is None:
                continue
            any_resolver_ok = True
            for r in rec:
                low = r.lower()
                if "v=dkim1" in low or "k=" in low:
                    found = True
                    break
            if found:
                break
        if found:
            dkim = True
        elif any_resolver_ok:
            dkim = False
        else:
            dkim = None
        if dkim is False:
            issues.append("no_dkim")

        # --- MX ---
        mx = self._mx(domain)
        real_mx = [h for h in mx if h != "."]
        null_mx = bool(mx) and all(h == "." for h in mx)
        mx_ok = bool(real_mx)
        if null_mx:
            issues.append("null_mx")
        elif not mx_ok:
            issues.append("no_mx")

        return DnsReport(
            domain=domain, spf=spf, dkim=dkim, dmarc=dmarc, mx_ok=mx_ok,
            spf_record=spf_record, dmarc_policy=dmarc_policy, issues=tuple(issues),
        )

    # ---- резолвинг ------------------------------------------------------- #

    def _txt(self, name: str) -> Optional[list[str]]:
        """TXT-записи имени. [] если записей нет; None если резолвер недоступен."""
        try:
            import dns.resolver  # type: ignore
            import dns.exception  # type: ignore
            try:
                answers = dns.resolver.resolve(name, "TXT", lifetime=self._timeout)
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                return []
            except dns.exception.DNSException:
                return self._txt_nslookup(name)
            out: list[str] = []
            for r in answers:
                # dnspython отдаёт строки TXT в кавычках/байтах — склеиваем
                strings = getattr(r, "strings", None)
                if strings is not None:
                    out.append("".join(
                        s.decode("utf-8", "replace") if isinstance(s, bytes) else str(s)
                        for s in strings))
                else:
                    out.append(str(r).strip('"'))
            return out
        except ImportError:
            return self._txt_nslookup(name)

    def _txt_nslookup(self, name: str) -> Optional[list[str]]:
        try:
            proc = subprocess.run(
                ["nslookup", "-query=txt", name],
                capture_output=True, text=True, timeout=self._timeout + 5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        out = proc.stdout or ""
        recs: list[str] = []
        # строки вида: name text = "v=spf1 ..." (могут быть склеены кавычками)
        for m in re.finditer(r'text\s*=\s*(.+)', out, re.IGNORECASE):
            joined = "".join(re.findall(r'"([^"]*)"', m.group(1)))
            if joined:
                recs.append(joined)
        # если резолвер отработал, но записей нет — пустой список; если сам
        # nslookup ничего не вернул (домена нет) — тоже []
        return recs

    def _mx(self, domain: str) -> list[str]:
        """MX-хосты; null-MX '.' сохраняется как '.'. [] если нет/не резолвится."""
        try:
            import dns.resolver  # type: ignore
            import dns.exception  # type: ignore
            try:
                answers = dns.resolver.resolve(domain, "MX", lifetime=self._timeout)
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                return []
            except dns.exception.DNSException:
                return self._mx_nslookup(domain)
            hosts: list[str] = []
            for r in sorted(answers, key=lambda x: getattr(x, "preference", 0)):
                raw = str(getattr(r, "exchange", r)).lower()
                if raw in (".", ""):
                    hosts.append(".")
                else:
                    h = raw.rstrip(".")
                    if h:
                        hosts.append(h)
            return hosts
        except ImportError:
            return self._mx_nslookup(domain)

    def _mx_nslookup(self, domain: str) -> list[str]:
        try:
            proc = subprocess.run(
                ["nslookup", "-query=mx", domain],
                capture_output=True, text=True, timeout=self._timeout + 5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return []
        out = proc.stdout or ""
        hosts: list[str] = []
        for m in re.finditer(
            r"mail exchanger\s*=\s*(?:\d+\s+)?([A-Za-z0-9.\-]+)", out, re.IGNORECASE
        ):
            raw = m.group(1).lower()
            if raw == ".":
                if "." not in hosts:
                    hosts.append(".")
            else:
                h = raw.rstrip(".")
                if h and h not in hosts:
                    hosts.append(h)
        return hosts
