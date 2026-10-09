# Проба паспорта на 3 компаниях пилота: обход (кладёт страницы в кэш) -> site_facts.sobrat -> что в карточке
import json, os, sys, io, subprocess
код = r'''
import json, os, io, sys
os.environ["KC_NABOR"] = "pilot"; os.environ["PROVIDER_MODEL"] = "gpt-6-luna"
sys.path.insert(0, r"C:\sender\server"); sys.path.insert(0, r"C:\sender")
import kc_kontakty as KK, site_facts as SF, sqlite3
сп = json.load(io.open(r"C:\sender\server\pilot-spisok.json", encoding="utf-8"))["компании"]
выбор = [к for к in сп.values() if к.get("сайт") and к["inn"].isdigit() and к.get("сегм_как") == "основной"][:3]
for к in выбор:
    KK.обход(к, к["сайт"])
итог = SF.sobrat(predel=3, spisok=[{"inn": к["inn"], "name": к["имя"], "site": к["сайт"]} for к in выбор], potokov=3)
c = sqlite3.connect(SF.BD)
out = {"сбор": итог}
for к in выбор:
    р = c.execute("select facts_json from site_facts where inn=?", (к["inn"],)).fetchone()
    ф = json.loads(р[0]) if р and р[0] else {}
    out[к["имя"][:40] + " " + к["сайт"][:40]] = {k: (str(v)[:160]) for k, v in ф.items() if k in ("продукция","сырьё","мощности","контроль_качества","оборудование_линии","масштаб","экспорт")}
print(json.dumps(out, ensure_ascii=False, indent=0))
'''
р = subprocess.run([sys.executable, '-c', код], cwd=r'C:\sender\server', capture_output=True, text=True, timeout=1500)
print('===ИТОГ==='); print(р.stdout[-5000:], р.stderr[-1500:])
