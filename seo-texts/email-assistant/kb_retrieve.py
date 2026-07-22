# -*- coding: utf-8 -*-
"""Ретрив под лида: из kb-retrieve.json выбрать РЕЛЕВАНТНОЕ для письма (не раздувая промпт).
select_for_lead(lead) → компактный блок: 2-3 кейса (город-матч приоритетнее), цены категории,
ценовой коридор по бюджет-баллу ОКВЭД, гео-агрегат («N внедрений в вашем городе»), триггер-фраза
по новостному сигналу. Использование (рассыльщик/автоответчик):
    from kb_retrieve import select_for_lead
    ctx = select_for_lead({'city':'Екатеринбург','sphere':'металлообработка','okved':'25.62',
                           'division':'kc','signal':{'event_type':'модернизация','days_ago':12}})"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
_KB = None


def _kb():
    global _KB
    if _KB is None:
        _KB = json.load(open(os.path.join(HERE, 'kb-retrieve.json')))
    return _KB


def _okved_budget(okved):
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'server'))
        import enrich_db as E
        return E.division_for_okveds(okved)
    except Exception:  # noqa: BLE001
        return ('', 0)


def _sig_phrase(sig):
    """Триггер-фраза по капекс-сигналу (идеи линз: тайминг + ФРП/ОЭЗ)."""
    if not sig:
        return ''
    et = (sig.get('event_type') or '').lower()
    days = sig.get('days_ago')
    fresh = (days is not None and days <= 30)
    if 'фрп' in et or 'займ' in (sig.get('what') or '').lower():
        return 'займ ФРП = подтверждённый бюджет на оборудование — уместно предложить конкретику под проект'
    if 'резидент' in et:
        return 'резидент ОЭЗ/ТОР обязан выполнять инвестплан — предложить оборудование под план с льготами'
    if fresh:
        return f'событие «{et}» свежее (≤30 дн) — тема письма с прямой отсылкой, срочный тон (успеть к запуску)'
    return f'событие «{et}» 1-3 мес назад — кейс-подход («как мы решали это у похожих»)'


def select_for_lead(lead):
    kb = _kb()
    city = (lead.get('city') or '').strip()
    region = (lead.get('region') or '').strip()
    sphere = (lead.get('sphere') or '').strip().lower()
    division = lead.get('division') or ''
    # 1) кейсы: город-матч > РЕГИОН-матч > отрасль > бренд
    scored = []
    for p in kb['projects']:
        s = 0
        if city and p['city'] and city.lower() == p['city'].lower():
            s += 10                                     # тот же город — сильнейший матч
        elif region and p.get('region') and region.lower() == p['region'].lower():
            s += 6                                      # тот же регион — тоже «рядом с вами»
        if sphere and sphere in (p['sphere'] or '').lower():
            s += 5
        if lead.get('brand') and lead['brand'].lower() in (p['brand'] or '').lower():
            s += 2
        if s:
            scored.append((s, p))
    cases = [p for _s, p in sorted(scored, key=lambda t: -t[0])[:3]]
    # 2) гео-агрегат: город точнее; фолбэк — регион («в Свердловской области N проектов»)
    geo = ''
    n_city = kb['city_counts'].get(city)
    n_reg = kb.get('region_counts', {}).get(region)
    if n_city:
        geo = f'в г. {city} у нас {n_city} реализованных проектов'
    elif n_reg:
        geo = f'в регионе «{region}» у нас {n_reg} реализованных проектов'
    # 3) ценовой коридор по бюджет-баллу ОКВЭД
    div_ok, budget = _okved_budget(lead.get('okved') or '')
    cat = ('Фотосепараторы' if 'meyer' in (division or div_ok) else 'Промышленные компрессоры')
    band = kb['budget_bands'].get(cat, {}).get(budget or 3, '')
    # 4) цены категории (медианы)
    price = kb['prices']['by_cat'].get(cat) or {}
    return dict(cases=cases, geo=geo, budget_score=budget or None,
                price_band=band, price_median=price, division=division or div_ok,
                signal_hint=_sig_phrase(lead.get('signal')))


if __name__ == '__main__':
    demo = select_for_lead({'city': 'Екатеринбург', 'sphere': 'металлообработка',
                            'okved': '25.62', 'division': 'kc',
                            'signal': {'event_type': 'модернизация', 'days_ago': 12}})
    print(json.dumps(demo, ensure_ascii=False, indent=1)[:1500])
