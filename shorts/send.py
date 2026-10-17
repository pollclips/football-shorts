"""Stuurt de payload naar de Make-webhook, die de video op YouTube zet."""
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def main():
    if (OUT / "skip").exists():
        print("Niets te versturen vandaag.")
        return
    url = os.environ.get("MAKE_WEBHOOK_URL", "").strip()
    if not url:
        sys.exit("MAKE_WEBHOOK_URL ontbreekt (zet hem als GitHub secret).")
    payload = json.loads((OUT / "payload.json").read_text())

    # wacht tot GitHub de nieuwe video publiek serveert
    for _ in range(36):
        r = requests.head(payload["video_url"], timeout=20, allow_redirects=True)
        if r.status_code == 200:
            break
        time.sleep(5)
    else:
        sys.exit(f"Video niet bereikbaar: {payload['video_url']} (is de repository wel Public?)")

    r = requests.post(url, json=payload, timeout=60)
    print("Make antwoordde:", r.status_code, r.text[:300])
    if r.status_code >= 300:
        sys.exit("Make heeft de aanvraag niet aanvaard.")
    print("Doorgestuurd. Publicatie gepland op", payload["publish_at"], "(UTC)")


if __name__ == "__main__":
    main()
