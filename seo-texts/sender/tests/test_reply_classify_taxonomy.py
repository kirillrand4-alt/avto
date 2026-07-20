"""Тесты новых классов reply_classify — 11-классная таксономия Meyer.

Старые классы (interested/neutral/not_interested/auto_reply/unsub_request)
уже покрыты в test_reply_classify.py — здесь тестируем ТОЛЬКО новое
поведение: бизнес-классы hot/deferred/redirect/wrong_contact/objection_*/
competitor_in_place, новые поля ReplySignal и коллизии с легаси-маркерами.
"""

import pytest

from sender.reply_classify import (
    ALL_KINDS,
    classify_reply,
    classify_reply_ai,
)


# --- Фейковый AI-классификатор (без сети, без провайдера) -------------------
class _FakeAi:
    """Возвращает заранее заданный dict, игнорируя вход. Для проверки того,
    что движок принимает от AI новые классы таксономии."""

    def __init__(self, result: dict):
        self._result = result

    def classify(self, subject: str, body: str) -> dict:
        return self._result


# --- 1. Семь реальных писем Meyer -> ожидаемые классы -----------------------
def test_hot_price_request():
    sig = classify_reply('Re: КП', 'Пришлите прайс-лист, пожалуйста')
    assert sig.kind == 'hot'


def test_deferred_construction():
    # Стройка/перенос закупки — интерес есть, но отложен во времени.
    sig = classify_reply('Re: предложение', 'Строим производство, вернёмся позже')
    assert sig.kind == 'deferred'
    # deferred_hint должен нести сработавшую фразу для оператора.
    assert sig.deferred_hint


def test_redirect_extracts_email():
    body = (
        'Ухожу в декрет, по всем вопросам пишите на общую почту '
        'info@bastion.ru для Володина Д.В.'
    )
    sig = classify_reply('Re: вопрос', body)
    assert sig.kind == 'redirect'
    # redirect_hint для редиректа — это извлечённый e-mail, а не фраза.
    assert sig.redirect_hint == 'info@bastion.ru'


def test_wrong_contact_no_such_person():
    sig = classify_reply('Re: письмо', 'Марии Сергеевны у нас нет')
    assert sig.kind == 'wrong_contact'


def test_objection_tech():
    body = 'Ваш рентген не видит нитки, волосы и окурки, нам не подходит'
    sig = classify_reply('Re: рентген', body)
    # «не видит» — конкретное техническое возражение, не голое «не подходит».
    assert sig.kind == 'objection_tech'


def test_objection_status_quo():
    sig = classify_reply('Re: детектор', 'Металлодетектор нас устраивает')
    assert sig.kind == 'objection_status_quo'


def test_competitor_in_place_brands():
    # Латинские бренды после глагола эксплуатации ловятся регексом.
    sig = classify_reply('Re: оборудование', 'Работают Bizerba и Mettler Toledo')
    assert sig.kind == 'competitor_in_place'


# --- 2. Коллизии: регрессы, критично ----------------------------------------
def test_no_need_is_not_wrong_contact():
    # «у нас нет потребности» — деловой отказ, НЕ «нет такого человека».
    # Негативный lookahead в _WRONG_CONTACT_RE обязан отсечь этот случай.
    sig = classify_reply('Re: компрессоры', 'у нас нет потребности в компрессорах')
    assert sig.kind == 'not_interested'


def test_has_supplier_is_not_competitor():
    # «Есть поставщик» — старый not_interested-маркер, НЕ competitor_in_place
    # (competitor ловит только «поставщик выбран» и латинские бренды).
    sig = classify_reply(
        'Re: предложение',
        'Спасибо, но нас это не интересует. Есть поставщик.',
    )
    assert sig.kind == 'not_interested'


def test_vacation_return_is_auto_reply_not_deferred():
    # «вернусь» — маркер отпуска (auto_reply), а не «вернёмся» (deferred).
    # auto_reply проверяется раньше deferred.
    sig = classify_reply('Автоответ', 'Я в отпуске, вернусь 5 августа')
    assert sig.kind == 'auto_reply'


def test_unsub_request():
    sig = classify_reply('Re: рассылка', 'не пишите нам больше')
    assert sig.kind == 'unsub_request'


# --- 3. Порядок приоритетов: hot раньше deferred ----------------------------
def test_hot_wins_over_deferred():
    # Письмо содержит и hot-маркер (пришлите КП), и deferred (вернёмся позже).
    # hot проверяется раньше — побеждает первое совпадение.
    sig = classify_reply('Re: закупка', 'Пришлите КП, но вернёмся к закупке позже')
    assert sig.kind == 'hot'


# --- 4. Новые поля дефолтны для старых вызовов ------------------------------
def test_new_fields_default_none_on_neutral():
    # Нейтральный текст без маркеров: новые поля остаются None, старые
    # позиционные вызовы/распаковка ReplySignal не ломаются.
    sig = classify_reply('Re: x', 'Нейтральный текст письма без маркеров совсем')
    assert sig.redirect_hint is None
    assert sig.deferred_hint is None


# --- 5. AI-путь принимает новые классы --------------------------------------
def test_ai_returns_new_class():
    # На нейтральном тексте правила дают neutral -> движок обращается к AI,
    # который возвращает новый класс таксономии.
    fake = _FakeAi({'kind': 'deferred', 'confidence': 0.9})
    sig = classify_reply_ai(
        'Re: письмо',
        'Нейтральный текст письма без маркеров совсем',
        ai=fake,  # третий позиционный — headers, AI передаётся kwarg-ом
    )
    assert sig.kind == 'deferred'
    # Маркер источника: классификация пришла от AI, а не от правил.
    assert 'ai_classified' in sig.matched


# --- 6. ALL_KINDS: все 12 меток, старые 6 не потеряны -----------------------
def test_all_kinds_complete():
    expected = {
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
    }
    assert set(ALL_KINDS) == expected
    assert len(ALL_KINDS) == 12


def test_all_kinds_keeps_legacy_labels():
    # Старые 6 меток обязаны сохраниться для обратной совместимости.
    legacy = ('interested', 'not_interested', 'neutral', 'auto_reply',
              'unsub_request', 'hot')
    for label in legacy:
        assert label in ALL_KINDS
