// Кубик-ДИСПЕТЧЕР ZennoPoster 7.9: запуск и остановка задач по файлу-команде.
//
// Зачем: чтобы Зенку запускал не оператор руками, а тот, кто увидел работу — скрипт
// на сервере кладёт строку в файл, диспетчер её выполняет. Владелец 13.08: «а ты не
// можешь запускать? или сделать настройки которые будут запускать её при определённых
// событиях».
//
// Почему именно так, а не по HTTP: внешнего API у ZennoPoster нет — порты 1000/1001/
// 5001/6001/6002 закрыты, TasksRunner.exe ключей не принимает, а OutputTaskLocalhostPort
// это ВЫВОД результата, а не приём заданий. Зато ИЗНУТРИ проекта доступен весь
// ZennoLab.CommandCenter.ZennoPoster (проверено по документации ZennoLab.CommandCenter.xml):
//   ZennoPoster.TasksList                  — список задач в xml
//   ZennoPoster.StartTask(name|id)         — запустить
//   ZennoPoster.StopTask(name|id)          — остановить
//   ZennoPoster.InterruptTask(name|id)     — прервать немедленно
//   ZennoPoster.SetMaxThreads(name|id, N)  — сколько потоков
//   ZennoPoster.GetThreadsCount(name)      — сколько сейчас крутится
// Значит достаточно одной ВЕЧНО ВИСЯЩЕЙ задачи-диспетчера, и весь остальной запуск идёт
// через файл.
//
// КАК ПОСТАВИТЬ (один раз):
//   1. Новый проект в ProjectMaker, один кубик C# — этот код. Браузер не нужен.
//   2. Сохранить как C:\seostat\drop\zenno\dispetcher.xmlz и добавить задачей в
//      ZennoPoster с именем «Dispetcher».
//   3. Потоков — 1. Повтор выполнения — бесконечно (кубик сам спит между кругами).
//   4. Запустить. Дальше не трогать: всё управление идёт файлом.
//
// ФАЙЛ КОМАНД: C:\seostat\drop\zenno\komanda.txt (по строке на команду, # — коммент)
//   pusk <задача> [потоков]   запустить задачу (и сразу выставить потоки)
//   stop <задача>             остановить мягко
//   sbros <задача>            прервать немедленно
//   potoki <задача> <N>       только сменить число потоков
//   spisok                    выписать все задачи в состояние
// Разобранные строки уходят в vypolneno.txt, файл команд очищается — повтора не будет.
//
// ОТВЕТ: C:\seostat\drop\zenno\dispetcher.json — состояние задач (имя, id, потоков
// сейчас, включена ли) плюс отчёт по последним командам. Пишется КАЖДЫЙ круг, поэтому
// по нему же видно, что диспетчер жив.

var bez_bom = new System.Text.UTF8Encoding(false);   // BOM ломает чтение из питона

Func<string, string, string> nastroyka = delegate(string imya, string po_umolchaniyu)
{
    try
    {
        string v = project.Variables[imya].Value;
        if (!string.IsNullOrEmpty(v)) return v;
    }
    catch { }        // переменной в проекте нет — штатный случай
    return po_umolchaniyu;
};

string koren = nastroyka("papka_obmena", @"C:\seostat\drop\zenno");
System.IO.Directory.CreateDirectory(koren);
string fajl_komand = System.IO.Path.Combine(koren, "komanda.txt");
string fajl_vypolneno = System.IO.Path.Combine(koren, "vypolneno.txt");
string fajl_sostoyaniya = System.IO.Path.Combine(koren, "dispetcher.json");

int krugov = int.Parse(nastroyka("krugov", "60"));        // кругов за одно выполнение
int pauza_sek = int.Parse(nastroyka("pauza_sek", "10"));  // сколько спать между кругами

// --- мелкая помощь --------------------------------------------------------------
Func<string, string, string> iz_xml = delegate(string xml, string teg)
{
    // без XmlDocument: в списке задач попадаются поля с не-xml символами, а нам нужны
    // ровно два значения — имя и id
    string o = "<" + teg + ">", z = "</" + teg + ">";
    int a = xml.IndexOf(o, StringComparison.OrdinalIgnoreCase);
    if (a < 0) return "";
    a += o.Length;
    int b = xml.IndexOf(z, a, StringComparison.OrdinalIgnoreCase);
    return b < 0 ? "" : xml.Substring(a, b - a).Trim();
};

Func<string, string> ekran = delegate(string s)
{
    if (s == null) return "";
    return s.Replace("\\", "\\\\").Replace("\"", "\\\"")
            .Replace("\r", " ").Replace("\n", " ").Replace("\t", " ");
};

// список задач: имя -> id, плюс сколько потоков сейчас крутится
Func<List<string>> zadachi = delegate()
{
    var vyshlo = new List<string>();
    try
    {
        foreach (var syroe in ZennoPoster.TasksList)
        {
            string xml = syroe == null ? "" : syroe.ToString();
            string imya = iz_xml(xml, "Name");
            string id = iz_xml(xml, "Id");
            if (imya == "") continue;
            int potokov = -1;
            try { potokov = ZennoPoster.GetThreadsCount(imya); }
            catch { }
            vyshlo.Add("{\"imya\":\"" + ekran(imya) + "\",\"id\":\"" + ekran(id)
                       + "\",\"potokov_seychas\":" + potokov.ToString() + "}");
        }
    }
    catch (Exception e)
    {
        vyshlo.Add("{\"oshibka\":\"" + ekran(e.Message) + "\"}");
    }
    return vyshlo;
};

// --- один круг ------------------------------------------------------------------
Func<List<string>> krug = delegate()
{
    var otchet = new List<string>();
    string[] stroki = new string[0];

    // читаем и СРАЗУ очищаем под общим замком: иначе при повторе выполнится дважды
    lock (SyncObjects.ListSyncer)
    {
        try
        {
            if (System.IO.File.Exists(fajl_komand))
            {
                stroki = System.IO.File.ReadAllLines(fajl_komand, System.Text.Encoding.UTF8);
                System.IO.File.WriteAllText(fajl_komand, "", bez_bom);
            }
        }
        catch (Exception e) { otchet.Add("файл команд не прочитан: " + e.Message); }
    }

    foreach (var syraya in stroki)
    {
        string s = (syraya ?? "").Trim();
        if (s == "" || s.StartsWith("#")) continue;

        var ch = s.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
        string cmd = ch[0].ToLower();
        string zadacha = ch.Length > 1 ? ch[1] : "";
        string itog;
        try
        {
            if (cmd == "spisok")
            {
                itog = "ok";
            }
            else if (zadacha == "")
            {
                itog = "не указана задача";
            }
            else if (cmd == "pusk")
            {
                if (ch.Length > 2)
                {
                    int n;
                    if (int.TryParse(ch[2], out n) && n > 0)
                        ZennoPoster.SetMaxThreads(zadacha, n);
                }
                ZennoPoster.StartTask(zadacha);
                itog = "ok";
            }
            else if (cmd == "stop")
            {
                ZennoPoster.StopTask(zadacha);
                itog = "ok";
            }
            else if (cmd == "sbros")
            {
                ZennoPoster.InterruptTask(zadacha);
                itog = "ok";
            }
            else if (cmd == "potoki")
            {
                int n;
                if (ch.Length > 2 && int.TryParse(ch[2], out n) && n > 0)
                {
                    ZennoPoster.SetMaxThreads(zadacha, n);
                    itog = "ok";
                }
                else itog = "не указано число потоков";
            }
            else
            {
                itog = "неизвестная команда";
            }
        }
        catch (Exception e)
        {
            // имя задачи ищется по первому совпадению: не нашлось — так и пишем,
            // чтобы не гадать по пустому логу
            itog = "ошибка: " + e.Message;
        }

        otchet.Add("{\"komanda\":\"" + ekran(s) + "\",\"itog\":\"" + ekran(itog) + "\"}");
        project.SendInfoToLog("диспетчер: " + s + " -> " + itog, true);

        lock (SyncObjects.ListSyncer)
        {
            try
            {
                System.IO.File.AppendAllText(
                    fajl_vypolneno,
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "\t" + s + "\t" + itog
                    + Environment.NewLine, bez_bom);
            }
            catch { }
        }
    }
    return otchet;
};

// --- работа ---------------------------------------------------------------------
var poslednee = new List<string>();
for (int i = 0; i < krugov; i++)
{
    var otchet = krug();
    if (otchet.Count > 0) poslednee = otchet;

    // состояние пишем КАЖДЫЙ круг: по времени файла видно, что диспетчер жив,
    // а по списку — что вообще есть в ZennoPoster и сколько потоков крутится
    var sost = new List<string>();
    sost.Add("\"vremya\":\"" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "\"");
    // раздельными числами, а не "1/60": дробь через слэш — не JSON, и питон
    // валился на разборе ответа (поймано сразу после установки диспетчера)
    sost.Add("\"krug\":" + (i + 1).ToString());
    sost.Add("\"krugov\":" + krugov.ToString());
    sost.Add("\"zadachi\":[" + string.Join(",", zadachi().ToArray()) + "]");
    sost.Add("\"poslednie_komandy\":[" + string.Join(",", poslednee.ToArray()) + "]");
    try
    {
        lock (SyncObjects.ListSyncer)
            System.IO.File.WriteAllText(fajl_sostoyaniya,
                                        "{" + string.Join(",", sost.ToArray()) + "}", bez_bom);
    }
    catch { }

    if (i + 1 < krugov) System.Threading.Thread.Sleep(pauza_sek * 1000);
}

return "диспетчер отработал круг";
