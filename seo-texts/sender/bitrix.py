"""
Коннектор Bitrix24 CRM для сервиса холодной B2B-рассылки ООО «Руспром».

Создаёт лиды из тёплых ответов на рассылку. Использует Bitrix24 REST API через webhook.
Модуль самодостаточен: работает только со стандартной библиотекой Python 3.11.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Попытка импорта базового исключения из общего модуля
try:
    from sender.errors import SenderError
except ImportError:
    class SenderError(Exception):
        """Базовое исключение для ошибок модулей sender."""
        pass


logger = logging.getLogger(__name__)


class BitrixError(SenderError):
    """Ошибка при взаимодействии с Bitrix24 API."""
    pass


class Suppression(Protocol):
    """Протокол для управления списком подавления."""
    def add_email(
        self,
        email: str,
        reason: str,
        *,
        source: str = "",
        campaign_id: Optional[int] = None
    ) -> bool:
        ...


class ReplyDeskSink(Protocol):
    """Протокол для обработки тёплых ответов на рассылку."""
    def push_warm_lead(
        self,
        recipient: Any,
        thread_id: str,
        snippet: str
    ) -> Optional[int]:
        ...


class BitrixClient:
    """
    HTTP-клиент для Bitrix24 REST API.
    
    Использует webhook URL для аутентификации. Поддерживает ретраи с экспоненциальным
    бэкоффом при временных сбоях сети и серверных ошибках.
    """

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = 15.0,
        retries: int = 3
    ) -> None:
        """
        Args:
            webhook_url: URL вебхука Bitrix24 (без имени метода)
            timeout: Таймаут HTTP-запроса в секундах
            retries: Количество повторных попыток при сбоях
        """
        self.webhook_url = webhook_url.rstrip('/')
        self.timeout = timeout
        self.retries = retries

    def call(self, method: str, params: dict) -> dict:
        """
        Выполняет вызов метода Bitrix24 REST API.
        
        Args:
            method: Имя метода API (например, 'crm.lead.add')
            params: Параметры запроса
            
        Returns:
            Результат вызова (содержимое поля 'result' из ответа)
            
        Raises:
            BitrixError: При ошибках API или сетевых проблемах после всех ретраев
        """
        url = f"{self.webhook_url}/{method}.json"
        payload = json.dumps(params).encode('utf-8')
        
        last_error = None
        
        for attempt in range(self.retries):
            try:
                request = Request(
                    url,
                    data=payload,
                    headers={'Content-Type': 'application/json'}
                )
                
                with urlopen(request, timeout=self.timeout) as response:
                    response_data = json.loads(response.read().decode('utf-8'))
                    
                    # Проверка на ошибку в ответе API
                    if 'error' in response_data:
                        error_msg = response_data.get(
                            'error_description',
                            response_data.get('error', 'Unknown error')
                        )
                        raise BitrixError(
                            f"Bitrix API error in {method}: {error_msg}"
                        )
                    
                    return response_data.get('result', {})
                    
            except HTTPError as e:
                # Клиентские ошибки (4xx) не ретраим
                if 400 <= e.code < 500:
                    raise BitrixError(
                        f"HTTP {e.code} error calling {method}: {e.reason}"
                    ) from e
                
                # Серверные ошибки (5xx) ретраим
                last_error = e
                
            except (URLError, OSError) as e:
                # Сетевые ошибки и таймауты ретраим
                last_error = e
            
            # Ретрай с экспоненциальным бэкоффом
            if attempt < self.retries - 1:
                backoff = 2 ** attempt  # 1, 2, 4 секунды
                logger.warning(
                    f"Bitrix API call {method} failed (attempt {attempt + 1}/"
                    f"{self.retries}), retrying in {backoff}s: {last_error}"
                )
                time.sleep(backoff)
        
        # Исчерпаны все попытки
        raise BitrixError(
            f"Failed to call {method} after {self.retries} attempts: {last_error}"
        ) from last_error


def extract_phone(text: str) -> Optional[str]:
    """
    Извлекает российский телефонный номер из текста.
    
    Поддерживает форматы: +7..., 8..., с разделителями (пробелы, дефисы, скобки).
    
    Args:
        text: Текст для поиска телефона
        
    Returns:
        Найденный номер телефона или None
    """
    if not text:
        return None
    
    # Паттерн для российских номеров: +7 или 8, затем 10 цифр
    # Допускаются пробелы, дефисы, скобки между цифрами
    pattern = r'(?:\+7|8)[\s\-\(]?\d{3}[\s\-\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
    
    match = re.search(pattern, text)
    if match:
        # Очищаем от разделителей
        phone = re.sub(r'[\s\-\(\)]', '', match.group(0))
        # Нормализуем: 8 -> +7
        if phone.startswith('8'):
            phone = '+7' + phone[1:]
        return phone
    
    return None


class BitrixSink:
    """
    Обработчик тёплых ответов для создания лидов в Bitrix24 CRM.
    
    Реализует протокол ReplyDeskSink. При получении тёплого ответа на рассылку
    создаёт лид в CRM с данными получателя и контекстом переписки.
    
    Поддерживает disabled-режим: если webhook URL не настроен, методы становятся
    безопасными no-op операциями (логируют warning, возвращают None/False).
    """

    def __init__(self, config: Any, store: Any = None) -> None:
        """
        Args:
            config: Объект конфигурации с методом get(key, default)
            store: Опциональное хранилище для дедупликации (с методом append_event)
        """
        self.config = config
        self.store = store
        self.enabled = False
        self.client: Optional[BitrixClient] = None
        
        # Получаем webhook URL из переменной окружения
        webhook_env_name = config.get("bitrix.webhook_env", "BITRIX_WEBHOOK_URL")
        webhook_url = os.environ.get(webhook_env_name)
        
        if not webhook_url:
            logger.warning(
                f"Bitrix24 connector disabled: environment variable "
                f"{webhook_env_name} not set"
            )
            return
        
        # Настройки
        self.entity = config.get("bitrix.entity", "lead")
        if self.entity != "lead":
            logger.warning(
                f"Bitrix24: entity '{self.entity}' not supported, using 'lead'"
            )
            self.entity = "lead"
        
        self.default_responsible = config.get("bitrix.default_responsible")
        self.source_id = config.get("bitrix.source_id", "EMAIL")
        self.portal_url = config.get("bitrix.portal_url")
        
        # Инициализируем клиент
        timeout = config.get("bitrix.timeout", 15.0)
        retries = config.get("bitrix.retries", 3)
        
        try:
            self.client = BitrixClient(
                webhook_url,
                timeout=timeout,
                retries=retries
            )
            self.enabled = True
            logger.info("Bitrix24 connector initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Bitrix24 client: {e}")

    def push_warm_lead(
        self,
        recipient: Any,
        thread_id: str,
        snippet: str
    ) -> Optional[int]:
        """
        Создаёт лид в Bitrix24 CRM из тёплого ответа на рассылку.
        
        Использует дедупликацию через store (если доступен) для предотвращения
        создания дубликатов при повторном поллинге IMAP.
        
        Args:
            recipient: Объект получателя с данными компании и контакта
            thread_id: Идентификатор email-треда (Message-ID или References)
            snippet: Фрагмент письма-ответа
            
        Returns:
            ID созданного лида или None (если лид уже создан, disabled-режим или ошибка)
        """
        if not self.enabled:
            logger.warning(
                "Bitrix24 connector disabled, skipping warm lead push"
            )
            return None
        
        # Дедупликация через store
        if self.store:
            dedup_key = f"bitrix_lead:{thread_id or recipient.email}"
            
            event = SimpleNamespace(
                dedup_key=dedup_key,
                event_type="bitrix_lead_created",
                event_ts=datetime.now(timezone.utc),
                message_id=None,
                recipient_id=recipient.id,
                campaign_id=None,
                mailbox_id=None,
                provider=None,
                detail={"thread_id": thread_id}
            )
            
            try:
                _, created = self.store.append_event(event)
                if not created:
                    logger.info(
                        f"Bitrix24 lead already exists for thread {thread_id}, "
                        f"skipping (dedup)"
                    )
                    return None
            except Exception as e:
                logger.error(f"Failed to check dedup for thread {thread_id}: {e}")
                # Продолжаем без дедупа — лучше дубликат, чем потеря лида
        
        # Формируем данные лида
        company = recipient.company_name or ""
        email = recipient.email
        contact_name = recipient.contact_name
        
        title = f"Ответ на рассылку: {company or email}"
        
        fields = {
            "TITLE": title,
            "EMAIL": [{"VALUE": email, "VALUE_TYPE": "WORK"}],
            "SOURCE_ID": self.source_id,
        }
        
        if contact_name:
            fields["NAME"] = contact_name
        
        if company:
            fields["COMPANY_TITLE"] = company
        
        # Комментарий с контекстом
        comments_parts = []
        if thread_id:
            comments_parts.append(f"Тред: {thread_id}")
        if snippet:
            comments_parts.append(snippet)
        
        if comments_parts:
            fields["COMMENTS"] = "\n\n".join(comments_parts)
        
        # Ответственный
        if self.default_responsible:
            fields["ASSIGNED_BY_ID"] = self.default_responsible
        
        # Извлечение телефона из snippet
        phone = extract_phone(snippet) if snippet else None
        if phone:
            fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "WORK"}]
        
        # Создание лида через API
        try:
            result = self.client.call("crm.lead.add", {"fields": fields})
            lead_id = int(result)
            
            logger.info(
                f"Created Bitrix24 lead #{lead_id} for {email} "
                f"(thread: {thread_id})"
            )
            
            return lead_id
            
        except BitrixError as e:
            logger.exception(
                f"Failed to create Bitrix24 lead for {email} "
                f"(thread: {thread_id}): {e}"
            )
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error creating Bitrix24 lead for {email}: {e}"
            )
            return None

    def card_url(self, lead_id: int) -> Optional[str]:
        """
        Формирует URL карточки лида в Bitrix24.
        
        Args:
            lead_id: ID лида в CRM
            
        Returns:
            URL карточки лида или None, если portal_url не настроен
        """
        if not self.portal_url:
            return None
        
        portal = self.portal_url.rstrip('/')
        return f"{portal}/crm/lead/details/{lead_id}/"
