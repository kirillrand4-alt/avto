# -*- coding: utf-8 -*-
# 13.10, владелец: «запускай, но проверь чтобы лишнего не отбросила». Строгая перепроверка сайтов, оставленных при
# «слабом» опровержении (опровергатель: «сайт не этой компании», сборка оставляла — случай «Агро-Альянс»: сайт холдинга
# записан за тёзкой по базе обзвона, письмо ушло клиенту в сделке). Цели — meyer7-oprov-strogo-celi.jsonl с дропа (683:
# компании «Компаний» с таким сайтом, КРОМЕ тех, где на сайте ИНН самой компании — те свои, не трогаем).
# Страховки от лишнего отсева:
#   1) вопрос 1 — «сайт этой компании или её группы/холдинга/ТД/бренда?»; «нет» только при явной другой организации,
#      расхождение ОКВЭД/масштаба само по себе — не «нет»;
#   2) для «нет» — независимый вопрос 2 «найди любые признаки связи сайта с компанией»; отсев — только «нет» + «связи нет»;
#   3) применение — после ручного просмотра выборки (здесь база не меняется).
# Итог — meyer7-oprov-strogo.jsonl (fsync, резюм) + дроп. Лог: oprov_strogo_*.log.
import collections, io, json, os, re, sys, threading, time
DIR = r'C:\sender\server'
ВЫХ = os.path.join(DIR, 'meyer7-oprov-strogo.jsonl')
_лок = threading.Lock()
ПРОМПТ1 = (
    'Для каждой компании реши: этот сайт — сайт ЭТОЙ компании (её собственный, или её холдинга/группы, управляющей '
    'компании, торгового дома, бренда, где компания — одно из предприятий)? Ответы:\n'
    '«да» — сайт её или её группы (совпадает название/бренд, город, руководитель, ИНН/ОГРН, адрес, профиль; группа, где она '
    'названа или очевидно входит);\n'
    '«нет» — сайт явно ДРУГОЙ организации без признаков связи с компанией: другое юрлицо из другого региона, тёзка, '
    'каталог/справочник/СМИ/личный сайт, сайт холдинга, в который эта компания явно не входит;\n'
    '«неясно» — данных мало.\n'
    'ВАЖНО: расхождение ОКВЭД, масштаба или выручки само по себе — НЕ повод для «нет» (ОКВЭД часто не отражает '
    'деятельность, выручка бывает занижена, у малого юрлица бывает сайт группы). «нет» — только когда видно, что сайт '
    'принадлежит другой, не связанной организации.\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер,"ответ":"да|нет|неясно","почему":"до 20 слов"}}]\n\n{блоки}')
ПРОМПТ2 = (
    'Для каждой пары «компания — сайт» найди ЛЮБЫЕ признаки, что сайт принадлежит этой компании или её группе: '
    'совпадение названия или его части/аббревиатуры, бренд, ИНН/ОГРН, город/район/посёлок, адрес, руководитель, телефон '
    'с кодом её региона, упоминание её как предприятия группы. Ответы: «связь есть» (назови признак), «связи нет» '
    '(сайт другой организации, признаков нет), «неясно».\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер,"ответ":"связь есть|связи нет|неясно","признак":"до 20 слов"}}]\n\n{блоки}')


def писать(r):
    with _лок:
        with io.open(ВЫХ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    import pilot_konveyer as PK
    os.environ.update(PK.Волны().env_шага('kc_kontakty.py'))
    import kc_kontakty as KK
    import _inn_zamer_meyer7 as Z
    t0 = time.time()
    цели = [json.loads(s) for s in io.open(r'C:\seostat\drop\drop-storage\meyer7-oprov-strogo-celi.jsonl', encoding='utf-8') if s.strip()]
    готово = {}
    if os.path.exists(ВЫХ):
        for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
                if y.get('ответ1'):
                    готово[y['ключ']] = y
            except (ValueError, KeyError):
                pass
    задачи = [x for x in цели if x['ключ'] not in готово]
    карта = json.load(io.open(os.path.join(DIR, 'meyer7-zenno-surrogat.json'), encoding='utf-8'))
    сур = collections.defaultdict(list)
    for кл, i in карта.items():
        сур[i].append(кл)
    кк = {x['ключ'] for x in задачи} | {k for x in задачи for k in сур.get(x['ключ'], [])}
    файлы = collections.defaultdict(list)
    for п in Z.ZENNO:
        if os.path.isdir(п):
            for e in os.scandir(п):
                if e.name.endswith('.html'):
                    k, _, n = e.name[:-5].rpartition('_')
                    if k in кк and n.isdigit():
                        файлы[k].append((e.path, int(n), п))
    print('целей', len(цели), '| уже', len(готово), '| к проверке', len(задачи), flush=True)

    def сайт_кратко(x):
        r = Z.одна((x['ключ'], x['сайт'], сур.get(x['ключ'], []), {k: файлы[k] for k in [x['ключ']] + сур.get(x['ключ'], []) if k in файлы}))
        стр = []
        for k in [x['ключ']] + сур.get(x['ключ'], []):
            стр += Z.страницы_кэша(k) + Z.страницы_зенки(k, файлы.get(k) or [])
        дом = Z.хост(x['сайт'])
        заг, глав, куски = '', '', []
        for y in стр:
            if дом and Z.хост(y.get('url') or '') not in (дом, 'www.' + дом) and not Z.хост(y.get('url') or '').endswith('.' + дом):
                continue
            h = y.get('html') or ''
            if not заг:
                м = re.search(r'<title[^>]*>(.*?)</title>', h, re.S | re.I)
                заг = Z.чистый(м.group(1))[:140] if м else ''
            if not глав:
                т = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', h[:300000], flags=re.S | re.I)
                глав = Z.чистый(т)[:700]
            if len(куски) < 3 and re.search(r'контакт|о-компании|about|rekviz|реквиз', (y.get('url') or '').lower()):
                т = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', h[:300000], flags=re.S | re.I)
                т = Z.чистый(т)
                м = re.search(r'(адрес|г\.\s*[А-ЯЁ]|ул\.|тел)', т, re.I)
                куски.append(т[max(0, (м.start() if м else 0) - 100):(м.start() if м else 0) + 300])
        return {'заголовок': заг, 'главная': глав, 'куски': куски, 'юр': list(r['юр'])[:6] + list(r['ип'])[:2], 'инн': list(r['инн'])[:5]}

    def блок(j, x, с):
        return ('%d. КОМПАНИЯ: %s, ИНН %s, %s, ОКВЭД %s (%s), выручка %s, руководитель: %s%s\n САЙТ: %s | заголовок: %s\n'
                ' Юрназвания на сайте: %s | ИНН на сайте: %s\n Главная: %s\n Контакты/о компании: %s\n'
                ' Прежние проверки: сайт-проверка «%s»; опровергатель: %s%s' % (
                    j, x['имя'], x['ключ'], x['регион'], x['оквэд'], x['сегм'][:60], x['выручка'] or 'нет данных', x['директор'] or 'нет данных',
                    ('; группа: ' + x['группа'][:80]) if x.get('группа') else '', x['сайт'], с['заголовок'], '; '.join(с['юр']) or '-',
                    ', '.join(с['инн']) or '-', с['главная'][:500], ' || '.join(k[:300] for k in с['куски'])[:700] or '-',
                    x['проверка'][:160], x['опровержение'][:200], (' «%s»' % x['цитата'][:150]) if x.get('цитата') else ''))

    def пачка(п_):
        сайты = [сайт_кратко(x) for x in п_]
        блоки = '\n\n'.join(блок(j, x, с) for j, (x, с) in enumerate(zip(п_, сайты), 1))
        о1 = KK.модель(ПРОМПТ1.format(блоки=блоки), True) or {}
        нет = [(j, x, с) for j, (x, с) in enumerate(zip(п_, сайты), 1) if (о1.get(j) or {}).get('ответ') == 'нет']
        о2 = {}
        if нет:
            б2 = '\n\n'.join(блок(k, x, с) for k, (_, x, с) in enumerate(нет, 1))
            о2_ = KK.модель(ПРОМПТ2.format(блоки=б2), True) or {}
            о2 = {j: о2_.get(k) or {} for k, (j, _, _) in enumerate(нет, 1)}
        for j, (x, с) in enumerate(zip(п_, сайты), 1):
            y1, y2 = о1.get(j) or {}, о2.get(j) or {}
            отсев = y1.get('ответ') == 'нет' and y2.get('ответ') == 'связи нет'
            писать({'ключ': x['ключ'], 'имя': x['имя'], 'сайт': x['сайт'], 'ответ1': y1.get('ответ') or '', 'почему1': y1.get('почему') or '',
                    'ответ2': y2.get('ответ') or '', 'признак2': y2.get('признак') or '', 'отсев': отсев, 'почт': x.get('почт'),
                    'номеров': x.get('номеров'), 'юр_на_сайте': с['юр'][:4], 'заголовок': с['заголовок']})

    from concurrent.futures import ThreadPoolExecutor
    пачки = [задачи[k:k + 6] for k in range(0, len(задачи), 6)]
    with ThreadPoolExecutor(8) as ex:
        for n, _ in enumerate(ex.map(пачка, пачки), 1):
            if n % 20 == 0:
                print('пачек', n, 'из', len(пачки), 'за %.1f мин' % ((time.time() - t0) / 60), flush=True)
    посл = {}
    for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
        try:
            y = json.loads(s)
            посл[y['ключ']] = y
        except (ValueError, KeyError):
            pass
    import shutil
    shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
    сч = collections.Counter('%s/%s' % (y['ответ1'] or '-', y['ответ2'] or '-') for y in посл.values())
    print('===ИТОГ СТРОГОЙ===', json.dumps({'всего': len(посл), 'отсев': sum(1 for y in посл.values() if y['отсев']), 'ответы': dict(сч.most_common())},
                                         ensure_ascii=False), 'за %.1f мин' % ((time.time() - t0) / 60), flush=True)


if __name__ == '__main__':
    sys.path.insert(0, DIR)
    sys.path.insert(0, r'C:\sender')
    os.chdir(DIR)
    os.environ.update({'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'PILOT_MODEL': 'gpt-6-luna',
                       'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'oprov_strogo_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_oprov_strogo_meyer7.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False)
        time.sleep(20)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                         ensure_ascii=False))
        sys.exit(0)
    main()
