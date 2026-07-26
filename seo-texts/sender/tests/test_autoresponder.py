"""Тесты для sender/autoresponder.py: план действий, рендер писем и QA-гейт.

Проверяем реальное поведение движка (чистая логика, без I/O и сети).
Сигналы собираем через ReplySignal из sender.reply_classify; если сигнатура
в окружении иная - мягко откатываемся на SimpleNamespace, т.к. autoresponder
читает поля через getattr и ему всё равно, чем сигнал представлен.
"""

from types import SimpleNamespace

import pytest

from sender.autoresponder import (
    AUTO,
    PILOT,
    Action,
    plan,
    qa_reply,
    render_reply,
)

try:  # предпочитаем настоящий ReplySignal, как просит роадмап
    from sender.reply_classify import ReplySignal  # type: ignore
except Exception:  # pragma: no cover - изолированный прогон без модуля
    ReplySignal = None  # type: ignore


# --------------------------------------------------------------------------- #
# Хелпер сборки сигнала
# --------------------------------------------------------------------------- #

def _signal(**kwargs):
    """Собрать ReplySignal с разумными дефолтами по всем полям сигнала.

    Дефолты покрывают поля, которые читает autoresponder (kind/phone/
    contact_hint/matched/redirect_hint/deferred_hint). Если реальный
    ReplySignal требует другой набор - падать на SimpleNamespace, чтобы
    тесты проверяли ПОВЕДЕНИЕ плана, а не форму конструктора.
    """
    fields = {
        'kind': None,
        'confidence': 1.0,
        'phone': None,
        'contact_hint': None,
        'matched': (),
        'redirect_hint': None,
        'deferred_hint': None,
    }
    fields.update(kwargs)
    if ReplySignal is not None:
        try:
            return ReplySignal(**fields)  # type: ignore[misc]
        except Exception:
            pass
    return SimpleNamespace(**fields)


def _kinds(actions):
    """Список kind-ов действий по порядку - удобно сверять состав плана."""
    return [a.kind for a in actions]


def _by_kind(actions, kind):
    """Первое действие нужного вида (для проверки его payload)."""
    for a in actions:
        if a.kind == kind:
            return a
    raise AssertionError(f'нет действия {kind!r} в плане {_kinds(actions)}')


# Все reply-классы, у которых есть собственное тело письма в _BODIES.
RENDER_KINDS = [
    'hot',
    'interested',
    'neutral',
    'deferred',
    'redirect',
    'wrong_contact',
    'objection_tech',
    'objection_status_quo',
    'competitor_in_place',
    'not_interested',
]


# --------------------------------------------------------------------------- #
# 1. plan() по каждому из 12 kind
# --------------------------------------------------------------------------- #

def test_plan_hot_auto_full_set():
    # Уточнение владельца (HOW-IT-WORKS §2.3): hot = ГОТОВЫЙ лид сразу в Bitrix
    # (ready, высокая готовность) + алерт; ответ робота — короткий ack.
    sig = _signal(kind='hot', phone='+79990001122', contact_hint='Иван')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['bitrix_push', 'notify', 'reply_auto']

    reply = _by_kind(actions, 'reply_auto')
    assert reply.payload['kind'] == 'hot'
    assert reply.payload['kind_hint'] == 'hot'
    assert reply.payload['ack_only'] is True
    assert reply.payload['phone'] == '+79990001122'
    assert reply.payload['contact_hint'] == 'Иван'

    bitrix = _by_kind(actions, 'bitrix_push')
    assert bitrix.payload['lead_status'] == 'ready'
    assert bitrix.payload['readiness'] == 'high'
    assert bitrix.payload['phone'] == '+79990001122'

    notify = _by_kind(actions, 'notify')
    assert notify.payload['reason'] == 'hot_lead'


def test_plan_deferred_snooze_90():
    # Отложенный интерес: черновик + снуз на 3 месяца (не закрытие сделки).
    sig = _signal(kind='deferred', deferred_hint='после Нового года')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['reply_draft', 'snooze']

    snooze = _by_kind(actions, 'snooze')
    assert snooze.payload['days'] == 90
    assert snooze.payload['reason'] == 'deferred'
    assert snooze.payload['deferred_hint'] == 'после Нового года'


def test_plan_redirect_forward_uses_hint():
    # Наводка на верный адрес: пересылка (to=redirect_hint) + благодарность.
    sig = _signal(kind='redirect', redirect_hint='snab@example.ru')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['forward', 'reply_draft']

    forward = _by_kind(actions, 'forward')
    assert forward.payload['to'] == 'snab@example.ru'
    assert forward.payload['kind'] == 'redirect'


def test_plan_wrong_contact_flag_then_draft():
    sig = _signal(kind='wrong_contact')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['flag_contact', 'reply_draft']

    flag = _by_kind(actions, 'flag_contact')
    assert flag.payload['reason'] == 'wrong_contact'


def test_plan_objection_tech_logs_matched():
    # Техвозражение логируем как продуктовый фидбек, matched -> кортеж.
    sig = _signal(kind='objection_tech', matched=['габариты', 'шум'])
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['log_objection', 'reply_draft']

    log = _by_kind(actions, 'log_objection')
    assert log.payload['objection'] == 'tech'
    assert log.payload['matched'] == ('габариты', 'шум')


def test_plan_objection_status_quo_only_draft():
    sig = _signal(kind='objection_status_quo')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['reply_draft']


def test_plan_competitor_in_place_low_priority():
    # Стоит конкурент: без давления, помечаем low_priority.
    sig = _signal(kind='competitor_in_place')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['reply_draft']

    draft = _by_kind(actions, 'reply_draft')
    assert draft.payload['low_priority'] is True


def test_plan_interested_only_draft():
    sig = _signal(kind='interested')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['reply_draft']


def test_plan_neutral_only_draft():
    sig = _signal(kind='neutral')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['reply_draft']


def test_plan_not_interested_closing():
    # Отказ: черновик с пометкой closing (мягко закрываем).
    sig = _signal(kind='not_interested')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['reply_draft']

    draft = _by_kind(actions, 'reply_draft')
    assert draft.payload['closing'] is True


def test_plan_auto_reply_empty():
    # Автоответ секретаря/сервера: реагировать нечем.
    sig = _signal(kind='auto_reply')
    assert plan(sig, mode=AUTO) == []


def test_plan_unsub_request_suppress_only():
    # Просьба отписать: только подавление, без письма.
    sig = _signal(kind='unsub_request')
    actions = plan(sig, mode=AUTO)
    assert _kinds(actions) == ['suppress']

    supp = _by_kind(actions, 'suppress')
    assert supp.payload['reason'] == 'unsub_request'


def test_plan_unknown_kind_empty():
    # Служебные/неизвестные классы: без действий, решает человек выше.
    sig = _signal(kind='__нет_такого__')
    assert plan(sig, mode=AUTO) == []


# --------------------------------------------------------------------------- #
# 2. Пилотное понижение авто-ответов
# --------------------------------------------------------------------------- #

def test_plan_hot_pilot_downgrades_reply_auto():
    # На пилоте reply_auto -> reply_draft, payload жив, метка downgraded_from.
    sig = _signal(kind='hot', phone='+70000000000')
    actions = plan(sig, mode=PILOT)
    assert _kinds(actions) == ['bitrix_push', 'notify', 'reply_draft']

    draft = _by_kind(actions, 'reply_draft')
    assert draft.payload['downgraded_from'] == 'reply_auto'
    # Контекст сигнала не теряется при понижении.
    assert draft.payload['phone'] == '+70000000000'
    assert draft.payload['kind_hint'] == 'hot'


def test_plan_hot_pilot_is_default_mode():
    # Дефолтный режим = pilot, поэтому без mode тоже понижаем.
    sig = _signal(kind='hot')
    actions = plan(sig)
    assert 'reply_auto' not in _kinds(actions)
    assert _by_kind(actions, 'reply_draft').payload['downgraded_from'] == 'reply_auto'


def test_plan_hot_auto_keeps_reply_auto():
    sig = _signal(kind='hot')
    actions = plan(sig, mode=AUTO)
    assert 'reply_auto' in _kinds(actions)
    # В авто-режиме понижения нет, метки downgraded_from тоже нет.
    assert 'downgraded_from' not in _by_kind(actions, 'reply_auto').payload


# --------------------------------------------------------------------------- #
# 3. render_reply на пустом ctx для каждого reply-kind
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize('kind', RENDER_KINDS)
def test_render_reply_empty_ctx_is_valid(kind):
    # Пустой ctx не должен ронять рендер и не оставлять висящих {...}.
    subject, body = render_reply(kind)  # ctx=None
    assert subject.strip(), 'тема не должна быть пустой'
    # #65: байлайн дописывает отправка единой подписью; в теле его НЕТ
    assert body.rstrip().endswith('С уважением,'), 'финал под подпись отправки'
    assert '—' not in subject and '—' not in body, 'длинное тире (—) запрещено'
    assert '–' not in subject and '–' not in body, 'длинное тире (–) запрещено'
    assert '{' not in body and '}' not in body, 'незаполненные плейсхолдеры в теле'
    # Дефолтная подпись менеджера, если ctx пуст.
    # #65: обезличенного «Менеджер направления» больше нет — имя подставит
    # подпись отправки из ящика/кампании
    assert 'Менеджер направления' not in body


# --------------------------------------------------------------------------- #
# 4. render_reply с ctx (manager + orig_subject)
# --------------------------------------------------------------------------- #

def test_render_reply_with_ctx_manager_and_subject():
    subject, body = render_reply(
        'hot', {'manager': 'Пётр Иванов', 'orig_subject': 'Вопрос'}
    )
    # Тема строится как Re: к исходной.
    assert subject.startswith('Re: ')
    assert 'Вопрос' in subject
    # #65: имени менеджера в теле больше нет — его подставит подпись отправки
    # (из ящика или из кампании); тело кончается «С уважением,»
    assert body.rstrip().endswith('С уважением,')


def test_render_reply_keeps_existing_re_prefix():
    # Уже есть Re: - не удваиваем префикс.
    subject, _ = render_reply('neutral', {'orig_subject': 'Re: Вопрос'})
    assert subject == 'Re: Вопрос'


def test_render_reply_redirect_mentions_new_contact():
    # Для redirect при known new_contact аккуратно упоминаем адресата.
    _, body = render_reply('redirect', {'new_contact': 'отдела снабжения'})
    assert 'отдела снабжения' in body


# --------------------------------------------------------------------------- #
# 5. qa_reply: механический гейт ловит проблемы
# --------------------------------------------------------------------------- #

def test_qa_reply_empty_subject_flagged():
    problems = qa_reply('   ', 'Текст с финалом.\n\nС уважением,')
    assert any('Пустая тема' in p for p in problems)


def test_qa_reply_long_dash_flagged():
    problems = qa_reply('Тема', 'Текст — с тире.\n\nС уважением,')
    assert any('Длинное тире' in p for p in problems)


def test_qa_reply_placeholder_flagged():
    problems = qa_reply('Тема', 'Привет {дыра}.\n\nС уважением,')
    assert any('Незаполненные плейсхолдеры' in p for p in problems)


def test_qa_reply_too_long_flagged():
    # Тело длиннее 1600 символов - больше одного экрана.
    body = 'a' * 1700 + '\n\nС уважением,'
    problems = qa_reply('Тема', body)
    assert any('длиннее 1600' in p for p in problems)


def test_qa_reply_missing_byline_flagged():
    # #65: гейт следит за финалом «С уважением,» (байлайн приклеит отправка) и
    # бракует байлайн В ТЕЛЕ — он бы задвоился с подписью отправки
    problems = qa_reply('Тема', 'Текст без финала.')
    assert any('С уважением' in p for p in problems)
    problems2 = qa_reply('Тема', 'Текст. ООО «Руспром».\n\nС уважением,')
    assert any('задвоится' in p for p in problems2)


def test_qa_reply_robot_word_flagged():
    problems = qa_reply('Тема', 'Пишет нейросеть.\n\nС уважением,')
    assert any('робот' in p.lower() for p in problems)


def test_qa_reply_spam_word_flagged():
    problems = qa_reply('Тема', '100% гарантия результата.\n\nС уважением,')
    assert any('100% гарантия' in p for p in problems)


def test_qa_reply_clean_hot_render_passes():
    # Чистый рендер боевого письма проходит гейт без замечаний.
    subject, body = render_reply('hot')
    assert qa_reply(subject, body) == []


# --------------------------------------------------------------------------- #
# 6. Регресс: qa_reply не флагает «скидку» и годы из письма клиента
# --------------------------------------------------------------------------- #

def test_qa_reply_allows_discount_and_years():
    # "скидка" - легитимная деловая тема; числа/годы проверяет слой выше.
    body = (
        'Здравствуйте!\n\n'
        'По вашему вопросу про скидку в 2024 году: посчитаем в 2025.\n\n'
        'С уважением,\n'
    )
    assert qa_reply('Про скидку', body) == []
