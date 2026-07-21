"""Ревью-конвейер ответных писем автоответчика.

Решение владельца (2026-07-20): каждое сгенерированное письмо проходит ВСЕ
8 ревьюеров ПЕРЕД отправкой. Есть критика — письмо не уходит, идёт на
перегенерацию. Двухслойная страховка: слой 0 (механический qa_reply, без LLM)
плюс слой 1 (8 LLM-линз) и финальный судья-скептик поверх.

Точка встраивания: между render_reply() и Action reply_auto|reply_draft.
reply_auto разрешён ТОЛЬКО при decision=SEND и пустых CRITICAL (см. allowed_auto).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sender.autoresponder import qa_reply  # слой 0: list[str] проблем
from sender.review_lenses import (  # слой 1 (+общий JSON-парсер — P2 №5)
    BLOCKING, LENSES, LensVerdict, _find_json_object, run_lenses,
)


@dataclass(frozen=True)
class ChainResult:
    """Итог прогона конвейера по одному письму.

    verdicts — вердикты ПОСЛЕДНЕЙ итерации (то, что реально увидит оператор);
    iterations — число сделанных перегенераций (0 — ни одной).
    """

    decision: str  # SEND | FIX | ESCALATE
    subject: str
    body: str
    verdicts: dict[str, LensVerdict]
    qa_problems: tuple[str, ...]
    iterations: int
    escalate_reason: str = ''
    judge_raw: str = ''


def review_chain(
    subject: str,
    body: str,
    *,
    incoming: str,
    reply_kind: str = '',
    kb_slice: str = '',
    caller=None,
    regenerate=None,
    max_iterations: int = 2,
) -> ChainResult:
    """Оркестрация ревью: qa_reply -> 8 линз -> судья, с петлёй перегенерации.

    regenerate: callable(subject, body, fixes: list[str]) -> (subject, body).
    Лимит max_iterations считается СУММАРНО на все перегенерации (и qa, и fix),
    чтобы не крутить письмо вечно.
    """
    # Судья по умолчанию ходит тем же шлюзом, что и линзы. Импорт ленивый:
    # default_caller тянет провайдерский клиент, а он нужен не всегда (в тестах
    # caller передают явно).
    if caller is None:
        from sender.review_lenses import default_caller
        caller = default_caller

    iterations = 0  # уже сделанные перегенерации

    while True:
        # --- а) слой 0: механический гейт ---
        qa_problems = tuple(qa_reply(subject, body))
        if qa_problems:
            # Провал слоя 0. Если можем и есть бюджет — сразу перегенерируем,
            # линзы на заведомо кривое письмо не тратим.
            if regenerate is not None and iterations < max_iterations:
                subject, body = regenerate(subject, body, list(qa_problems))
                iterations += 1
                continue
            # Нет regenerate или лимит исчерпан: идём к линзам, но qa-проблемы
            # держим в копилке — человек увидит их в черновике.

        # --- б) слой 1: 8 линз параллельно ---
        verdicts = run_lenses(
            incoming=incoming,
            reply_subject=subject,
            reply_body=body,
            reply_kind=reply_kind,
            kb_slice=kb_slice,
            caller=caller,
        )

        # --- в) эскалация-гейт: CRITICAL значит сразу человеку, без перегенераций ---
        esc_name, esc_verdict = _find_escalation(verdicts)
        if esc_verdict is not None and esc_verdict.verdict == 'CRITICAL':
            reason = (
                '; '.join(esc_verdict.problems)
                if esc_verdict.problems
                else 'эскалация-гейт: вопрос вне зоны робота'
            )
            return ChainResult(
                decision='ESCALATE',
                subject=subject,
                body=body,
                verdicts=verdicts,
                qa_problems=qa_problems,
                iterations=iterations,
                escalate_reason=reason,
            )

        # --- г) судья-скептик ---
        judge_decision, judge_reason, judge_fixes, judge_raw = _run_judge(
            subject, body, verdicts, caller
        )
        decision = _resolve_decision(judge_decision, verdicts, qa_problems)

        if decision == 'SEND':
            return ChainResult(
                decision='SEND',
                subject=subject,
                body=body,
                verdicts=verdicts,
                qa_problems=qa_problems,
                iterations=iterations,
                judge_raw=judge_raw,
            )

        if decision == 'ESCALATE':
            return ChainResult(
                decision='ESCALATE',
                subject=subject,
                body=body,
                verdicts=verdicts,
                qa_problems=qa_problems,
                iterations=iterations,
                escalate_reason=judge_reason or 'судья: требуется человек',
                judge_raw=judge_raw,
            )

        # --- д) decision == FIX ---
        if regenerate is None:
            # Перегенерировать нечем: отдаём FIX как есть — черновик с
            # замечаниями, дальше решает человек.
            return ChainResult(
                decision='FIX',
                subject=subject,
                body=body,
                verdicts=verdicts,
                qa_problems=qa_problems,
                iterations=iterations,
                judge_raw=judge_raw,
            )

        if iterations < max_iterations:
            fixes = _collect_fixes(judge_fixes, verdicts)
            subject, body = regenerate(subject, body, fixes)
            iterations += 1
            continue  # повторяем шаги а)-г)

        # Лимит перегенераций исчерпан — не крутим вечно, отдаём человеку.
        return ChainResult(
            decision='ESCALATE',
            subject=subject,
            body=body,
            verdicts=verdicts,
            qa_problems=qa_problems,
            iterations=iterations,
            escalate_reason='лимит перегенераций исчерпан',
            judge_raw=judge_raw,
        )


def allowed_auto(result: ChainResult) -> bool:
    """Правило спеки: reply_auto только при SEND и пустых CRITICAL.

    Дополнительно требуем пустой слой 0 — если механический гейт что-то
    поймал, авто-отправка недопустима.
    """
    if result.decision != 'SEND':
        return False
    if result.qa_problems:
        return False
    return not any(v.verdict == 'CRITICAL' for v in result.verdicts.values())


def summarize(result: ChainResult) -> str:
    """Короткая русская сводка для лога и черновика оператору."""
    lines = [f'Решение: {result.decision} | перегенераций: {result.iterations}']
    if result.escalate_reason:
        lines.append(f'Причина: {result.escalate_reason}')
    if result.qa_problems:
        lines.append('QA (слой 0): ' + '; '.join(result.qa_problems))
    for name, v in result.verdicts.items():
        first = v.problems[0] if v.problems else ''
        if first:
            lines.append(f'{name}: {v.verdict} ({first})')
        else:
            lines.append(f'{name}: {v.verdict}')
    return '\n'.join(lines)


# --- вспомогательное (внутреннее) ---

def _find_escalation(verdicts: dict[str, LensVerdict]):
    """Находит вердикт эскалация-гейта среди линз по имени.

    Ключи линз в разных сборках могут быть латиницей или кириллицей, поэтому
    ищем по подстроке, а не по точному имени.
    """
    for name, v in verdicts.items():
        low = name.lower()
        if 'escal' in low or 'эскал' in low:
            return name, v
    return None, None


def _resolve_decision(
    judge_decision,
    verdicts: dict[str, LensVerdict],
    qa_problems: tuple[str, ...],
) -> str:
    """Финальное решение: ответ судьи + детерминированные страховки поверх.

    Судья может ошибаться или быть недоступен, поэтому доверяем ему только в
    рамках, которые не нарушают вето блокирующих линз.
    """
    blocking_critical = any(
        name in BLOCKING and v.verdict == 'CRITICAL'
        for name, v in verdicts.items()
    )
    any_critical = any(v.verdict == 'CRITICAL' for v in verdicts.values())
    fully_clean = (not qa_problems) and all(
        v.verdict == 'PASS' for v in verdicts.values()
    )

    if judge_decision in ('SEND', 'FIX', 'ESCALATE'):
        decision = judge_decision
    else:
        # Судья недоступен/нераспарсен — решаем консервативно сами.
        if any_critical or qa_problems:
            decision = 'FIX'
        elif fully_clean:
            decision = 'SEND'
        else:
            decision = 'FIX'  # есть WARN — сомнение значит не слать

    # Вето блокирующих: SEND при их CRITICAL невозможен.
    if decision == 'SEND' and blocking_critical:
        decision = 'FIX'

    return decision


def _run_judge(subject: str, body: str, verdicts: dict[str, LensVerdict], caller):
    """Отдельный вызов судьи. Возвращает (decision|None, reason, fixes, raw).

    Любой сбой шлюза/парсинга -> decision=None, чтобы наверху сработала
    консервативная страховка.
    """
    prompt = _judge_prompt(subject, body, verdicts)
    try:
        raw = caller(prompt)
    except Exception:
        return None, '', [], ''
    # caller может вернуть (text, model) — как default_caller линз
    if isinstance(raw, tuple):
        raw = str(raw[0]) if raw else ''
    if not isinstance(raw, str):
        raw = str(raw)

    chunk = _find_json_object(raw)
    if not chunk:
        return None, '', [], raw
    try:
        data = json.loads(chunk)
    except (ValueError, TypeError):
        return None, '', [], raw
    if not isinstance(data, dict):
        return None, '', [], raw

    decision = data.get('decision')
    if isinstance(decision, str):
        decision = decision.strip().upper()
    else:
        decision = None

    reason = data.get('reason') or ''
    fixes = data.get('fixes') or []
    if not isinstance(fixes, list):
        fixes = [fixes]

    return decision, str(reason), [str(f) for f in fixes], raw


def _judge_prompt(subject: str, body: str, verdicts: dict[str, LensVerdict]) -> str:
    """Промпт судьи: письмо + сводка 8 вердиктов, строгий JSON на выходе."""
    lines = []
    for name, v in verdicts.items():
        probs = '; '.join(v.problems) if v.problems else 'нет'
        lines.append(f'- {name}: {v.verdict} (проблемы: {probs})')
    summary = '\n'.join(lines)
    return (
        'Ты финальный судья-скептик ревью ответного письма автоответчика. '
        'По умолчанию недоверчив: сомнение значит не слать.\n\n'
        f'ТЕМА: {subject}\n\n'
        f'ТЕЛО:\n{body}\n\n'
        f'ВЕРДИКТЫ 8 ревьюеров:\n{summary}\n\n'
        'Верни СТРОГО один JSON без пояснений до или после: '
        '{"decision":"SEND|FIX|ESCALATE","reason":"...","fixes":["..."]}. '
        'SEND только если критики нет. '
        'FIX если есть CRITICAL или значимые WARN (в fixes перечисли правки). '
        'ESCALATE если вопрос вне зоны робота.'
    )


def _collect_fixes(judge_fixes, verdicts: dict[str, LensVerdict]) -> list[str]:
    """Собирает правки для перегенерации: судья + все линзы, без дублей."""
    fixes: list[str] = list(judge_fixes)
    for v in verdicts.values():
        fixes.extend(v.fixes or [])
    seen: set[str] = set()
    out: list[str] = []
    for f in fixes:
        s = str(f)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out
