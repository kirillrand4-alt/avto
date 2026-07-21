# -*- coding: utf-8 -*-
"""Разбор разметок контактов по выводу прогона-500 (enrich с contact_src).
Отвечает: (1) откуда тянем email (mailto/текст/JSON-LD/деобфускация/JS-рендер),
(2) извлекается ли РОЛЬ скриптом (local-part + контекст-метка) или это «каша» → LLM,
(3) покрытие детерминированного экстрактора vs где нужен fable/haiku.
Сверяет скрипт-роль с fable-ролью (согласие). Запуск: python3 analyze_markup.py <enrich_out.json>
"""
import sys, json, re
from collections import Counter

# local-part -> роль (прямой детерминированный сигнал)
LOCAL_ROLE = [
    (r'zakup|snab|snabzh|postavk|opt|torg|zayavk', 'снабжение/закупки'),
    (r'sale|prodazh|prodaji|sbyt|kommerc|market|zayavka|order|zakaz', 'продажи'),
    (r'director|dir\b|ceo|gendir|glava|rukovod|boss', 'директор'),
    (r'buh|account|finans|oplata|bill', 'бухгалтерия'),
    (r'inzh|engineer|tech|tehn|service|servis|proekt|konstr', 'гл.инженер'),
    (r'hr\b|kadr|personal|resume|vacan', 'кадры'),
    (r'info|office|ofis|mail|post|priem|reception|sekret|kontakt|general|company|zavod|firma|manager', 'общий/приёмная'),
]
# контекст-метки рядом с email (второй детерминированный сигнал)
CTX_ROLE = [
    (r'закуп|снабж|тендер|поставщик', 'снабжение/закупки'),
    (r'прода|сбыт|коммерч|менеджер|отдел прод|заявк|заказ', 'продажи'),
    (r'директор|руководител|генеральн', 'директор'),
    (r'бухгалт|финанс', 'бухгалтерия'),
    (r'инженер|технич|сервис|проект|конструктор', 'гл.инженер'),
    (r'приёмн|приемн|секрет|ресепш|общий', 'общий/приёмная'),
    (r'кадр|персонал|hr|ваканс', 'кадры'),
]


def script_role(local, ctx):
    """Определить роль детерминированно: сначала по local-part, потом по контексту."""
    l = (local or '').lower()
    for rx, role in LOCAL_ROLE:
        if re.search(rx, l):
            return role, 'local-part'
    c = (ctx or '').lower()
    for rx, role in CTX_ROLE:
        if re.search(rx, c):
            return role, 'context'
    return None, None  # «каша» — детерминированно роль не ясна


def main():
    path = sys.argv[1]
    d = json.load(open(path))
    results = d.get('data', {}).get('results') if 'data' in d else d.get('results', d)
    if isinstance(results, dict):
        results = results.get('results', [])
    src_counter = Counter()
    role_src_counter = Counter()          # каким сигналом определилась роль
    email_total = 0
    email_role_by_script = 0
    sites_with_email = 0
    sites_script_lpr = 0                   # сайтов, где скрипт дал хоть одну роль
    sites_kasha = 0                        # email есть, но роль скриптом не ясна ни у одного
    agree = [0, 0]                         # [совпало с fable, всего сравнений]
    examples_kasha = []
    for r in results:
        cs = r.get('contact_src') or {}
        emails = cs.get('emails') or {}
        if not emails:
            continue
        sites_with_email += 1
        # роли по данным провайдера (fable) — для сверки
        fable_roles = {(e.get('email') or '').lower(): (e.get('role') or '')
                       for e in (r.get('emails') or [])}
        any_role, any_kasha = False, False
        for em, meta in emails.items():
            email_total += 1
            src_counter[meta.get('src', '?')] += 1
            role, sig = script_role(meta.get('local'), meta.get('ctx'))
            if role:
                email_role_by_script += 1
                role_src_counter[sig] += 1
                any_role = True
                fr = fable_roles.get(em)
                if fr:
                    agree[1] += 1
                    # грубое совпадение по ключевому слову роли
                    if role.split('/')[0][:4].lower() in fr.lower() or fr.lower()[:4] in role.lower():
                        agree[0] += 1
            else:
                any_kasha = True
                if len(examples_kasha) < 12:
                    examples_kasha.append({'email': em, 'local': meta.get('local'),
                                           'ctx': (meta.get('ctx') or '')[:70]})
        if any_role:
            sites_script_lpr += 1
        elif any_kasha:
            sites_kasha += 1

    rep = {
        'sites_with_email': sites_with_email,
        'emails_total': email_total,
        'source_breakdown': dict(src_counter),
        'source_pct': {k: round(100 * v / max(1, email_total), 1) for k, v in src_counter.items()},
        'role_by_script': {
            'emails_with_script_role': email_role_by_script,
            'pct_of_emails': round(100 * email_role_by_script / max(1, email_total), 1),
            'signal': dict(role_src_counter),
        },
        'coverage_sites': {
            'script_gives_role': sites_script_lpr,
            'kasha_need_llm': sites_kasha,
            'pct_script': round(100 * sites_script_lpr / max(1, sites_with_email), 1),
        },
        'script_vs_fable_role_agree': (round(100 * agree[0] / agree[1], 1) if agree[1] else None,
                                       f'{agree[0]}/{agree[1]}'),
        'kasha_examples': examples_kasha,
    }
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
