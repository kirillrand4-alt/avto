"""Тесты ревью-конвейера: sender/review_chain.py и линзы sender/review_lenses.py.

Только фейковые caller (callable(prompt) -> str), без сети и без провайдера.
Фейкового судью узнаём по формату итогового JSON в промпте, линзы — по названию
роли в их системном промпте.
"""

import json

import pytest

from sender.review_lenses import (
    parse_verdict,
    run_lenses,
    LensVerdict,
    LENSES,
    BLOCKING,
)
from sender.review_chain import (
    review_chain,
    allowed_auto,
    ChainResult,
)


# --- общие данные писем ---
# CLEAN_* должно проходить механический слой 0 (qa_reply). Канон #65: тело
# кончается «С уважением,» — полную подпись (имя, юр-атрибуция с ИНН) дописывает
# отправка, в теле её быть не должно, иначе задвоится.
INCOMING = 'Здравствуйте. Интересует поставка партии. Сергей.'
CLEAN_SUBJECT = 'Ответ по вашему запросу на поставку'
CLEAN_BODY = (
    'Здравствуйте, Сергей.\n\n'
    'Спасибо за обращение. '
    'По вашему запросу готовы подготовить коммерческое предложение.\n\n'
    'Подскажите, пожалуйста, какой объём партии вам нужен?\n\n'
    'С уважением,'
)
# Тело с длинным тире — заведомый провал слоя 0 (правило владельца).
DASH_BODY = CLEAN_BODY.replace('готовы подготовить', 'готовы — подготовить')


# --- фейковый шлюз ---

def _identify(prompt: str) -> str:
    """Определяет, чей это промпт: судьи или конкретной линзы.

    Судья уникален форматом итогового JSON, линзы — фразой роли в системном
    промпте. Ищем по подстроке, чтобы не зависеть от точной вёрстки промпта.
    """
    # Судью проверяем первым: его формат ответа ни у одной линзы не встречается.
    if 'SEND|FIX|ESCALATE' in prompt or '"decision"' in prompt:
        return 'judge'
    p = prompt.lower()
    if 'факт-чекер' in p:
        return 'fact_check'
    if 'юрист' in p:
        return 'legal'
    if 'эскалация-гейт' in p:
        return 'escalation_gate'
    if 'скептик классификации' in p:
        return 'class_skeptic'
    if 'продажник-квалификатор' in p:
        return 'sales_qualifier'
    if 'адвокат клиента' in p:
        return 'client_advocate'
    if 'тон-редактор' in p:
        return 'tone_editor'
    if 'спам-техник' in p:
        return 'spam_tech'
    return 'unknown'


def lens_json(verdict, problems=None, fixes=None) -> str:
    """Строка ответа линзы в том формате, что ждёт parse_verdict."""
    return json.dumps(
        {
            'verdict': verdict,
            'problems': list(problems or []),
            'fixes': list(fixes or []),
        },
        ensure_ascii=False,
    )


def judge_json(decision, reason='', fixes=None) -> str:
    """Строка ответа судьи в том формате, что ждёт _run_judge."""
    return json.dumps(
        {'decision': decision, 'reason': reason, 'fixes': list(fixes or [])},
        ensure_ascii=False,
    )


def make_caller(*, lenses=None, judge='SEND', judge_reason='', fail=None):
    """Фабрика фейкового caller.

    lenses: dict lens->вердикт (str) либо dict с ключами verdict/problems/fixes;
    по умолчанию любая линза отвечает PASS.
    fail: множество имён линз, на которых caller бросает исключение (эмуляция
    сбоя шлюза — проверяем консервативную обработку в run_lenses).
    """
    lenses = lenses or {}
    fail = set(fail or ())

    def caller(prompt: str) -> str:
        who = _identify(prompt)
        if who == 'judge':
            return judge_json(judge, judge_reason)
        if who in fail:
            raise RuntimeError('шлюз недоступен')
        spec = lenses.get(who, 'PASS')
        if isinstance(spec, dict):
            return lens_json(
                spec.get('verdict', 'PASS'),
                spec.get('problems'),
                spec.get('fixes'),
            )
        return lens_json(spec)

    return caller


class RegenSpy:
    """Счётчик вызовов regenerate. fn — необязательная логика перегенерации."""

    def __init__(self, fn=None):
        self.calls = 0
        self.fn = fn

    def __call__(self, subject, body, fixes):
        self.calls += 1
        if self.fn is not None:
            return self.fn(subject, body, fixes)
        return subject, body  # по умолчанию письмо не меняем


# === 1. parse_verdict ===

def test_parse_verdict_valid_json():
    raw = lens_json('CRITICAL', ['нет ИНН'], ['добавить ИНН'])
    v = parse_verdict('legal', raw)
    assert v.verdict == 'CRITICAL'
    assert 'нет ИНН' in v.problems
    assert 'добавить ИНН' in v.fixes


def test_parse_verdict_json_with_surrounding_junk():
    # Модель нередко льёт болтовню вокруг JSON — разбор должен вытащить объект.
    raw = 'Вот ответ: {"verdict": "WARN", "problems": ["сухой тон"], "fixes": []} конец'
    v = parse_verdict('tone_editor', raw)
    assert v.verdict == 'WARN'
    assert 'сухой тон' in v.problems


def test_parse_verdict_broken_json_warn():
    # Сбалансированные скобки, но невалидный JSON -> WARN, а не тихий PASS.
    raw = 'Ответ: {"verdict": "PASS", "problems": [битый]}'
    v = parse_verdict('fact_check', raw)
    assert v.verdict == 'WARN'
    assert 'разобрать' in v.problems[0]


def test_parse_verdict_unknown_verdict_downgraded_to_warn():
    # Вердикт вне множества PASS/WARN/CRITICAL нормализуем в WARN.
    raw = lens_json('ok')
    v = parse_verdict('spam_tech', raw)
    assert v.verdict == 'WARN'


# === 2. run_lenses с фейковым caller ===

def test_run_lenses_calls_all_eight():
    caller = make_caller()
    verdicts = run_lenses(
        incoming=INCOMING,
        reply_subject=CLEAN_SUBJECT,
        reply_body=CLEAN_BODY,
        caller=caller,
    )
    # Прогнаны ровно все линзы из спеки.
    assert set(verdicts) == set(LENSES)


def test_run_lenses_advisory_failure_is_warn():
    # Сбой шлюза на совещательной линзе не блокирует, но сигналит -> WARN.
    caller = make_caller(fail={'tone_editor'})
    verdicts = run_lenses(
        incoming=INCOMING,
        reply_subject=CLEAN_SUBJECT,
        reply_body=CLEAN_BODY,
        caller=caller,
    )
    assert 'tone_editor' not in BLOCKING
    assert verdicts['tone_editor'].verdict == 'WARN'


def test_run_lenses_blocking_failure_is_critical():
    # Сбой на блокирующей линзе -> CRITICAL: сомнение значит не слать.
    caller = make_caller(fail={'fact_check'})
    verdicts = run_lenses(
        incoming=INCOMING,
        reply_subject=CLEAN_SUBJECT,
        reply_body=CLEAN_BODY,
        caller=caller,
    )
    assert 'fact_check' in BLOCKING
    assert verdicts['fact_check'].verdict == 'CRITICAL'


# === 3. review_chain: чистое письмо + судья SEND ===

def test_chain_all_pass_judge_send():
    caller = make_caller(judge='SEND')  # все линзы PASS
    res = review_chain(
        CLEAN_SUBJECT,
        CLEAN_BODY,
        incoming=INCOMING,
        caller=caller,
    )
    assert res.decision == 'SEND'
    assert res.iterations == 0
    assert allowed_auto(res) is True


# === 4. факт-чекер CRITICAL + наивный SEND судьи -> страховка ===

def test_chain_blocking_critical_vetoes_send():
    caller = make_caller(lenses={'fact_check': 'CRITICAL'}, judge='SEND')
    res = review_chain(
        CLEAN_SUBJECT,
        CLEAN_BODY,
        incoming=INCOMING,
        caller=caller,
        regenerate=None,
    )
    # Судья наивно сказал SEND, но вето блокирующей линзы не даёт отправить.
    assert res.decision != 'SEND'
    assert allowed_auto(res) is False


# === 5. эскалация-гейт CRITICAL -> ESCALATE сразу, без перегенераций ===

def test_chain_escalation_gate_short_circuits():
    caller = make_caller(
        lenses={
            'escalation_gate': {
                'verdict': 'CRITICAL',
                'problems': ['escalate: рекламация'],
            }
        },
        judge='SEND',
    )
    spy = RegenSpy()
    res = review_chain(
        CLEAN_SUBJECT,
        CLEAN_BODY,
        incoming=INCOMING,
        caller=caller,
        regenerate=spy,
    )
    assert res.decision == 'ESCALATE'
    assert spy.calls == 0  # эскалация-гейт срабатывает до петли перегенерации
    assert res.escalate_reason


# === 6. FIX-петля: CRITICAL до регена, PASS после (маркер в body) ===

def test_chain_fix_loop_recovers_after_regenerate():
    marker = 'Уточнение добавлено.'

    def caller(prompt: str) -> str:
        who = _identify(prompt)
        if who == 'judge':
            return judge_json('SEND')
        if who == 'fact_check':
            # До регена факт-чекер видит проблему, после — маркер в теле -> PASS.
            if marker in prompt:
                return lens_json('PASS')
            return lens_json('CRITICAL', ['выдуманная цифра'], ['убрать цифру'])
        return lens_json('PASS')

    def regenerate(subject, body, fixes):
        # маркер — В ТЕЛО, а не после финала: «С уважением,» должен остаться
        # последней строкой (канон #65), иначе слой 0 честно бракует
        return subject, body.replace('С уважением,', marker + '\nС уважением,')

    res = review_chain(
        CLEAN_SUBJECT,
        CLEAN_BODY,
        incoming=INCOMING,
        caller=caller,
        regenerate=regenerate,
        max_iterations=2,
    )
    assert res.decision == 'SEND'
    assert res.iterations == 1
    assert marker in res.body


# === 7. Лимит перегенераций ===

def test_chain_regeneration_limit_escalates():
    def caller(prompt: str) -> str:
        who = _identify(prompt)
        if who == 'judge':
            return judge_json('SEND')
        if who == 'fact_check':
            return lens_json('CRITICAL', ['всегда плохо'])  # ремонту не поддаётся
        return lens_json('PASS')

    spy = RegenSpy()  # тело не меняем — линза так и остаётся CRITICAL
    res = review_chain(
        CLEAN_SUBJECT,
        CLEAN_BODY,
        incoming=INCOMING,
        caller=caller,
        regenerate=spy,
        max_iterations=2,
    )
    assert res.decision == 'ESCALATE'
    assert 'лимит' in res.escalate_reason
    assert res.iterations == 2
    assert spy.calls == 2


# === 8. regenerate=None при CRITICAL -> FIX (черновик), без исключений ===

def test_chain_no_regenerate_returns_fix():
    caller = make_caller(lenses={'fact_check': 'CRITICAL'}, judge='SEND')
    res = review_chain(
        CLEAN_SUBJECT,
        CLEAN_BODY,
        incoming=INCOMING,
        caller=caller,
        regenerate=None,
    )
    assert res.decision == 'FIX'


# === 9. qa-гейт (слой 0): длинное тире чинится до линз ===

def test_chain_qa_gate_fixes_dash_before_lenses():
    def fix_dash(subject, body, fixes):
        # Меняем длинное тире на дефис — механический слой 0 требует этого.
        return subject, body.replace('—', '-')

    caller = make_caller(judge='SEND')
    res = review_chain(
        CLEAN_SUBJECT,
        DASH_BODY,
        incoming=INCOMING,
        caller=caller,
        regenerate=fix_dash,
        max_iterations=2,
    )
    # qa-петля отработала до линз: в итоговом письме длинного тире нет.
    assert '—' not in res.body


# === 10. allowed_auto: SEND, но CRITICAL у совещательной линзы -> False ===

def test_allowed_auto_send_with_advisory_critical_is_false():
    # Совещательная линза не даёт вето (SEND возможен), но авто-отправка
    # недопустима при любом CRITICAL.
    verdicts = {
        'client_advocate': LensVerdict(
            lens='client_advocate',
            verdict='CRITICAL',
            problems=('риск жалобы',),
        ),
        'tone_editor': LensVerdict(lens='tone_editor', verdict='PASS'),
    }
    res = ChainResult(
        decision='SEND',
        subject=CLEAN_SUBJECT,
        body=CLEAN_BODY,
        verdicts=verdicts,
        qa_problems=(),
        iterations=0,
    )
    assert 'client_advocate' not in BLOCKING
    assert allowed_auto(res) is False
