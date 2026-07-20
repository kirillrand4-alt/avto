# -*- coding: utf-8 -*-
"""Сборка SENDER-ARCHITECTURE.md из module-docs.json + провайдерский синтез
анализа ПЕРЕСЕЧЕНИЙ модулей (нужны ли, что дублируется). Запускать после
gen_module_docs.py."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
import gen_provider

DIR = os.path.dirname(os.path.abspath(__file__))
docs = json.load(open(os.path.join(DIR, 'module-docs.json'), encoding='utf-8'))
by = {d['module']: d for d in docs}

# группировка по слоям (для читаемости документа)
LAYERS = [
 ('Ядро данных и конфиг', ['config','store','dtos','errors']),
 ('Приём и подготовка получателей', ['importer','validation','suppression','personalize']),
 ('Отправка', ['sender','cadence','gates','warmup']),
 ('Входящие и автоответчик', ['imap_watcher','reply_classify','autoresponder','review_lenses','review_chain']),
 ('Интеграции наружу', ['bitrix','leaddesk','notify','postoffice','tracking','unsub','unsub_server']),
 ('Оркестрация и интерфейсы', ['orchestrator','analytics','dns','auth','cli']),
]
placed = {m for _, ms in LAYERS for m in ms}
extra = [d['module'] for d in docs if d['module'] not in placed]
if extra:
    LAYERS.append(('Прочее', extra))

# --- провайдерский синтез пересечений ---
summ = []
for d in docs:
    if 'error' in d: continue
    summ.append(f"### {d['module']}\nназначение: {d.get('one_line','')}\n"
                f"обязанности: {'; '.join(d.get('responsibilities',[])[:6])}\n"
                f"источники: {'; '.join(d.get('data_sources',[])[:6])}\n"
                f"БД: {'; '.join(d.get('db_touchpoints',[])[:6])}\n"
                f"зависит от: {', '.join(d.get('depends_on',[]))}\n"
                f"пересечения(само): {'; '.join(d.get('overlaps',[]))}")
OVL_PROMPT = ("Ты — архитектор. Ниже сводки всех модулей системы холодной рассылки. "
 "Найди РЕАЛЬНЫЕ пересечения/дублирование логики между модулями и оцени, нужны ли "
 "они как отдельные модули или это дубли. Особое внимание: не дублируют ли друг друга "
 "прогрев(warmup) и рассыльщик(sender); cadence и orchestrator (планирование); "
 "gates и warmup (оценка здоровья/репутации); лимиты отправки (sender.can_send_now / "
 "warmup ramp / gates). Для КАЖДОГО найденного пересечения верни: модули, что именно "
 "пересекается, вердикт (ОК-разделение / СЛИЯНИЕ / РЕФАКТОР / ДУБЛЬ-УДАЛИТЬ) и почему.\n\n"
 "Верни СТРОГО JSON без markdown: {\"overlaps\":[{\"modules\":[...],\"what\":\"...\","
 "\"verdict\":\"ОК|СЛИЯНИЕ|РЕФАКТОР|ДУБЛЬ\",\"why\":\"...\"}],"
 "\"summary\":\"общий вывод: есть ли лишние модули\"}\n\n=== СВОДКИ ===\n" + "\n\n".join(summ))

def find_json(raw):
    s,depth,instr,esc=-1,0,False,False
    for i,ch in enumerate(raw):
        if s==-1:
            if ch=='{': s,depth=i,1
            continue
        if instr:
            if esc:esc=False
            elif ch=='\\':esc=True
            elif ch=='"':instr=False
            continue
        if ch=='"':instr=True
        elif ch=='{':depth+=1
        elif ch=='}':
            depth-=1
            if depth==0:return raw[s:i+1]
    return None

overlap = {'overlaps': [], 'summary': ''}
for a in range(4):
    try:
        msg = gen_provider._raw_stream([{'role':'user','content':OVL_PROMPT}],'claude-fable-5',3000,thinking=False)
        t=''.join(b.text for b in msg.content if getattr(b,'type','')=='text')
        overlap = json.loads(find_json(t)); break
    except Exception as ex:
        if a==3: print('overlap synth failed:', ex, file=sys.stderr)
json.dump(overlap, open(os.path.join(DIR,'overlap-analysis.json'),'w'), ensure_ascii=False, indent=1)

# --- сборка markdown ---
def esc(s): return str(s).replace('|','\\|')
out = []
out.append("# SENDER-ARCHITECTURE — как работает система холодной рассылки\n")
out.append("Автодокументация всех модулей `seo-texts/sender/` (провайдер claude-fable-5) "
           "+ ручная верификация ключевых узлов. Что делает, ОТКУДА берёт данные, логика "
           "обработки, где трогает БД, пересечения модулей.\n")
ok = sum(1 for d in docs if 'error' not in d)
out.append(f"**Покрытие: {ok}/{len(docs)} модулей.** Единый писатель в БД (SQLite) — "
           "`store.py`; остальные ходят в БД только через него.\n")

out.append("## Поток данных (tick-цикл оркестратора)\n")
out.append("```\nrecover_stale → IMAP poll (reply/bounce) → gates (kill-switch) →\n"
           "cadence.plan_campaign → enqueue → claim_due → personalize.render →\n"
           "sender.pick_mailbox → sender.send → warmup.run_cycle → TickResult\n```\n")

for title, mods in LAYERS:
    out.append(f"\n## Слой: {title}\n")
    for m in mods:
        d = by.get(m)
        if not d:
            continue
        if 'error' in d:
            out.append(f"### `{m}` ({d.get('_lines','?')} строк)\n_ошибка автодоку: {d['error']}_\n")
            continue
        out.append(f"### `{m}.py` ({d.get('_lines','?')} строк)")
        out.append(f"**{d.get('one_line','')}**\n")
        if d.get('responsibilities'):
            out.append("- Обязанности: " + "; ".join(d['responsibilities'][:7]))
        if d.get('data_sources'):
            out.append("- **Источники данных:** " + "; ".join(d['data_sources'][:8]))
        if d.get('processing_logic'):
            out.append("- Логика обработки: " + "; ".join(d['processing_logic'][:8]))
        if d.get('db_touchpoints'):
            out.append("- **БД (через store):** " + "; ".join(d['db_touchpoints'][:8]))
        if d.get('external_io'):
            out.append("- Наружу (I/O): " + "; ".join(d['external_io'][:6]))
        if d.get('public_api'):
            out.append("- Публичный API: " + ", ".join(d['public_api'][:8]))
        if d.get('depends_on'):
            out.append("- Зависит от: " + ", ".join(d['depends_on']))
        out.append("")

# карта «где используется обработка из базы обзвона/данных»
out.append("\n## Где используется обработка данных из БД\n")
for d in docs:
    if d.get('db_touchpoints'):
        out.append(f"- **{d['module']}**: " + "; ".join(d['db_touchpoints'][:5]))

# анализ пересечений
out.append("\n## Анализ пересечений модулей (нужны ли в коде)\n")
out.append(f"_Синтез: {esc(overlap.get('summary',''))}_\n")
if overlap.get('overlaps'):
    out.append("| Модули | Что пересекается | Вердикт | Почему |")
    out.append("|---|---|---|---|")
    for o in overlap['overlaps']:
        out.append(f"| {esc(', '.join(o.get('modules',[])))} | {esc(o.get('what',''))} | "
                   f"**{esc(o.get('verdict',''))}** | {esc(o.get('why',''))} |")

open(os.path.join(DIR,'SENDER-ARCHITECTURE.md'),'w').write('\n'.join(out))
print(f"SENDER-ARCHITECTURE.md собран: {ok}/{len(docs)} модулей, "
      f"{len(overlap.get('overlaps',[]))} пересечений")
