"""
Клиент Постофиса Mail.ru (postmaster.mail.ru) для мониторинга репутации доменов рассылки.

ВАЖНО: Точные пути API endpoints необходимо сверить с актуальной документацией Mail.ru
при первом live-вызове после получения токена и подтверждения доменов в кабинете.
Все пути и базовый URL настраиваются через config, чтобы легко адаптировать к реальному API.

Модуль работает в режиме disabled при отсутствии токена — все публичные методы становятся
безопасными no-op (логируют warning, возвращают None/False) без падения сервиса.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from sender.errors import SenderError  # noqa: E402

# Попытка импорта SenderError из sender.errors, фолбэк на локальный класс


logger = logging.getLogger(__name__)


class PostofficeError(SenderError):
    """Ошибка при работе с API Постофиса Mail.ru."""
    pass


class PostofficeClient:
    """
    Клиент для работы с API Постофиса Mail.ru.
    
    Поддерживает получение сводки по домену, статистики спам-жалоб и генерацию отчётов.
    При отсутствии токена работает в режиме disabled (методы возвращают None).
    """

    def __init__(self, config: Any):
        """
        Инициализация клиента.

        Args:
            config: Объект конфигурации с методом get(key, default).
        """
        self._config = config
        self._disabled = False

        # Получаем имя переменной окружения для токена
        token_env = config.get("postoffice.token_env", "POSTOFFICE_TOKEN")
        self._token = os.environ.get(token_env, "").strip()

        # o2-flow (реальный Postmaster API Mail.ru): бессрочный refresh_token
        # обменивается на часовой access_token на https://o2.mail.ru/token.
        # Если задан refresh — берём токен из него (и обновляем при 401/403).
        refresh_env = config.get("postoffice.refresh_token_env",
                                 "POSTMASTER_REFRESH_TOKEN")
        self._refresh_token = os.environ.get(refresh_env, "").strip()
        self._o2_url = config.get("postoffice.o2_url", "https://o2.mail.ru/token")
        self._o2_client_id = config.get("postoffice.o2_client_id",
                                        "postmaster_api_client")

        if not self._token and self._refresh_token:
            try:
                self._refresh_access_token()
            except Exception as exc:  # noqa: BLE001 - не роняем сборку
                logger.warning("Постофис: обмен refresh_token не удался: %s", exc)

        if not self._token:
            logger.warning(
                "Постофис Mail.ru: токен не найден (%s / %s), модуль disabled",
                token_env, refresh_env
            )
            self._disabled = True
            self._base_url = ""
            return

        # Базовый URL API (конфигурируемый)
        self._base_url = config.get(
            "postoffice.base_url",
            "https://postmaster.mail.ru"
        ).rstrip("/")

        # Таймаут запросов
        self._timeout = config.get("postoffice.timeout", 15)

        # Количество повторов при ошибках сети/5xx
        self._retries = config.get("postoffice.retries", 2)

        # Задержка между повторами (секунды)
        self._retry_delay = config.get("postoffice.retry_delay", 1.0)

        logger.info("Постофис Mail.ru: клиент инициализирован, base=%s", self._base_url)

    def _refresh_access_token(self) -> None:
        """Обменять refresh_token на свежий access_token (o2.mail.ru/token).

        refresh_token бессрочный; access живёт час. Сбой → PostofficeError,
        вызывающий сам решает (в __init__ — degrade в disabled)."""
        if not self._refresh_token:
            raise PostofficeError("нет refresh_token для обновления access")
        data = urllib.parse.urlencode({
            "client_id": self._o2_client_id,
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }).encode()
        req = urllib.request.Request(
            self._o2_url, data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise PostofficeError(f"o2 refresh failed: {exc}") from exc
        token = (payload.get("access_token") or "").strip()
        if not token:
            raise PostofficeError(f"o2 без access_token: {payload}")
        self._token = token
        logger.info("Постофис: access_token обновлён через refresh_token")

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """
        Выполнить GET-запрос к API.

        Args:
            path: Путь относительно base_url (например, "/domain/summary").
            params: Параметры запроса (словарь).

        Returns:
            Распарсенный JSON-ответ как словарь.

        Raises:
            PostofficeError: При ошибке запроса или некорректном ответе.
        """
        if self._disabled:
            return {}

        if params is None:
            params = {}

        # Ревью (подтверждено): токен в query-string оседает в access-логах
        # и прокси — передаём ТОЛЬКО заголовком Authorization (ниже).
        # Формируем полный URL
        query_string = urllib.parse.urlencode(params)
        url = f"{self._base_url}{path}?{query_string}"

        # Подготовка заголовков (также передаём токен через Authorization)
        # ВАЖНО (сверено с help.mail.ru/postmaster/api 28.07.2026): Постмастер
        # ждёт НЕСТАНДАРТНЫЙ заголовок «Bearer: <access_token>», а не
        # «Authorization: Bearer». Authorization шлём тоже - на случай, если
        # сервис начнёт понимать канон.
        headers = {
            "Bearer": self._token,
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": "SenderService/1.0"
        }

        # Попытки с ретраями
        last_error = None
        refreshed = False
        for attempt in range(self._retries + 1):
            try:
                headers["Bearer"] = self._token
                headers["Authorization"] = f"Bearer {self._token}"
                request = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    status = response.status
                    body = response.read().decode("utf-8")

                    # Успешный ответ
                    if 200 <= status < 300:
                        try:
                            return json.loads(body)
                        except json.JSONDecodeError as e:
                            raise PostofficeError(
                                f"Некорректный JSON в ответе: {e}"
                            ) from e

                    # 5xx — можем попробовать ещё раз
                    if status >= 500:
                        last_error = PostofficeError(
                            f"Ошибка сервера {status}: {body[:200]}"
                        )
                        if attempt < self._retries:
                            time.sleep(self._retry_delay * (attempt + 1))
                            continue
                        raise last_error

                    # 4xx и другие — не ретраим
                    raise PostofficeError(
                        f"HTTP {status}: {body[:200]}"
                    )

            except urllib.error.HTTPError as e:
                # HTTPError уже содержит код ответа
                status = e.code
                body = e.read().decode("utf-8", errors="replace")

                # 401/403 — access_token протух: один раз обновляем по refresh
                # и повторяем тот же запрос (не считая это ретраем сети).
                if status in (401, 403) and self._refresh_token and not refreshed:
                    refreshed = True
                    try:
                        self._refresh_access_token()
                        continue
                    except PostofficeError:
                        pass

                if status >= 500:
                    last_error = PostofficeError(
                        f"HTTP {status}: {body[:200]}"
                    )
                    if attempt < self._retries:
                        time.sleep(self._retry_delay * (attempt + 1))
                        continue
                    raise last_error

                raise PostofficeError(
                    f"HTTP {status}: {body[:200]}"
                ) from e

            except urllib.error.URLError as e:
                # Сетевая ошибка — ретраим
                last_error = PostofficeError(
                    f"Ошибка сети: {e.reason}"
                )
                if attempt < self._retries:
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue
                raise last_error from e

            except Exception as e:
                raise PostofficeError(
                    f"Неожиданная ошибка при запросе: {e}"
                ) from e

        # Если дошли сюда, значит все попытки исчерпаны
        if last_error:
            raise last_error
        raise PostofficeError("Не удалось выполнить запрос")

    def domain_summary(self, domain: str) -> Optional[dict]:
        """
        Получить сводку по домену (общая репутация, статус и т.д.).

        Args:
            domain: Доменное имя для проверки.

        Returns:
            Словарь с данными от API или None, если клиент в режиме disabled.
        """
        if self._disabled:
            logger.warning("Постофис Mail.ru disabled: domain_summary(%s) -> None", domain)
            return None

        path = self._config.get("postoffice.summary_path", "/ext-api/stat-list/")
        # у Постмастера stat-list требует date_from; без него 400. Берём
        # последние 7 дней - тот горизонт, на котором видно смену репутации.
        from datetime import date, timedelta
        params = {"domain": domain,
                  "date_from": (date.today() - timedelta(days=7)).isoformat(),
                  "date_to": date.today().isoformat()}

        try:
            result = self._get(path, params)
            logger.debug("Постофис: summary для %s получена", domain)
            return result
        except PostofficeError as e:
            logger.error("Постофис: ошибка получения summary для %s: %s", domain, e)
            raise

    def spam_rate(
        self,
        domain: str,
        date_from: str,
        date_to: str
    ) -> Optional[dict]:
        """
        Получить статистику спам-жалоб по домену за период.

        Args:
            domain: Доменное имя.
            date_from: Начало периода в формате YYYY-MM-DD.
            date_to: Конец периода в формате YYYY-MM-DD.

        Returns:
            Словарь с данными от API или None, если клиент в режиме disabled.
        """
        if self._disabled:
            logger.warning(
                "Постофис Mail.ru disabled: spam_rate(%s, %s, %s) -> None",
                domain, date_from, date_to
            )
            return None

        path = self._config.get("postoffice.spam_path", "/ext-api/stat-list-detailed/")
        params = {
            "domain": domain,
            "date_from": date_from,
            "date_to": date_to
        }

        try:
            result = self._get(path, params)
            logger.debug(
                "Постофис: spam_rate для %s (%s..%s) получена",
                domain, date_from, date_to
            )
            return result
        except PostofficeError as e:
            logger.error(
                "Постофис: ошибка получения spam_rate для %s: %s",
                domain, e
            )
            raise

    def reg_list(self) -> Optional[list]:
        """Домены, подтверждённые в кабинете Постмастера (/ext-api/reg-list/).

        Первый вызов после получения токена: если тут пусто, статистики не
        будет ни по одному домену — их сначала надо подтвердить в кабинете.
        """
        if self._disabled:
            return None
        d = self._get(self._config.get("postoffice.reg_list_path",
                                       "/ext-api/reg-list/"))
        return d.get("domains") if isinstance(d, dict) else d

    def troubles(self) -> Optional[list]:
        """Домены с проблемами SPF/DKIM/DMARC по мнению Mail.ru
        (/ext-api/troubles-list/) — самый ценный для нас метод: показывает
        ровно те причины, по которым письма уходят в спам."""
        if self._disabled:
            return None
        d = self._get(self._config.get("postoffice.troubles_path",
                                       "/ext-api/troubles-list/"))
        return d.get("troubles") if isinstance(d, dict) else d

    def report(self, domains: list[str]) -> dict:
        """
        Сформировать отчёт по списку доменов (summary + spam за последние 7 дней).

        Ошибки по отдельным доменам не прерывают формирование отчёта — домен с ошибкой
        попадает в результат с ключом "error".

        Args:
            domains: Список доменных имён для проверки.

        Returns:
            Словарь вида {"domains": [{"domain": ..., "summary": ..., "spam": ...}, ...]}.
        """
        if self._disabled:
            logger.warning("Постофис Mail.ru disabled: report() -> пустой отчёт")
            return {"domains": []}

        # Вычисляем даты для запроса спам-статистики (последние 7 дней)
        now = datetime.now(timezone.utc)
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        results = []

        for domain in domains:
            domain_result = {"domain": domain}

            # Получаем summary
            try:
                summary = self.domain_summary(domain)
                domain_result["summary"] = summary
            except PostofficeError as e:
                domain_result["error"] = f"summary: {e}"
                results.append(domain_result)
                continue

            # Получаем spam_rate
            try:
                spam = self.spam_rate(domain, date_from, date_to)
                domain_result["spam"] = spam
            except PostofficeError as e:
                domain_result["error"] = f"spam_rate: {e}"
                results.append(domain_result)
                continue

            results.append(domain_result)

        logger.info("Постофис: отчёт сформирован для %d доменов", len(domains))
        return {"domains": results}


def reputation_alert(
    report: dict,
    *,
    spam_threshold_pct: float = 1.0
) -> list[str]:
    """
    Проверить отчёт на превышение порога спам-жалоб и сформировать список алертов.

    Ищет показатели спам-жалоб гибко (ключи вида spam/complaints/spam_rate) в данных
    каждого домена. Если показатель найден и превышает порог — формируется алерт.

    Args:
        report: Отчёт, возвращённый методом PostofficeClient.report().
        spam_threshold_pct: Порог процента спам-жалоб (по умолчанию 1.0%).

    Returns:
        Список строк-алертов для доменов с превышением порога.
    """
    alerts = []

    domains = report.get("domains", [])
    if not domains:
        return alerts

    for domain_data in domains:
        domain = domain_data.get("domain", "unknown")

        # Если есть ошибка — включаем её в алерт
        if "error" in domain_data:
            alerts.append(
                f"[{domain}] Ошибка получения данных: {domain_data['error']}"
            )
            continue

        # Ищем показатели спам-жалоб в данных
        spam_data = domain_data.get("spam", {})
        summary_data = domain_data.get("summary", {})

        # Ищем ключи с процентом спама (гибкий поиск)
        spam_rate = None

        # Вариант 1: spam.spam_rate
        if isinstance(spam_data, dict):
            spam_rate = _find_spam_rate(spam_data)

        # Вариант 2: summary.spam_rate или summary.complaints
        if spam_rate is None and isinstance(summary_data, dict):
            spam_rate = _find_spam_rate(summary_data)

        # Если показатель не найден — пропускаем
        if spam_rate is None:
            continue

        # Проверяем превышение порога
        if spam_rate > spam_threshold_pct:
            alerts.append(
                f"[{domain}] Превышен порог спам-жалоб: {spam_rate:.2f}% "
                f"(порог: {spam_threshold_pct:.2f}%)"
            )

    return alerts


def _find_spam_rate(data: dict) -> Optional[float]:
    """
    Гибкий поиск показателя процента спам-жалоб в словаре данных.

    Ищет ключи вида: spam_rate, spam, complaints, complaint_rate и т.д.

    Args:
        data: Словарь с данными от API.

    Returns:
        Числовое значение процента спам-жалоб или None, если не найдено.
    """
    # Список возможных ключей для показателя спама (в порядке приоритета)
    possible_keys = [
        "spam_rate",
        "spam_pct",
        "spam_percent",
        "complaint_rate",
        "complaints_pct",
        "spam",
        "complaints"
    ]

    for key in possible_keys:
        value = data.get(key)
        if value is not None:
            # Пытаемся преобразовать в float
            try:
                return float(value)
            except (ValueError, TypeError):
                continue

    # Рекурсивно ищем во вложенных словарях
    for value in data.values():
        if isinstance(value, dict):
            result = _find_spam_rate(value)
            if result is not None:
                return result

    return None
