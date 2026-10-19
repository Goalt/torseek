"""Generate torrseek/fixtures/torrents.json (deterministic, legal content only).

Run from the repo root:  python3 tools/gen_fixtures.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from torrseek.torrentfile import build_info, infohash  # noqa: E402

rng = random.Random(20261019)
GB = 1024**3
MB = 1024**2
records: list[dict] = []


def date_between(start: str, end: str) -> datetime:
    a = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    b = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    return a + timedelta(seconds=rng.randint(0, int((b - a).total_seconds())))


def jitter(size: float) -> int:
    return int(size * rng.uniform(0.93, 1.07))


def add(title, category, files, description, when, popularity=1.0, name=None):
    m = re.search(r"(20\d\d)[-.]?(\d\d)[-.]?(\d\d)?", title)
    if m and category in ("dataset", "books", "linux"):  # dated title: upload right after it
        y, mo, d = int(m[1]), int(m[2]), int(m[3] or 1)
        if 1 <= mo <= 12 and 1 <= d <= 31:
            when = datetime(y, mo, d, tzinfo=timezone.utc) + timedelta(hours=rng.randint(2, 60))
    seeders = int(rng.paretovariate(1.2) * 15 * popularity)
    leechers = int(seeders * rng.uniform(0.02, 0.6)) + rng.randint(0, 5)
    if name is None:
        name = files[0][0].split("/")[0] if len(files) > 1 or "/" in files[0][0] else files[0][0]
    rec = {
        "id": f"t{len(records) + 1:04d}",
        "title": title,
        "name": name,
        "size_bytes": sum(s for _, s in files),
        "seeders": seeders,
        "leechers": leechers,
        "category": category,
        "uploaded_at": when.isoformat(),
        "description": description,
        "files": [{"path": p, "size_bytes": s} for p, s in files],
    }
    rec["infohash"] = infohash(build_info(rec))
    records.append(rec)


def iso(title, category, filename, size, desc, when, pop=1.0, checksum=True):
    files = [(filename, jitter(size))]
    if checksum:
        folder = filename.rsplit(".", 1)[0]
        files = [(f"{folder}/{filename}", files[0][1]), (f"{folder}/SHA256SUMS", 104)]
    add(title, category, files, desc, when, pop)


# ---------------------------------------------------------------- linux
distros = [
    # (title, filename, size_gb, release_date, popularity, description)
    ("Ubuntu 24.04.3 LTS Desktop amd64", "ubuntu-24.04.3-desktop-amd64.iso", 5.9, "2025-08-07", 9, "Ubuntu long-term support release, desktop image with GNOME."),
    ("Ubuntu 24.04.3 LTS Server amd64", "ubuntu-24.04.3-live-server-amd64.iso", 3.1, "2025-08-07", 5, "Ubuntu Server live installer, LTS."),
    ("Ubuntu 24.04.3 LTS Server arm64", "ubuntu-24.04.3-live-server-arm64.iso", 2.9, "2025-08-07", 2, "Ubuntu Server for 64-bit ARM machines."),
    ("Ubuntu 25.04 Desktop amd64", "ubuntu-25.04-desktop-amd64.iso", 6.0, "2025-04-17", 4, "Ubuntu interim release Plucky Puffin."),
    ("Ubuntu 25.10 Desktop amd64", "ubuntu-25.10-desktop-amd64.iso", 5.7, "2025-10-09", 7, "Ubuntu interim release Questing Quokka."),
    ("Ubuntu 26.04 LTS Desktop amd64", "ubuntu-26.04-desktop-amd64.iso", 6.1, "2026-04-23", 10, "Ubuntu 26.04 LTS, five years of standard support."),
    ("Ubuntu 26.04 LTS Server amd64", "ubuntu-26.04-live-server-amd64.iso", 3.2, "2026-04-23", 6, "Ubuntu Server 26.04 LTS live installer."),
    ("Ubuntu 22.04.5 LTS Desktop amd64", "ubuntu-22.04.5-desktop-amd64.iso", 4.7, "2024-09-12", 3, "Previous LTS, Jammy Jellyfish point release."),
    ("Kubuntu 26.04 LTS amd64", "kubuntu-26.04-desktop-amd64.iso", 4.4, "2026-04-23", 3, "Ubuntu flavour with KDE Plasma."),
    ("Xubuntu 26.04 LTS amd64", "xubuntu-26.04-desktop-amd64.iso", 3.9, "2026-04-23", 2, "Ubuntu flavour with Xfce."),
    ("Lubuntu 26.04 LTS amd64", "lubuntu-26.04-desktop-amd64.iso", 3.1, "2026-04-23", 1.5, "Lightweight Ubuntu flavour with LXQt."),
    ("Ubuntu MATE 26.04 LTS amd64", "ubuntu-mate-26.04-desktop-amd64.iso", 4.0, "2026-04-23", 1, "Ubuntu flavour with the MATE desktop."),
    ("Debian 13.1 netinst amd64", "debian-13.1.0-amd64-netinst.iso", 0.75, "2025-09-06", 6, "Debian trixie network installer."),
    ("Debian 13.1 DVD-1 amd64", "debian-13.1.0-amd64-DVD-1.iso", 3.9, "2025-09-06", 3, "Debian trixie first installation DVD."),
    ("Debian 13.1 netinst arm64", "debian-13.1.0-arm64-netinst.iso", 0.6, "2025-09-06", 2, "Debian trixie network installer for arm64."),
    ("Debian 13.1 live GNOME amd64", "debian-live-13.1.0-amd64-gnome.iso", 3.4, "2025-09-06", 2.5, "Debian live image with GNOME."),
    ("Debian 13.1 live KDE amd64", "debian-live-13.1.0-amd64-kde.iso", 3.6, "2025-09-06", 2, "Debian live image with KDE Plasma."),
    ("Debian 12.12 netinst i386", "debian-12.12.0-i386-netinst.iso", 0.65, "2025-09-06", 1, "Debian bookworm installer for 32-bit PCs."),
    ("Fedora 43 Workstation x86_64", "Fedora-Workstation-Live-43-1.6.x86_64.iso", 2.3, "2025-10-28", 6, "Fedora Workstation with GNOME."),
    ("Fedora 43 Server x86_64 DVD", "Fedora-Server-dvd-x86_64-43-1.6.iso", 2.6, "2025-10-28", 2, "Fedora Server full DVD."),
    ("Fedora 43 KDE Plasma x86_64", "Fedora-KDE-Desktop-Live-43-1.6.x86_64.iso", 2.7, "2025-10-28", 3, "Fedora KDE Plasma Desktop edition."),
    ("Fedora 44 Workstation x86_64", "Fedora-Workstation-Live-44-1.4.x86_64.iso", 2.4, "2026-04-21", 5, "Fedora Workstation with GNOME."),
    ("Linux Mint 22.2 Cinnamon 64-bit", "linuxmint-22.2-cinnamon-64bit.iso", 2.9, "2025-09-04", 8, "Linux Mint Zara with Cinnamon."),
    ("Linux Mint 22.2 MATE 64-bit", "linuxmint-22.2-mate-64bit.iso", 2.9, "2025-09-04", 2, "Linux Mint Zara with MATE."),
    ("Linux Mint 22.2 Xfce 64-bit", "linuxmint-22.2-xfce-64bit.iso", 2.8, "2025-09-04", 2.5, "Linux Mint Zara with Xfce."),
    ("LMDE 7 Cinnamon 64-bit", "lmde-7-cinnamon-64bit.iso", 2.7, "2025-10-14", 1.5, "Linux Mint Debian Edition."),
    ("Arch Linux 2026.10.01 x86_64", "archlinux-2026.10.01-x86_64.iso", 1.2, "2026-10-01", 5, "Monthly Arch Linux installation image."),
    ("Arch Linux 2026.09.01 x86_64", "archlinux-2026.09.01-x86_64.iso", 1.2, "2026-09-01", 2, "Monthly Arch Linux installation image."),
    ("Alpine Linux 3.22.2 standard x86_64", "alpine-standard-3.22.2-x86_64.iso", 0.21, "2025-10-08", 2, "Small, security-oriented distribution based on musl and busybox."),
    ("Alpine Linux 3.22.2 standard x86", "alpine-standard-3.22.2-x86.iso", 0.19, "2025-10-08", 1, "Alpine for 32-bit x86 (the base of iSH)."),
    ("Alpine Linux 3.22.2 extended x86_64", "alpine-extended-3.22.2-x86_64.iso", 1.0, "2025-10-08", 0.8, "Alpine with common packages for offline install."),
    ("openSUSE Leap 16.0 DVD x86_64", "Leap-16.0-online-installer-x86_64.install.iso", 4.6, "2025-10-01", 2, "openSUSE Leap 16 installer."),
    ("openSUSE Tumbleweed DVD x86_64 Snapshot 20261012", "openSUSE-Tumbleweed-DVD-x86_64-Snapshot20261012-Media.iso", 4.4, "2026-10-12", 2, "Rolling release openSUSE."),
    ("Manjaro KDE 25.0.10 x86_64", "manjaro-kde-25.0.10-minimal-x86_64.iso", 3.6, "2025-10-05", 3, "Arch-based Manjaro with KDE Plasma."),
    ("Kali Linux 2026.3 Installer amd64", "kali-linux-2026.3-installer-amd64.iso", 4.2, "2026-09-02", 7, "Penetration testing and security auditing distribution."),
    ("Kali Linux 2026.3 Live amd64", "kali-linux-2026.3-live-amd64.iso", 4.3, "2026-09-02", 5, "Kali live image."),
    ("Rocky Linux 10.0 DVD x86_64", "Rocky-10.0-x86_64-dvd1.iso", 9.8, "2025-06-11", 2.5, "Enterprise Linux, RHEL compatible."),
    ("AlmaLinux 10.0 DVD x86_64", "AlmaLinux-10.0-x86_64-dvd.iso", 9.6, "2025-05-27", 2, "Enterprise Linux, RHEL compatible."),
    ("CentOS Stream 10 x86_64 DVD", "CentOS-Stream-10-latest-x86_64-dvd1.iso", 8.1, "2026-08-14", 1, "Upstream for RHEL."),
    ("elementary OS 8.0.2 amd64", "elementaryos-8.0.2-stable-amd64.iso", 3.1, "2025-06-30", 2, "Ubuntu-based distro with the Pantheon desktop."),
    ("Pop!_OS 24.04 LTS amd64 Intel", "pop-os_24.04_amd64_intel_1.iso", 2.8, "2025-12-11", 3, "System76 Pop!_OS with COSMIC desktop."),
    ("Pop!_OS 24.04 LTS amd64 NVIDIA", "pop-os_24.04_amd64_nvidia_1.iso", 3.3, "2025-12-11", 3, "Pop!_OS with NVIDIA drivers preinstalled."),
    ("Zorin OS 18 Core 64-bit", "Zorin-OS-18-Core-64-bit.iso", 4.0, "2025-10-14", 3, "Beginner-friendly Ubuntu-based distro."),
    ("NixOS 25.05 GNOME x86_64", "nixos-gnome-25.05-x86_64-linux.iso", 2.5, "2025-05-23", 2, "Declarative Linux distribution."),
    ("NixOS 25.05 minimal x86_64", "nixos-minimal-25.05-x86_64-linux.iso", 1.1, "2025-05-23", 1.5, "NixOS minimal installer."),
    ("Tails 7.1 amd64", "tails-amd64-7.1.img", 1.6, "2025-10-14", 2, "Portable privacy-focused live system."),
    ("Raspberry Pi OS (64-bit) 2025-10-01", "2025-10-01-raspios-trixie-arm64.img.xz", 1.2, "2025-10-01", 4, "Official Raspberry Pi operating system."),
    ("Raspberry Pi OS Lite (64-bit) 2025-10-01", "2025-10-01-raspios-trixie-arm64-lite.img.xz", 0.5, "2025-10-01", 3, "Raspberry Pi OS without desktop."),
    ("Slackware 15.0 x86_64 DVD", "slackware64-15.0-install-dvd.iso", 3.6, "2022-02-03", 0.6, "The oldest maintained Linux distribution."),
    ("Gentoo minimal install amd64 20261013", "install-amd64-minimal-20261013T170339Z.iso", 0.75, "2026-10-13", 0.8, "Gentoo minimal installation CD."),
    ("Void Linux 20250202 x86_64 glibc", "void-live-x86_64-20250202-base.iso", 0.6, "2025-02-02", 0.7, "Independent distro with runit and xbps."),
    ("MX Linux 25 Xfce x64", "MX-25_x64.iso", 2.5, "2025-11-15", 2, "Midweight Debian-based distribution."),
    ("Puppy Linux BookwormPup64 10.0.11", "BookwormPup64_10.0.11.iso", 0.55, "2025-06-20", 0.8, "Tiny live distribution that runs from RAM."),
    ("FreeBSD 14.3 amd64 disc1", "FreeBSD-14.3-RELEASE-amd64-disc1.iso", 1.3, "2025-06-10", 1.5, "FreeBSD operating system installer."),
    ("FreeBSD 15.0 amd64 dvd1", "FreeBSD-15.0-RELEASE-amd64-dvd1.iso", 4.6, "2025-12-02", 1.2, "FreeBSD 15 full DVD."),
    ("OpenBSD 7.8 amd64 install78.img", "install78.img", 0.75, "2025-10-22", 0.8, "Security-focused BSD."),
    ("Proxmox VE 9.0 ISO Installer", "proxmox-ve_9.0-1.iso", 1.6, "2025-08-05", 3, "Virtualization platform based on Debian."),
    ("TrueNAS SCALE 25.04 amd64", "TrueNAS-SCALE-25.04.2.iso", 2.0, "2025-07-29", 2, "Open storage OS."),
    ("Clonezilla live 3.2.2 amd64", "clonezilla-live-3.2.2-15-amd64.iso", 0.48, "2025-06-04", 1.5, "Disk imaging and cloning live system."),
    ("GParted Live 1.7.0 amd64", "gparted-live-1.7.0-8-amd64.iso", 0.6, "2025-08-11", 1.5, "Partition editor live system."),
    ("SystemRescue 12.02 amd64", "systemrescue-12.02-amd64.iso", 1.1, "2025-08-18", 1.2, "Rescue toolkit live system."),
]
for title, fn, size, when, pop, desc in distros:
    iso(title, "linux", fn, size * GB, desc, datetime.fromisoformat(when).replace(tzinfo=timezone.utc) + timedelta(hours=rng.randint(1, 30)), pop)

# ---------------------------------------------------------------- software
software = [
    ("LibreOffice 25.8.2 Linux x86_64 deb", "LibreOffice_25.8.2_Linux_x86-64_deb.tar.gz", 230, "2025-10-09", 3),
    ("LibreOffice 25.8.2 Windows x86_64", "LibreOffice_25.8.2_Win_x86-64.msi", 350, "2025-10-09", 4),
    ("LibreOffice 25.8.2 macOS aarch64", "LibreOffice_25.8.2_MacOS_aarch64.dmg", 300, "2025-10-09", 2),
    ("Blender 4.5.3 LTS Linux x64", "blender-4.5.3-linux-x64.tar.xz", 350, "2025-09-22", 4),
    ("Blender 4.5.3 LTS Windows x64", "blender-4.5.3-windows-x64.msi", 380, "2025-09-22", 5),
    ("Blender 5.0.0 Linux x64", "blender-5.0.0-linux-x64.tar.xz", 370, "2025-11-18", 4),
    ("GIMP 3.0.6 AppImage x86_64", "GIMP-3.0.6-x86_64.AppImage", 150, "2025-10-06", 3),
    ("Inkscape 1.4.2 AppImage x86_64", "Inkscape-1.4.2-x86_64.AppImage", 130, "2025-05-15", 2),
    ("Krita 5.2.13 AppImage x86_64", "krita-5.2.13-x86_64.appimage", 230, "2025-09-17", 2),
    ("Kdenlive 25.08.2 AppImage x86_64", "kdenlive-25.08.2-x86_64.AppImage", 210, "2025-10-07", 2),
    ("OBS Studio 32.0.1 Windows x64", "OBS-Studio-32.0.1-Windows-x64-Installer.exe", 145, "2025-10-01", 3),
    ("VLC media player 3.0.21 Windows 64-bit", "vlc-3.0.21-win64.exe", 42, "2024-06-10", 3),
    ("Audacity 3.7.5 AppImage x86_64", "audacity-linux-3.7.5-x64-22.04.AppImage", 90, "2025-08-04", 2),
    ("Godot Engine 4.5 Linux x86_64", "Godot_v4.5-stable_linux.x86_64.zip", 60, "2025-09-15", 2),
    ("FreeCAD 1.0.2 AppImage x86_64", "FreeCAD_1.0.2-conda-Linux-x86_64-py311.AppImage", 800, "2025-08-04", 1.5),
    ("KiCad 9.0.5 Windows x86_64", "kicad-9.0.5-x86_64.exe", 1400, "2025-10-01", 1.2),
    ("Thunderbird 144.0 Linux x86_64", "thunderbird-144.0.tar.xz", 85, "2025-10-14", 1),
    ("Firefox 144.0 Linux x86_64", "firefox-144.0.tar.xz", 80, "2025-10-14", 2),
    ("Android Studio Otter 2025.2.1 Linux", "android-studio-2025.2.1.7-linux.tar.gz", 1300, "2025-10-09", 1.5),
    ("Python 3.14.0 source tarball", "Python-3.14.0.tar.xz", 23, "2025-10-07", 1),
    ("Linux kernel 6.17 source", "linux-6.17.tar.xz", 150, "2025-09-28", 1.5),
    ("QEMU 10.1.0 source", "qemu-10.1.0.tar.xz", 140, "2025-08-26", 0.8),
    ("Darktable 5.2.1 AppImage x86_64", "Darktable-5.2.1-x86_64.AppImage", 200, "2025-08-04", 1),
    ("Shotcut 25.08 AppImage x86_64", "shotcut-linux-x86_64-250817.AppImage", 220, "2025-08-17", 1),
    ("MuseScore Studio 4.6 AppImage x86_64", "MuseScore-Studio-4.6.0-x86_64.AppImage", 160, "2025-09-25", 1),
]
for title, fn, size, when, pop in software:
    d = datetime.fromisoformat(when).replace(tzinfo=timezone.utc) + timedelta(hours=rng.randint(1, 30))
    add(title, "software", [(fn, jitter(size * MB))], f"Official release of {title.split(' ')[0]} (free and open-source software).", d, pop, name=fn)

# ---------------------------------------------------------------- video
def film(title, year, folder, size_gb, desc, pop, when, subs=("en",)):
    main = int(size_gb * GB * rng.uniform(0.97, 1.03))
    files = [(f"{folder}/{folder}.mkv", main)]
    files += [(f"{folder}/Subs/{folder}.{lang}.srt", rng.randint(20_000, 90_000)) for lang in subs]
    files.append((f"{folder}/poster.jpg", rng.randint(150_000, 900_000)))
    add(title, "video", files, desc, date_between(when, "2026-10-15"), pop, name=folder)

open_movies = [
    ("Big Buck Bunny (2008)", "Blender Foundation open movie, CC BY 3.0.", [("1080p", 0.7), ("4K 60fps", 3.6)], 6),
    ("Elephants Dream (2006)", "The first Blender open movie, CC BY 2.5.", [("1080p", 0.8)], 2),
    ("Sintel (2010)", "Blender open movie about a girl and her dragon, CC BY 3.0.", [("1080p", 1.2), ("4K", 4.4)], 5),
    ("Tears of Steel (2012)", "Blender open movie, live action with VFX, CC BY 3.0.", [("1080p", 1.4), ("4K", 6.2)], 4),
    ("Cosmos Laundromat - First Cycle (2015)", "Blender open movie pilot, CC BY 4.0.", [("1080p", 1.0), ("4K", 3.8)], 3),
    ("Caminandes 1 - Llama Drama (2013)", "Short Blender animation about Koro the llama, CC BY 3.0.", [("1080p", 0.15)], 1.5),
    ("Caminandes 2 - Gran Dillama (2013)", "Short Blender animation, CC BY 3.0.", [("1080p", 0.18)], 1.2),
    ("Caminandes 3 - Llamigos (2016)", "Short Blender animation, CC BY 4.0.", [("1080p", 0.2), ("4K", 0.9)], 1.5),
    ("Glass Half (2015)", "Short Blender comedy about art critics, CC BY 4.0.", [("1080p", 0.25)], 1),
    ("Agent 327 - Operation Barbershop (2017)", "Blender studio animated short, CC BY 4.0.", [("1080p", 0.35), ("4K", 1.6)], 2.5),
    ("Hero (2018)", "Grease Pencil showcase short film, CC BY 4.0.", [("1080p", 0.12)], 1),
    ("Spring (2019)", "Blender studio short about a shepherd girl, CC BY 4.0.", [("1080p", 0.5), ("4K", 2.1)], 3),
    ("Coffee Run (2020)", "Blender studio short, CC BY 4.0.", [("1080p", 0.2)], 1.5),
    ("Sprite Fright (2021)", "Blender studio horror-comedy short, CC BY 4.0.", [("1080p", 0.6), ("4K", 2.4)], 3),
    ("Charge (2022)", "Blender studio action short, CC BY 4.0.", [("1080p", 0.4), ("4K", 1.8)], 2),
    ("Wing It! (2023)", "Blender studio comedy short, CC BY 4.0.", [("1080p", 0.3)], 1.5),
    ("Singularity (2025)", "Blender studio short film, CC BY 4.0.", [("1080p", 0.5), ("4K", 2.0)], 2),
]
for title, desc, variants, pop in open_movies:
    for quality, size in variants:
        folder = title.split(" (")[0].split(" - ")[0].replace(" ", ".").replace("!", "") + "." + quality.replace(" ", ".")
        film(f"{title} {quality}", 0, folder, size, desc, pop * (0.7 if "4K" in quality else 1), "2022-01-01", ("en", "ru", "de", "es"))

public_domain = [
    ("Night of the Living Dead (1968)", "George A. Romero horror classic, public domain in the US.", 1.4, 4),
    ("Nosferatu (1922)", "F. W. Murnau silent horror film, public domain.", 1.1, 3),
    ("Metropolis (1927) restored", "Fritz Lang silent science fiction epic, public domain in the US.", 2.2, 3),
    ("The General (1926)", "Buster Keaton silent comedy, public domain.", 1.0, 2),
    ("Sherlock Jr. (1924)", "Buster Keaton silent comedy, public domain.", 0.6, 1.5),
    ("The Cabinet of Dr. Caligari (1920)", "German expressionist silent film, public domain.", 0.9, 1.5),
    ("A Trip to the Moon (1902)", "Georges Melies silent film, public domain.", 0.2, 2),
    ("Plan 9 from Outer Space (1957)", "Ed Wood science fiction film, public domain.", 1.0, 1.5),
    ("Charade (1963)", "Cary Grant and Audrey Hepburn thriller, public domain in the US.", 1.8, 3),
    ("His Girl Friday (1940)", "Howard Hawks screwball comedy, public domain.", 1.3, 1.5),
    ("Steamboat Willie (1928)", "Early Mickey Mouse cartoon, public domain since 2024.", 0.1, 3),
    ("The Kid (1921)", "Charlie Chaplin silent comedy-drama, public domain.", 0.8, 2),
    ("Battleship Potemkin (1925)", "Sergei Eisenstein silent film, public domain.", 1.0, 1.5),
    ("Детство Горького (1938)", "Советская экранизация автобиографии М. Горького, общественное достояние.", 1.2, 0.6),
    ("D.O.A. (1949)", "Film noir classic, public domain.", 1.1, 1),
    ("Apollo 11 - NASA restored mission footage", "NASA public domain footage of the Apollo 11 mission.", 6.5, 3),
    ("NASA - Earth from the ISS 4K timelapse collection", "Public domain ISS footage from NASA.", 12.0, 2),
    ("Blue Marble - NASA visualization collection", "NASA Scientific Visualization Studio, public domain.", 3.3, 1),
]
for title, desc, size, pop in public_domain:
    folder = "".join(ch if ch.isalnum() else "." for ch in title).strip(".")
    while ".." in folder:
        folder = folder.replace("..", ".")
    film(title, 0, folder, size, desc, pop, "2022-01-01", ("en",))

# ---------------------------------------------------------------- audio
librivox = [
    ("Pride and Prejudice", "Jane Austen", 61), ("The Adventures of Sherlock Holmes", "Arthur Conan Doyle", 12),
    ("Moby Dick", "Herman Melville", 136), ("Frankenstein", "Mary Shelley", 28),
    ("Dracula", "Bram Stoker", 27), ("The War of the Worlds", "H. G. Wells", 27),
    ("Alice's Adventures in Wonderland", "Lewis Carroll", 12), ("The Time Machine", "H. G. Wells", 12),
    ("Анна Каренина", "Лев Толстой", 120), ("Преступление и наказание", "Фёдор Достоевский", 40),
    ("The Art of War", "Sun Tzu", 13), ("Meditations", "Marcus Aurelius", 12),
]
for book, author, chapters in librivox:
    folder = "".join(ch if ch.isalnum() else "_" for ch in book).strip("_") + "_librivox"
    files = [(f"{folder}/{i:03d}_{folder}_64kb.mp3", rng.randint(8, 30) * MB) for i in range(1, chapters + 1)]
    add(f"{book} - {author} (LibriVox audiobook, MP3 64kbps)", "audio", files,
        f"Public domain audiobook of '{book}' by {author}, read by LibriVox volunteers.",
        date_between("2022-01-01", "2026-10-15"), 1.2, name=folder)

albums = [
    ("Nine Inch Nails - The Slip (2008) FLAC", "CC BY-NC-SA release by Nine Inch Nails.", 10, 3),
    ("Nine Inch Nails - Ghosts I-IV (2008) FLAC", "Instrumental album released under CC BY-NC-SA.", 36, 3),
    ("Nine Inch Nails - Ghosts V-VI (2020) FLAC", "Free instrumental albums released in 2020.", 23, 2),
    ("Musopen - Chopin Complete Nocturnes FLAC", "Public domain recordings commissioned by Musopen.", 21, 2),
    ("Musopen - Beethoven Symphonies 3, 5, 7 FLAC", "Public domain recordings by the Czech National Symphony Orchestra.", 12, 2),
    ("Musopen - Bach Goldberg Variations (Kimiko Ishizaka) FLAC", "Open Goldberg Variations, released into the public domain.", 32, 2.5),
    ("Kimiko Ishizaka - The Open Well-Tempered Clavier FLAC", "Public domain recording of Bach's WTC Book 1.", 48, 1.5),
    ("Kevin MacLeod - Royalty Free Music Collection MP3", "Incompetech music under CC BY 4.0.", 150, 1.5),
    ("Jamendo - Creative Commons Electronic 2025 Sampler MP3", "Tracks licensed under Creative Commons.", 40, 0.8),
    ("Free Music Archive - fma_small dataset MP3", "8000 30-second clips used for music classification research.", 160, 1),
    ("BBC Sound Effects - RemArc subset WAV", "Sound effects licensed for personal, educational and research use.", 500, 1),
    ("NASA - Sounds of Space collection", "Public domain audio from NASA missions.", 60, 1),
]
for title, desc, tracks, pop in albums:
    folder = "".join(ch if ch.isalnum() else "_" for ch in title.split(" FLAC")[0].split(" MP3")[0]).strip("_")
    ext = "flac" if "FLAC" in title else ("wav" if "WAV" in title else "mp3")
    per = 30 * MB if ext != "mp3" else 6 * MB
    files = [(f"{folder}/{i:02d}.{ext}", jitter(per)) for i in range(1, tracks + 1)]
    files.append((f"{folder}/cover.jpg", rng.randint(200_000, 2_000_000)))
    add(title, "audio", files, desc, date_between("2022-01-01", "2026-10-15"), pop, name=folder)

# ---------------------------------------------------------------- books
books = [
    ("Project Gutenberg DVD (2010 edition)", "Project_Gutenberg_DVD_2010", 8.0, "About 29,500 public domain e-books.", 2),
    ("Project Gutenberg Top 100 EPUB collection 2026", "PG_Top100_EPUB_2026", 0.08, "The 100 most downloaded public domain books in EPUB.", 2.5),
    ("Standard Ebooks complete collection 2026-09", "standardebooks_2026_09", 1.9, "Carefully produced public domain e-books.", 2),
    ("Structure and Interpretation of Computer Programs (CC BY-SA)", "SICP", 0.012, "Abelson and Sussman's classic, CC BY-SA 4.0.", 1.5),
    ("Pro Git, 2nd Edition (CC BY-NC-SA)", "progit2", 0.02, "Scott Chacon and Ben Straub's book about Git.", 1.5),
    ("Think Python 3rd Edition (CC BY-NC)", "thinkpython3", 0.01, "Allen Downey's introduction to Python.", 1),
    ("Open Textbook Library - Mathematics bundle", "OTL_math", 1.2, "Openly licensed university mathematics textbooks.", 1),
    ("OpenStax College Physics 2e PDF", "openstax_college_physics_2e", 0.08, "Free, peer-reviewed textbook, CC BY 4.0.", 1),
    ("OpenStax Biology 2e PDF", "openstax_biology_2e", 0.1, "Free, peer-reviewed textbook, CC BY 4.0.", 1),
    ("Wikibooks dump 2026-09-01", "enwikibooks-20260901", 0.9, "All English Wikibooks pages, CC BY-SA.", 0.6),
    ("青空文庫 (Aozora Bunko) full archive 2026", "aozorabunko_2026", 2.4, "Japanese public domain literature collection.", 0.7),
    ("Библиотека Мошкова - классика (общественное достояние)", "lib_ru_classic_pd", 0.6, "Русская классическая литература в общественном достоянии.", 0.8),
    ("Internet Archive - Pulp Magazine Archive sample", "pulpmagazinearchive_sample", 6.0, "Public domain pulp magazines scanned by the Internet Archive.", 0.8),
    ("arXiv - CS papers bulk sample 2025", "arxiv_cs_2025_sample", 40.0, "Open-access arXiv papers, bulk PDF sample.", 1),
]
for title, folder, size_gb, desc, pop in books:
    n = rng.randint(3, 12)
    total = size_gb * GB
    files = [(f"{folder}/part{i:02d}.zip", jitter(total / n)) for i in range(1, n + 1)]
    files.append((f"{folder}/README.txt", rng.randint(1000, 9000)))
    add(title, "books", files, desc, date_between("2022-01-01", "2026-10-15"), pop, name=folder)

# ---------------------------------------------------------------- datasets
datasets = [
    ("Wikipedia enwiki pages-articles dump 2026-10-01", "enwiki-20261001", 24, 8, "English Wikipedia XML dump, CC BY-SA.", 5),
    ("Wikipedia enwiki pages-articles dump 2026-09-01", "enwiki-20260901", 24, 8, "English Wikipedia XML dump, CC BY-SA.", 2),
    ("Wikipedia ruwiki pages-articles dump 2026-10-01", "ruwiki-20261001", 5.6, 4, "Русская Википедия, полный дамп статей, CC BY-SA.", 2),
    ("Wikipedia dewiki pages-articles dump 2026-10-01", "dewiki-20261001", 7.4, 4, "German Wikipedia XML dump, CC BY-SA.", 1.5),
    ("Wikidata JSON dump 2026-10-06", "wikidata-20261006-all.json", 140, 1, "Complete Wikidata entity dump, CC0.", 2),
    ("Kiwix Wikipedia EN all maxi 2026-09 (ZIM)", "wikipedia_en_all_maxi_2026-09", 112, 1, "Offline Wikipedia with images for Kiwix.", 4),
    ("Kiwix Wikipedia RU all maxi 2026-09 (ZIM)", "wikipedia_ru_all_maxi_2026-09", 38, 1, "Офлайн-Википедия с изображениями для Kiwix.", 2),
    ("OpenStreetMap planet-latest.osm.pbf 2026-10-13", "planet-261013.osm.pbf", 82, 1, "Full OpenStreetMap planet export, ODbL.", 4),
    ("OpenStreetMap Europe extract 2026-10", "europe-latest.osm.pbf", 30, 1, "Geofabrik Europe extract, ODbL.", 2),
    ("OpenStreetMap Russia extract 2026-10", "russia-latest.osm.pbf", 3.9, 1, "Geofabrik Russia extract, ODbL.", 1.5),
    ("Stack Exchange data dump 2026-09", "stackexchange_2026_09", 95, 12, "All Stack Exchange sites, CC BY-SA.", 3),
    ("Common Crawl CC-MAIN-2026-38 WET sample", "CC-MAIN-2026-38-wet-sample", 60, 10, "Extracted plain text sample from Common Crawl.", 1.2),
    ("MNIST handwritten digits", "mnist", 0.011, 4, "Classic handwritten digit dataset.", 3),
    ("Fashion-MNIST", "fashion-mnist", 0.03, 4, "Zalando article images, MIT license.", 2),
    ("CIFAR-10 python version", "cifar-10-batches-py", 0.16, 7, "60000 32x32 colour images in 10 classes.", 3),
    ("CIFAR-100 python version", "cifar-100-python", 0.16, 3, "60000 32x32 colour images in 100 classes.", 2),
    ("COCO 2017 train images", "coco2017_train", 18, 1, "Common Objects in Context, CC BY 4.0.", 3),
    ("COCO 2017 val images and annotations", "coco2017_val", 1.0, 2, "COCO 2017 validation split.", 2.5),
    ("LibriSpeech ASR corpus train-clean-100", "LibriSpeech_train-clean-100", 6.3, 1, "Read English speech derived from LibriVox, CC BY 4.0.", 2),
    ("LibriSpeech ASR corpus train-clean-360", "LibriSpeech_train-clean-360", 23, 1, "Read English speech, CC BY 4.0.", 1.5),
    ("Mozilla Common Voice 22.0 Russian", "cv-corpus-22.0-ru", 4.5, 1, "Crowdsourced speech dataset, CC0.", 1),
    ("Mozilla Common Voice 22.0 English", "cv-corpus-22.0-en", 88, 1, "Crowdsourced speech dataset, CC0.", 2),
    ("NYC TLC Trip Records 2025 (Parquet)", "nyc_tlc_2025", 7.0, 12, "New York taxi trip records, public data.", 1.5),
    ("NOAA GHCN-Daily 2026-10 snapshot", "ghcnd_all_2026_10", 3.3, 1, "Global historical daily climate data, public domain.", 1),
    ("US Census ACS 2024 5-year summary files", "acs2024_5yr", 12, 6, "American Community Survey data, public domain.", 0.8),
    ("OpenAlex works snapshot 2026-09", "openalex_works_2026_09", 330, 30, "Open catalog of scholarly works, CC0.", 1),
    ("Project Gutenberg plain text corpus 2026", "gutenberg_txt_2026", 15, 5, "All PG books as UTF-8 text for NLP.", 1.5),
    ("The Stack v2 dedup (Python subset sample)", "the_stack_v2_python_sample", 45, 8, "Permissively licensed source code sample.", 1),
    ("SRTM 30m elevation tiles (Europe)", "srtm30_europe", 25, 6, "NASA Shuttle Radar Topography Mission data, public domain.", 0.8),
    ("Sentinel-2 L2A sample tiles 2026", "sentinel2_l2a_sample_2026", 14, 6, "Copernicus open satellite imagery.", 0.8),
    ("ImageNet-style Open Images V7 validation", "openimages_v7_validation", 12, 4, "Open Images validation split, CC BY 4.0.", 1.2),
    ("Kinetics-700-2020 validation clips", "kinetics700_2020_val", 30, 10, "Short YouTube action clips list and media for research.", 1),
    ("Debian archive snapshot of main/source 2026-10", "debian_main_source_2026_10", 110, 20, "Debian source packages snapshot.", 0.6),
    ("Enron email dataset (CMU)", "enron_mail_20150507", 0.42, 1, "Public research email corpus.", 1.2),
    ("GDELT events 2025 full year", "gdelt_events_2025", 9.5, 12, "Global event database, open data.", 0.7),
]
for title, folder, size_gb, parts, desc, pop in datasets:
    total = size_gb * GB
    if parts == 1:
        files = [(folder, jitter(total))]
        name = folder
        add(title, "dataset", files, desc, date_between("2022-01-01", "2026-10-15"), pop, name=name)
        continue
    files = [(f"{folder}/{folder}-part{i:03d}.tar", jitter(total / parts)) for i in range(1, parts + 1)]
    files.append((f"{folder}/LICENSE.txt", rng.randint(1000, 20000)))
    files.append((f"{folder}/checksums.sha256", 80 * parts))
    add(title, "dataset", files, desc, date_between("2022-01-01", "2026-10-15"), pop, name=folder)

out = ROOT / "torrseek" / "fixtures" / "torrents.json"
out.write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"wrote {len(records)} records to {out}")
