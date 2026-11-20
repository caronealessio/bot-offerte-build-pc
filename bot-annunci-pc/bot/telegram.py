"""Invio messaggi su Telegram."""
from __future__ import annotations

import html
import os
import time

import requests

MAX_LEN = 3900


def esc(t: str) -> str:
    return html.escape(t or "", quote=False)


class Telegram:
    def __init__(self, dry_run: bool = False):
        self.token = os.getenv("TELEGRAM_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.dry_run = dry_run or not (self.token and self.chat_id)
        if self.dry_run and not dry_run:
            print("ATTENZIONE: TELEGRAM_TOKEN/TELEGRAM_CHAT_ID mancanti, i messaggi vengono solo stampati.")
        self.inviati = 0

    def invia(self, testo: str):
        if len(testo) > MAX_LEN:
            testo = testo[:MAX_LEN] + "\n…"
        if self.dry_run:
            print("----- [TELEGRAM, simulato] -----\n" + testo + "\n")
            self.inviati += 1
            return
        for tentativo in range(3):
            r = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": testo,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            if r.status_code == 429:
                time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1)
                continue
            if not r.ok:
                print(f"Telegram errore {r.status_code}: {r.text[:300]}")
            break
        self.inviati += 1
        time.sleep(1.1)  # limite Telegram ~1 msg/s per chat
