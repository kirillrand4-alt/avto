# -*- coding: utf-8 -*-
"""Чем управляются демоны: службы, задачи расписания или запущены руками.

Без этого останавливать их нельзя: поднять обратно будет нечем.
"""
import subprocess


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=120).stdout.strip()


службы = пш(
    "Get-Service | Where-Object { $_.Name -like '*ender*' -or "
    "$_.Name -like '*nrich*' -or $_.Name -like '*job*' -or "
    "$_.Name -like '*fakt*' -or $_.Name -like '*zenno*' -or "
    "$_.DisplayName -like '*sender*' } | "
    "ForEach-Object { \"$($_.Name) = $($_.Status)  [$($_.DisplayName)]\" }")

задачи = пш(
    "Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' } | "
    "ForEach-Object { "
    "  $д = ($_.Actions | ForEach-Object { \"$($_.Execute) $($_.Arguments)\" })"
    " -join ' ; '; "
    "  if ($д -match 'job_runner|enrich_panel|fakty_cikl|zenno_most|sender') "
    "    { \"$($_.TaskName) = $($_.State) :: $д\" } }")

# у кого какой родитель — руками запущенное висит на explorer/cmd
родители = пш(
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Where-Object { $_.CommandLine -like '*job_runner*' -or "
    "$_.CommandLine -like '*enrich_panel*' -or "
    "$_.CommandLine -like '*fakty_cikl*' -or "
    "$_.CommandLine -like '*zenno_most*' -or "
    "$_.CommandLine -like '*serve-api*' } | ForEach-Object { "
    "  $р = (Get-CimInstance Win32_Process -Filter "
    "\"ProcessId=$($_.ParentProcessId)\" -ErrorAction SilentlyContinue); "
    "  \"$($_.ProcessId)|родитель $($_.ParentProcessId) "
    "$(if($р){$р.Name}else{'нет'})|\" + "
    "$_.CommandLine.Substring(0,[Math]::Min(70,$_.CommandLine.Length)) }")

print("=" * 70)
print("=== СВОДКА: ЧЕМ УПРАВЛЯЮТСЯ ДЕМОНЫ ===")
print("СЛУЖБЫ:")
for с in (службы or "   ни одной подходящей").splitlines():
    print("   " + с[:120])
print("")
print("ЗАДАЧИ РАСПИСАНИЯ, поднимающие эти процессы:")
for с in (задачи or "   ни одной").splitlines():
    print("   " + с[:150])
print("")
print("ПРОЦЕССЫ И ИХ РОДИТЕЛИ (родитель services.exe = служба;")
print("explorer/cmd/powershell = запущен руками):")
for с in (родители or "   нет").splitlines():
    print("   " + с[:130])
