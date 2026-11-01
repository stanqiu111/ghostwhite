"""Two real Ghostwhite processes, databases and HTTP origins; no external nodes.

Default: HTTP federation lifecycle. --browser also verifies real remote pages.
--media additionally checks synthetic audio/video delivery; run only where
WebRTC is permitted. Never changes browser policy or the development database.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def serve(directory, role):
    config = json.loads((directory / "config.json").read_text())
    other = "b" if role == "a" else "a"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ghostwhite.settings")
    from django.conf import settings
    settings.DEBUG = True
    settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
        "NAME": str(directory / f"{role}.sqlite3"),
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"}}}
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.core.servers.basehttp import ThreadedWSGIServer, WSGIRequestHandler
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.wsgi import get_wsgi_application
    from authors.models import Author
    from nodes.models import Node
    from streams.models import Stream
    call_command("migrate", interactive=False, verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL")
    Node.objects.all().delete()  # Isolated fixture database only.
    local = Node.objects.create(is_local=True, host_url=config[role]["base"],
        username=f"node-{role}", password=config[role]["secret"])
    remote = Node.objects.create(host_url=config[other]["base"],
        username=f"node-{other}", password=config[other]["secret"])
    author = Author.objects.create_user(username=f"user-{role}", password=config["password"],
        node=local, display_name=f"Studio {role.upper()}", approved=True, is_active=True)
    stream = Stream.objects.create(owner=author, node=local, title=f"Node {role.upper()} studio")

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, *args):
            pass

    class Server(ThreadedWSGIServer):
        request_queue_size = 64

    server = Server(("127.0.0.1", config[role]["port"]), QuietHandler)
    server.set_app(StaticFilesHandler(get_wsgi_application()))
    (directory / f"{role}.json").write_text(json.dumps({"stream": stream.serial, "author": author.id, "remote": str(remote.pk)}))
    server.serve_forever()


def run():
    import requests
    checks = []

    def passed(name):
        checks.append(name)
        print("PASS", name, flush=True)

    with tempfile.TemporaryDirectory(prefix="ghostwhite-federation-") as folder:
        directory = Path(folder)
        config = {"password": secrets.token_urlsafe(24)}
        for role in ("a", "b"):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            config[role] = {"port": port, "base": f"http://127.0.0.1:{port}", "secret": secrets.token_urlsafe(24)}
        (directory / "config.json").write_text(json.dumps(config))
        processes, logs = [], []
        try:
            for role in ("a", "b"):
                log = (directory / f"{role}.log").open("w+")
                logs.append(log)
                env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "DJANGO_DEBUG": "1"}
                processes.append(subprocess.Popen([sys.executable, __file__, "--serve", folder, role],
                    cwd=ROOT, env=env, stdout=log, stderr=log))
            deadline = time.monotonic() + 50
            while not all((directory / f"{role}.json").exists() for role in ("a", "b")):
                if time.monotonic() > deadline or any(p.poll() is not None for p in processes):
                    raise RuntimeError("The isolated nodes did not start.")
                time.sleep(0.1)
            sessions = {}
            for role in ("a", "b"):
                config[role].update(json.loads((directory / f"{role}.json").read_text()))
                session = requests.Session()
                session.trust_env = False  # Test loopback only; production transport retains proxy policy.
                response = session.post(config[role]["base"] + "/api/authors/login/",
                    json={"username": f"user-{role}", "password": config["password"]}, timeout=10)
                assert response.status_code == 200, response.status_code
                session.headers["X-CSRFToken"] = session.cookies["csrftoken"]
                sessions[role] = session

            def request(role, method, path, expected=200, **kwargs):
                response = sessions[role].request(method, config[role]["base"] + path, timeout=15, **kwargs)
                assert response.status_code == expected, (method, path, response.status_code, response.text[:300])
                return response

            a, b = config["a"], config["b"]
            proxy_list = f'/api/remote-nodes/{b["remote"]}/streams/'
            proxy = proxy_list + a["stream"] + "/"
            local = f'/api/streams/{a["stream"]}/'
            data = request("b", "GET", proxy_list).json()
            assert data["items"][0]["serial"] == a["stream"]
            reverse = request("a", "GET", f'/api/remote-nodes/{a["remote"]}/streams/').json()
            assert reverse["items"][0]["serial"] == b["stream"]
            page = request("b", "GET", data["items"][0]["watchUrl"]).text
            assert f'data-api-base="{proxy}"' in page and 'id="shareScreenBtn"' not in page
            assert a["secret"] not in page and b["secret"] not in page
            passed("both independent nodes discover streams; viewer stays on home origin without host account")

            request("b", "POST", proxy + "signals/", 201, json={"kind": "join", "direction": "to_streamer", "peer_id": "http-viewer"})
            assert request("a", "GET", local + "signals/", params={"role": "streamer"}).json()["items"][0]["kind"] == "join"
            request("a", "POST", local + "signals/", 201, json={"kind": "offer", "direction": "to_viewer", "peer_id": "http-viewer", "payload": {"sdp": "HTTP relay fixture, not real SDP"}})
            assert request("b", "GET", proxy + "signals/", params={"role": "viewer", "peer_id": "http-viewer"}).json()["items"][0]["kind"] == "offer"
            request("b", "POST", proxy + "signals/", 201, json={"kind": "answer", "direction": "to_streamer", "peer_id": "http-viewer"})
            assert request("a", "GET", local + "signals/", params={"role": "streamer"}).json()["items"][0]["kind"] == "answer"
            passed("join/offer/answer cross two real HTTP servers; signal envelope coverage only")

            request("b", "GET", proxy + "signals/", 403, params={"role": "streamer"})
            request("b", "POST", proxy + "signals/", 403, json={"kind": "offer", "direction": "to_viewer", "peer_id": "hijack"})
            message = '<script>window.federationProbe=true</script> cross-node chat'
            request("b", "POST", proxy + "bullets/", 201, json={"content": message})
            bullet = request("a", "GET", local + "bullets/", params={"latest": 1}).json()["items"][0]
            assert bullet["content"] == message and bullet["sender"]["displayName"] == "Studio B"
            passed("remote owner impersonation rejected; cross-node chat retains exact content and sender")

            with sqlite3.connect(directory / "a.sqlite3") as db:
                db.execute("UPDATE nodes_node SET is_disabled=1 WHERE is_local=0")
            request("b", "GET", proxy_list, 403)
            with sqlite3.connect(directory / "a.sqlite3") as db:
                db.execute("UPDATE nodes_node SET is_disabled=0 WHERE is_local=0")
            request("b", "GET", proxy_list)
            passed("host-node disable immediately rejects fresh federation requests; re-enable restores access")

            if "--browser" in sys.argv or "--media" in sys.argv:
                config.update({"media": "--media" in sys.argv, "watchPath": data["items"][0]["watchUrl"],
                    "output": os.environ.get("STREAM_FEDERATION_OUTPUT", "/tmp/ghostwhite-federation-preview")})
                import math, struct, wave
                audio = directory / "tone.wav"
                with wave.open(str(audio), "wb") as sound:
                    sound.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                    sound.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 440 * i / 48000))) for i in range(48000 * 10)))
                config["audio"] = str(audio)
                subprocess.run(["node", str(Path(__file__).with_suffix(".cjs"))], input=json.dumps(config),
                    cwd=ROOT, text=True, check=True, timeout=180)

            request("a", "POST", local + "end/")
            request("b", "GET", proxy + "signals/", 410, params={"role": "viewer", "peer_id": "http-viewer"})
            request("b", "POST", proxy + "bullets/", 410, json={"content": "late"})
            assert request("b", "GET", proxy).json()["status"] == "ended"
            assert request("b", "GET", proxy_list).json()["items"] == []
            with sqlite3.connect(directory / "a.sqlite3") as db:
                assert db.execute("SELECT COUNT(*) FROM streams_streampeer").fetchone()[0] == 0
                assert db.execute("SELECT COUNT(*) FROM streams_streamsignal").fetchone()[0] == 0
            passed("end state propagates; discovery removes room; signaling mailboxes are purged")
            print(json.dumps({"httpChecks": len(checks), "checks": checks, "mediaAttempted": "--media" in sys.argv}), flush=True)
        except Exception:
            for log in logs:
                log.flush(); log.seek(0)
                print(log.read()[-4000:], file=sys.stderr)
            raise
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            for log in logs:
                log.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        serve(Path(sys.argv[2]), sys.argv[3])
    else:
        run()
