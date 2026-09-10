// ak_reestry_min.cs - МИНИМАЛЬНАЯ версия для проверки компиляции.
// Один блок "Свой код" (Own code, C#). Ничего не возвращает, переменных проекта не трогает.
// Берёт первое невыполненное задание, открывает URL, ждёт 15 секунд, сохраняет HTML.

string obmen = @"C:\seostat\drop\zenno";
string fZad = obmen + @"\ak_zadaniya.txt";
string fOtdano = obmen + @"\ak_otdano.txt";
string dGotovo = obmen + @"\ak_gotovo";

System.IO.Directory.CreateDirectory(dGotovo);

string id = "";
string url = "";

if (System.IO.File.Exists(fZad))
{
    string otdano = "";
    if (System.IO.File.Exists(fOtdano)) otdano = System.IO.File.ReadAllText(fOtdano);

    string[] stroki = System.IO.File.ReadAllLines(fZad, System.Text.Encoding.UTF8);
    for (int i = 0; i < stroki.Length; i++)
    {
        string s = stroki[i].Trim();
        if (s.Length == 0) continue;
        string[] ch = s.Split(';');
        if (ch.Length < 3) continue;
        if (otdano.Contains(ch[0].Trim() + "\r\n")) continue;
        id = ch[0].Trim();
        url = ch[2].Trim();
        System.IO.File.AppendAllText(fOtdano, id + "\r\n", System.Text.Encoding.UTF8);
        break;
    }
}

if (id.Length == 0)
{
    project.SendInfoToLog("заданий нет", true);
}
else
{
    project.SendInfoToLog("открываю " + id + " " + url, true);
    instance.ActiveTab.Navigate(url, "");
    instance.ActiveTab.WaitDownloading();
    System.Threading.Thread.Sleep(15000);

    string html = instance.ActiveTab.DocumentText;
    if (html == null) html = "";
    System.IO.File.WriteAllText(dGotovo + "\\" + id + ".html", html, System.Text.Encoding.UTF8);
    project.SendInfoToLog("сохранено " + id + ", знаков " + html.Length.ToString(), true);
}
