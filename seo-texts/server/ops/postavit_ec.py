# -*- coding: utf-8 -*-
"""Поставить репо-версию enrich_contacts.py на сервер: бэкап, проба, откат.

ЗАЧЕМ. Серверный модуль отстал: 46 функций против 85 в репозитории. Из-за
этого `leadership.py` падает на КАЖДОЙ цели с `AttributeError: module
'enrich_contacts' has no attribute 'branch_links'` — 20 из 20 в пилоте, при
этом оп завершается с кодом 0 и рапортует «обработано 20». Тем же местом
сломан и `core_sites.py`: он зовёт `EC.phones_in`, которой на сервере тоже нет.
То есть весь слой обхода сайтов мёртв, и по коду возврата этого не видно.

ЧТО ПРОВЕРЕНО ПЕРЕД ЗАМЕНОЙ (я уже однажды затёр этим чужую работу)
  * имена функций: серверные 46 — строгое подмножество репозиторных 85,
    своих у сервера НЕТ ни одной;
  * построчно: 68 незакомментированных строк сервера не встречаются в репо, и
    все они — тот же код на другом уровне вложенности, то есть старая ветка,
    а не чужая правка;
  * репозиторный файл последний раз менялся 02.08 и лежит в git.

ПОРЯДОК. Бэкап с меткой времени → замена → проба В ОТДЕЛЬНОМ ПРОЦЕССЕ (импорт
в текущий бесполезен, модуль уже загружен) → при любом провале откат из бэкапа.
Проба спрашивает не «импортируется ли», а наличие всех прежних 46 функций плюс
тех, из-за которых всё затевалось.

Запуск: python postavit_ec.py [--apply]
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time

ЦЕЛЬ = r'C:\sender\server\enrich_contacts.py'
НОВЫЙ = r'C:\seostat\drop\drop-storage\REPO-enrich_contacts-0805.py'
# Путь к интерпретатору не угадываем: берём тот, которым нас же и запустили.
ПИТОН = sys.executable
ПРИМЕНИТЬ = '--apply' in sys.argv

ПРЕЖНИЕ = """_PACE _base_index _base_peek _base_pick _best_by_role _bump
_cached_dolphin_profiles _chain_next _contact_cap _domain _done_inns
_egrul_emails_by_inn _eis_get _fetch_site _finalize_smtp _find_base _get_base
_harvest_from_html _is_competitor _is_junk_email _is_own_site _looks_blocked
_next_dolphin_profile _opo_worker _org_page_probe _parse_kg _parse_profile_ids
_read_secret _resolve_dolphin_profiles _site_cache_get _vk_api_via_dolphin
crawl_contacts enrich_one extract_roles find_directory_contacts
find_hh_compressor find_opo_signal find_site_via_listorg find_site_via_search
find_site_via_xmlriver find_staff_via_search find_vk_group_contacts
find_zakupki_contacts main mx_ok smtp_verify""".split()
РАДИ_ЧЕГО = ['branch_links', 'phones_in', 'people_from_html', 'persist_contacts',
             'find_leadership_via_search', 'phone_strings']


def проба():
    """Отдельный процесс: модуль в текущем уже загружен, его импорт ничего не скажет."""
    код = (
        'import sys, json\n'
        'sys.path.insert(0, r"C:\\sender\\server")\n'
        'import enrich_contacts as EC\n'
        'нет = [и for и in %r if not hasattr(EC, и)]\n'
        'ради = [и for и in %r if not hasattr(EC, и)]\n'
        'проба_тел = []\n'
        'try:\n'
        '    проба_тел = [m.group(0) for m in EC.phones_in('
        '"звоните +7 (343) 555-12-34 или 8 3439 39-50-10")]\n'
        'except Exception as e:\n'
        '    проба_тел = ["ОШИБКА " + type(e).__name__]\n'
        'print(json.dumps({"poteryano": нет, "ne_poyavilos": ради,'
        ' "telefony": проба_тел, "funkciy": len([x for x in dir(EC)'
        ' if not x.startswith("__")])}, ensure_ascii=False))\n'
    ) % (ПРЕЖНИЕ, РАДИ_ЧЕГО)
    п = subprocess.run([ПИТОН, '-c', код], capture_output=True, text=True,
                       timeout=180)
    хвост = (п.stdout or '').strip().splitlines()
    try:
        return json.loads(хвост[-1]) if хвост else {'err': 'молчание пробы'}
    except Exception:
        return {'err': (п.stderr or п.stdout or '')[-400:]}


def sha(п):
    return hashlib.sha256(io.open(п, 'rb').read()).hexdigest()[:16]


def main():
    if not os.path.exists(НОВЫЙ):
        print('нет файла на дропе:', НОВЫЙ)
        return
    print(f'сейчас  {os.path.getsize(ЦЕЛЬ):8} байт  sha {sha(ЦЕЛЬ)}')
    print(f'ставим  {os.path.getsize(НОВЫЙ):8} байт  sha {sha(НОВЫЙ)}')
    до = проба()
    print('проба ДО замены:', json.dumps(до, ensure_ascii=False)[:220])
    if not ПРИМЕНИТЬ:
        print('СУХОЙ ПРОГОН — ничего не заменено')
        return

    метка = time.strftime('%Y%m%d-%H%M%S')
    бэкап = ЦЕЛЬ + f'.bak-{метка}'
    shutil.copy2(ЦЕЛЬ, бэкап)
    print('бэкап:', os.path.basename(бэкап))
    shutil.copy2(НОВЫЙ, ЦЕЛЬ)
    после = проба()
    print('проба ПОСЛЕ замены:', json.dumps(после, ensure_ascii=False)[:300])

    плохо = (после.get('err') or после.get('poteryano')
             or после.get('ne_poyavilos')
             or not после.get('telefony')
             or any('ОШИБКА' in str(x) for x in после.get('telefony', [])))
    if плохо:
        shutil.copy2(бэкап, ЦЕЛЬ)
        print('ОТКАТ ВЫПОЛНЕН — вернул прежний файл, причина выше')
        print('после отката sha', sha(ЦЕЛЬ))
        return
    print()
    print('ЗАМЕНА ПРИНЯТА')
    print(f'   функций стало           {после.get("funkciy")}')
    print(f'   прежних потеряно        {len(после.get("poteryano") or [])}')
    print(f'   нужных появилось        {len(РАДИ_ЧЕГО)}')
    print(f'   телефоны из пробы       {после.get("telefony")}')
    print(f'   бэкап                   {os.path.basename(бэкап)}')


if __name__ == '__main__':
    main()
