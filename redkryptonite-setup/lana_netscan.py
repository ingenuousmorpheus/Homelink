r"""
╔══════════════════════════════════════════════════════════════╗
║   LANA  ·  NETWORK SCANNER  —  who's on the LAN               ║
║   Phones · TVs · speakers · PCs · IoT — discovered + typed     ║
╚══════════════════════════════════════════════════════════════╝

How it works (no admin, no new heavy deps):
  1. Ping-sweep the local /24 (concurrent) to wake the ARP cache.
  2. Read `arp -a` for IP + MAC of everything that answered / is known.
  3. Reverse-DNS each for a hostname.
  4. Vendor from the MAC OUI (curated table + cached macvendors.com fallback).
  5. Guess device TYPE from hostname keywords + vendor.

Type/vendor are best-effort heuristics (a Samsung MAC could be a phone OR a TV),
so counts are "approximately N", not gospel.
"""

import re
import json
import socket
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import requests

_OUI_CACHE = Path(r"C:\LANA\oui_cache.json")

# A few high-confidence OUI prefixes (first 3 octets, UPPER, no separators) → vendor.
# Unknown prefixes fall back to a cached macvendors.com lookup.
_OUI = {
    "B827EB": "Raspberry Pi", "DCA632": "Raspberry Pi", "E45F01": "Raspberry Pi",
    "B0A737": "Roku", "CC6DA0": "Roku", "D83134": "Roku", "AC3A7A": "Roku",
    "B827EB": "Raspberry Pi", "001C62": "LG", "A816B2": "LG", "001E75": "LG",
    "24CE33": "Amazon", "0C47C9": "Amazon", "68B6B3": "Amazon", "FC65DE": "Amazon", "44650D": "Amazon",
    "3C5AB4": "Google", "5460D0": "Google", "94EB2C": "Google", "F4F5E8": "Google", "DA0A60": "Google",
    "B827EB": "Raspberry Pi", "240AC4": "Espressif", "30AEA4": "Espressif", "84CCA8": "Espressif", "A4CF12": "Espressif",
    "50C7BF": "TP-Link", "A42BB0": "TP-Link", "C006C3": "TP-Link",
    "0050F2": "Microsoft", "281878": "Microsoft", "7C1E52": "Microsoft",
}

_VENDOR_TYPE = {
    "apple": "Apple device", "samsung": "Samsung device", "google": "Google device",
    "amazon": "Amazon device", "roku": "TV / streaming", "lg": "TV", "sony": "TV / console",
    "vizio": "TV", "tcl": "TV", "hisense": "TV", "microsoft": "PC / Xbox",
    "tp-link": "router / AP", "netgear": "router / AP", "ubiquiti": "router / AP", "asus": "router / AP",
    "espressif": "smart home / IoT", "raspberry": "Raspberry Pi", "sonos": "smart speaker",
    "nest": "smart home", "roku ": "TV / streaming",
}

_TYPE_RULES = [
    (("iphone", "galaxy", "pixel", "oneplus", "redmi", "xiaomi", "huawei", "android", "-phone"), "phone"),
    (("ipad", "tablet", "kindle", "-tab"), "tablet"),
    (("tv", "bravia", "webos", "aquos", "roku", "firetv", "fire-tv", "chromecast", "shield",
      "appletv", "apple-tv", "vizio", "hisense", "samsungtv", "lgwebos", "googlecast", "tizen",
      "dial-multiscreen", "mediarenderer", "dlna"), "TV / streaming"),
    (("echo", "alexa", "dot", "homepod", "google-home", "googlehome", "nest-mini", "nest-hub", "sonos"), "smart speaker"),
    (("watch",), "watch"),
    (("macbook", "imac", "mac-", "-mac", "desktop", "laptop", "alienware", "lenovo", "thinkpad",
      "dell", "-pc", "win-", "lenovomonitor"), "computer"),
    (("printer", "epson", "canon", "brother"), "printer"),
    (("ring", "wyze", "blink", "cam-", "camera", "doorbell"), "camera"),
    (("router", "gateway", "netgear", "tp-link", "tplink", "linksys", "asus", "orbi", "eero",
      "ubiquiti", "unifi", "archer", "calix"), "router / AP"),
    (("ex73", "ex63", "ex62", "ex68", "extender", "-rpt", "repeater", "deco"), "Wi-Fi extender"),
    (("esp", "tasmota", "shelly", "tuya", "smartplug", "bulb", "-light", "switch"), "smart home / IoT"),
]


def _local_subnet():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]
    finally:
        s.close()
    return ip.rsplit(".", 1)[0], ip


_NO_WINDOW = 0x08000000   # CREATE_NO_WINDOW — essential under pythonw (no console) so child procs don't fail


def _ping(ip):
    try:
        r = subprocess.run(["ping", "-n", "1", "-w", "350", ip],
                           capture_output=True, text=True, timeout=3, creationflags=_NO_WINDOW)
        return ip if "TTL=" in r.stdout.upper() else None
    except Exception:
        return None


def _arp_table():
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, text=True,
                             timeout=8, creationflags=_NO_WINDOW).stdout
    except Exception:
        return {}
    table = {}
    for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})", out):
        mac = m.group(2).upper().replace("-", ":")
        if mac not in ("FF:FF:FF:FF:FF:FF",) and not mac.startswith("01:00:5E"):
            table[m.group(1)] = mac
    return table


def _rdns(ip):
    try:
        socket.setdefaulttimeout(0.7)
        return socket.gethostbyaddr(ip)[0].split(".")[0]
    except Exception:
        return ""


def _ssdp_discover(timeout=2.5):
    """UPnP/SSDP M-SEARCH → {ip: descriptive text} (SERVER + ST headers). Catches TVs / casting /
    media renderers / speakers that don't reveal much via ARP+DNS."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           "MAN: \"ssdp:discover\"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n").encode()
    info = {}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        s.settimeout(timeout)
        s.sendto(msg, ("239.255.255.250", 1900))
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, addr = s.recvfrom(2048)
            except socket.timeout:
                break
            txt = data.decode("utf-8", "ignore")
            bits = []
            for hdr in ("SERVER", "ST", "NT"):
                m = re.search(hdr + r":\s*(.+)", txt, re.I)
                if m:
                    bits.append(m.group(1).strip())
            if bits:
                info.setdefault(addr[0], set()).update(bits)
        s.close()
    except Exception:
        pass
    return {ip: " · ".join(sorted(v)) for ip, v in info.items()}


def _name_from_ssdp(hints):
    """Pull a friendly-ish device word out of the SSDP SERVER string (e.g. 'Roku', 'Samsung')."""
    for brand in ("Roku", "Samsung", "LG", "Sony", "Bravia", "VIZIO", "Hisense", "TCL", "Sonos",
                  "Chromecast", "Google", "Amazon", "Philips", "Denon", "Yamaha", "webOS", "Tizen"):
        if brand.lower() in hints.lower():
            return brand
    return ""


_oui_disk = None
def _vendor(mac):
    global _oui_disk
    if not mac:
        return ""
    if int(mac[:2], 16) & 0x02:                 # locally-administered bit = randomized/private MAC
        return "(private MAC)"
    pfx = mac.replace(":", "")[:6].upper()
    if pfx in _OUI:
        return _OUI[pfx]
    if _oui_disk is None:
        try: _oui_disk = json.loads(_OUI_CACHE.read_text())
        except Exception: _oui_disk = {}
    if pfx in _oui_disk:
        return _oui_disk[pfx]
    try:                                        # best-effort online lookup (only cache hits)
        r = requests.get(f"https://api.macvendors.com/{mac}", timeout=3)
        v = r.text.strip() if r.status_code == 200 else ""
    except Exception:
        v = ""
    if v:
        _oui_disk[pfx] = v
        try: _OUI_CACHE.write_text(json.dumps(_oui_disk))
        except Exception: pass
    return v


def _classify(name, vendor):
    s = (name + " " + vendor).lower()
    for keys, t in _TYPE_RULES:
        if any(k in s for k in keys):
            return t
    for vk, t in _VENDOR_TYPE.items():
        if vk in s:
            return t
    return "unknown"


def scan(self_ip_label="this PC"):
    """Return (devices, summary). devices = list of {ip,mac,vendor,name,type}."""
    base, my_ip = _local_subnet()
    ips = [f"{base}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=80) as ex:
        alive = {ip for ip in ex.map(_ping, ips) if ip}
    arp = _arp_table()
    ssdp = _ssdp_discover()                              # UPnP/SSDP enrichment (TVs, casting, media)
    all_ips = sorted(alive | set(arp.keys()) | set(ssdp.keys()),
                     key=lambda x: tuple(int(o) for o in x.split(".")) if x.count(".") == 3 else (999,))
    names = {}
    with ThreadPoolExecutor(max_workers=40) as ex:
        for ip, nm in zip(all_ips, ex.map(_rdns, all_ips)):
            names[ip] = nm
    devices = []
    for ip in all_ips:
        mac = arp.get(ip, "")
        vendor = _vendor(mac)
        name = names.get(ip, "")
        hint = ssdp.get(ip, "")
        if not name and hint:
            name = _name_from_ssdp(hint)
        if ip == my_ip:
            name = name or "Alienware"; dtype = "computer (this PC)"
        else:
            dtype = _classify(name + " " + hint, vendor)
        devices.append({"ip": ip, "mac": mac, "vendor": vendor or "?",
                        "name": name or "", "type": dtype, "upnp": bool(hint)})
    summary = {}
    for d in devices:
        summary[d["type"]] = summary.get(d["type"], 0) + 1
    return devices, summary
