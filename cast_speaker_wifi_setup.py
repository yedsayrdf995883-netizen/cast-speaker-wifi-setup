"""Put a Google Cast speaker (JBL Link and similar) on Wi-Fi from a computer.

For speakers the current Google Home app no longer finds. Needs only Python 3.8+
and a computer with Wi-Fi; nothing to install.

1. Factory reset the speaker and wait until it has restarted. It then
   broadcasts its own open Wi-Fi network, named after the speaker.
2. Connect this computer's Wi-Fi to that network (no password, "no internet"
   is expected).
3. Run:   python cast_speaker_wifi_setup.py
4. Pick your home network, type its password, and wait for the speaker to join.
5. Reconnect the computer to your home Wi-Fi.

The password is encrypted with the speaker's own public key before it is sent
and is never stored or printed.

Options:  --ssid NAME   home network to join (skips the menu)
          --name NAME   name to give the speaker
          --host ADDR   speaker address on its setup network (default 192.168.255.249;
                        if nothing answers there, this computer's gateway is tried)
          --dry-run     stop before any Wi-Fi details are sent
"""
import argparse
import base64
import getpass
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import warnings

DEFAULT_HOST = "192.168.255.249"      # a Cast device's own address on its setup network
PORT = 8443
WPA_AUTH_OPEN = 1


class Speaker:
    def __init__(self, host):
        self.host = host
        self.base = f"https://{host}:{PORT}"
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)   # self-signed device certificate
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:                                             # old speakers use old TLS
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                ctx.minimum_version = ssl.TLSVersion.TLSv1
            ctx.set_ciphers("ALL:@SECLEVEL=0")
        except (ValueError, ssl.SSLError):
            pass
        self.ctx = ctx

    def reachable(self, timeout=3):
        try:
            with socket.create_connection((self.host, PORT), timeout=timeout):
                return True
        except OSError:
            return False

    def call(self, method, path, body=None, timeout=10):
        """Returns (http status, parsed JSON or text). Status 0 = no answer."""
        data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        except (OSError, ssl.SSLError):
            return 0, None
        text = raw.decode("utf-8", "replace").strip()
        try:
            return status, json.loads(text) if text else None
        except ValueError:
            return status, text


def gateways():
    """This computer's default gateways. On a setup network the speaker is the gateway."""
    cmd = {"win32": ["ipconfig"], "darwin": ["netstat", "-rn", "-f", "inet"]}.get(sys.platform, ["ip", "route"])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, errors="replace").stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines():
        if re.search(r"gateway|^default", line.strip(), re.I):
            found += re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line)
    return [ip for ip in dict.fromkeys(found) if ip != "0.0.0.0"]


def find_speaker(host):
    """The given address if a Cast speaker answers there, else any gateway that does."""
    for ip in [host] + [g for g in gateways() if g != host]:
        spk = Speaker(ip)
        if spk.reachable(timeout=2):
            status, info = spk.call("GET", "/setup/eureka_info", timeout=5)
            if status == 200 and isinstance(info, dict) and "public_key" in info:
                return spk, info
    return None, None


def rsa_encrypt(pubkey_b64, message):
    """RSA PKCS#1 v1.5 encryption with the speaker's key (DER RSAPublicKey)."""
    der = base64.b64decode(pubkey_b64)

    def read(buf, pos):                # -> (value, next position)
        n = buf[pos + 1]
        pos += 2
        if n & 0x80:
            k = n & 0x7F
            n = int.from_bytes(buf[pos:pos + k], "big")
            pos += k
        return buf[pos:pos + n], pos + n

    seq, _ = read(der, 0)
    n_bytes, nxt = read(seq, 0)
    e_bytes, _ = read(seq, nxt)
    n, e = int.from_bytes(n_bytes, "big"), int.from_bytes(e_bytes, "big")
    k = (n.bit_length() + 7) // 8
    if len(message) > k - 11:
        raise ValueError("password too long for the speaker's key")
    pad = bytearray()
    while len(pad) < k - len(message) - 3:
        pad += bytes(b for b in os.urandom(k) if b)
    block = b"\x00\x02" + bytes(pad[:k - len(message) - 3]) + b"\x00" + message
    return base64.b64encode(pow(int.from_bytes(block, "big"), e, n).to_bytes(k, "big")).decode()


def ask(prompt, secret=False):
    if not sys.stdin.isatty():         # piped input, e.g. automated tests
        print(prompt, end="", flush=True)
        return sys.stdin.readline().rstrip("\r\n")
    return getpass.getpass(prompt) if secret else input(prompt)


def scan(spk):
    """Networks the speaker can see, strongest first, one entry per name."""
    best = {}
    for _ in range(3):
        spk.call("POST", "/setup/scan_wifi")
        time.sleep(7)
        status, nets = spk.call("GET", "/setup/scan_results")
        for n in nets if status == 200 and isinstance(nets, list) else []:
            name = n.get("ssid")
            if name and n.get("signal_level", -999) > best.get(name, {}).get("signal_level", -999):
                best[name] = n
        if best:
            break
    return sorted(best.values(), key=lambda n: -n.get("signal_level", -999))


def choose(nets, wanted):
    if wanted:
        hit = next((n for n in nets if n["ssid"] == wanted), None)
        if not hit:
            sys.exit(f"The speaker cannot see '{wanted}'. It sees: " + ", ".join(n["ssid"] for n in nets))
        return hit
    print("\nNetworks the speaker can see:")
    for i, n in enumerate(nets, 1):
        lock = "open" if n.get("wpa_auth") == WPA_AUTH_OPEN else "password"
        print(f"  {i:2}. {n['ssid']:<32} {n.get('signal_level', '?')} dBm  {lock}")
    while True:
        pick = ask("Number of your home network: ").strip()
        if pick.isdigit() and 1 <= int(pick) <= len(nets):
            return nets[int(pick) - 1]
        print("Type one of the numbers above.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ssid")
    ap.add_argument("--name")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    while True:
        spk, info = find_speaker(a.host)
        if spk:
            break
        print(f"\nNo speaker found at {a.host} or at this computer's gateway. Connect the Wi-Fi to the")
        print("speaker's own network (named after the speaker, no password), wait until it says connected,")
        if ask("then press Enter to retry, or type q to quit: ").strip().lower() == "q":
            sys.exit(1)
    print(f"Speaker: {info.get('name')}   firmware {info.get('cast_build_revision')}   at {spk.host}")
    if info.get("connected"):
        print(f"Note: it is already on Wi-Fi '{info.get('ssid')}'. Continuing will move it.")

    print("Asking the speaker which networks it can see...")
    nets = scan(spk)
    if not nets:
        sys.exit("The speaker found no Wi-Fi networks. Move it closer to the router and run again.")
    target = choose(nets, a.ssid)
    home = target["ssid"]
    print(f"Chosen: {home} ({target.get('signal_level')} dBm at the speaker)")
    if target.get("signal_level", 0) < -75:
        print("Warning: that signal is weak where the speaker stands; the connection may be unreliable.")

    if a.dry_run:
        print("Dry run: stopping before any Wi-Fi details are sent.")
        return

    body = {"ssid": home, "wpa_auth": target.get("wpa_auth"),
            "wpa_cipher": target.get("wpa_cipher"), "signal_level": target.get("signal_level")}
    if target.get("wpa_auth") != WPA_AUTH_OPEN:
        password = ask(f"Wi-Fi password for '{home}' (not shown): ", secret=True)
        if not 8 <= len(password) <= 63:
            sys.exit("A Wi-Fi password is 8 to 63 characters.")
        body["enc_passwd"] = rsa_encrypt(info["public_key"], password.encode("utf-8"))
        del password

    status, reply = spk.call("POST", "/setup/connect_wifi", body)
    if status != 200:
        sys.exit(f"The speaker rejected the Wi-Fi details (HTTP {status} {reply or ''}).")
    print("Sent. Waiting for the speaker to join (up to 90 s)...")

    ip, lost = None, 0
    for _ in range(30):
        time.sleep(3)
        status, st = spk.call("GET", "/setup/eureka_info", timeout=5)
        if status != 200 or not isinstance(st, dict):
            lost += 1
            continue
        if st.get("connected") and st.get("ip_address"):
            ip = st["ip_address"]
            break
    if not ip:
        if lost > 20:
            sys.exit("Lost contact with the speaker after sending. This computer probably dropped off the\n"
                     "setup network. If the speaker announces it is connected, it worked; otherwise rejoin\n"
                     "its network and run again.")
        sys.exit("The speaker did not get onto the Wi-Fi. A wrong password is the usual cause; run again.")
    print(f"The speaker joined '{home}' with address {ip}")

    status, _ = spk.call("POST", "/setup/save_wifi", {"keep_hotspot_until_connected": True})
    print("Saved the network on the speaker." if status == 200 else f"Warning: saving returned HTTP {status}.")
    name = a.name if a.name is not None else ask("Name for the speaker (Enter to keep the current one): ").strip()
    if name:
        status, _ = spk.call("POST", "/setup/set_eureka_info", {"name": name})
        print(f"Named it '{name}'." if status == 200 else f"Warning: naming returned HTTP {status}.")

    print(f"\nDone. Reconnect this computer to '{home}'.")
    print(f"Check: http://{ip}:8008/setup/eureka_info should then show the speaker's status.")
    print("The Google Home app on the same Wi-Fi should now offer to add the speaker to your home.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped.")
