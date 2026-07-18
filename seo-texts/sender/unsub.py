"""
RFC 8058 One-Click Unsubscribe implementation.

Provides token generation, header construction, and HTTP handler logic
for List-Unsubscribe-Post: One-Click workflow with immediate suppression.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

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
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        
        sig_bytes = hmac.new(self._secret, payload_json.encode("utf-8"), hashlib.sha256).digest()
        
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).rstrip(b"=").decode("ascii")
        sig_b64 = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode("ascii")
        
        return f"{payload_b64}.{sig_b64}"

    def _verify_token(self, token: str) -> dict[str, int]:
        """
        Verify token signature and return payload dict.
        
        Raises ValidationError with specific error for each failure mode:
        - Invalid base64 → "Invalid base64"
        - Invalid JSON → "Invalid JSON payload"
        - Missing fields → "Missing or invalid field"
        - Signature mismatch → "Signature mismatch"
        
        Returns dict with 'rid', 'cid', 'ts'.
        """
        parts = token.split(".", 1)
        if len(parts) != 2:
            raise ValidationError("Token format invalid")
        
        payload_b64, sig_b64 = parts
        
        # Decode payload base64
        try:
            payload_b64_padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_b64_padded.encode("ascii"))
        except Exception as e:
            raise ValidationError(f"Invalid base64: {e}")
        
        # Decode payload JSON
        try:
            payload_str = payload_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValidationError(f"Invalid UTF-8 in token: {e}")
        
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON payload: {e}")
        
        if not isinstance(payload, dict):
            raise ValidationError("Payload must be dict")
        
        # Validate payload structure
        for key in ("rid", "cid", "ts"):
            if key not in payload or not isinstance(payload[key], int):
                raise ValidationError(f"Missing or invalid field: {key}")
        
        # Decode signature base64
        try:
            sig_b64_padded = sig_b64 + "=" * ((4 - len(sig_b64) % 4) % 4)
            sig_bytes = base64.urlsafe_b64decode(sig_b64_padded.encode("ascii"))
        except Exception as e:
            raise ValidationError(f"Invalid base64: {e}")
        
        # Compute expected signature
        canonical_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        expected_sig = hmac.new(self._secret, canonical_json.encode("utf-8"), hashlib.sha256).digest()
        
        # Constant-time compare
        if not hmac.compare_digest(sig_bytes, expected_sig):
            raise ValidationError("Signature mismatch")
        
        return payload

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
                pass  # журнал не должен ломать one-click (ответ 200 обязателен)

        return UnsubResult(ok=True, recipient_id=recipient_id, already=not added)
