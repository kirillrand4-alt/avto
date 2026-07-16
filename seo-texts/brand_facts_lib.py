# -*- coding: utf-8 -*-
"""Гейт достоверности брендовых фактов -> компактный блок для payload генератора.

Единый источник фактуры о брендах: kb/brand-facts-clean.json (уже прошёл аудит +
верификацию зависимостей). В текст пускаем ТОЛЬКО подтверждённое:
  - positioning/country      — если заполнены и не в caveats
  - series                   — только confidence high/medium (low выкидываем)
  - safe_facts               — все (это и есть выжимка после аудита)
  - confirmed_dependencies   — все (подтверждённые закономерности из прайса, замечание №4)
  - caveats                  — идут в блок «НЕ УТВЕРЖДАТЬ» (охранный барьер для модели)

Импортируется любым билдером payload'ов:  from brand_facts_lib import fact_block, tone_for
"""
import json, os, re

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB = None

# Тональные тиры (решение владельца): rodnoy=Enger (продвигаем),
# druzhestvennyy=офиц. дилерство «Руспром» (тёпло), neytralnyy=эксперт + честный мост к Enger.
TONE = {
    'enger': 'rodnoy',
    'berg': 'druzhestvennyy', 'atom': 'druzhestvennyy',
    'cross_air': 'druzhestvennyy', 'crossair': 'druzhestvennyy',
    'dali': 'druzhestvennyy', 'hansmann': 'druzhestvennyy',
}
_GATE_OK = {'high', 'medium', 'medium-low'}  # серии ниже medium в текст не идём


def _load():
    global _DB
    if _DB is None:
        with open(os.path.join(_HERE, 'kb', 'brand-facts-clean.json'), encoding='utf-8') as f:
            _DB = json.load(f)
    return _DB


def _norm(slug):
    return re.sub(r'[^a-z0-9]+', '_', str(slug).strip().lower()).strip('_')


def _find(slug):
    db = _load()
    n = _norm(slug)
    if n in db:
        return db[n]
    # запасной поиск по имени бренда
    for r in db.values():
        if _norm(r.get('brand', '')) == n:
            return r
    return None


def tone_for(slug):
    """rodnoy | druzhestvennyy | neytralnyy — по бренду фасета."""
    return TONE.get(_norm(slug), 'neytralnyy')


def _series_lines(series):
    out = []
    if not isinstance(series, dict):
        return out
    for group, items in series.items():
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            if it.get('confidence') not in _GATE_OK:
                continue
            parts = [it.get('prefix') or it.get('name') or '']
            desc = it.get('name') if it.get('prefix') else None
            if desc and desc != parts[0]:
                parts.append(desc)
            for k, lab in (('power_kW', 'кВт'), ('pressure_atm', 'атм'), ('perf_m3min', 'м³/мин')):
                if it.get(k):
                    parts.append(f'{it[k]} {lab}')
            line = ' — '.join(p for p in parts[:2]) + (
                ' (' + ', '.join(parts[2:]) + ')' if len(parts) > 2 else '')
            if line.strip(' —'):
                out.append(line.strip())
    return out


def fact_block(slug, max_facts=8, max_deps=6, include_series=True):
    """Вернуть готовый текстовый блок фактуры для поля payload['brand_facts'].
    None -> бренда нет в базе (билдер решает, писать ли страницу без брендовой фактуры)."""
    r = _find(slug)
    if not r:
        return None
    L = []
    pos = r.get('positioning')
    if pos:
        L.append(str(pos).strip())
    elif r.get('country'):
        L.append(f'Страна производства: {r["country"]}.')

    if include_series:
        sl = _series_lines(r.get('series'))
        if sl:
            L.append('Серии (подтверждённые): ' + '; '.join(sl[:6]) + '.')

    facts = [str(f).strip() for f in (r.get('safe_facts') or []) if str(f).strip()]
    if facts:
        L.append('Факты:\n' + '\n'.join('- ' + f for f in facts[:max_facts]))

    deps = [str(d).strip() for d in (r.get('confirmed_dependencies') or []) if str(d).strip()]
    if deps:
        L.append('Технические закономерности (подтверждены прайсом):\n'
                 + '\n'.join('- ' + d for d in deps[:max_deps]))

    cav = [str(c).strip() for c in (r.get('caveats') or []) if str(c).strip()]
    if cav:
        L.append('НЕ УТВЕРЖДАТЬ (нет подтверждения):\n'
                 + '\n'.join('- ' + c for c in cav))

    return '\n\n'.join(L)


def has_brand(slug):
    return _find(slug) is not None


if __name__ == '__main__':
    import sys
    db = _load()
    if len(sys.argv) > 1:
        s = sys.argv[1]
        print('TONE:', tone_for(s))
        print('=' * 60)
        print(fact_block(s))
    else:
        # сводка покрытия
        for s in sorted(db):
            fb = fact_block(s) or ''
            print(f'{s:20} tone={tone_for(s):14} facts_block={len(fb)}ch')
