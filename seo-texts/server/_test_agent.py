import io, json, os, sys, time
os.environ['KC_NABOR'] = 'poisk'
sys.path.insert(0, r'C:\sender\server')
import kc_agent_glubokiy as A
сп = json.load(io.open(r'C:\sender\server\poisk-spisok.json', encoding='utf-8'))['компании']
к = dict(сп['3115006100'], отклонены='miratorg.ru?')
t = time.time()
итог, открыто, история = A.агент(к)
рез = A.проверить(к, итог, открыто)
рез['журнал'] = [h[:220] for h in история]
рез['сек'] = round(time.time() - t)
print('===ИТОГ==='); print(json.dumps(рез, ensure_ascii=False, indent=1)[:6000])
