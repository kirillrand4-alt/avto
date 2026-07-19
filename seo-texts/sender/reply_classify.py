"""
Суб-классификация входящих ответов холодной B2B-рассылки (RU).

Различает категории ответов:
- hot: явная заинтересованность, запрос КП/счёта
- interested: запрос дополнительной информации
- neutral: нейтральный ответ без явных сигналов
- auto_reply: автоответ, отпуск, вне офиса
- not_interested: отказ, нет потребности
- unsub_request: просьба отписать

Извлекает контактные данные (телефон, имя из подписи).
"""

import re
from dataclasses import dataclass
from typing import Optional, Protocol

# Пытаемся импортировать SenderError, иначе локальный fallback
try:
    from sender.errors import SenderError
except ImportError:
    class SenderError(Exception):
        """Локальный fallback для ошибок модуля sender."""
        pass


@dataclass(frozen=True)
class ReplySignal:
    """
    Результат классификации ответа.
    
    Поля:
        kind: категория ответа (hot | interested | neutral | auto_reply | not_interested | unsub_request)
        confidence: уверенность в классификации (0..1)
        phone: извлечённый номер телефона в формате +7XXXXXXXXXX
        contact_hint: имя/должность из подписи письма
        matched: кортеж сработавших маркеров (для отладки)
    """
    kind: str
    confidence: float
    phone: Optional[str] = None
    contact_hint: Optional[str] = None
    matched: tuple[str, ...] = ()


class AiClassifier(Protocol):
    """Протокол для опционального AI-классификатора."""
    
    def classify(self, subject: str, body: str) -> dict:
        """
        Классифицировать текст с помощью AI.
        
        Возвращает dict с ключами:
            kind: str — категория
            confidence: float — уверенность
            phone: Optional[str] — извлечённый телефон
        """
        ...


# Словари маркеров для классификации (регистронезависимо, ё→е)
_AUTO_REPLY_MARKERS = (
    'автоответ',
    'в отпуске',
    'нахожусь в отпуске',
    'вне офиса',
    'out of office',
    'ooo:',
    'буду недоступен',
    'вернусь',
    'командировк',
    'автоматически',
    'автоматический ответ',
)

_UNSUB_MARKERS = (
    'отпишите',
    'отписаться',
    'уберите из рассылки',
    'удалите меня',
    'не пишите',
    'прекратите присылать',
    'unsubscribe',
    'больше не присылайте',
    'не хочу получать',
    'отписка',
)

_NOT_INTERESTED_MARKERS = (
    'не интересует',
    'не интересно',
    'неактуально',
    'не актуально',
    'нет потребности',
    'не требуется',
    'спасибо, не нужно',
    'уже купили',
    'есть поставщик',
    'не нужно',
    'нам не подходит',
    'не рассматриваем',
)

_HOT_MARKERS = (
    'выставьте счет',
    'выставьте счёт',
    'счет на оплату',
    'счёт на оплату',
    'готовы купить',
    'готовы заказать',
    'пришлите кп',
    'коммерческое предложение',
    'прайс',
    'позвоните',
    'перезвоните',
    'свяжитесь со мной',
    'хочу купить',
    'заказать',
    'оформить заказ',
)

_INTERESTED_MARKERS = (
    'пришлите',
    'подробнее',
    'расскажите',
    'характеристики',
    'сроки поставки',
    'условия',
    'каталог',
    'больше информации',
    'дополнительные сведения',
    'уточните',
)

# Заголовки, указывающие на автоответ
_AUTO_REPLY_HEADERS = (
    'auto-submitted',
    'x-autoreply',
    'x-autorespond',
    'x-autoresponder',
)


def _normalize_text(text: str) -> str:
    """Нормализация текста: lowercase, ё→е."""
    return text.lower().replace('ё', 'е')


def normalize_phone(value: str) -> Optional[str]:
    """Нормализовать телефонную строку в канон +7XXXXXXXXXX (или None).

    Тонкая обёртка над :func:`extract_phone` для веб-панели: оператор вводит
    номер в произвольном формате (8 921…, +7 (921)…), на выходе — единый вид
    для сравнения/дедупа лидов.
    """
    return extract_phone(value)


def extract_phone(text: str) -> Optional[str]:
    """
    Извлечь российский телефон из текста.
    
    Поддерживаемые форматы:
    - +7XXXXXXXXXX
    - 8XXXXXXXXXX
    - 7XXXXXXXXXX
    - с разделителями: скобки, дефисы, пробелы
    
    Возвращает нормализованный формат +7XXXXXXXXXX или None.
    Не путает с ИНН (12 цифр) и другими числами.
    """
    if not text:
        return None

    # Префикс +7/8/7 и РОВНО 10 цифр после него (с разделителями), границы по
    # цифрам с двух сторон: ИНН 7712345678 (10 цифр, где 7 — первая ЦИФРА
    # номера, а не префикс) не матчится — после префикса остаётся только 9.
    pattern = re.compile(r"(?<!\d)(?:\+\s*7|[78])(?:[\s\-().]*\d){10}(?!\d)")

    for match in pattern.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))[-10:]
        # первая цифра кода: мобильные 9xx и города 3xx-6xx/8xx; 7xx в РФ
        # не выделены (и отсекают 12-значные ИНН вида 77…)
        if digits[0] in "345689":
            return f"+7{digits}"

    return None


def _extract_contact_hint(body: str) -> Optional[str]:
    """
    Извлечь контактную информацию из подписи письма.
    
    Ищет последнюю непустую строку после разделителей подписи
    (С уважением, --, Best regards и т.п.).
    """
    if not body:
        return None
    
    # Разделители подписи
    signature_markers = (
        'с уважением',
        'best regards',
        'regards',
        'sincerely',
        '--',
        '—',
        'с благодарностью',
        'искренне ваш',
    )
    
    lines = body.split('\n')
    signature_start = -1
    
    # Найти начало подписи
    for i, line in enumerate(lines):
        line_norm = _normalize_text(line.strip())
        for marker in signature_markers:
            if marker in line_norm:
                signature_start = i
                break
        if signature_start >= 0:
            break
    
    # Если подпись не найдена, брать последние 5 строк
    if signature_start < 0:
        signature_start = max(0, len(lines) - 5)
    
    # Взять строки после маркера подписи
    signature_lines = lines[signature_start + 1:]

    # Идём СВЕРХУ ВНИЗ: сразу после «С уважением» обычно имя человека, ниже —
    # должность и компания. Строки-компании (ООО/АО/ИП…) пропускаем.
    for line in signature_lines:
        line = line.strip()

        if not line:
            continue

        # Фильтры: длина, отсутствие URL/email
        if len(line) > 80:
            continue

        line_lower = line.lower()
        if 'http' in line_lower or '@' in line_lower or 'www.' in line_lower:
            continue

        # Пропустить строки, которые выглядят как телефон/факс
        if re.search(r'\d{3,}', line):
            continue

        # Пропустить юрлицо — нам нужен человек
        if re.match(r'^["«]?\s*(ооо|зао|оао|пао|ао|ип|нко)\b', line_lower):
            continue
        
        return line
    
    return None


def _check_auto_reply_headers(headers: Optional[dict]) -> bool:
    """Проверить заголовки на признаки автоответа."""
    if not headers:
        return False
    
    # Нормализуем ключи заголовков
    headers_norm = {k.lower(): v for k, v in headers.items()}
    
    # Auto-Submitted: не 'no'
    auto_submitted = headers_norm.get('auto-submitted', '').lower()
    if auto_submitted and auto_submitted != 'no':
        return True
    
    # Precedence: auto_reply
    precedence = headers_norm.get('precedence', '').lower()
    if 'auto' in precedence:
        return True
    
    # Другие заголовки автоответа
    for header in _AUTO_REPLY_HEADERS[1:]:  # пропускаем auto-submitted, проверили выше
        if header in headers_norm:
            return True
    
    return False


def _match_markers(text: str, markers: tuple[str, ...]) -> tuple[str, ...]:
    """
    Проверить наличие маркеров в тексте.
    
    Возвращает кортеж найденных маркеров.
    """
    text_norm = _normalize_text(text)
    matched = []
    
    for marker in markers:
        if marker in text_norm:
            matched.append(marker)
    
    return tuple(matched)


def classify_reply(
    subject: str,
    body: str,
    headers: Optional[dict] = None
) -> ReplySignal:
    """
    Классифицировать ответ на основе правил.
    
    Порядок проверок (первое совпадение побеждает):
    1. auto_reply — заголовки + текстовые маркеры
    2. unsub_request — просьба отписаться
    3. not_interested — отказ
    4. hot — явная заинтересованность, запрос КП/счёта, наличие телефона
    5. interested — запрос информации, вопросы
    6. neutral — всё остальное
    
    Аргументы:
        subject: тема письма
        body: тело письма
        headers: заголовки письма (опционально)
    
    Возвращает:
        ReplySignal с результатами классификации
    """
    full_text = f"{subject}\n{body}"
    phone = extract_phone(full_text)
    contact_hint = _extract_contact_hint(body)
    
    # 1. Проверка auto_reply
    if _check_auto_reply_headers(headers):
        return ReplySignal(
            kind='auto_reply',
            confidence=0.9,
            phone=phone,
            contact_hint=contact_hint,
            matched=('header_auto_reply',)
        )
    
    # Отрицания глушат авто-маркеры: «мы НЕ в отпуске, интересует цена» — живой
    # ответ, а не OOO. Вырезаем отрицаемые обороты из текста перед сканом.
    auto_scan_text = re.sub(
        r"не\s+(?:в\s+отпуске?|вне\s+офиса|недоступ\w*)", " ", full_text)
    auto_matched = _match_markers(auto_scan_text, _AUTO_REPLY_MARKERS)
    if auto_matched:
        return ReplySignal(
            kind='auto_reply',
            confidence=0.9,
            phone=phone,
            contact_hint=contact_hint,
            matched=auto_matched
        )
    
    # 2. Проверка unsub_request
    unsub_matched = _match_markers(full_text, _UNSUB_MARKERS)
    if unsub_matched:
        return ReplySignal(
            kind='unsub_request',
            confidence=0.9,
            phone=phone,
            contact_hint=contact_hint,
            matched=unsub_matched
        )
    
    # 3. Проверка not_interested
    not_interested_matched = _match_markers(full_text, _NOT_INTERESTED_MARKERS)
    if not_interested_matched:
        return ReplySignal(
            kind='not_interested',
            confidence=0.9,
            phone=phone,
            contact_hint=contact_hint,
            matched=not_interested_matched
        )
    
    # 4. Проверка hot
    hot_matched = _match_markers(full_text, _HOT_MARKERS)
    
    # Телефон в теле — сильный сигнал hot
    if phone and hot_matched:
        matched = hot_matched + ('phone_found',)
        return ReplySignal(
            kind='hot',
            confidence=0.9,
            phone=phone,
            contact_hint=contact_hint,
            matched=matched
        )
    
    if hot_matched:
        return ReplySignal(
            kind='hot',
            confidence=0.9,
            phone=phone,
            contact_hint=contact_hint,
            matched=hot_matched
        )
    
    if phone:
        return ReplySignal(
            kind='hot',
            confidence=0.9,
            phone=phone,
            contact_hint=contact_hint,
            matched=('phone_found',)
        )
    
    # 5. Проверка interested
    interested_matched = _match_markers(full_text, _INTERESTED_MARKERS)
    
    # Вопросительный знак в короткой реплике (до 200 символов)
    has_question = '?' in body and len(body.strip()) < 200
    
    if interested_matched or has_question:
        matched = interested_matched
        if has_question and not matched:
            matched = ('short_question',)
        elif has_question:
            matched = matched + ('short_question',)
        
        return ReplySignal(
            kind='interested',
            confidence=0.6,
            phone=phone,
            contact_hint=contact_hint,
            matched=matched
        )
    
    # 6. Neutral — всё остальное
    return ReplySignal(
        kind='neutral',
        confidence=0.3,
        phone=phone,
        contact_hint=contact_hint,
        matched=()
    )


def classify_reply_ai(
    subject: str,
    body: str,
    headers: Optional[dict] = None,
    ai: Optional[AiClassifier] = None
) -> ReplySignal:
    """
    Классифицировать ответ с опциональной AI-поддержкой.
    
    Алгоритм:
    1. Применить правила классификации
    2. Если результат neutral/interested и AI доступен — переклассифицировать через AI
    3. При ошибках AI вернуть результат правил
    
    Аргументы:
        subject: тема письма
        body: тело письма
        headers: заголовки письма (опционально)
        ai: опциональный AI-классификатор
    
    Возвращает:
        ReplySignal с результатами классификации
    """
    # Сначала применяем правила
    rule_result = classify_reply(subject, body, headers)
    
    # Если AI не задан или результат уверенный — возвращаем результат правил
    if ai is None or rule_result.kind not in ('neutral', 'interested'):
        return rule_result
    
    # Пытаемся переклассифицировать через AI
    try:
        ai_result = ai.classify(subject, body)
        
        # Валидация результата AI
        if not isinstance(ai_result, dict):
            return rule_result
        
        ai_kind = ai_result.get('kind')
        ai_confidence = ai_result.get('confidence')
        ai_phone = ai_result.get('phone')
        
        # Проверяем валидность kind
        valid_kinds = {'hot', 'interested', 'neutral', 'auto_reply', 'not_interested', 'unsub_request'}
        if ai_kind not in valid_kinds:
            return rule_result
        
        # Проверяем confidence
        if not isinstance(ai_confidence, (int, float)) or not (0 <= ai_confidence <= 1):
            ai_confidence = 0.5
        
        # Используем телефон из правил, если AI не нашёл
        final_phone = ai_phone if ai_phone else rule_result.phone
        
        # Объединяем сигналы
        return ReplySignal(
            kind=ai_kind,
            confidence=ai_confidence,
            phone=final_phone,
            contact_hint=rule_result.contact_hint,
            matched=rule_result.matched + ('ai_classified',)
        )
    
    except Exception:
        # При любых ошибках AI возвращаем результат правил
        return rule_result
