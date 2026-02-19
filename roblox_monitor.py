#!/usr/bin/env python3
"""
Roblox Process Monitor - Discord Webhook
Monitoring Roblox instances dan kirim ke Discord
"""

import os
import sys
import time
import datetime
import platform
import requests
import psutil

# ─────────────────────────────────────────
#  KONFIGURASI
# ─────────────────────────────────────────
INTERVAL_SECONDS = 60        # Interval kirim ke Discord (detik)
PROCESS_NAMES    = [         # Nama proses Roblox yang dicari
    "RobloxPlayerBeta",
    "RobloxPlayer",
    "Roblox",
    "roblox",
    "wine",                  # Untuk Roblox via Wine di Linux
]
BOT_NAME         = "Roblox Monitor"
BOT_AVATAR       = "https://i.imgur.com/4M34hi2.png"
FOOTER_TEXT      = "Roblox Monitor • Powered by Python"

# ─────────────────────────────────────────
#  WARNA EMBED DISCORD
# ─────────────────────────────────────────
COLOR_GREEN  = 0x57F287  # Online
COLOR_RED    = 0xED4245  # Offline
COLOR_YELLOW = 0xFEE75C  # Warning

# ─────────────────────────────────────────
#  SIMPAN WAKTU START TIAP PROSES
# ─────────────────────────────────────────
process_start_times = {}


def clear():
    os.system("cls" if platform.system() == "Windows" else "clear")


def format_uptime(seconds: float) -> str:
    """Format detik ke Xh Ym"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"


def get_temp() -> str:
    """Ambil suhu CPU (Linux/Termux)"""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return "N/A"
        for key in ["cpu_thermal", "coretemp", "k10temp", "acpitz", "cpu-thermal"]:
            if key in temps:
                return f"{temps[key][0].current:.1f}°C"
        # Ambil yang pertama tersedia
        first = next(iter(temps.values()))
        return f"{first[0].current:.1f}°C"
    except Exception:
        # Coba baca langsung dari file (Termux/Android)
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return f"{int(f.read().strip()) / 1000:.1f}°C"
        except Exception:
            return "N/A"


def get_system_stats() -> dict:
    """Ambil statistik sistem"""
    ram    = psutil.virtual_memory()
    cpu    = psutil.cpu_percent(interval=1)
    temp   = get_temp()
    ram_free_mb = ram.available // (1024 * 1024)
    ram_pct     = ram.percent
    return {
        "ram_free_mb": ram_free_mb,
        "ram_pct"    : ram_pct,
        "cpu_pct"    : cpu,
        "temp"       : temp,
    }


def find_roblox_processes() -> list:
    """Cari semua proses Roblox yang sedang berjalan"""
    found = []
    for proc in psutil.process_iter(["pid", "name", "create_time", "memory_info", "cpu_percent"]):
        try:
            pname = proc.info["name"] or ""
            if any(rn.lower() in pname.lower() for rn in PROCESS_NAMES):
                pid = proc.info["pid"]
                # Simpan waktu mulai pertama kali terdeteksi
                if pid not in process_start_times:
                    process_start_times[pid] = proc.info["create_time"]

                uptime_sec = time.time() - process_start_times[pid]
                mem_mb     = proc.info["memory_info"].rss // (1024 * 1024)
                # cpu_percent butuh 2 panggilan; pakai oneshot
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
    return found


def print_terminal(stats: dict, procs: list, online: int, webhook_url: str):
    """Tampilkan info di terminal"""
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
    """Buat Discord embed payload"""
    now_str = datetime.datetime.now().strftime("Today at %I:%M %p")
    color   = COLOR_GREEN if online > 0 else COLOR_RED

    # System Stats field
    sys_val = (
        f"🖥️ RAM: {stats['ram_free_mb']}MB free ({100 - stats['ram_pct']:.0f}%)\n"
        f"⚙️ CPU: {stats['cpu_pct']}%\n"
        f"🌡️ Temp: {stats['temp']}"
    )

    # Status Overview field
    status_val = (
        f"🟢 Online: {online}\n"
        f"🔴 Offline: 0\n"
        f"🤖 Total: {online}"
    )

    # Application Details field
    if procs:
        app_lines = []
        for p in procs:
            line = (
                f"🟢 `{p['name'][:15]}`  "
                f"⏱ {format_uptime(p['uptime_sec'])}  "
                f"💾 {p['mem_mb']} MB  "
                f"⚙️ {p['cpu_pct']:.1f}%"
            )
            app_lines.append(line)
        app_val = "\n".join(app_lines)
    else:
        app_val = "❌ Tidak ada proses Roblox berjalan."

    embed = {
        "title" : "🎮 Roblox Monitor",
        "color" : color,
        "fields": [
            {"name": "📊 System Stats",       "value": sys_val,    "inline": False},
            {"name": "📡 Status Overview",    "value": status_val, "inline": False},
            {"name": "📋 Application Details","value": app_val,    "inline": False},
        ],
        "footer": {
            "text": f"{FOOTER_TEXT} • {now_str}"
        },
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
    return embed


def send_to_discord(webhook_url: str, embed: dict):
    """Kirim embed ke Discord webhook"""
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
    """Validasi URL webhook Discord"""
    if not url.startswith("https://discord.com/api/webhooks/") and \
       not url.startswith("https://discordapp.com/api/webhooks/"):
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

    # Input webhook URL
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
                print("  Keluar...")
                sys.exit(0)

    print(f"  ⏱️  Interval update : {INTERVAL_SECONDS} detik")
    print(f"  🔍  Memantau proses : {', '.join(PROCESS_NAMES)}")
    print("  🚀  Monitoring dimulai! Tekan Ctrl+C untuk berhenti.\n")
    time.sleep(2)

    # Loop utama
    while True:
        try:
            stats  = get_system_stats()
            procs  = find_roblox_processes()
            online = len(procs)

            # Tampil di terminal
            print_terminal(stats, procs, online, webhook_url)

            # Kirim ke Discord
            embed = build_embed(stats, procs, online)
            send_to_discord(webhook_url, embed)

            # Tunggu interval
            time.sleep(INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n\n  👋  Monitor dihentikan. Sampai jumpa!")
            sys.exit(0)
        except Exception as e:
            print(f"\n  ⚠️  Error tak terduga: {e}")
            print(f"  🔄  Coba lagi dalam 10 detik...")
            time.sleep(10)


if __name__ == "__main__":
    # Cek dependensi
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
        print("❌  Library berikut belum terinstall:")
        for lib in missing:
            print(f"   - {lib}")
        print("\nInstall dengan perintah:")
        print(f"   pip install {' '.join(missing)}")
        print("\nUntuk Termux:")
        print(f"   pip install {' '.join(missing)}")
        sys.exit(1)

    main()
