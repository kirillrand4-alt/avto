"""
sender/autoresponder.py

План действий и рендер ответных писем автоответчика B2B-рассылки
(компрессоры/пищевое оборудование, кампания Meyer).

Чистая логика: без I/O, без сети, только stdlib. Модуль решает ДВЕ задачи:
  * plan()        - по ReplySignal собрать список Action для конвейера;
  * render_reply()- отрендерить (subject, body) по классу письма;
  * qa_reply()    - механический QA-гейт (слой 0 ревью-конвейера).

Тексты и лестница контакта заданы плейбуком владельца: тон инженера-практика,
без канцелярита, без длинных тире, всегда конкретный следующий шаг.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Тип ReplySignal нужен только для аннотаций; в рантайме без него обойдёмся,
# поэтому импорт мягкий (как в других модулях sender).
try:  # pragma: no cover - зависит от окружения
    from sender.reply_classify import ReplySignal  # type: ignore
except Exception:  # noqa: BLE001 - типов может не быть при изолированном тесте
    ReplySignal = Any  # type: ignore


# --------------------------------------------------------------------------- #
# Константы режимов и политики авто-ответа
# --------------------------------------------------------------------------- #

PILOT = 'pilot'
AUTO = 'auto'

# Какие классы вообще могут уходить в авто-режиме. Начинаем консервативно:
# только явный "горячий" запрос. Расширим по мере накопления золотых пар.
AUTO_REPLY_ALLOWED_KINDS = frozenset({'hot'})


# --------------------------------------------------------------------------- #
# Модель действия
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Action:
    """Единица работы для конвейера. kind из фиксированного набора:
    reply_auto, reply_draft, bitrix_push, notify, snooze, forward,
    flag_contact, suppress, log_objection. payload несёт контекст действия."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Безопасная подстановка ctx в шаблоны
# --------------------------------------------------------------------------- #

class _SafeDict(dict):
    """dict для str.format_map: отсутствующий ключ -> пустая строка.
    Так неполный ctx не роняет рендер KeyError и не оставляет '{...}' в письме."""

    def __missing__(self, key: str) -> str:  # noqa: D401 - см. docstring класса
        return ''


# --------------------------------------------------------------------------- #
# plan(): маппинг класса письма в набор действий
# --------------------------------------------------------------------------- #

def _reply_payload(signal: Any, **extra: Any) -> dict[str, Any]:
    """Собрать payload для reply_* с signal-контекстом.
    Кладём kind всегда, phone/contact_hint - только если пришли."""
    p: dict[str, Any] = {'kind': getattr(signal, 'kind', None)}
    phone = getattr(signal, 'phone', None)
    if phone:
        p['phone'] = phone
    contact_hint = getattr(signal, 'contact_hint', None)
    if contact_hint:
        p['contact_hint'] = contact_hint
    p.update(extra)
    return p


def plan(signal: Any, ctx: Optional[dict] = None, mode: str = PILOT) -> list[Action]:
    """По ReplySignal вернуть план действий.

    В mode='pilot' любой reply_auto понижается до reply_draft: payload
    сохраняется, добавляется downgraded_from='reply_auto'. Так на пилоте ничего
    не улетает клиенту без ручной проверки, но разметка "это был бы авто" живёт.
    """
    kind = getattr(signal, 'kind', None)
    actions: list[Action] = []

    if kind == 'hot':
        # Уточнение владельца (2026-07-20, HOW-IT-WORKS §2.3): запрос прайса/КП =
        # уже квалифицированный интент. ГОТОВЫЙ лид сразу в Bitrix (status ready,
        # высокая готовность) + алерт продажнику; КП готовит и звонит ПРОДАЖНИК,
        # робот запрос сам не отрабатывает. Письмо робота — только короткое
        # подтверждение получения (опционально, проходит ревью-конвейер).
        actions.append(Action('bitrix_push', {
            'kind': kind,
            'phone': getattr(signal, 'phone', None),
            'contact_hint': getattr(signal, 'contact_hint', None),
            'lead_status': 'ready',
            'readiness': 'high',
        }))
        actions.append(Action('notify', {
            'kind': kind,
            'phone': getattr(signal, 'phone', None),
            'reason': 'hot_lead',
        }))
        actions.append(Action('reply_auto',
                              _reply_payload(signal, kind_hint='hot', ack_only=True)))

    elif kind == 'deferred':
        # Отложенный интерес: благодарим и снуз на 3 месяца (это НЕ закрытие).
        # Парсинг конкретных сроков не городим - фиксируем deferred_hint как есть.
        actions.append(Action('reply_draft', _reply_payload(signal)))
        actions.append(Action('snooze', {
            'days': 90,
            'reason': 'deferred',
            'deferred_hint': getattr(signal, 'deferred_hint', None),
        }))

    elif kind == 'redirect':
        # Наводка на верный адрес: пересылаем и благодарим.
        actions.append(Action('forward', {
            'to': getattr(signal, 'redirect_hint', None),
            'kind': kind,
        }))
        actions.append(Action('reply_draft', _reply_payload(signal)))

    elif kind == 'wrong_contact':
        # Контакт битый: помечаем и вежливо просим верного адресата.
        actions.append(Action('flag_contact', {
            'kind': kind,
            'reason': 'wrong_contact',
        }))
        actions.append(Action('reply_draft', _reply_payload(signal)))

    elif kind == 'objection_tech':
        # Техническое возражение: логируем как продуктовый фидбек, честно закрываем.
        actions.append(Action('log_objection', {
            'kind': kind,
            'objection': 'tech',
            'matched': tuple(getattr(signal, 'matched', ()) or ()),
        }))
        actions.append(Action('reply_draft', _reply_payload(signal)))

    elif kind == 'objection_status_quo':
        # "Нас всё устраивает": мягкий нуртуринг без дожима.
        actions.append(Action('reply_draft', _reply_payload(signal)))

    elif kind == 'competitor_in_place':
        # Стоит конкурент: учитываем, низкий приоритет, без давления.
        actions.append(Action('reply_draft', _reply_payload(signal, low_priority=True)))

    elif kind == 'interested':
        actions.append(Action('reply_draft', _reply_payload(signal)))

    elif kind == 'neutral':
        actions.append(Action('reply_draft', _reply_payload(signal)))

    elif kind == 'not_interested':
        actions.append(Action('reply_draft', _reply_payload(signal, closing=True)))

    elif kind == 'auto_reply':
        # Автоответ секретаря/сервера: реагировать нечем.
        actions = []

    elif kind == 'unsub_request':
        # Просьба отписать: только подавление, без письма.
        actions.append(Action('suppress', {'kind': kind, 'reason': 'unsub_request'}))

    else:
        # Служебные/неизвестные классы: без действий (решит человек выше).
        actions = []

    # Пилотное понижение авто-ответов до черновиков.
    if mode == PILOT and actions:
        downgraded: list[Action] = []
        for a in actions:
            if a.kind == 'reply_auto':
                p = dict(a.payload)
                p['downgraded_from'] = 'reply_auto'
                downgraded.append(Action('reply_draft', p))
            else:
                downgraded.append(a)
        actions = downgraded

    return actions


# --------------------------------------------------------------------------- #
# render_reply(): русские шаблоны на каждый reply_* класс
# --------------------------------------------------------------------------- #

# Подпись менеджера (не "ИИ"). Байлайн "ООО «Руспром»" проверяется QA-гейтом.
_SIGNATURE_TPL = '{manager}\nООО «Руспром»\nprokompressor.ru'

# Осмысленные темы по классу, если нет orig_subject. Без длинных тире.
_SUBJECTS: dict[str, str] = {
    'hot': 'Ваш запрос: готовим коммерческое предложение',
    'interested': 'По вашему запросу на оборудование',
    'neutral': 'Уточнение по вашему запросу',
    'deferred': 'Ваш проект: остаёмся на связи',
    'redirect': 'Спасибо за контакт',
    'wrong_contact': 'Уточнение адресата по вопросу снабжения',
    'objection_tech': 'Спасибо за ответ',
    'objection_status_quo': 'На будущее по контролю продукции',
    'competitor_in_place': 'Спасибо за ответ',
    'not_interested': 'Спасибо за ответ',
}

# Тела писем. Тон инженера-практика, 1 экран, без длинных тире и без цифр/цен.
_BODIES: dict[str, str] = {
    # hot: короткое подтверждение получения (владелец: запрос КП отрабатывает
    # ПРОДАЖНИК — готовит КП и звонит; робот не задаёт квал-вопросов).
    'hot': (
        'Здравствуйте!\n\n'
        'Спасибо за запрос, получили его. Менеджер подготовит коммерческое '
        'предложение и свяжется с вами сегодня в рабочее время.\n\n'
        '{signature}'
    ),
    'interested': (
        'Здравствуйте!\n\n'
        'Спасибо за интерес, готов помочь с подбором.\n'
        'Подскажите задачу: под какой процесс нужно оборудование и какой '
        'примерно объём производства?\n\n'
        'Удобнее всего обсудить голосом: оставьте номер, инженер быстро '
        'уточнит детали и предложит вариант.\n\n'
        '{signature}'
    ),
    'neutral': (
        'Здравствуйте!\n\n'
        'Спасибо за ответ. Уточните, пожалуйста, что именно интересно: '
        'подбор оборудования под задачу, цена по конкретной модели или каталог?\n'
        'Отталкиваясь от этого, подготовлю ответ по делу.\n\n'
        '{signature}'
    ),
    'deferred': (
        'Здравствуйте!\n\n'
        'Спасибо, что написали. Зафиксировали ваш проект и вернёмся ближе '
        'к сроку запуска.\n'
        'Подскажите ориентир по срокам: на какой период планируете закупку '
        'оборудования?\n\n'
        '{signature}'
    ),
    'redirect': (
        'Здравствуйте!\n\n'
        'Спасибо за наводку, напишем по указанному адресу.{new_contact_line}\n\n'
        '{signature}'
    ),
    'wrong_contact': (
        'Здравствуйте!\n\n'
        'Извините за беспокойство, похоже, мы обратились не по адресу.\n'
        'Подскажите, пожалуйста, кто у вас отвечает за снабжение или '
        'техническое оснащение производства, чтобы мы написали верному '
        'специалисту.\n\n'
        '{signature}'
    ),
    'objection_tech': (
        'Здравствуйте!\n\n'
        'Спасибо за прямой ответ, это ценно. Раз наше решение под вашу задачу '
        'сейчас не подходит, настаивать не будем.\n'
        'Если требования изменятся, будем рады вернуться к разговору.\n\n'
        '{signature}'
    ),
    'objection_status_quo': (
        'Здравствуйте!\n\n'
        'Понимаю, если текущее решение вас устраивает, навязывать не буду.\n'
        'Один момент на будущее: металлодетектор не видит неметаллические '
        'включения (стекло, камень, кость, пластик), рентген такие тоже '
        'контролирует.\n'
        'Если будет интерес сравнить, я на связи.\n\n'
        '{signature}'
    ),
    'competitor_in_place': (
        'Здравствуйте!\n\n'
        'Спасибо, понял. Раз вы уже работаете с поставщиками, навязываться '
        'не буду.\n'
        'Будем на связи, если что-то поменяется или захотите сравнить условия.\n\n'
        '{signature}'
    ),
    'not_interested': (
        'Здравствуйте!\n\n'
        'Спасибо за ответ, не будем вас беспокоить. Если ситуация изменится, '
        'будем рады помочь с подбором оборудования.\n\n'
        '{signature}'
    ),
}


def _subject_for(kind: str, d: dict[str, Any]) -> str:
    """Тема: Re: к исходной, если она есть; иначе осмысленная по классу."""
    orig = d.get('orig_subject')
    if orig:
        orig = str(orig).strip()
        if orig.lower().startswith('re:'):
            return orig
        return 'Re: ' + orig
    return _SUBJECTS.get(kind, 'Ваш запрос')


def render_reply(kind: str, ctx: Optional[dict] = None) -> tuple[str, str]:
    """Отрендерить (subject, body) для класса письма.

    Подстановка ctx безопасная: недостающие ключи -> пустая строка, так пустой
    ctx даёт валидное письмо без висящих '{...}'. manager по умолчанию
    'Менеджер направления', подпись собирается автоматически.
    """
    d: dict[str, Any] = dict(ctx or {})
    d.setdefault('manager', 'Менеджер направления')

    # Подпись собираем заранее и кладём в ctx как {signature}.
    d['signature'] = _SIGNATURE_TPL.format_map(_SafeDict(d))

    # Для redirect: если знаем новый контакт, аккуратно упоминаем его.
    new_contact = d.get('new_contact')
    d['new_contact_line'] = (
        ' Продублируем информацию для {0}.'.format(new_contact) if new_contact else ''
    )

    subject = _subject_for(kind, d)
    body_tpl = _BODIES.get(kind, _BODIES['neutral'])
    body = body_tpl.format_map(_SafeDict(d)).strip() + '\n'

    return subject, body


# --------------------------------------------------------------------------- #
# qa_reply(): механический QA-гейт (слой 0)
# --------------------------------------------------------------------------- #

# Плейсхолдер, не заполненный при рендере.
_PLACEHOLDER_RE = re.compile(r'\{[^}]*\}')

# Слова, выдающие робота. Word-boundary, регистронезависимо.
# \bбот\b намеренно узкое, чтобы не ловить "работа/работают".
_ROBOT_PATTERNS = [
    re.compile(r'\bИИ\b', re.IGNORECASE),
    re.compile(r'\bискусственн\w*\s+интеллект\w*', re.IGNORECASE),
    re.compile(r'\bнейросет\w*', re.IGNORECASE),
    re.compile(r'\bассистент\w*', re.IGNORECASE),
    re.compile(r'\bбот\b', re.IGNORECASE),
]

# Спам-стоп-слова (подстрока, нижний регистр). "скидк" сюда НЕ входит:
# скидка - нормальная деловая тема, ловить её - ложные срабатывания.
_SPAM_WORDS = [
    '100% гарантия',
    'супервыгодн',
    'только сегодня',
    'жми',
    '!!!',
]


def qa_reply(subject: str, body: str) -> list[str]:
    """Механический гейт: список проблем (строки на русском). Пустой = ок.

    Не флагаем "скидк" и не флагаем числа/годы: цифры могут прийти из письма
    клиента, а скидка - легитимная тема. Числа проверяет более высокий слой.
    """
    problems: list[str] = []
    subject = subject or ''
    body = body or ''

    # Пустая тема.
    if not subject.strip():
        problems.append('Пустая тема письма.')

    # Длинные тире где угодно.
    if any(dash in subject or dash in body for dash in ('—', '–')):
        problems.append('Длинное тире в теме или теле письма, заменить на дефис.')

    # Незаполненные плейсхолдеры.
    holders = _PLACEHOLDER_RE.findall(subject + '\n' + body)
    if holders:
        problems.append(
            'Незаполненные плейсхолдеры: ' + ', '.join(sorted(set(holders)))
        )

    # Длина: больше одного экрана.
    if len(body) > 1600:
        problems.append('Тело письма длиннее 1600 символов, больше одного экрана.')

    # Байлайн обязателен.
    if 'ООО «Руспром»' not in body:
        problems.append('Нет байлайна «ООО «Руспром»» в теле письма.')

    # Подпись не должна выдавать робота.
    for pat in _ROBOT_PATTERNS:
        if pat.search(body):
            problems.append('Текст выдаёт робота: слова про ИИ/нейросеть/бота.')
            break

    # Спам-стоп-слова.
    low = body.lower()
    for w in _SPAM_WORDS:
        if w in low:
            problems.append('Спам-стоп-слово в тексте: ' + w)

    return problems
