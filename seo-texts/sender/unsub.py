"""
RFC 8058 One-Click Unsubscribe implementation.

Provides token generation, header construction, and HTTP handler logic
for List-Unsubscribe-Post: One-Click workflow with immediate suppression.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

logger = logging.getLogger("sender.unsub")

if TYPE_CHECKING:
    from typing import Any
    from .config import Config
    from .store import Store
    from .suppression import Suppression


class ValidationError(Exception):
    """Invalid token or signature."""


@dataclass(frozen=True)
class UnsubResult:
    """Result of one-click unsubscribe action."""
    ok: bool
    recipient_id: int | None
    already: bool


class Unsub:
    """
    One-click unsubscribe handler per RFC 8058.
    
    Generates signed tokens embedding recipient_id + campaign_id + timestamp,
    constructs List-Unsubscribe headers, and processes POST requests.
    Immediately adds email to suppression table with reason='unsubscribe'.
    """

    def __init__(self, config: "Config", store: "Store", suppression: "Suppression"):
        self._config = config
        self._store = store
        self._suppression = suppression
        legal = config.legal()
        self._base_url = legal.unsub_base_url.rstrip("/")
        secret_env = legal.unsub_secret_env
        secret = os.environ.get(secret_env)
        if not secret:
            raise ValueError(f"Missing environment variable: {secret_env}")
        self._secret = secret.encode("utf-8")

    def make_token(self, recipient_id: int, campaign_id: int) -> str:
        """
        Generate signed token for recipient + campaign.
        
        Token format: base64url(json_payload).base64url(hmac_bytes)
        Payload and signature encoded separately for better error diagnosis.
        """
        ts = int(time.time())
        payload = {"rid": recipient_id, "cid": campaign_id, "ts": ts}
        # P2 №2: формат/подпись живут в едином ядре sender.tokens (общий с
        # трекинг-пикселем механизм, семантика и класс ошибки — свои).
        from sender.tokens import sign_token
        return sign_token(self._secret, payload)

    def _verify_token(self, token: str) -> dict[str, int]:
        """
        Verify token signature and return payload dict.

        Ядро проверки — sender.tokens.verify_token (P2 №2, общий механизм с
        трекингом); тексты причин отказа сохранены дословно, наружу — прежний
        ValidationError этого модуля.
        """
        from sender.tokens import TokenError, verify_token
        try:
            return verify_token(self._secret, token,
                                required_int_fields=("rid", "cid", "ts"))
        except TokenError as e:
            raise ValidationError(str(e))

    def list_unsubscribe_headers(self, token: str) -> dict[str, str]:
        """
        Build List-Unsubscribe and List-Unsubscribe-Post headers.
        
        Returns dict with two headers:
          - List-Unsubscribe: <https://...?t=token>, <mailto:unsub@...>
          - List-Unsubscribe-Post: List-Unsubscribe=One-Click
        """
        query = urlencode({"t": token})
        https_url = f"{self._base_url}?{query}"
        mailto_url = f"mailto:unsub@{self._config.legal().entity.lower().replace(' ', '')}.ru?subject=unsubscribe"
        
        return {
            "List-Unsubscribe": f"<{https_url}>, <{mailto_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    def handle_one_click(self, token: str) -> UnsubResult:
        """
        Process one-click unsubscribe POST request.
        
        Steps:
          1. Verify token signature
          2. Lookup recipient by rid
          3. Add email to suppression (idempotent)
          4. Return result
        
        Raises ValidationError if token invalid.
        Returns UnsubResult with ok=False if recipient not found, ok=True otherwise.
        """
        payload = self._verify_token(token)
        recipient_id = payload["rid"]
        campaign_id = payload["cid"]
        
        recipient = self._store.get_recipient(recipient_id)
        if not recipient:
            return UnsubResult(ok=False, recipient_id=recipient_id, already=False)
        
        # Add to suppression (idempotent via UNIQUE constraint)
        added = self._suppression.add_email(
            email=recipient.email,
            reason="unsubscribe",
            source="one_click",
            campaign_id=campaign_id,
        )

        # ФЗ-152: отказ в журнал оснований (только при первом срабатывании,
        # реплеи токена журнал не раздувают); guard для мок-store в юнитах
        if added and hasattr(self._store, "log_consent"):
            try:
                self._store.log_consent(
                    email=recipient.email,
                    action="unsubscribe",
                    recipient_id=recipient_id,
                    source="one_click",
                    campaign_id=campaign_id,
                )
            except Exception:
                # Журнал не должен ломать one-click (ответ 200 обязателен),
                # но молчать нельзя (П1.4): пропуск записи в consent_log —
                # юридический след, оператор должен видеть сбой в логах.
                logger.exception(
                    "consent_log failed for one-click unsubscribe: "
                    "recipient_id=%s email=%s", recipient_id, recipient.email,
                )

        return UnsubResult(ok=True, recipient_id=recipient_id, already=not added)
