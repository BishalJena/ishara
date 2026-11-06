"""Local web-app test server with fake telephony and the real optional ASL model.

Run from backend/: uv run --extra web-recognition python -m scripts.web_demo
Access code: ishara-web-demo (localhost only). No paid provider is configured.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.web_recognition import ASLRecognizer
from scripts.local_demo import _serve, bind_socket, build_local_demo


def main() -> None:
    # A synthetic dial target for the existing fake; never passed to a real provider.
    number = "+91" + "2" + "0" * 9
    demo = build_local_demo(
        app_token="ishara-web-demo", contacts=["clinic=" + number], receptionist="steer"
    )
    model = Path(__file__).resolve().parents[2] / "ios/Ishara/LocalAssets/asl-signs.tflite"
    demo.app.state.web_recognizer = ASLRecognizer(str(model))
    print("Local web test server: http://127.0.0.1:8780; no calls or paid inference")
    asyncio.run(_serve(demo, bind_socket("127.0.0.1", 8780)))


if __name__ == "__main__":
    main()
