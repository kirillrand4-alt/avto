"""
Модуль уведомлений Telegram для сервиса рассылки.

Отправляет события операторам через Telegram Bot API. Поддерживает дебаунс,
тихие часы для некритичных событий, приоритизацию по серьёзности.
При отсутствии токена/конфига работает в режиме disabled (no-op).
"""

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

try:
    from sender.errors import SenderError
except ImportError:
    class SenderError(Exception):
        """Локальный фолбэк для SenderError."""
        pass

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Фолбэк для окружений без zoneinfo (Python <3.9 backport)
    ZoneInfo = None


logger = logging.getLogger(__name__)


class NotifyError(SenderError):
    """Ошибка модуля уведомлений."""
    pass


# Карта серьёзности событий (P1 - критично, P2 - важно, P3 - информация)
EVENT_SEVERITY = {
    # P1 - требует немедленного внимания
    "kill_switch_triggered": "P1",
    
    # P2 - требует скорого реагирования
    "complaint_rate_approaching_kill": "P2",
    "smtp_persistent_failure": "P2",
    "warm_lead_created": "P2",
    "provider_bounce_trip": "P2",
    
    # P3 - всё остальное (информационные события)
}


# Окна дебаунса в секундах (0 = не дебаунсить, шлём всегда)
DEBOUNCE_SEC = {
    "complaint_rate_approaching_kill": 1800,  # 30 минут
    "smtp_persistent_failure": 3600,  # 1 час
    "provider_bounce_trip": 3600,  # 1 час
    "kill_switch_triggered": 0,  # всегда шлём
    "warm_lead_created": 0,  # всегда шлём
}


class Notifier:
    """
    Отправитель уведомлений в Telegram.
    
    При отсутствии токена или ops_chat_id работает в режиме disabled:
    публичные методы становятся безопасными no-op.
    """
    
    def __init__(self, config, store=None):
        """
        Инициализация notifier.
        
        Args:
            config: объект конфигурации с методом get(key, default)
            store: опциональный store для персистентного дебаунса
        """
        self.config = config
        self.store = store
        self.disabled = False
        
        # Получаем токен из environment
        token_env = config.get("notify.token_env", "TELEGRAM_BOT_TOKEN")
        self.token = os.environ.get(token_env)
        
        # Получаем chat IDs
        self.ops_chat = config.get("notify.ops_chat_id", None)
        self.oncall_chat = config.get("notify.oncall_chat_id", None)
        
        # API base для тестирования
        self.api_base = config.get("notify.api_base", "https://api.telegram.org")
        
        # Проверяем обязательные параметры
        if not self.token or not self.ops_chat:
            logger.warning(
                "Notifier disabled: missing token_env=%s or ops_chat_id",
                token_env
            )
            self.disabled = True
        
        # Настройка таймзоны для тихих часов
        self.msk_tz = None
        if ZoneInfo is not None:
            try:
                self.msk_tz = ZoneInfo("Europe/Moscow")
            except Exception:
                logger.warning("ZoneInfo Europe/Moscow недоступна, фолбэк на UTC+3")
        
        logger.info(
            "Notifier initialized: disabled=%s, ops_chat=%s, oncall_chat=%s",
            self.disabled,
            self.ops_chat,
            self.oncall_chat
        )
    
    def _get_severity(self, event_type: str) -> str:
        """Определить серьёзность события (P1/P2/P3)."""
        return EVENT_SEVERITY.get(event_type, "P3")
    
    def _should_debounce(
        self,
        event_type: str,
        now: datetime
    ) -> bool:
        """
        Проверить дебаунс: нужно ли пропустить событие.
        
        Returns:
            True если событие уже отправлялось в текущем окне (пропустить)
        """
        window = DEBOUNCE_SEC.get(event_type, 0)
        
        # Нет дебаунса или нет store
        if window == 0 or self.store is None:
            return False
        
        # Вычисляем bucket текущего окна
        bucket = int(now.timestamp() // window)
        dedup_key = f"notify:{event_type}:{bucket}"
        
        # Пытаемся записать событие
        try:
            event_in = SimpleNamespace(
                dedup_key=dedup_key,
                event_type="notify_sent",
                event_ts=now,
                message_id=None,
                recipient_id=None,
                campaign_id=None,
                mailbox_id=None,
                provider=None,
                detail={"event_type": event_type}
            )
            
            _, created = self.store.append_event(event_in)
            
            # created=False означает уже была запись с таким dedup_key
            if not created:
                logger.debug(
                    "Debounce hit for %s in bucket %d",
                    event_type,
                    bucket
                )
                return True
            
        except Exception as e:
            logger.warning("Store debounce check failed: %s", e)
            # При ошибке store не блокируем отправку
            return False
        
        return False
    
    def _is_quiet_hours(self, now: datetime, severity: str) -> bool:
        """
        Проверить тихие часы для P3 событий.
        
        P3 события отправляются только 09:00-21:00 по Москве.
        P1 и P2 отправляются всегда.
        
        Returns:
            True если сейчас тихие часы и событие нельзя отправлять
        """
        if severity in ("P1", "P2"):
            return False
        
        # Конвертируем в московское время
        if self.msk_tz is not None:
            local_time = now.astimezone(self.msk_tz)
        else:
            # Фолбэк на UTC+3
            import datetime as dt
            utc_plus_3 = dt.timezone(dt.timedelta(hours=3))
            local_time = now.astimezone(utc_plus_3)
        
        hour = local_time.hour
        
        # Тихие часы: вне 09:00-21:00
        if hour < 9 or hour >= 21:
            logger.debug(
                "Quiet hours: event at %02d:00 MSK (P3 only 09:00-21:00)",
                hour
            )
            return True
        
        return False
    
    def _format_message(
        self,
        event_type: str,
        payload: dict,
        severity: str
    ) -> str:
        """
        Форматировать HTML-сообщение для Telegram.
        
        Args:
            event_type: тип события
            payload: данные события
            severity: серьёзность (P1/P2/P3)
        
        Returns:
            HTML-текст сообщения
        """
        # Эмодзи по серьёзности
        emoji = {
            "P1": "🔴",
            "P2": "🟠",
            "P3": "ℹ️"
        }.get(severity, "ℹ️")
        
        # Заголовок
        lines = [
            f"{emoji} <b>{severity}</b> {event_type}"
        ]
        
        # Ключевые поля payload построчно
        for key, value in payload.items():
            # Экранируем HTML
            value_str = str(value)
            value_str = (
                value_str
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            
            # Ограничиваем длину значений
            if len(value_str) > 200:
                value_str = value_str[:197] + "..."
            
            lines.append(f"  {key}: {value_str}")
        
        # Специальная обработка для warm_lead_created
        if event_type == "warm_lead_created" and "card_url" in payload:
            card_url = str(payload["card_url"])
            lines.append(f'  <a href="{card_url}">Открыть карточку</a>')
        
        return "\n".join(lines)
    
    def _send_telegram(
        self,
        chat_id: Any,
        text: str,
        retries: int = 2
    ) -> bool:
        """
        Отправить сообщение в Telegram через Bot API.
        
        Args:
            chat_id: ID чата
            text: HTML-текст сообщения
            retries: количество повторных попыток
        
        Returns:
            True при успешной отправке
        """
        url = f"{self.api_base}/bot{self.token}/sendMessage"
        
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        json_data = json.dumps(data).encode("utf-8")
        
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=json_data,
                    headers={"Content-Type": "application/json"}
                )
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        return True
                    else:
                        logger.warning(
                            "Telegram API returned status %d",
                            response.status
                        )
                        
            except urllib.error.HTTPError as e:
                # 5xx - можем повторить
                if e.code >= 500 and attempt < retries:
                    logger.warning(
                        "Telegram API HTTP %d, retry %d/%d",
                        e.code,
                        attempt + 1,
                        retries
                    )
                    continue
                else:
                    logger.exception("Telegram API HTTP error")
                    return False
                    
            except urllib.error.URLError as e:
                # Сетевая ошибка - можем повторить
                if attempt < retries:
                    logger.warning(
                        "Telegram API network error, retry %d/%d: %s",
                        attempt + 1,
                        retries,
                        e
                    )
                    continue
                else:
                    logger.exception("Telegram API network error")
                    return False
                    
            except Exception:
                logger.exception("Telegram API unexpected error")
                return False
        
        return False
    
    def notify(
        self,
        event_type: str,
        payload: dict,
        *,
        now: datetime | None = None
    ) -> bool:
        """
        Отправить уведомление о событии.
        
        Применяет дебаунс, проверяет тихие часы, отправляет в соответствующие чаты.
        
        Args:
            event_type: тип события
            payload: данные события
            now: опциональная метка времени (для тестирования)
        
        Returns:
            True если уведомление успешно отправлено
        """
        if self.disabled:
            return False
        
        if now is None:
            now = datetime.now(timezone.utc)
        
        severity = self._get_severity(event_type)
        
        # Проверка дебаунса
        if self._should_debounce(event_type, now):
            return False
        
        # Проверка тихих часов для P3
        if self._is_quiet_hours(now, severity):
            return False
        
        # Форматируем сообщение
        try:
            text = self._format_message(event_type, payload, severity)
        except Exception:
            logger.exception("Failed to format message")
            return False
        
        # Отправка в ops_chat
        success = self._send_telegram(self.ops_chat, text)
        
        # P1 события дополнительно в oncall_chat
        if success and severity == "P1" and self.oncall_chat:
            oncall_success = self._send_telegram(self.oncall_chat, text)
            if not oncall_success:
                logger.warning("Failed to send P1 to oncall_chat")
        
        return success
    
    def digest(
        self,
        stats: dict,
        *,
        now: datetime | None = None
    ) -> bool:
        """
        Отправить дневную сводку статистики.
        
        Args:
            stats: словарь со статистикой
            now: опциональная метка времени
        
        Returns:
            True при успешной отправке
        """
        if self.disabled:
            return False
        
        if now is None:
            now = datetime.now(timezone.utc)
        
        # Форматируем сводку как P3 событие
        try:
            lines = ["ℹ️ <b>P3</b> Дневная сводка"]
            
            for key, value in stats.items():
                value_str = str(value)
                value_str = (
                    value_str
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                
                lines.append(f"  {key}: {value_str}")
            
            text = "\n".join(lines)
            
        except Exception:
            logger.exception("Failed to format digest")
            return False
        
        # Отправляем в ops_chat
        return self._send_telegram(self.ops_chat, text)


def notify_gate_trips(
    notifier: Notifier,
    decisions: list,
    *,
    now: datetime | None = None
) -> int:
    """
    Отправить уведомления о срабатывании gate-ограничений.
    
    Хелпер для оркестратора: конвертирует GateDecision-подобные объекты
    в соответствующие события уведомлений.
    
    Args:
        notifier: экземпляр Notifier
        decisions: список объектов с атрибутами scope, target, tripped,
                   metric, value, threshold
        now: опциональная метка времени
    
    Returns:
        Количество успешно отправленных уведомлений
    """
    sent_count = 0
    
    for decision in decisions:
        # Пропускаем не-tripped решения
        if not getattr(decision, "tripped", False):
            continue
        
        scope = getattr(decision, "scope", None)
        target = getattr(decision, "target", None)
        metric = getattr(decision, "metric", None)
        value = getattr(decision, "value", None)
        threshold = getattr(decision, "threshold", None)
        
        # Определяем тип события по scope
        if scope == "global":
            event_type = "kill_switch_triggered"
        elif scope == "mailbox":
            # smtp_persistent_failure НЕТ в списке - используем общий mailbox_gate_trip
            event_type = "mailbox_gate_trip"
        elif scope == "recipient_provider":
            event_type = "provider_bounce_trip"
        else:
            # Неизвестный scope - пропускаем
            logger.warning("Unknown gate scope: %s", scope)
            continue
        
        # Формируем payload
        payload = {
            "scope": scope,
            "target": target,
            "metric": metric,
            "value": value,
            "threshold": threshold
        }
        
        # Отправляем уведомление
        try:
            if notifier.notify(event_type, payload, now=now):
                sent_count += 1
        except Exception:
            logger.exception(
                "Failed to notify gate trip: event_type=%s",
                event_type
            )
    
    return sent_count
