"""Reproduce paper/figures/app_*.png (UC-060) with headless Chrome over the DevTools protocol.

    uv run streamlit run app/main.py --server.headless true --server.port 8599 \\
        --theme.base light --client.toolbarMode minimal -- --sample &
    uv run python app/screenshots.py --url http://localhost:8599 --chrome "/path/to/chrome"

Waits until the page shows its data footer (the app has finished rendering), then captures.
No extra dependency: uses `websockets` (installed with streamlit's server).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
QUESTION = {
    "hub": "Zürich HB",
    "arr_line": "IC1",
    "time_band": "morning_peak",
    "day": "all",
    "margin": "3",
}  # the UC-004 borderline segment
VIEWS = {
    "app_form.png": {"view": "answer"},  # the question form (sidebar) next to the answer
    "app_answer.png": {**QUESTION, "view": "answer"},
    "app_official.png": {**QUESTION, "view": "official"},
    "app_chatbot.png": {**QUESTION, "view": "chatbot"},
}
DONE_MARKER = "Data: opentransportdata.swiss"


async def _shoot(ws_url: str, url: str, out: Path, width: int, height: int) -> None:
    ws = await websockets.connect(ws_url, max_size=64 * 1024 * 1024)
    ids = iter(range(1, 10_000))

    async def call(method: str, **params):
        i = next(ids)
        await ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == i:
                return msg.get("result", {})

    await call("Emulation.setDeviceMetricsOverride", width=width, height=height,
               deviceScaleFactor=2, mobile=False)  # fmt: skip
    await call("Page.navigate", url=url)
    deadline = time.time() + 60
    while time.time() < deadline:
        res = await call("Runtime.evaluate", expression="document.body.innerText",
                         returnByValue=True)  # fmt: skip
        if DONE_MARKER in res.get("result", {}).get("value", ""):
            break
        await asyncio.sleep(0.5)
    await asyncio.sleep(1.5)  # let progress bars and badges settle
    shot = await call("Page.captureScreenshot", format="png")
    out.write_bytes(base64.b64decode(shot["data"]))
    await ws.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8599")
    ap.add_argument(
        "--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    )
    ap.add_argument("--out", type=Path, default=ROOT / "paper" / "figures")
    ap.add_argument("--port", type=int, default=9333)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        chrome = subprocess.Popen([args.chrome, "--headless=new", "--disable-gpu",
                                   f"--remote-debugging-port={args.port}",
                                   f"--user-data-dir={profile}", "about:blank"],
                                  stderr=subprocess.DEVNULL)  # fmt: skip
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(f"http://localhost:{args.port}/json/version")
                    break
                except OSError:
                    time.sleep(0.2)
            for name, params in VIEWS.items():
                req = urllib.request.Request(f"http://localhost:{args.port}/json/new?about:blank",
                                             method="PUT")  # fmt: skip
                target = json.loads(urllib.request.urlopen(req).read())
                url = f"{args.url}/?{urllib.parse.urlencode(params)}"
                asyncio.run(_shoot(target["webSocketDebuggerUrl"], url, args.out / name, 1400, 900))
                print(f"wrote {args.out / name}")
        finally:
            chrome.terminate()
            chrome.wait(timeout=10)


if __name__ == "__main__":
    main()
