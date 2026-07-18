"""
Импорт и валидация базы получателей для холодной рассылки.

Модуль обеспечивает потоковую обработку CSV-файлов произвольного размера
с автодетектом формата, пакетную запись в БД и валидацию емейлов.
"""

import csv
import re
from pathlib import Path
from typing import Optional, Callable, Iterator, Any
from collections import Counter

try:
    from sender.store import Store, RecipientIn
    from sender.config import Config
    from sender.validation import Validation
    from sender.suppression import Suppression
    from sender.errors import SenderError
except ImportError:
    # Фолбэк если errors не экспортирован
    class SenderError(Exception):
        """Базовая ошибка движка рассылки."""


class ImporterError(SenderError):
    """Ошибка импорта данных."""


# Регулярка для базовой синтакс-проверки email
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9._+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$'
)


# Алиасы колонок для автодетекта
COLUMN_ALIASES = {
    'email': ['email', 'e-mail', 'почта', 'email_address', 'адрес'],
    'inn': ['inn', 'инн'],
    'company_name': ['company', 'название', 'наименование', 'организация', 'company_name'],
    'okved': ['okved', 'оквэд'],
    'segment': ['segment', 'сегмент'],
    'contact_name': ['contact', 'фио', 'контакт', 'contact_name'],
    'source': ['source', 'источник'],
}


def _detect_delimiter(path: Path, encoding: str = 'utf-8-sig') -> str:
    """
    Определяет разделитель CSV через csv.Sniffer.
    
    Читает первые 64КБ файла, пытается определить delimiter.
    Фолбэк: ';' затем ','.
    """
    try:
        with open(path, 'r', encoding=encoding, newline='') as f:
            sample = f.read(65536)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            return delimiter
    except (csv.Error, UnicodeDecodeError):
        pass
    
    # Фолбэк по популярности в российских CSV
    return ';'


def _detect_encoding(path: Path) -> str:
    """
    Определяет кодировку файла.
    
    Пробует utf-8-sig, при неудаче — cp1251.
    """
    for enc in ['utf-8-sig', 'cp1251']:
        try:
            with open(path, 'r', encoding=enc) as f:
                f.read(8192)
            return enc
        except UnicodeDecodeError:
            continue
    
    # На всякий случай вернём utf-8 как последний фолбэк
    return 'utf-8'


def _autodetect_column_map(headers: list[str]) -> dict[str, str]:
    """
    Автоматически определяет маппинг колонок по заголовку.
    
    Ищет совпадения с алиасами (регистронезависимо).
    Возвращает dict: canonical_name -> actual_header.
    """
    mapping = {}
    headers_lower = {h.strip().lower(): h for h in headers}
    
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in headers_lower:
                mapping[canonical] = headers_lower[alias]
                break
    
    return mapping


def _normalize_email(email: str) -> Optional[str]:
    """
    Нормализует email: strip, lower, базовая валидация.
    
    Возвращает None если email невалиден.
    """
    if not email:
        return None
    
    email = email.strip().lower()
    
    if not EMAIL_PATTERN.match(email):
        return None
    
    return email


def _extract_domain(email: str) -> str:
    """Извлекает домен из email."""
    return email.split('@', 1)[1]


def _read_csv_stream(
    path: Path,
    column_map: dict[str, str],
    delimiter: str,
    encoding: str,
) -> Iterator[dict[str, Any]]:
    """
    Потоковый читатель CSV с маппингом колонок.
    
    Yields словари с каноническими именами полей.
    """
    with open(path, 'r', encoding=encoding, newline='') as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        
        for row in reader:
            mapped = {}
            for canonical, header in column_map.items():
                value = row.get(header, '').strip()
                if value:
                    mapped[canonical] = value
            
            if mapped:
                yield mapped


def import_csv(
    store: Store,
    csv_path: str,
    *,
    column_map: Optional[dict[str, str]] = None,
    batch_size: int = 1000,
    limit: Optional[int] = None,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> dict[str, int]:
    """
    Импортирует получателей из CSV в базу.
    
    Потоковая обработка с автодетектом формата и батчинговой записью.
    Дедупликация по email происходит через upsert в БД, но для честного
    счётчика duplicates_in_file ведётся set встреченных email.
    
    Args:
        store: хранилище движка
        csv_path: путь к CSV-файлу
        column_map: явный маппинг канонических имён на заголовки CSV,
                   если None — автодетект
        batch_size: размер батча для bulk_upsert_recipients
        limit: максимум строк для обработки (None = все)
        progress_cb: коллбэк для отчёта прогресса, вызывается каждые 10000 строк
    
    Returns:
        Словарь со статистикой:
        - total_rows: всего строк обработано
        - imported: успешно импортировано
        - skipped_invalid: пропущено (невалидный email)
        - duplicates_in_file: повторы email внутри файла
    
    Raises:
        ImporterError: если обязательная колонка email не найдена
    """
    path = Path(csv_path)
    
    if not path.exists():
        raise ImporterError(f"Файл не найден: {csv_path}")
    
    # Детект кодировки и разделителя
    encoding = _detect_encoding(path)
    delimiter = _detect_delimiter(path, encoding)
    
    # Определяем маппинг колонок
    if column_map is None:
        with open(path, 'r', encoding=encoding, newline='') as f:
            reader = csv.reader(f, delimiter=delimiter)
            headers = next(reader, [])
        
        column_map = _autodetect_column_map(headers)
    
    # Проверяем наличие email
    if 'email' not in column_map:
        # Собираем список найденных колонок для диагностики
        with open(path, 'r', encoding=encoding, newline='') as f:
            reader = csv.reader(f, delimiter=delimiter)
            headers = next(reader, [])
        
        raise ImporterError(
            f"Обязательная колонка 'email' не найдена. "
            f"Найденные колонки: {', '.join(headers)}"
        )
    
    # Счётчики
    total_rows = 0
    imported = 0
    skipped_invalid = 0
    seen_emails = set()
    duplicates_in_file = 0
    
    # Батч для накопления
    batch = []
    
    # Потоковая обработка
    for row_dict in _read_csv_stream(path, column_map, delimiter, encoding):
        if limit is not None and total_rows >= limit:
            break
        
        total_rows += 1
        
        # Прогресс каждые 10000 строк
        if progress_cb and total_rows % 10000 == 0:
            progress_cb(total_rows)
        
        # Извлекаем и нормализуем email
        raw_email = row_dict.get('email', '')
        email = _normalize_email(raw_email)
        
        if not email:
            skipped_invalid += 1
            continue
        
        # Отслеживаем дубликаты внутри файла
        if email in seen_emails:
            duplicates_in_file += 1
        else:
            seen_emails.add(email)
        
        # Извлекаем домен
        domain = _extract_domain(email)
        
        # Собираем RecipientIn
        recipient = RecipientIn(
            email=email,
            domain=domain,
            inn=row_dict.get('inn'),
            company_name=row_dict.get('company_name'),
            okved=row_dict.get('okved'),
            segment=row_dict.get('segment'),
            contact_name=row_dict.get('contact_name'),
            source=row_dict.get('source'),
        )
        
        batch.append(recipient)
        
        # Сброс батча
        if len(batch) >= batch_size:
            count = store.bulk_upsert_recipients(batch)
            imported += count
            batch.clear()
    
    # Финальный батч
    if batch:
        count = store.bulk_upsert_recipients(batch)
        imported += count
    
    # Финальный прогресс
    if progress_cb and total_rows > 0:
        progress_cb(total_rows)
    
    return {
        'total_rows': total_rows,
        'imported': imported,
        'skipped_invalid': skipped_invalid,
        'duplicates_in_file': duplicates_in_file,
    }


def import_suppression(
    store: Store,
    path: str,
    *,
    scope: str,
    reason: str = "competitor",
) -> int:
    """
    Импортирует список подавления из файла.
    
    Файл содержит значения по строке (ИНН или домены).
    Строки начинающиеся с '#' игнорируются как комментарии.
    
    Args:
        store: хранилище движка
        path: путь к файлу
        scope: 'inn' или 'domain'
        reason: причина подавления
    
    Returns:
        Количество добавленных записей.
    
    Raises:
        ImporterError: при неверном scope или ошибке чтения
    """
    if scope not in ('inn', 'domain'):
        raise ImporterError(f"Неверный scope: {scope}. Ожидается 'inn' или 'domain'")
    
    file_path = Path(path)
    if not file_path.exists():
        raise ImporterError(f"Файл не найден: {path}")
    
    suppression = Suppression(store)
    added = 0
    
    # Определяем кодировку
    encoding = _detect_encoding(file_path)
    
    with open(file_path, 'r', encoding=encoding) as f:
        for line in f:
            line = line.strip()
            
            # Пропускаем комментарии и пустые строки
            if not line or line.startswith('#'):
                continue
            
            # Добавляем в подавление
            if scope == 'inn':
                if suppression.add_inn(line, reason, source=str(file_path)):
                    added += 1
            else:  # domain
                # Нормализуем домен
                domain = line.lower()
                if suppression.add_domain(domain, reason, source=str(file_path)):
                    added += 1
    
    return added


def validate_recipients(
    store: Store,
    config: Config,
    *,
    limit: Optional[int] = None,
    only_unknown: bool = True,
    batch_size: int = 200,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> dict[str, int]:
    """
    Валидирует получателей через внешний сервис.
    
    Процесс резюмируем: при only_unknown=True валидируются только получатели
    с valid_status='unknown', уже провалидированные не трогаются.
    
    Сначала собирает список (id, email) для валидации (чтобы избежать
    конфликтов курсора при параллельной записи), затем валидирует батчами
    и обновляет статусы в БД.
    
    Args:
        store: хранилище движка
        config: конфигурация (нужна для Validation)
        limit: максимум получателей для валидации (None = все)
        only_unknown: валидировать только с valid_status='unknown'
        batch_size: размер батча для validate_batch
        progress_cb: коллбэк для прогресса, вызывается каждые 1000 получателей
    
    Returns:
        Словарь со счётчиками по статусам:
        - total: всего провалидировано
        - valid: валидных
        - invalid: невалидных
        - unknown: неопределённых (сервис недоступен и т.п.)
        - risky: рискованных
    """
    # Собираем список получателей для валидации
    recipients_to_validate = []
    
    valid_status_filter = 'unknown' if only_unknown else None
    
    for recipient in store.iter_recipients(valid_status=valid_status_filter):
        recipients_to_validate.append((recipient.id, recipient.email))
        
        if limit is not None and len(recipients_to_validate) >= limit:
            break
    
    if not recipients_to_validate:
        return {
            'total': 0,
            'valid': 0,
            'invalid': 0,
            'unknown': 0,
            'risky': 0,
        }
    
    # Валидируем батчами
    validation = Validation(config)
    status_counts = Counter()
    processed = 0
    
    for i in range(0, len(recipients_to_validate), batch_size):
        batch = recipients_to_validate[i:i + batch_size]
        emails = [email for _, email in batch]
        
        # Валидация батча
        results = validation.validate_batch(emails)
        
        # Обновляем статусы в БД
        for (recipient_id, _), result in zip(batch, results):
            store.set_recipient_validation(
                recipient_id,
                valid_status=result.valid_status,
                mx_provider=result.provider,
                catch_all=getattr(result, 'catch_all', None),
                role_based=getattr(result, 'role_based', None),
                disposable=getattr(result, 'disposable', None),
            )
            
            status_counts[result.valid_status] += 1
            processed += 1
        
        # Прогресс каждые 1000 получателей
        if progress_cb and processed % 1000 == 0:
            progress_cb(processed)
    
    # Финальный прогресс
    if progress_cb and processed > 0:
        progress_cb(processed)
    
    return {
        'total': processed,
        'valid': status_counts.get('valid', 0),
        'invalid': status_counts.get('invalid', 0),
        'unknown': status_counts.get('unknown', 0),
        'risky': status_counts.get('risky', 0),
    }


def _read_suppression_file(path: Path) -> Iterator[str]:
    """
    Потоковый читатель файла подавления.
    
    Yields строки без комментариев и пустых строк.
    """
    encoding = _detect_encoding(path)
    
    with open(path, 'r', encoding=encoding) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                yield line


def import_suppression_bulk(
    store: Store,
    path: str,
    *,
    scope: str,
    reason: str = "competitor",
    batch_size: int = 1000,
) -> int:
    """
    Массовый импорт подавления через import_competitors.
    
    Использует Suppression.import_competitors для эффективной батчевой вставки.
    
    Args:
        store: хранилище движка
        path: путь к файлу
        scope: 'inn' или 'domain'
        reason: причина подавления
        batch_size: размер батча для import_competitors
    
    Returns:
        Количество добавленных записей.
    """
    if scope not in ('inn', 'domain'):
        raise ImporterError(f"Неверный scope: {scope}. Ожидается 'inn' или 'domain'")
    
    file_path = Path(path)
    if not file_path.exists():
        raise ImporterError(f"Файл не найден: {path}")
    
    suppression = Suppression(store)
    total_added = 0
    batch = []
    
    for value in _read_suppression_file(file_path):
        if scope == 'domain':
            value = value.lower()
        
        batch.append(value)
        
        if len(batch) >= batch_size:
            added = suppression.import_competitors(batch, scope=scope)
            total_added += added
            batch.clear()
    
    # Финальный батч
    if batch:
        added = suppression.import_competitors(batch, scope=scope)
        total_added += added
    
    return total_added
