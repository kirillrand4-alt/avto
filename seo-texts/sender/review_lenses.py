"""sender/review_lenses.py — 8 LLM-линз ревью ответных писем автоответчика.

Слой 1 конвейера ревью: каждое сгенерированное письмо прогоняется через все 8
линз ПЕРЕД отправкой (решение владельца 2026-07-20 — качество важнее скорости).
Одна линза = один короткий вызов с JSON-ответом; блокирующие линзы при CRITICAL
дают вето. Здесь только линзы и вспомогалки; судья/петля перегенерации — снаружи.

Движок держим на stdlib: httpx тянем лениво внутри провайдерского вызова, чтобы
тесты с фейковым caller не требовали сетевых зависимостей.
"""

import json
import re
import time
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor


@dataclass(frozen=True)
class LensVerdict:
    """Вердикт одной линзы. frozen — вердикты неизменяемы после разбора."""
    lens: str
    verdict: str  # PASS | WARN | CRITICAL
    problems: tuple[str, ...] = ()
    fixes: tuple[str, ...] = ()
    raw: str = ""
    model: str = ""


# Порядок строго по спеке: сначала 4 блокирующие, потом 4 совещательные.
LENSES: tuple[str, ...] = (
    'fact_check',
    'legal',
    'escalation_gate',
    'class_skeptic',
    'sales_qualifier',
    'client_advocate',
    'tone_editor',
    'spam_tech',
)

# CRITICAL этих четырёх = вето (письмо не уходит). Остальные могут дать CRITICAL
# тоже, но судья решает — здесь важна консервативность при СБОЕ блокирующих.
BLOCKING: frozenset = frozenset(LENSES[:4])

LENS_TITLES: dict[str, str] = {
    'fact_check': 'Факт-чекер против базы',
    'legal': 'Юрист ФЗ-38/152',
    'escalation_gate': 'Эскалация-гейт',
    'class_skeptic': 'Классификация-скептик',
    'sales_qualifier': 'Продажник-квалификатор',
    'client_advocate': 'Клиент-адвокат',
    'tone_editor': 'Тон-редактор',
    'spam_tech': 'Спам-техник',
}

# Единое требование к формату ответа — добавляется в конец каждого промпта.
# Экономит токены и заставляет модель отдавать разбираемый JSON.
_JSON_TAIL = (
    'Ответь СТРОГО одним JSON-объектом без другого текста, комментариев и '
    'markdown: {"verdict": "PASS|WARN|CRITICAL", "problems": [...], "fixes": [...]}. '
    'problems — что не так (пусто если всё ок), fixes — конкретные правки для '
    'перегенерации.'
)

# Вердикты, которые считаем валидными. Всё прочее нормализуем в WARN.
_VALID_VERDICTS = frozenset({'PASS', 'WARN', 'CRITICAL'})


def _lens_system(lens: str) -> str:
    """Короткий системный промпт линзы. Каждая линза — своя строка спеки.

    Держим компактно: у линзы одна работа, лишние абзацы только размывают фокус
    и жгут токены.
    """
    if lens == 'fact_check':
        return (
            'Ты факт-чекер ответного письма. Сверь КАЖДУЮ цифру, модель, '
            'модификацию, срок, гарантию и цену в письме со справкой из базы '
            '(answer-kb КЦ / факты брендов). Любой факт НЕ из базы, выдуманная '
            'модификация или несовпадение с базой -> verdict CRITICAL. Если фактов '
            'нет или все подтверждены базой -> PASS. Фактура — главный риск, будь строг.'
        )
    if lens == 'legal':
        return (
            'Ты юрист по ФЗ-38 (реклама) и ФЗ-152 (персданные). ВАЖНО про '
            'инфраструктуру: атрибуцию (ООО «Руспром» + ИНН) и ссылку отписки '
            'движок добавляет АВТОМАТИЧЕСКИ при отправке (personalize и '
            'заголовки List-Unsubscribe) — их отсутствие в черновике НЕ '
            'нарушение, не флагай это. Проверяй сам ТЕКСТ: нет незаконной '
            'публичной оферты (твёрдая цена+срок как обязательство); нет '
            'нарушения работы с персданными (лишние ПД третьих лиц, передача '
            'данных); текст не просит «ответьте СТОП» вместо штатной отписки и '
            'не противоречит атрибуции (чужое юрлицо, чужой бренд как свой). '
            'Реальное нарушение -> CRITICAL, иначе PASS.'
        )
    if lens == 'escalation_gate':
        return (
            'Ты эскалация-гейт. Реши НЕ «как написать», а «должен ли робот вообще '
            'отвечать сам». Триггеры на человека: горячий/незакрытый торг, '
            'рекламация, сумма > 1 млн ₽, госзакупки, лизинг, юридический вопрос, '
            'агрессия получателя. Любой триггер -> verdict CRITICAL, в problems '
            'добавь пометку "escalate" и причину. Иначе PASS.'
        )
    if lens == 'class_skeptic':
        return (
            'Ты скептик классификации входящего. Перепроверь присвоенный класс по '
            'тексту письма клиента. Особо ищи путаницу: deferred спутан с '
            'not_interested; redirect спутан с auto_reply. Ошибка класса ведёт к '
            'потере лида -> CRITICAL. Класс верен -> PASS.'
        )
    if lens == 'sales_qualifier':
        return (
            'Ты продажник-квалификатор. Оцени движение по лестнице контакта: '
            'выявлена ли потребность; задан РОВНО один уточняющий вопрос (не три); '
            'телефон предложен вовремя (не рано, не поздно); следующий шаг конкретен. '
            'Слабое движение к цели -> WARN, грубый срыв воронки -> CRITICAL.'
        )
    if lens == 'client_advocate':
        return (
            'Ты адвокат клиента: симулируй ЛПР-получателя. Письмо раздражает? Оно '
            'отвечает на ЕГО вопрос или толкает наш интерес? Есть риск жалобы или '
            'ощущение спама? Проблемы восприятия -> WARN, явный риск жалобы/обиды '
            '-> CRITICAL.'
        )
    if lens == 'tone_editor':
        return (
            'Ты тон-редактор в роли инженера-практика. Требуй: без канцелярита и '
            'восторгов, объём в 1 экран, живой деловой тон, подпись менеджера, '
            'никаких длинных тире. Нарушения тона/объёма и обезличенная подпись '
            '(«менеджер» без имени — имя подставится позже) -> WARN; подпись, '
            'выдающая ИИ/бота/нейросеть -> CRITICAL.'
        )
    if lens == 'spam_tech':
        return (
            'Ты спам-техник. Проверь тему и тело на спам-триггеры (КАПС, '
            'восклицания, «бесплатно», «срочно»), подозрительные/сокращённые ссылки, '
            'баланс текст/ссылки. Ответ не должен жечь репутацию ящика. Риск попасть '
            'в спам -> WARN, грубые триггеры/фишинг-вид ссылок -> CRITICAL.'
        )
    # Неизвестная линза — общий предохранитель, не роняем сборку промпта.
    return 'Ты ревьюер ответного письма. Оцени качество и корректность.'


def build_lens_prompt(
    lens: str,
    *,
    incoming: str,
    reply_subject: str,
    reply_body: str,
    reply_kind: str = '',
    kb_slice: str = '',
    extra: str = '',
) -> str:
    """Собрать полный промпт линзы: её роль + данные письма + требование JSON.

    kb_slice передаём всем, но реально нужен факт-чекеру; для прочих он лишь
    контекст. extra — точка расширения (few-shot, доп. инструкции пакета).
    """
    parts = [_lens_system(lens), '']
    parts.append('=== ВХОДЯЩЕЕ ПИСЬМО КЛИЕНТА ===')
    parts.append(incoming.strip() or '(пусто)')
    if reply_kind:
        parts.append('')
        parts.append(f'=== ТИП ОТВЕТА: {reply_kind} ===')
    parts.append('')
    parts.append('=== НАШ ОТВЕТ (тема) ===')
    parts.append(reply_subject.strip() or '(пусто)')
    parts.append('')
    parts.append('=== НАШ ОТВЕТ (тело) ===')
    parts.append(reply_body.strip() or '(пусто)')
    if kb_slice.strip():
        parts.append('')
        parts.append('=== СПРАВКА ИЗ БАЗЫ (для сверки фактов) ===')
        parts.append(kb_slice.strip())
    if extra.strip():
        parts.append('')
        parts.append(extra.strip())
    parts.append('')
    parts.append(_JSON_TAIL)
    return '\n'.join(parts)


def _find_json_object(raw: str) -> Optional[str]:
    """Вытащить первый сбалансированный {...} из строки (модель льёт мусор вокруг).

    Идём по символам, считаем глубину скобок, уважаем строки и экранирование —
    наивный поиск по первой/последней скобке ломается на вложенности.
    """
    start = -1
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(raw):
        if start == -1:
            if ch == '{':
                start = i
                depth = 1
            continue
        if in_str:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
    return None


def parse_verdict(lens: str, raw: str, model: str = '') -> LensVerdict:
    """Разобрать сырой ответ линзы в LensVerdict.

    Нераспарсиваемое или битый JSON -> WARN (сигнал «разбор не удался»), а не тихий
    PASS — не заглушаем проблему. Вердикт вне множества тоже понижаем до WARN.
    """
    blob = _find_json_object(raw or '')
    if not blob:
        return LensVerdict(
            lens=lens,
            verdict='WARN',
            problems=('не удалось разобрать ответ линзы',),
            raw=raw,
            model=model,
        )
    try:
        data = json.loads(blob)
    except (ValueError, TypeError):
        return LensVerdict(
            lens=lens,
            verdict='WARN',
            problems=('не удалось разобрать ответ линзы',),
            raw=raw,
            model=model,
        )
    if not isinstance(data, dict):
        return LensVerdict(
            lens=lens,
            verdict='WARN',
            problems=('не удалось разобрать ответ линзы',),
            raw=raw,
            model=model,
        )

    verdict = str(data.get('verdict', '')).strip().upper()
    problems = _as_str_tuple(data.get('problems'))
    fixes = _as_str_tuple(data.get('fixes'))

    if verdict not in _VALID_VERDICTS:
        # Неизвестный вердикт: не доверяем, помечаем и оставляем WARN.
        problems = problems + (f'нераспознанный verdict: {verdict or "(пусто)"}',)
        verdict = 'WARN'

    return LensVerdict(
        lens=lens,
        verdict=verdict,
        problems=problems,
        fixes=fixes,
        raw=raw,
        model=model,
    )


def _as_str_tuple(value) -> tuple[str, ...]:
    """Привести поле JSON к кортежу непустых строк (модель шлёт разное)."""
    if value is None:
        return ()
    if isinstance(value, str):
        v = value.strip()
        return (v,) if v else ()
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            s = str(item).strip()
            if s:
                out.append(s)
        return tuple(out)
    s = str(value).strip()
    return (s,) if s else ()


def default_caller(prompt: str, max_tokens: int = 2000) -> tuple[str, str]:
    """Провайдерский вызов одной линзы -> (text, использованная_модель).

    Ленивый импорт gen_provider из родительского каталога пакета sender. Ретраи с
    экспоненциальным бэкоффом+джиттером (флаки-шлюз); слишком короткий ответ =
    провал; после 3 подряд неудач уходим на более сильную модель. httpx импортим
    лениво внутри — движок остаётся на stdlib, фейковые тесты его не тянут.

    max_tokens — потолок ответа. 2000 хватало линзам и коротким письмам, но
    13.08 канон редактора удлинил письма вдвое (140-190 слов), и партия из
    четырёх обрывалась на середине JSON: разбор честно говорил «нет JSON»,
    а выглядело это как каприз модели. Генератор писем зовёт с большим
    потолком (см. ai_quota._default_gen_factory).
    """
    import httpx  # noqa: F401  # ленивый импорт: движок stdlib, нужен только в бою

    # gen_provider лежит на уровень выше пакета sender.
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    import gen_provider  # type: ignore

    model = 'claude-fable-5'
    fallback = 'claude-opus-4-8'
    messages = [{'role': 'user', 'content': prompt}]

    consecutive_fail = 0
    last_err: Optional[Exception] = None
    for attempt in range(8):
        try:
            msg = gen_provider._raw_stream(messages, model, max_tokens,
                                           thinking=False)
            # _raw_stream возвращает _Msg; текстовый канал — блоки type='text'
            text = ''.join(
                b.text for b in msg.content if getattr(b, 'type', '') == 'text')
            if text and len(text) >= 20:
                return text, model
            # Слишком короткий ответ считаем провалом (пустышка/обрыв шлюза).
            raise RuntimeError('слишком короткий ответ линзы')
        except Exception as exc:  # noqa: BLE001 — тут ловим всё: сеть флаки
            last_err = exc
            consecutive_fail += 1
            if consecutive_fail >= 3 and model != fallback:
                # Переключаемся на более мощную модель — сбрасываем счётчик.
                model = fallback
                consecutive_fail = 0
            # Экспоненциальный бэкофф с джиттером, чтобы не долбить шлюз в такт.
            backoff = min(30.0, (2 ** attempt) * 0.5) + random.uniform(0, 0.5)
            time.sleep(backoff)

    raise RuntimeError(f'линза не получила ответ после ретраев: {last_err}')


def _call_lens(
    lens: str,
    prompt: str,
    caller: Callable,
) -> LensVerdict:
    """Один вызов линзы с обёрткой ошибок. caller может вернуть (text,model) или text.

    Падение линзы не роняет конвейер: обычная линза -> WARN. Но блокирующая линза
    при сбое -> CRITICAL («сомнение = не слать») — иначе можно молча пропустить
    факт/юр/эскалацию/класс.
    """
    try:
        result = caller(prompt)
        if isinstance(result, tuple):
            text, model = (list(result) + ['', ''])[:2]
        else:
            text, model = result, ''
        return parse_verdict(lens, str(text), str(model))
    except Exception as exc:  # noqa: BLE001 — изолируем сбой линзы
        if lens in BLOCKING:
            return LensVerdict(
                lens=lens,
                verdict='CRITICAL',
                problems=('блокирующая линза недоступна', f'сбой: {exc}'),
            )
        return LensVerdict(
            lens=lens,
            verdict='WARN',
            problems=(f'линза упала: {exc}',),
        )


def run_lenses(
    *,
    incoming: str,
    reply_subject: str,
    reply_body: str,
    reply_kind: str = '',
    kb_slice: str = '',
    caller: Optional[Callable] = None,
    parallel: int = 1,
) -> dict[str, LensVerdict]:
    """Прогнать ВСЕ 8 линз по письму -> {lens: LensVerdict}.

    caller инъектируется (для тестов — фейк). parallel=1 по умолчанию
    (последовательно, детерминировано и дешевле по подключениям); parallel>1 —
    ThreadPoolExecutor (вызовы независимы и I/O-bound).
    """
    call = caller or default_caller

    prompts = {
        lens: build_lens_prompt(
            lens,
            incoming=incoming,
            reply_subject=reply_subject,
            reply_body=reply_body,
            reply_kind=reply_kind,
            kb_slice=kb_slice,
        )
        for lens in LENSES
    }

    results: dict[str, LensVerdict] = {}

    if parallel and parallel > 1:
        workers = min(parallel, len(LENSES))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_call_lens, lens, prompts[lens], call): lens
                for lens in LENSES
            }
            for fut, lens in futures.items():
                results[lens] = fut.result()
    else:
        for lens in LENSES:
            results[lens] = _call_lens(lens, prompts[lens], call)

    # Возвращаем в каноничном порядке спеки для стабильного обхода судьёй.
    return {lens: results[lens] for lens in LENSES}


def kb_slice_for(text: str, kb: dict) -> str:
    """Компактный срез answer-kb для факт-чекера по тексту письма (< 4000 симв.).

    Берём только то, что реально упомянуто: company целиком, бренды из text и по
    ним warranties/claims (первые 2) и медиану цены. Полную базу в промпт не льём
    — дорого и размывает сверку.
    """
    if not kb:
        return ''

    text_low = (text or '').lower()
    parts: list[str] = []

    company = kb.get('company')
    if company:
        try:
            parts.append(
                'company: ' + json.dumps(company, ensure_ascii=False)
            )
        except (TypeError, ValueError):
            parts.append('company: ' + str(company))

    brands = kb.get('brands') or {}
    prices = (kb.get('prices') or {}).get('by_brand') or {}

    mentioned: list[str] = []
    if isinstance(brands, dict):
        brand_names = list(brands.keys())
    elif isinstance(brands, (list, tuple)):
        brand_names = [str(b) for b in brands]
    else:
        brand_names = []

    for name in brand_names:
        if name and str(name).lower() in text_low:
            mentioned.append(name)

    for name in mentioned:
        chunk = [f'бренд {name}:']
        info = brands.get(name) if isinstance(brands, dict) else None
        if isinstance(info, dict):
            warranties = info.get('warranties')
            if isinstance(warranties, (list, tuple)) and warranties:
                chunk.append(
                    '  гарантии: '
                    + '; '.join(str(w) for w in warranties[:2])
                )
            elif warranties:
                chunk.append(f'  гарантии: {warranties}')
            claims = info.get('claims')
            if isinstance(claims, (list, tuple)) and claims:
                chunk.append(
                    '  утверждения: '
                    + '; '.join(str(c) for c in claims[:2])
                )
            elif claims:
                chunk.append(f'  утверждения: {claims}')
        price = prices.get(name) if isinstance(prices, dict) else None
        if isinstance(price, dict):
            median = price.get('median')
            if median is not None:
                chunk.append(f'  медиана цены: {median}')
        elif price is not None:
            chunk.append(f'  медиана цены: {price}')
        if len(chunk) > 1:
            parts.append('\n'.join(chunk))

    result = '\n'.join(parts).strip()
    if len(result) > 4000:
        # Жёсткий потолок — режем по границе, промпт не должен раздуваться.
        result = result[:4000].rstrip()
    return result
