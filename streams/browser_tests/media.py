"""Run native Chromium media tests against an isolated real Django/SQLite app.

Use --baseline to serve the pre-feature stream page/JS without changing the checkout.
Synthetic devices replace hardware; browser media APIs and signaling remain real.
"""
import json
import math
import os
from pathlib import Path
import secrets
from socketserver import ThreadingMixIn
import struct
import subprocess
import sys
import tempfile
import threading
import wave

ROOT = Path(__file__).resolve().parents[2]
BASELINE_REF = "1eb0a5bb933dbd7b632864da2dc2f90c3bb51e4a"
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ghostwhite.settings")
os.environ.setdefault("DJANGO_DEBUG", "1")


def main():
    import django
    from django.conf import settings

    baseline = "--baseline" in sys.argv
    with tempfile.TemporaryDirectory(prefix="ghostwhite-media-") as directory:
        directory = Path(directory)
        settings.DATABASES = {"default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(directory / "test.sqlite3"),
            # Concurrent signaling polls read then delete inside atomic().
            # Acquire the SQLite write reservation up front to avoid lock upgrades.
            "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
        }}
        settings.DEBUG = True
        settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
        overrides = {}
        if baseline:
            template = directory / "templates/streams/stream_detail.html"
            template.parent.mkdir(parents=True)
            template.write_bytes(subprocess.check_output([
                "git", "show", f"{BASELINE_REF}:streams/templates/streams/stream_detail.html"
            ], cwd=ROOT))
            settings.TEMPLATES[0]["DIRS"] = [str(directory / "templates")]
            for name in ("screenshare.js", "player_controls.js"):
                overrides[f"/static/streams/{name}"] = subprocess.check_output([
                    "git", "show", f"{BASELINE_REF}:streams/static/streams/{name}"
                ], cwd=ROOT)
        django.setup()
        from django.core.management import call_command
        from django.core.servers.basehttp import WSGIRequestHandler, WSGIServer
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.core.wsgi import get_wsgi_application
        from django.db import connections
        from authors.models import Author
        from nodes.models import Node
        from streams.models import Stream

        call_command("migrate", interactive=False, verbosity=0)

        class QuietHandler(WSGIRequestHandler):
            def log_message(self, *args):
                pass

        class Server(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = Server(("127.0.0.1", 0), QuietHandler)
        base = f"http://127.0.0.1:{server.server_port}"
        app = StaticFilesHandler(get_wsgi_application())

        def application(environ, start_response):
            path = environ["PATH_INFO"]
            if path == "/capture-source/":
                start_response("200 OK", [("Content-Type", "text/html")])
                return [b'<title>Commentary capture source</title><h1>Screen capture</h1>'
                        b'<p id="clock"></p><script>setInterval(()=>clock.textContent=Date.now(),100)</script>']
            if path in overrides:
                start_response("200 OK", [("Content-Type", "text/javascript")])
                return [overrides[path]]
            return app(environ, start_response)

        server.set_app(application)
        local = Node.objects.get(is_local=True)
        local.host_url = base
        local.save()
        password = secrets.token_urlsafe(24)
        users = [Author.objects.create_user(
            username=name, password=password, node=local, display_name=name,
            approved=True, is_active=True,
        ) for name in ["media-owner"] + [f"media-viewer-{i}" for i in range(7)]]
        stream = Stream.objects.create(owner=users[0], node=local, title="Microphone media fixture")
        audio_file = directory / "tone.wav"
        with wave.open(str(audio_file), "wb") as output:
            output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            output.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 48000)))
                                        for i in range(48000 * 4)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                ["node", str(Path(__file__).with_suffix(".cjs"))], cwd=ROOT,
                input=json.dumps({"base": base, "path": stream.get_absolute_url(),
                                  "password": password, "audio": str(audio_file), "baseline": baseline,
                                  "captureOnly": "--capture-only" in sys.argv}),
                text=True, timeout=360,
            )
            return result.returncode
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            connections.close_all()


if __name__ == "__main__":
    raise SystemExit(main())
