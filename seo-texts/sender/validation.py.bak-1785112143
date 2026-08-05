"""E-mail validation for the Rusprom cold-outreach sender.

Focused on three jobs, no message is ever sent from here:

* MX resolution — dnspython when available, otherwise an ``nslookup``
  subprocess fallback (plus a socket A-record probe for deliverability).
* Provider classification — yandex | mailru | google | outlook | vk |
  other | unknown, first by well-known consumer domain, then by MX host.
* Signal detection — catch-all (optional SMTP RCPT probe), role-based
  local parts and disposable domains.

The module talks to the rest of the service only through
:class:`ValidationResult` (see the contract §3) and the shared exception
hierarchy (§2). Both are imported from the package when present and fall
back to local definitions so the module stays self-contained and testable.
"""

from __future__ import annotations

import logging
import re
import socket
import subprocess
import smtplib
import uuid
from dataclasses import dataclass, field
from email.utils import parseaddr
from typing import Any, Optional, Sequence, TYPE_CHECKING
from sender.errors import SenderError, ValidationError  # noqa: E402

logger = logging.getLogger("sender.validation")

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .config import Config

__all__ = [
    "Validation",
    "ValidationResult",
    "ValidationError",
    "SenderError",
]

# --------------------------------------------------------------------------
# Shared contract types / errors (imported if available, else defined here).
# --------------------------------------------------------------------------


try:  # pragma: no cover - integration path
    from .dtos import ValidationResult  # type: ignore
except Exception:  # pragma: no cover - standalone path

    @dataclass(frozen=True)
    class ValidationResult:
        """Outcome of validating a single address (contract §3)."""

        email: str
        valid_status: str  # valid|invalid|risky|unknown
        provider: str
        mx_ok: bool
        catch_all: Optional[bool]
        role_based: Optional[bool]
        disposable: Optional[bool]
        detail: dict[str, Any] = field(default_factory=dict)


class _ResolverError(Exception):
    """Internal: the DNS resolution mechanism itself is unavailable.

    Distinct from "domain has no MX" (an empty result), this signals a
    systemic failure (no resolver, timeout, broken nameservers).
    """


# --------------------------------------------------------------------------
# Static classification tables.
# --------------------------------------------------------------------------

# Well-known consumer mail domains → provider. These are authoritative and
# are treated as *not* catch-all (a specific mailbox either exists or not).
_DOMAIN_PROVIDER: dict[str, str] = {
    # Yandex
    "yandex.ru": "yandex", "yandex.com": "yandex", "ya.ru": "yandex",
    "yandex.by": "yandex", "yandex.kz": "yandex", "yandex.ua": "yandex",
    "yandex.com.tr": "yandex", "narod.ru": "yandex",
    # Mail.ru group
    "mail.ru": "mailru", "bk.ru": "mailru", "inbox.ru": "mailru",
    "list.ru": "mailru", "internet.ru": "mailru", "mail.ua": "mailru",
    # Google
    "gmail.com": "google", "googlemail.com": "google",
    # Microsoft / Outlook
    "outlook.com": "outlook", "hotmail.com": "outlook", "live.com": "outlook",
    "msn.com": "outlook", "hotmail.co.uk": "outlook", "outlook.ru": "outlook",
    "live.ru": "outlook",
    # VK
    "vk.com": "vk", "vk.team": "vk",
}

# MX hostname substrings → provider. Order matters: specific before generic.
_MX_PATTERNS: tuple[tuple[str, str], ...] = (
    ("mx.yandex", "yandex"),
    ("yandex.net", "yandex"),
    ("yandex.ru", "yandex"),
    ("mxs.mail.ru", "mailru"),
    ("emx.mail.ru", "mailru"),
    ("mx.mail.ru", "mailru"),
    (".mail.ru", "mailru"),
    ("aspmx.l.google.com", "google"),
    ("l.google.com", "google"),
    ("googlemail.com", "google"),
    ("google.com", "google"),
    ("mail.protection.outlook.com", "outlook"),
    ("protection.outlook.com", "outlook"),
    ("outlook.com", "outlook"),
    ("hotmail.com", "outlook"),
    ("mx.vk", "vk"),
)

# Baseline disposable/temporary-mail domains. Config may extend this set.
_DISPOSABLE_DOMAINS: frozenset[str] = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.info",
    "sharklasers.com", "10minutemail.com", "temp-mail.org", "tempmail.com",
    "throwawaymail.com", "yopmail.com", "getnada.com", "nada.email",
    "trashmail.com", "dispostable.com", "maildrop.cc", "mailnesia.com",
    "mohmal.com", "fakeinbox.com", "spam4.me", "tempinbox.com",
    "tempmailaddress.com", "mailcatch.com", "discard.email",
    "emailondeck.com", "mintemail.com", "mytemp.email", "tempr.email",
    "mailtemp.io", "1secmail.com", "1secmail.org", "1secmail.net",
    "moakt.com", "luxusmail.org", "tempail.com",
})

# RFC 2142 / commonly-mailboxed role prefixes always treated as role-based.
_BASE_ROLE_PREFIXES: frozenset[str] = frozenset({
    "info", "sales", "office", "admin", "support", "mail", "postmaster",
    "abuse", "hostmaster", "webmaster", "noreply", "no-reply", "contact",
    "hello", "hr", "billing", "accounts", "root", "help", "service",
})

# Offline typo corrections for major RU/consumer mail domains. Conservative:
# only misspellings that are NOT legitimate mail services themselves. The
# address is never rewritten silently — the correction is reported via
# ``detail['typo_suggestion']`` for the base-cleaning pipeline to apply.
_TYPO_DOMAINS: dict[str, str] = {
    # mail.ru
    "mial.ru": "mail.ru", "mali.ru": "mail.ru", "maul.ru": "mail.ru",
    "meil.ru": "mail.ru", "mail.ur": "mail.ru", "mail.ry": "mail.ru",
    "maill.ru": "mail.ru", "msil.ru": "mail.ru", "mai.ru": "mail.ru",
    # yandex.ru
    "yandx.ru": "yandex.ru", "yadex.ru": "yandex.ru", "yndex.ru": "yandex.ru",
    "yandex.ry": "yandex.ru", "yandeks.ru": "yandex.ru",
    "iandex.ru": "yandex.ru", "yandex.ur": "yandex.ru",
    # gmail.com (gmail.ru намеренно НЕ здесь: исторически отдельный сервис)
    "gmial.com": "gmail.com", "gamil.com": "gmail.com", "gmal.com": "gmail.com",
    "gmail.con": "gmail.com", "gmail.cim": "gmail.com", "gmali.com": "gmail.com",
    # rambler.ru
    "ramler.ru": "rambler.ru", "rambler.ry": "rambler.ru",
    # bk.ru / list.ru / inbox.ru
    "bk.ur": "bk.ru", "list.ur": "list.ru", "inbox.ur": "inbox.ru",
}

# Pragmatic RFC-5321-ish syntax check (ASCII domain, requires a TLD).
_LOCAL = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
_DOMAIN = r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}"
_EMAIL_RE = re.compile(rf"^{_LOCAL}@{_DOMAIN}$")

try:  # optional dependency
    import dns.resolver  # type: ignore  # noqa: F401
    import dns.exception  # type: ignore  # noqa: F401

    _HAS_DNSPYTHON = True
except Exception:  # pragma: no cover - env without dnspython
    _HAS_DNSPYTHON = False


class Validation:
    """Validate addresses: MX + provider + catch-all/role/disposable.

    Configuration is read once from the immutable :class:`Config` under the
    ``validation.*`` namespace and cached on the instance.
    """

    def __init__(self, config: "Config") -> None:
        get = config.get
        self._config = config
        self._check_mx = bool(get("validation.check_mx", True))
        self._detect_catch_all = bool(get("validation.detect_catch_all", True))
        self._detect_role = bool(get("validation.detect_role", True))
        self._detect_disposable = bool(get("validation.detect_disposable", True))
        # SMTP RCPT probing for catch-all is off by default: it opens port-25
        # connections that many networks block and providers rate-limit.
        self._smtp_probe = bool(get("validation.smtp_probe", False))
        self._dns_timeout = float(get("validation.dns_timeout_sec", 5.0))
        self._smtp_timeout = float(get("validation.smtp_timeout_sec", 10.0))
        self._probe_from = str(get("validation.probe_from", "probe@localhost"))
        # Ревью (подтверждено): дефолт probe@localhost — невалидный MAIL FROM
        # по RFC 5321; включённая проба с ним — сигнатура зондирования, IP
        # кампании летит в блок-листы. Требуем реальный адрес при включении.
        if self._smtp_probe:
            local, _, dom = self._probe_from.partition("@")
            if not local or "." not in dom or dom.lower() in ("localhost",):
                raise ValidationError(
                    "validation.smtp_probe включён, но probe_from не является "
                    f"валидным адресом ({self._probe_from!r}): задайте реальный "
                    "адрес на своём домене И запускайте пробу с отдельного IP, "
                    "не с IP кампании")

        roles = set(_BASE_ROLE_PREFIXES)
        cfg_roles = get("validation.role_prefixes", None)
        if cfg_roles:
            roles |= {str(p).strip().lower() for p in cfg_roles if str(p).strip()}
        self._role_prefixes = frozenset(roles)

        disposable = set(_DISPOSABLE_DOMAINS)
        cfg_disp = get("validation.disposable_domains", None)
        if cfg_disp:
            disposable |= {str(d).strip().lower() for d in cfg_disp if str(d).strip()}
        self._disposable = frozenset(disposable)

        typos = dict(_TYPO_DOMAINS)
        cfg_typos = get("validation.typo_domains", None)
        if cfg_typos:
            try:
                typos.update({
                    str(k).strip().lower(): str(v).strip().lower()
                    for k, v in dict(cfg_typos).items()
                    if str(k).strip() and str(v).strip()
                })
            except (TypeError, ValueError, AttributeError):
                pass  # malformed config extension is ignored, baseline stays
        self._typo_domains = typos

        # DNS caches: the 161k base concentrates on a few thousand apex
        # domains (74% on 4 of them) — never resolve the same domain twice.
        # Sits ABOVE _resolve_mx/_has_a_record so tests stubbing those still
        # intercept; resolver errors are never cached (transient).
        self._cache_max = int(get("validation.dns_cache_max", 200_000))
        self._mx_cache: dict[str, list[str]] = {}
        self._a_cache: dict[str, bool] = {}

    # ---- public API ------------------------------------------------------

    def validate(self, email: str) -> ValidationResult:
        """Validate a single address; invalidity is reported, never raised."""
        parsed = self._normalize_email(email)
        if parsed is None:
            domain_guess = self._guess_domain(email)
            provider = self._provider_from_domain(domain_guess) or "unknown"
            return ValidationResult(
                email="",
                valid_status="invalid",
                provider=provider,
                mx_ok=False,
                catch_all=None,
                role_based=None,
                disposable=None,
                detail={"reasons": ["invalid_syntax"]},
            )

        local, domain = parsed
        norm_email = f"{local}@{domain}"
        reasons: list[str] = []

        role_based = self._is_role(local) if self._detect_role else None
        disposable = self._is_disposable(domain) if self._detect_disposable else None
        if role_based:
            reasons.append("role_based")
        if disposable:
            reasons.append("disposable")

        prov_direct = self._provider_from_domain(domain)
        provider = prov_direct or "unknown"

        typo_target = self._typo_domains.get(domain)
        if typo_target:
            reasons.append("domain_typo")

        mx_hosts: list[str] = []
        mx_ok = False
        a_ok = False
        mx_error = False
        null_mx = False
        catch_all: Optional[bool] = None

        if self._check_mx:
            try:
                mx_hosts = self._mx_cached(domain)
            except _ResolverError:
                mx_error = True
                reasons.append("mx_unavailable")
            # RFC 7505: единственная MX-запись "." = «домен почту не принимает».
            # Это жёсткий invalid, A-фолбэк не смотрим (те самые 6 411 мёртвых MX).
            null_mx = bool(mx_hosts) and all(h == "." for h in mx_hosts)
            if null_mx:
                mx_hosts = []
                reasons.append("null_mx")
            else:
                mx_hosts = [h for h in mx_hosts if h != "."]
            mx_ok = bool(mx_hosts)

            if not mx_ok and not mx_error and not null_mx:
                a_ok = self._a_cached(domain)

            if prov_direct is None and mx_hosts:
                provider = self._provider_from_mx(mx_hosts)

            if self._detect_catch_all and mx_ok:
                if prov_direct is not None:
                    # Consumer mailbox provider: not a catch-all domain.
                    catch_all = False
                elif self._smtp_probe:
                    catch_all = self._probe_catch_all(domain, mx_hosts)

            if not mx_ok and not a_ok and not mx_error and not null_mx:
                reasons.append("no_mx")

        status = self._classify(
            check_mx=self._check_mx,
            mx_error=mx_error,
            mx_ok=mx_ok,
            a_ok=a_ok,
            disposable=disposable,
            catch_all=catch_all,
            role_based=role_based,
        )

        if catch_all:
            reasons.append("catch_all")
        if self._check_mx and not mx_error and not mx_ok and a_ok:
            reasons.append("mx_only_a")

        detail: dict[str, Any] = {
            "domain": domain,
            "local": local,
            "mx": mx_hosts[:5],
            "mx_error": mx_error,
            "reasons": reasons,
            # consumer — публичный ящик (mail.ru и т.п.); hosted — корп-домен на
            # почтовом хостинге (Яндекс360/VK WS/GWS); corp — свой/прочий сервер.
            # Каденция делит темп отправки по этому классу.
            "provider_class": self._provider_class(prov_direct, provider),
        }
        if typo_target:
            detail["typo_suggestion"] = f"{local}@{typo_target}"
        return ValidationResult(
            email=norm_email,
            valid_status=status,
            provider=provider,
            mx_ok=mx_ok,
            catch_all=catch_all,
            role_based=role_based,
            disposable=disposable,
            detail=detail,
        )

    def validate_batch(self, emails: Sequence[str]) -> list[ValidationResult]:
        """Validate a sequence of addresses, preserving order."""
        return [self.validate(e) for e in emails]

    def detect_provider(self, domain: str) -> str:
        """Classify a domain's mail provider.

        Returns yandex|mailru|google|outlook|vk|other|unknown. Raises
        :class:`ValidationError` only on a systemic resolver failure; an
        unresolvable/MX-less domain simply yields ``unknown``.
        """
        d = self._norm_domain(domain)
        if not d:
            return "unknown"
        prov = self._provider_from_domain(d)
        if prov:
            return prov
        try:
            mx_hosts = self._mx_cached(d)
        except _ResolverError as exc:
            raise ValidationError(f"MX resolution failed for {d!r}: {exc}") from exc
        # null-MX sentinel "." не является хостом провайдера
        return self._provider_from_mx([h for h in mx_hosts if h != "."])

    # ---- classification helpers -----------------------------------------

    @staticmethod
    def _classify(
        *,
        check_mx: bool,
        mx_error: bool,
        mx_ok: bool,
        a_ok: bool,
        disposable: Optional[bool],
        catch_all: Optional[bool],
        role_based: Optional[bool],
    ) -> str:
        """Fold all signals into valid|invalid|risky|unknown (invalid wins)."""
        if not check_mx:
            if disposable or role_based:
                return "risky"
            return "unknown"
        if mx_error:
            if disposable or role_based:
                return "risky"
            return "unknown"
        if not (mx_ok or a_ok):
            return "invalid"
        if disposable:
            return "risky"
        if catch_all:
            return "risky"
        if role_based:
            return "risky"
        if not mx_ok:  # deliverable only via A record — accept but flag
            return "risky"
        return "valid"

    def _provider_from_domain(self, domain: str) -> Optional[str]:
        return _DOMAIN_PROVIDER.get(domain)

    @staticmethod
    def _provider_class(prov_direct: Optional[str], provider: str) -> str:
        """consumer | hosted | corp | unknown — класс получателя для каденции."""
        if prov_direct is not None:
            return "consumer"
        if provider in ("yandex", "mailru", "google", "outlook", "vk"):
            return "hosted"
        if provider == "other":
            return "corp"
        return "unknown"

    @staticmethod
    def _provider_from_mx(mx_hosts: Sequence[str]) -> str:
        for host in mx_hosts:
            for pattern, provider in _MX_PATTERNS:
                if pattern in host:
                    return provider
        return "other" if mx_hosts else "unknown"

    def _is_role(self, local: str) -> bool:
        low = local.lower()
        if low in self._role_prefixes:
            return True
        head = re.split(r"[._+\-]", low, maxsplit=1)[0]
        return head in self._role_prefixes

    def _is_disposable(self, domain: str) -> bool:
        return domain in self._disposable

    # ---- normalization ---------------------------------------------------

    def _normalize_email(self, email: str) -> Optional[tuple[str, str]]:
        """Return (local, ascii-domain) or None if syntactically invalid."""
        if not isinstance(email, str):
            return None
        raw = email.strip()
        if not raw:
            return None
        _, addr = parseaddr(raw)
        addr = (addr or "").strip()
        if "@" not in addr:
            return None
        local, _, domain = addr.rpartition("@")
        local = local.strip()
        domain = self._norm_domain(domain)
        if not local or not domain:
            return None
        candidate = f"{local}@{domain}"
        if len(candidate) > 254:
            return None
        if not _EMAIL_RE.match(candidate):
            return None
        return local, domain

    @staticmethod
    def _norm_domain(domain: str) -> str:
        # P2: канон домена ЕДИНЫЙ с suppression.normalize_domain — иначе
        # стоп-лист рассинхронится с валидацией (www/IDNA/точки). Семантика
        # остаётся мягкой: мусор -> "" (регекс синтаксиса отсечёт дальше).
        if not isinstance(domain, str):
            return ""
        try:
            from sender.suppression import normalize_domain
            return normalize_domain(domain)
        except Exception:  # noqa: BLE001 - строгий канон отверг -> мягкий путь
            d = domain.strip().lower().rstrip(".")
            if not d:
                return ""
            try:
                d = d.encode("idna").decode("ascii")
            except Exception:
                pass
            return d

    @staticmethod
    def _guess_domain(email: Any) -> str:
        if not isinstance(email, str) or "@" not in email:
            return ""
        return email.strip().rpartition("@")[2].strip().lower().rstrip(".")

    # ---- MX / A resolution ----------------------------------------------

    def _mx_cached(self, domain: str) -> list[str]:
        """Cached ``_resolve_mx``; resolver errors are not cached."""
        if domain in self._mx_cache:
            return self._mx_cache[domain]
        hosts = self._resolve_mx(domain)
        if len(self._mx_cache) >= self._cache_max:
            self._mx_cache.pop(next(iter(self._mx_cache)))
        self._mx_cache[domain] = hosts
        return hosts

    def _a_cached(self, domain: str) -> bool:
        if domain in self._a_cache:
            return self._a_cache[domain]
        ok = self._has_a_record(domain)
        if len(self._a_cache) >= self._cache_max:
            self._a_cache.pop(next(iter(self._a_cache)))
        self._a_cache[domain] = ok
        return ok

    def _resolve_mx(self, domain: str) -> list[str]:
        """Return MX hostnames (pref-sorted, lowercased); [] if none exist.

        A null-MX record (RFC 7505, exchange ``.``) is preserved as the literal
        entry ``"."`` so callers can distinguish «почту не принимаем» from
        «MX-записей нет».

        Raises :class:`_ResolverError` when no resolution mechanism works.
        """
        if _HAS_DNSPYTHON:
            try:
                return self._resolve_mx_dnspython(domain)
            except _ResolverError:
                # Transient dnspython failure: fall back to nslookup.
                return self._resolve_mx_nslookup(domain)
        return self._resolve_mx_nslookup(domain)

    def _resolve_mx_dnspython(self, domain: str) -> list[str]:
        # P2 №3: механика в dnscore (общая с dns.py); наш контракт ошибок
        # (_ResolverError) переводится здесь. Метод остаётся тест-швом.
        from sender.dnscore import DnsResolveError, resolve_mx_dnspython
        try:
            return resolve_mx_dnspython(domain, self._dns_timeout)
        except DnsResolveError as exc:
            raise _ResolverError(str(exc)) from exc

    def _resolve_mx_nslookup(self, domain: str) -> list[str]:
        # P2 №3: общий nslookup-парсер из dnscore; контракт ошибок наш.
        from sender.dnscore import DnsResolveError, resolve_mx_nslookup
        try:
            return resolve_mx_nslookup(domain, self._dns_timeout)
        except DnsResolveError as exc:
            raise _ResolverError(str(exc)) from exc

    @staticmethod
    def _has_a_record(domain: str) -> bool:
        """True if the domain resolves to any A/AAAA address (mail fallback)."""
        try:
            socket.getaddrinfo(domain, None)
            return True
        except (socket.gaierror, UnicodeError, OSError):
            return False

    # ---- catch-all probe (no message content is ever sent) -------------

    def _probe_catch_all(self, domain: str, mx_hosts: Sequence[str]) -> Optional[bool]:
        """True if the MX accepts a random unlikely address (catch-all)."""
        if not mx_hosts:
            return None
        probe_addr = f"catchall-probe-{uuid.uuid4().hex[:12]}@{domain}"
        return self._smtp_accepts(mx_hosts[0], probe_addr)

    def _smtp_accepts(self, mx_host: str, addr: str) -> Optional[bool]:
        """RCPT-probe a single address. True/False accepted; None if unknown.

        Issues HELO/MAIL/RCPT only — no DATA, so nothing is delivered.
        """
        try:
            with smtplib.SMTP(mx_host, 25, timeout=self._smtp_timeout) as smtp:
                smtp.ehlo_or_helo_if_needed()
                smtp.mail(self._probe_from)
                code, _ = smtp.rcpt(addr)
        except (smtplib.SMTPException, OSError) as exc:
            # П3.3: временный сбой (таймаут/отказ соединения) -> unknown, но
            # больше не молча — иначе деградацию MX не видно в логах.
            logger.debug("RCPT-проба %s@%s не удалась: %s", addr, mx_host, exc)
            return None
        # П3.3: нестандартный сервер может отдать не-int код — раньше сравнение
        # роняло TypeError сквозь except и валило весь батч валидации.
        if not isinstance(code, int) or isinstance(code, bool):
            logger.debug("RCPT-проба %s: нечисловой код %r", mx_host, code)
            return None
        if 200 <= code < 300:
            return True
        if code >= 500:
            return False
        return None
