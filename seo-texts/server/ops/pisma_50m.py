# -*- coding: utf-8 -*-
"""10 писем по компаниям с выручкой от 50 млн.

Отбор НЕ подменяется: берём штатный AiQuota.candidates (в нём стоп-лист, ОКВЭД,
гейт «не покупатель», мёртвые адреса, направление, накал) и добавляем ПОВЕРХ
фильтр по выручке из enrich.db/companies.revenue_rub. Патчим только экземпляр в
своём процессе — файлы на сервере не трогаем, каталог делят другие сессии.

Останавливаемся на очереди подтверждения (pending) — дальше ХОЛД.

  pisma_50m.py proba [N] [кампания]  — холостой: кого бы взяли, без генерации
  pisma_50m.py boy   [N] [кампания]  — боевой: генерация в очередь
"""
import json
import os
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')

REZHIM = sys.argv[1] if len(sys.argv) > 1 else 'proba'
SKOLKO = int(sys.argv[2]) if len(sys.argv) > 2 else 10
KAMPANIYA = int(sys.argv[3]) if len(sys.argv) > 3 else 10
POROG = 50_000_000
ZHURNAL = r'C:\sender\_ops\zhurnal-50m.jsonl'

from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402

cfg = Config.load(r'C:\sender\sender.yaml', env=os.environ)


def klyuch(k, po_umolchaniyu):
    """cfg.get без ключа бросает ConfigError — здесь нужен мягкий дефолт."""
    try:
        return cfg.get(k, po_umolchaniyu) or po_umolchaniyu
    except Exception:  # noqa: BLE001
        return po_umolchaniyu


db_path = klyuch('service.db_path', r'C:\sender\sender.db')
store = Store(db_path)
aq = build_ai_quota(store, cfg)

enrich_path = klyuch('service.enrich_db', r'C:\sender\enrich.db')


def vyruchka(inns):
    """ИНН -> (рубли, год, имя). Отсутствие записи не равно нулю."""
    out = {}
    if not inns:
        return out
    e = sqlite3.connect(enrich_path)
    try:
        for i in range(0, len(inns), 400):
            ch = inns[i:i + 400]
            q = ('select inn, revenue_rub, revenue_year, name from companies '
                 'where inn in (%s)' % ','.join('?' * len(ch)))
            for r in e.execute(q, ch):
                out[str(r[0])] = (r[1], r[2], r[3])
    finally:
        e.close()
    return out


ZAPAS = 1500
otbor_zhurnal = {}


def tolko_bogatye(campaign_id, limit):
    """Тот же набор гейтов, что в штатном candidates(), но выручка отсекает ДО
    гейта «не покупатель».

    Порядок важен деньгами: «не покупатель» — две линзы через провайдера на
    каждую компанию без кэшированного вердикта, замер в коде ~2.9 с на штуку.
    В штатном порядке он судил бы сотни компаний, из которых мы бы потом
    выбросили те, что мельче 50 млн. Здесь он судит окно из limit*2 уже
    отфильтрованных — то есть примерно двадцать вместо четырёхсот.

    Внутри окна порядок штатный: сначала накал новостного повода (для того он и
    считается), выручка — вторым ключом.
    """
    seg = aq._segment(campaign_id)
    used = aq._already(campaign_id)

    pool = aq._kandidaty_po_gruppe(seg, used, ZAPAS, campaign_id=campaign_id)
    bylo = len(pool)

    netselevye = aq._nontarget_inns([r.inn for r in pool if r.inn])
    pool = [r for r in pool if str(r.inn) not in netselevye]

    mertvye = aq._dead_addresses([r.email for r in pool if r.email])
    pool = [r for r in pool if (r.email or '').strip().lower() not in mertvye]

    v_stope = aq._v_stop_liste(pool)
    pool = [r for r in pool if r.id not in v_stope]

    inns = {r.id: ''.join(c for c in str(getattr(r, 'inn', '') or '') if c.isdigit())
            for r in pool}
    rev = vyruchka(sorted({i for i in inns.values() if i}))
    bogatye, bez_dannyh, melkie = [], 0, 0
    for r in pool:
        v = rev.get(inns[r.id])
        if not v or not isinstance(v[0], (int, float)):
            bez_dannyh += 1          # нет записи о выручке — это не «ноль»
            continue
        if v[0] < POROG:
            melkie += 1
            continue
        bogatye.append(r)

    zhar = aq._hotness_map([r.inn for r in bogatye if r.inn])
    bogatye.sort(key=lambda r: (-(zhar.get(str(r.inn), 0)),
                                -(rev.get(inns[r.id])[0] or 0)))

    # ОДИН ИНН — ОДИН СЛОТ. Замер 30.08: ИНН 7705825797 занял два места из
    # десяти, причём адреса за ним стоят от разных организаций (данные в базе
    # спорные). Потолок «2 адреса на компанию» стоит дальше, на очереди, и до
    # него дело дошло бы уже после оплаченной генерации второго письма.
    po_inn, unikalnye = set(), []
    for r in bogatye:
        klyuch_inn = inns[r.id] or f'rid-{r.id}'
        if klyuch_inn in po_inn:
            continue
        po_inn.add(klyuch_inn)
        unikalnye.append(r)
    dublej = len(bogatye) - len(unikalnye)
    bogatye = unikalnye

    # Гейт «не покупатель» падает В ПРОПУСК: если провайдер не ответил (а он
    # отвечает 403, когда на кошельке пусто), _not_buyers вернёт пустое
    # множество, и внешне это неотличимо от «все проверены и все годные».
    # Поэтому считаем отдельно, скольких он судил и скольких реально снял:
    # «судил 20, снял 0» — это сигнал, что вердиктов не было вовсе.
    gotovye, okno, sdvig, sudili, snyato = [], max(1, limit * 2), 0, 0, 0
    while len(gotovye) < limit and sdvig < len(bogatye):
        chast = bogatye[sdvig:sdvig + okno]
        sdvig += len(chast)
        sudili += len(chast)
        ne_pokupateli = aq._not_buyers([r for r in chast if r.inn])
        snyato += len(ne_pokupateli)
        gotovye.extend(r for r in chast if str(r.inn) not in ne_pokupateli)
    vzyato = gotovye[:limit]

    otbor_zhurnal.update({
        'gruppa': seg, 'po_gruppe_nashli': bylo, 'zapas': ZAPAS,
        'srezal_okved': len(netselevye), 'srezal_mertvye_adresa': len(mertvye),
        'srezal_stop_list': len(v_stope),
        'bez_dannyh_o_vyruchke': bez_dannyh, 'melche_50mln': melkie,
        'ot_50mln': len(bogatye), 'srezal_dubli_po_inn': dublej,
        'gejt_ne_pokupatel_sudil': sudili, 'gejt_snyal': snyato,
        'vzyato': len(vzyato),
        'vzyatye': [{'rid': r.id, 'inn': r.inn, 'email': r.email,
                     'company': (r.company_name or '')[:44],
                     'mln': round((rev.get(inns[r.id])[0] or 0) / 1e6),
                     'god': rev.get(inns[r.id])[1],
                     'nakal': zhar.get(str(r.inn), 0)} for r in vzyato],
    })
    return vzyato


aq.candidates = tolko_bogatye

if REZHIM == 'proba':
    vzyali = tolko_bogatye(KAMPANIYA, SKOLKO)
    print('=== ХОЛОСТОЙ ПРОГОН, генерации не было ===')
    print(json.dumps(otbor_zhurnal, ensure_ascii=False, indent=1))
    sys.exit(0)

# боевой: квота = уже сгенерённое сегодня + SKOLKO, чтобы получить ровно SKOLKO новых
den = aq.today()
bylo_ok, bylo_brak = aq.counters(KAMPANIYA, [den]).get(den, (0, 0))
nachalo = time.time()
res = aq.run_today(KAMPANIYA, today=den, quota=bylo_ok + bylo_brak + SKOLKO)

svod = {'rezhim': 'boy', 'kampaniya': KAMPANIYA, 'den': den,
        'bylo_do': bylo_ok + bylo_brak, 'kvota': res.quota,
        'kandidatov': res.candidates, 'zaplanirovano': res.planned,
        'ok': getattr(res, 'ok', None), 'brak': getattr(res, 'brak', None),
        'prichina': getattr(res, 'reason', None),
        'sekund': round(time.time() - nachalo, 1), 'otbor': otbor_zhurnal}
try:
    with open(ZHURNAL, 'a', encoding='utf-8') as f:
        f.write(json.dumps(svod, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
except Exception as ex:  # noqa: BLE001
    svod['zhurnal_err'] = str(ex)[:200]

# что реально легло в очередь
s = sqlite3.connect(db_path)
svod['v_ocheredi_pending'] = s.execute(
    'select count(*) from confirm_reviews where campaign_id=? and status="pending"',
    (KAMPANIYA,)).fetchone()[0]
svod['svezhie'] = [
    {'id': r[0], 'email': r[1], 'subject': (r[2] or '')[:70], 'status': r[3]}
    for r in s.execute(
        'select id, email, subject, status from confirm_reviews '
        'where campaign_id=? order by id desc limit ?', (KAMPANIYA, SKOLKO))]

print('=== ИТОГ ===')
print(json.dumps(svod, ensure_ascii=False, indent=1))
