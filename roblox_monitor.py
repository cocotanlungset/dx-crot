#!/usr/bin/env python3
"""
Roblox Process Monitor - Discord Webhook
Support Android Root (Termux + su)
"""

import os
import sys
import time
import datetime
import platform
import subprocess
import requests
import psutil

# ─────────────────────────────────────────
#  KONFIGURASI
# ─────────────────────────────────────────
INTERVAL_SECONDS = 60
PROCESS_NAMES    = [
    "com.roblox.client",
    "com.roblox",
    "roblox",
    "RobloxPlayerBeta",
    "RobloxPlayer",
]
BOT_NAME     = "Roblox Monitor"
BOT_AVATAR   = "https://i.imgur.com/4M34hi2.png"
FOOTER_TEXT  = "Roblox Monitor • Powered by Python"

COLOR_GREEN  = 0x57F287
COLOR_RED    = 0xED4245

process_start_times = {}


def clear():
    os.system("cls" if platform.system() == "Windows" else "clear")


def format_uptime(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"


def get_temp() -> str:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return f"{int(f.read().strip()) / 1000:.1f}°C"
    except Exception:
        pass
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for key in ["cpu_thermal", "coretemp", "k10temp", "acpitz", "cpu-thermal"]:
                if key in temps:
                    return f"{temps[key][0].current:.1f}°C"
            first = next(iter(temps.values()))
            return f"{first[0].current:.1f}°C"
    except Exception:
        pass
    return "N/A"


def get_system_stats() -> dict:
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    return {
        "ram_free_mb": ram.available // (1024 * 1024),
        "ram_pct"    : ram.percent,
        "cpu_pct"    : cpu,
        "temp"       : get_temp(),
    }


def find_roblox_with_su() -> list:
    """Deteksi proses Roblox menggunakan su (root)"""
    found = []
    try:
        result = subprocess.run(
            ["su", "-c", "ps -e"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.splitlines()
        for line in lines:
            line_lower = line.lower()
            if any(pn.lower() in line_lower for pn in PROCESS_NAMES):
                parts = line.split()
                if len(parts) < 2:
                    continue
                try:
                    pid = int(parts[1])
                except ValueError:
                    try:
                        pid = int(parts[0])
                    except ValueError:
                        continue

                pname = parts[-1]

                if pid not in process_start_times:
                    process_start_times[pid] = time.time()
                uptime_sec = time.time() - process_start_times[pid]

                # Ambil memory via /proc/<pid>/status
                mem_mb = 0
                try:
                    mem_result = subprocess.run(
                        ["su", "-c", f"cat /proc/{pid}/status"],
                        capture_output=True, text=True, timeout=5
                    )
                    for mline in mem_result.stdout.splitlines():
                        if mline.startswith("VmRSS:"):
                            mem_kb = int(mline.split()[1])
                            mem_mb = mem_kb // 1024
                            break
                except Exception:
                    pass

                found.append({
                    "pid"       : pid,
                    "name"      : pname,
                    "uptime_sec": uptime_sec,
                    "mem_mb"    : mem_mb,
                    "cpu_pct"   : 0.0,
                })
    except Exception as e:
        print(f"  ⚠️  su error: {e}")
    return found


def find_roblox_processes() -> list:
    """Coba psutil dulu, fallback ke su jika tidak ada hasil"""
    found = []
    for proc in psutil.process_iter(["pid", "name", "create_time", "memory_info", "cpu_percent"]):
        try:
            pname = proc.info["name"] or ""
            if any(rn.lower() in pname.lower() for rn in PROCESS_NAMES):
                pid = proc.info["pid"]
                if pid not in process_start_times:
                    process_start_times[pid] = proc.info["create_time"]
                uptime_sec = time.time() - process_start_times[pid]
                mem_mb     = proc.info["memory_info"].rss // (1024 * 1024)
                cpu_pct    = proc.cpu_percent(interval=0.1)
                found.append({
                    "pid"       : pid,
                    "name"      : pname,
                    "uptime_sec": uptime_sec,
                    "mem_mb"    : mem_mb,
                    "cpu_pct"   : cpu_pct,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not found:
        found = find_roblox_with_su()
    return found


def print_terminal(stats: dict, procs: list, online: int, webhook_url: str):
    clear()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 55)
    print(f"  🎮  ROBLOX MONITOR  |  {now}")
    print("=" * 55)
    print(f"  💾  RAM Free : {stats['ram_free_mb']} MB  ({100 - stats['ram_pct']:.0f}% free)")
    print(f"  ⚙️   CPU      : {stats['cpu_pct']}%")
    print(f"  🌡️   Temp     : {stats['temp']}")
    print("-" * 55)
    print(f"  🟢  Online   : {online}")
    print(f"  🔴  Offline  : 0")
    print(f"  🤖  Total    : {online}")
    print("-" * 55)
    if procs:
        print("  APPLICATION DETAILS")
        for i, p in enumerate(procs, 1):
            print(f"  [{i}] PID:{p['pid']}  ⏱ {format_uptime(p['uptime_sec'])}"
                  f"  💾 {p['mem_mb']} MB  ⚙️ {p['cpu_pct']:.1f}%")
    else:
        print("  Tidak ada proses Roblox yang berjalan.")
    print("-" * 55)
    print(f"  🔗  Webhook  : {webhook_url[:40]}...")
    print(f"  ⏳  Next update dalam {INTERVAL_SECONDS} detik...")
    print("=" * 55)


def build_embed(stats: dict, procs: list, online: int) -> dict:
    now_str = datetime.datetime.now().strftime("Today at %I:%M %p")
    color   = COLOR_GREEN if online > 0 else COLOR_RED

    sys_val = (
        f"🖥️ RAM: {stats['ram_free_mb']}MB free ({100 - stats['ram_pct']:.0f}%)\n"
        f"⚙️ CPU: {stats['cpu_pct']}%\n"
        f"🌡️ Temp: {stats['temp']}"
    )
    status_val = (
        f"🟢 Online: {online}\n"
        f"🔴 Offline: 0\n"
        f"🤖 Total: {online}"
    )

    if procs:
        app_lines = []
        for p in procs:
            line = (
                f"🟢 `{p['name'][-20:]}`  "
                f"⏱ {format_uptime(p['uptime_sec'])}  "
                f"💾 {p['mem_mb']} MB  "
                f"⚙️ {p['cpu_pct']:.1f}%"
            )
            app_lines.append(line)
        app_val = "\n".join(app_lines)
    else:
        app_val = "❌ Tidak ada proses Roblox berjalan."

    return {
        "title" : "🎮 Roblox Monitor",
        "color" : color,
        "fields": [
            {"name": "📊 System Stats",        "value": sys_val,    "inline": False},
            {"name": "📡 Status Overview",     "value": status_val, "inline": False},
            {"name": "📋 Application Details", "value": app_val,    "inline": False},
        ],
        "footer"   : {"text": f"{FOOTER_TEXT} • {now_str}"},
        "timestamp": datetime.datetime.utcnow().isoformat()
    }


def send_to_discord(webhook_url: str, embed: dict):
    payload = {
        "username"  : BOT_NAME,
        "avatar_url": BOT_AVATAR,
        "embeds"    : [embed],
    }
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code in (200, 204):
            print(f"  ✅  Berhasil dikirim ke Discord!")
        else:
            print(f"  ⚠️  Discord error: {r.status_code} - {r.text[:100]}")
    except requests.exceptions.RequestException as e:
        print(f"  ❌  Gagal kirim ke Discord: {e}")


def validate_webhook(url: str) -> bool:
    if not ("discord.com/api/webhooks/" in url or "discordapp.com/api/webhooks/" in url):
        return False
    try:
        r = requests.get(url, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def main():
    clear()
    print("=" * 55)
    print("  🎮  ROBLOX MONITOR - Setup")
    print("=" * 55)
    print()

    while True:
        webhook_url = input("  Masukkan Discord Webhook URL:\n  > ").strip()
        if not webhook_url:
            print("  ❌  URL tidak boleh kosong!\n")
            continue
        print("  🔍  Memvalidasi webhook...")
        if validate_webhook(webhook_url):
            print("  ✅  Webhook valid!\n")
            break
        else:
            print("  ❌  Webhook tidak valid atau tidak bisa dijangkau.")
            retry = input("  Coba lagi? (y/n): ").strip().lower()
            if retry != "y":
                sys.exit(0)

    print(f"  ⏱️  Interval update : {INTERVAL_SECONDS} detik")
    print(f"  🔍  Memantau proses : {', '.join(PROCESS_NAMES)}")
    print(f"  🔑  Mode root (su)  : Aktif")
    print("  🚀  Monitoring dimulai! Tekan Ctrl+C untuk berhenti.\n")
    time.sleep(2)

    while True:
        try:
            stats  = get_system_stats()
            procs  = find_roblox_processes()
            online = len(procs)

            print_terminal(stats, procs, online, webhook_url)
            embed = build_embed(stats, procs, online)
            send_to_discord(webhook_url, embed)

            time.sleep(INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n\n  👋  Monitor dihentikan. Sampai jumpa!")
            sys.exit(0)
        except Exception as e:
            print(f"\n  ⚠️  Error: {e}")
            print(f"  🔄  Retry dalam 10 detik...")
            time.sleep(10)


if __name__ == "__main__":
    missing = []
    try:
        import psutil
    except ImportError:
        missing.append("psutil")
    try:
        import requests
    except ImportError:
        missing.append("requests")

    if missing:
        print("❌  Library belum terinstall:")
        for lib in missing:
            print(f"   - {lib}")
        print(f"\n   pip install {' '.join(missing)}")
        sys.exit(1)

    main()
