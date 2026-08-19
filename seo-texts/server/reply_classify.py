"""
Суб-классификация входящих ответов холодной B2B-рассылки (RU).

Различает категории ответов:
- hot: явная заинтересованность, запрос КП/счёта
- deferred: интерес есть, но отложен (стройка/бюджет/сезон)
- redirect: передача ЛПР, «пишите другому/на другой адрес»
- wrong_contact: адресат не тот человек / его нет
- objection_tech: техническое возражение к продукту
- objection_status_quo: «нас устраивает текущее решение»
- competitor_in_place: уже работают с конкурентом
- interested: запрос дополнительной информации
- neutral: нейтральный ответ без явных сигналов
- auto_reply: автоответ, отпуск, вне офиса
- not_interested: отказ, нет потребности
- unsub_request: просьба отписать

Извлекает контактные данные (телефон, имя из подписи), e-mail редиректа и
фразу-маркер отсрочки.
"""

import re
from dataclasses import dataclass
from typing import Optional, Protocol
from sender.errors import SenderError  # noqa: E402

# Пытаемся импортировать SenderError, иначе локальный fallback


@dataclass(frozen=True)
class ReplySignal:
    """
    Результат классификации ответа.

    Поля:
        kind: категория ответа (см. ALL_KINDS)
        confidence: уверенность в классификации (0..1)
        phone: извлечённый номер телефона в формате +7XXXXXXXXXX
        contact_hint: имя/должность из подписи письма
        matched: кортеж сработавших маркеров (для отладки)
        redirect_hint: e-mail из письма-редиректа (или сработавшая фраза)
        deferred_hint: сработавшая фраза отсрочки
    """
    kind: str
    confidence: float
    phone: Optional[str] = None
    contact_hint: Optional[str] = None
    matched: tuple[str, ...] = ()
    # Новые поля добавлены в конец с дефолтом None — старые вызовы/сериализация
    # (позиционные аргументы, распаковка) продолжают работать без изменений.
    redirect_hint: Optional[str] = None
    deferred_hint: Optional[str] = None


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


# Полный набор меток движка: 7 бизнес-классов таксономии + interested/neutral/
# not_interested (легаси-совместимость) + служебные auto_reply/unsub_request.
# Экспортируется для переиспользования (autoresponder валидирует по нему).
ALL_KINDS: tuple[str, ...] = (
    'hot',
    'deferred',
    'redirect',
    'wrong_contact',
    'objection_tech',
    'objection_status_quo',
    'competitor_in_place',
    'interested',
    'not_interested',
    'neutral',
    'auto_reply',
    'unsub_request',
)


# Словари маркеров для классификации (регистронезависимо, ё→е)
_AUTO_REPLY_MARKERS = (
    'автоответ',
    # Вежливые роботы секретариата: заголовка Auto-Submitted у них часто нет, а
    # смысл тот же — «письмо получено, ответим». Раньше такие ловились только
    # заголовком, и без него уезжали в neutral (замер 19.08).
    'письмо получено',
    'ваше письмо получено',
    'обязательно ответим',
    'ответим в кратчайшие сроки',
    'ваше обращение принято',
    'ваше сообщение получено',
    'спасибо за ваше обращение',
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
    # ПАДЕЖИ И РОДЫ (19.08). Маркеры стояли только в среднем роде, а люди пишут
    # «тема не актуальна», «вопрос не актуален», «данные работы не актуальны» —
    # и такой отказ проваливался в neutral или, хуже, в hot.
    'не актуальна',
    'не актуален',
    'не актуальны',
    'неактуальна',
    'неактуален',
    'не планируем',
    'не закупаем',
    'закупать не планируем',
    'не занимаемся',
    'не используется',
    'не используем',
    'используем свои',
    'свои компрессор',
    'своё оборудование',
    'свое оборудование',
    'данная тема для нас не',
    'тема не актуальна',
    'вопрос не актуален',
    'спасибо за предложение, не',
    'спасибо, не актуально',
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
    # ЖИВОЙ СПРОС СВОИМИ СЛОВАМИ (19.08, «Росткран»). Человек написал «Интерес
    # в 2 компрессорах» — прямее некуда, а разметка дала neutral: словарь знал
    # только канцелярит «пришлите КП» и «прайс». Формулировки взяты из реальных
    # ответов. Отказу они не мешают: отказ и интерес сравниваются по месту в
    # тексте, и «не интересует» стоит раньше своего «интерес».
    'интерес в',
    'интерес к ',
    'интересны',
    'интересует стоимость',
    'нужен компрессор',
    'нужны компрессор',
    'нужна компрессорная',
    'требуется компрессор',
    'подберите',
    'что можете предложить',
    'сколько стоит',
    'какие есть варианты',
    'рассмотрим предложение',
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

# deferred — интерес отложен во времени. НЕ включаем «вернусь» (это авто-маркер
# отпуска), только формы «вернемся» и явные сигналы стройки/переноса.
_DEFERRED_MARKERS = (
    'вернемся позже',
    'вернемся к этому вопросу',
    'вернемся к вопросу',
    'вернемся через',
    'строим производство',
    'строим завод',
    'строится производство',
    'запускаем производство',
    'пока не готовы',
    'отложим',
    'перенесем на',
    'в следующем году',
    'через полгода',
    'через год',
    'когда запустим',
    'планируем позже',
    'свяжемся позже',
    'обратимся позже',
)

# redirect — передача ЛПР или смена адресата. Маркеры узкие, чтобы не ловить
# hot-обороты (hot проверяется раньше в любом случае).
_REDIRECT_MARKERS = (
    'ухожу в декрет',
    'в декрете',
    'пишите на',
    'пишите по адресу',
    'пишите напрямую',
    'обращайтесь к',
    'обращайтесь по адресу',
    'перенаправляю',
    'переадресую',
    'этим вопросом занимается',
    'этим занимается',
    'теперь занимается',
    'адресуйте',
)

# wrong_contact — адресат не тот человек. Общее «у нас нет» ловим отдельным
# регексом с негативным lookahead (см. _WRONG_CONTACT_RE).
_WRONG_CONTACT_MARKERS = (
    'нет такого сотрудника',
    'нет такого человека',
    'такого сотрудника нет',
    'не работает у нас',
    'у нас не работает',
    'вы ошиблись адресатом',
    'ошиблись адресом',
    'неверный адресат',
    'не тот адресат',
    'уволился',
    'уволилась',
    'больше не работает',
)

# objection_tech — узкие технические возражения. НЕ включаем голое «не подходит»
# (это not_interested): нужен конкретный «не видит/не ловит/…».
_OBJECTION_TECH_MARKERS = (
    'не видит',
    'не ловит',
    'не распознает',
    'не обнаружива',
    'не детектирует',
    'не определяет',
    'технически не',
    'не справится с',
    'не справляется с',
)

# objection_status_quo — «текущее решение устраивает». Нормализация ё→е делает
# «всё устраивает» == «все устраивает».
_OBJECTION_STATUS_QUO_MARKERS = (
    'нас устраивает',
    'все устраивает',
    'нас все устраивает',
    'довольны текущим',
    'довольны существующим',
    'работает и устраивает',
    'менять не планируем',
    'пока устраивает',
)

# competitor_in_place — фразовые маркеры. Латинские бренды после «работаем с/
# работают/используем/стоят» ловим регексом. НЕ включаем «есть поставщик»
# (это старый not_interested-маркер).
_COMPETITOR_MARKERS = (
    'поставщик выбран',
    'подрядчик выбран',
    'есть подрядчик по',
    'уже есть подрядчик',
)

# Заголовки, указывающие на автоответ
_AUTO_REPLY_HEADERS = (
    'auto-submitted',
    'x-autoreply',
    'x-autorespond',
    'x-autoresponder',
)

# Латинский бренд конкурента после глагола эксплуатации. Триггер-глагол —
# регистронезависимо (?i:), а сам бренд обязан начинаться с заглавной латинской.
_COMPETITOR_BRAND_RE = re.compile(
    r"(?i:работа(?:ем|ют)|использу(?:ем|ют)|стоят|стоит|установлен\w*)"
    r"\s+(?:с\s+)?([A-Z][A-Za-z][\w\-]*)"
)

# Общее «у нас нет <человека>» — но НЕ «у нас нет потребности/бюджета/…»
# (это not_interested). Негативный lookahead отсекает деловой отказ.
_WRONG_CONTACT_RE = re.compile(
    r"у нас нет(?!\s+(?:потребност|необходимост|бюджет|задач|нужд|"
    r"денег|времени|планов|интереса))"
)

# E-mail для redirect_hint.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


# ЦИТАТА ИСХОДНОГО ПИСЬМА (19.08). Ответ почти всегда содержит наше же письмо
# ниже — с нашей подписью, телефоном и словами про подбор оборудования. Правила
# читали ВЕСЬ текст, поэтому телефон нашего же менеджера делал ответ «горячим».
# Режем по обычным разделителям цитирования; если после среза ничего не осталось
# (человек ответил только внутри цитаты), возвращаем исходный текст.
_ЦИТАТА = re.compile(
    r"^\s*>|^-{2,}\s*(?:Пересланное|Исходное|Original)|"
    r"^\s*(?:От|From)\s*:|^\s*(?:Отправлено|Sent)\s*:|"
    r"^\s*Отправлено из|^\s*(?:Пн|Вт|Ср|Чт|Пт|Сб|Вс|Понедельник|Вторник|Среда|"
    r"Четверг|Пятница|Суббота|Воскресенье)[,.]?\s+\d{1,2}\s+\w+\s+\d{4}|"
    r"^\s*\d{1,2}\.\d{2}\.\d{4}.{0,40}(?:пишет|wrote)|"
    r"^\s*On .{0,80}wrote:", re.I)


def bez_citaty(body: str) -> str:
    """Только то, что человек написал САМ: без процитированного нашего письма."""
    свои = []
    for строка in str(body or "").splitlines():
        if _ЦИТАТА.search(строка):
            break
        свои.append(строка)
    свой_текст = "\n".join(свои).strip()
    return свой_текст or str(body or "")


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


def _extract_email(text: str) -> Optional[str]:
    """Извлечь первый e-mail из текста (для redirect_hint) или None."""
    if not text:
        return None
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else None


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


def _detect_redirect(full_text: str, norm_text: str) -> tuple[tuple[str, ...], Optional[str]]:
    """Найти маркеры редиректа. hint = e-mail из текста или первая фраза."""
    matched = _match_markers(norm_text, _REDIRECT_MARKERS)
    if not matched:
        return (), None
    email = _extract_email(full_text)
    hint = email if email else matched[0]
    return matched, hint


def _detect_deferred(norm_text: str) -> tuple[tuple[str, ...], Optional[str]]:
    """Найти маркеры отсрочки. hint = первая сработавшая фраза."""
    matched = _match_markers(norm_text, _DEFERRED_MARKERS)
    if not matched:
        return (), None
    return matched, matched[0]


def _detect_wrong_contact(norm_text: str) -> tuple[str, ...]:
    """Найти маркеры «не тот адресат» + общий регекс «у нас нет <человека>»."""
    matched = list(_match_markers(norm_text, _WRONG_CONTACT_MARKERS))
    if _WRONG_CONTACT_RE.search(norm_text):
        matched.append('у нас нет')
    return tuple(matched)


def _detect_competitor(full_text: str, norm_text: str) -> tuple[str, ...]:
    """Найти фразы «поставщик выбран» и латинские бренды после глагола."""
    matched = list(_match_markers(norm_text, _COMPETITOR_MARKERS))
    # Бренд ищем в ОРИГИНАЛЕ: нормализация ломает заглавную латинскую букву.
    for m in _COMPETITOR_BRAND_RE.finditer(full_text):
        matched.append(m.group(1))
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
    3. hot — явная заинтересованность, запрос КП/счёта, наличие телефона
    4. redirect — передача ЛПР / другой адрес
    5. deferred — интерес отложен
    6. wrong_contact — не тот адресат
    7. objection_tech — техническое возражение
    8. objection_status_quo — «нас устраивает текущее»
    9. competitor_in_place — уже работают с конкурентом
    10. interested — запрос информации, вопросы
    11. not_interested — отказ
    12. neutral — всё остальное

    ПОПРАВКА 19.08: отказ и hot решаются не порядком правил, а МЕСТОМ В ТЕКСТЕ —
    что человек написал раньше, то и считается его ответом. Голый телефон больше
    не делает письмо горячим: в деловой подписи он есть всегда. И читаем только
    то, что человек написал сам, без цитаты нашего же письма (bez_citaty).

    Аргументы:
        subject: тема письма
        body: тело письма
        headers: заголовки письма (опционально)

    Возвращает:
        ReplySignal с результатами классификации
    """
    свой = bez_citaty(body)
    full_text = f"{subject}\n{свой}"
    norm_full = _normalize_text(full_text)
    phone = extract_phone(full_text)
    contact_hint = _extract_contact_hint(свой)

    # 1. Проверка auto_reply (заголовки)
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

    # 3. Отказ против интереса. ПОРЯДОК ПЕРЕСМОТРЕН 19.08 по замеру владельца:
    # из 47 лидов 21 стоял «горячим», хотя люди писали «тема не актуальна».
    # Виноваты были два правила:
    #   * «телефон в теле = hot» — в русской деловой подписи телефон есть ВСЕГДА,
    #     поэтому любой вежливый отказ с подписью становился горячим;
    #   * hot проверялся раньше отказа, и одно слово «заказать» перебивало
    #     прямое «не планируем закупать».
    # Теперь: отказ и интерес сравниваются ПО МЕСТУ В ТЕКСТЕ — что человек сказал
    # раньше, то и есть его ответ. Телефон сам по себе больше ничего не решает:
    # он лишь усиливает hot, когда рядом есть слова о покупке.
    hot_matched = _match_markers(full_text, _HOT_MARKERS)
    refuse_matched = _match_markers(full_text, _NOT_INTERESTED_MARKERS)
    нижний = full_text.lower().replace('ё', 'е')

    def _где(маркеры):
        места = [нижний.find(м.lower()) for м in маркеры]
        места = [x for x in места if x >= 0]
        return min(места) if места else 10 ** 9

    if hot_matched and refuse_matched:
        # оба класса в одном письме: «не актуально, но пришлите прайс на будущее»
        if _где(refuse_matched) <= _где(hot_matched):
            return ReplySignal(
                kind='not_interested', confidence=0.75, phone=phone,
                contact_hint=contact_hint,
                matched=refuse_matched + ('раньше_чем_hot',))
        return ReplySignal(
            kind='hot', confidence=0.75, phone=phone, contact_hint=contact_hint,
            matched=hot_matched + ('раньше_чем_отказ',))

    if refuse_matched:
        return ReplySignal(
            kind='not_interested', confidence=0.85, phone=phone,
            contact_hint=contact_hint, matched=refuse_matched)

    if hot_matched:
        matched = hot_matched + (('phone_found',) if phone else ())
        return ReplySignal(
            kind='hot', confidence=0.9, phone=phone, contact_hint=contact_hint,
            matched=matched)

    # 4. Проверка redirect
    redirect_matched, redirect_hint = _detect_redirect(full_text, norm_full)
    if redirect_matched:
        return ReplySignal(
            kind='redirect',
            confidence=0.8,
            phone=phone,
            contact_hint=contact_hint,
            matched=redirect_matched,
            redirect_hint=redirect_hint
        )

    # 5. Проверка deferred
    deferred_matched, deferred_hint = _detect_deferred(norm_full)
    if deferred_matched:
        return ReplySignal(
            kind='deferred',
            confidence=0.8,
            phone=phone,
            contact_hint=contact_hint,
            matched=deferred_matched,
            deferred_hint=deferred_hint
        )

    # 6. Проверка wrong_contact
    wrong_matched = _detect_wrong_contact(norm_full)
    if wrong_matched:
        return ReplySignal(
            kind='wrong_contact',
            confidence=0.8,
            phone=phone,
            contact_hint=contact_hint,
            matched=wrong_matched
        )

    # 7. Проверка objection_tech (узкие маркеры, раньше not_interested)
    obj_tech_matched = _match_markers(full_text, _OBJECTION_TECH_MARKERS)
    if obj_tech_matched:
        return ReplySignal(
            kind='objection_tech',
            confidence=0.8,
            phone=phone,
            contact_hint=contact_hint,
            matched=obj_tech_matched
        )

    # 8. Проверка objection_status_quo
    obj_sq_matched = _match_markers(full_text, _OBJECTION_STATUS_QUO_MARKERS)
    if obj_sq_matched:
        return ReplySignal(
            kind='objection_status_quo',
            confidence=0.8,
            phone=phone,
            contact_hint=contact_hint,
            matched=obj_sq_matched
        )

    # 9. Проверка competitor_in_place
    competitor_matched = _detect_competitor(full_text, norm_full)
    if competitor_matched:
        return ReplySignal(
            kind='competitor_in_place',
            confidence=0.8,
            phone=phone,
            contact_hint=contact_hint,
            matched=competitor_matched
        )

    # 10. Проверка interested
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

    # 11. Проверка not_interested (после interested — тексты отказа не содержат
    #     interested-маркеров и коротких вопросов)
    not_interested_matched = _match_markers(full_text, _NOT_INTERESTED_MARKERS)
    if not_interested_matched:
        return ReplySignal(
            kind='not_interested',
            confidence=0.9,
            phone=phone,
            contact_hint=contact_hint,
            matched=not_interested_matched
        )

    # 12. Neutral — всё остальное
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

        # Проверяем валидность kind (все 11 бизнес/легаси + служебные)
        valid_kinds = set(ALL_KINDS)
        if ai_kind not in valid_kinds:
            return rule_result

        # Проверяем confidence
        if not isinstance(ai_confidence, (int, float)) or not (0 <= ai_confidence <= 1):
            ai_confidence = 0.5

        # Используем телефон из правил, если AI не нашёл
        final_phone = ai_phone if ai_phone else rule_result.phone

        # Объединяем сигналы (hint-поля берём из правил — AI их не заполняет)
        return ReplySignal(
            kind=ai_kind,
            confidence=ai_confidence,
            phone=final_phone,
            contact_hint=rule_result.contact_hint,
            matched=rule_result.matched + ('ai_classified',),
            redirect_hint=rule_result.redirect_hint,
            deferred_hint=rule_result.deferred_hint
        )

    except Exception:
        # При любых ошибках AI возвращаем результат правил
        return rule_result
