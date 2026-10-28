"""Run native Chromium media tests against an isolated real Django/SQLite app.

Use --baseline to serve the pre-feature stream page/JS without changing the checkout.
Synthetic devices replace hardware; browser media APIs and signaling remain real.
"""
import json
import math
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import tempfile
import threading
import time
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
    ui_check = "--ui-check" in sys.argv
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
        from django.core.servers.basehttp import ThreadedWSGIServer, WSGIRequestHandler
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.core.wsgi import get_wsgi_application
        from django.db import connections
        from authors.models import Author
        from nodes.models import Node
        from streams.models import Stream

        call_command("migrate", interactive=False, verbosity=0)
        # Test database only: readers need not block the signaling/login writer.
        # Writers still serialize; IMMEDIATE avoids read-to-write upgrades.
        with connections["default"].cursor() as cursor:
            cursor.execute("PRAGMA journal_mode=WAL")
            assert cursor.fetchone()[0] == "wal"

        class QuietHandler(WSGIRequestHandler):
            def log_message(self, *args):
                pass

        class Server(ThreadedWSGIServer):
            # Several browser contexts can open asset/poll sockets at once.
            request_queue_size = 64

        server = Server(("127.0.0.1", 0), QuietHandler)
        base = f"http://127.0.0.1:{server.server_port}"
        app = StaticFilesHandler(get_wsgi_application())

        def route(environ, start_response):
            path = environ["PATH_INFO"]
            if path == "/capture-source/":
                start_response("200 OK", [("Content-Type", "text/html")])
                return [b'<title>Commentary capture source</title><h1>Screen capture</h1>'
                        b'<p id="clock"></p><script>setInterval(()=>clock.textContent=Date.now(),100)</script>']
            if path == "/test-tone.wav":
                content = audio_file.read_bytes()
                start_response("200 OK", [("Content-Type", "audio/wav"), ("Content-Length", str(len(content)))])
                return [content]
            if path in overrides:
                start_response("200 OK", [("Content-Type", "text/javascript")])
                return [overrides[path]]
            return app(environ, start_response)

        diagnostics = {"requests": 0, "server_errors": 0, "slow_requests": 0, "max_seconds": 0}
        diagnostic_lock = threading.Lock()

        def application(environ, start_response):
            started = time.monotonic()
            status_code = 500
            response = None

            def record_status(status, headers, exc_info=None):
                nonlocal status_code
                status_code = int(status.split()[0])
                return start_response(status, headers, exc_info)

            try:
                response = route(environ, record_status)
                yield from response
            finally:
                if response is not None and hasattr(response, "close"):
                    response.close()
                elapsed = round(time.monotonic() - started, 3)
                with diagnostic_lock:
                    diagnostics["requests"] += 1
                    diagnostics["server_errors"] += status_code >= 500
                    diagnostics["slow_requests"] += elapsed >= 3
                    diagnostics["max_seconds"] = max(diagnostics["max_seconds"], elapsed)
                if status_code >= 500 or elapsed >= 3:
                    # Do not log credentials, bodies, cookies, or auth headers.
                    print("Server request diagnostic:", json.dumps({
                        "method": environ["REQUEST_METHOD"], "path": environ["PATH_INFO"],
                        "status": status_code, "seconds": elapsed,
                    }), file=sys.stderr, flush=True)

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
        if ui_check:
            users[0].display_name = "Studio host"
            users[0].save()
            users[1].display_name = "Preview viewer"
            users[1].save()
            stream.title = "Studio session: ideas in progress"
            stream.description = "An open studio for sharing work in progress and talking through the details. Join the conversation while we explore a few ideas together."
            stream.save()
        audio_file = directory / "tone.wav"
        with wave.open(str(audio_file), "wb") as output:
            output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            output.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 48000)))
                                        for i in range(48000 * 4)))
        # Fixture connections belong to the main thread; the standard Django
        # threaded server additionally closes each request worker's connections.
        connections.close_all()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                ["node", str(Path(__file__).with_name("ui.cjs") if ui_check else Path(__file__).with_suffix(".cjs"))], cwd=ROOT,
                input=json.dumps({"base": base, "path": stream.get_absolute_url(),
                                  "password": password, "audio": str(audio_file), "baseline": baseline,
                                  "captureOnly": "--capture-only" in sys.argv,
                                  "serverCheck": "--server-check" in sys.argv,
                                  "output": os.environ.get("STREAM_UI_OUTPUT", "/tmp/ghostwhite-ui-preview")}),
                text=True, timeout=360,
            )
            return result.returncode
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            connections.close_all()
            print("Server diagnostics:", json.dumps(diagnostics), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
