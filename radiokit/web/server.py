"""Servidor web local (solo 127.0.0.1) con API JSON para la interfaz de radiokit."""
from __future__ import annotations

import csv
import io
import json
import mimetypes
import threading
import traceback
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import __version__, drivers
from ..core.image import MemoryImage
from ..core.model import PMR_SUBTONES, Channel
from ..core.service import RadioService
from ..core.transport import list_ports

STATIC = Path(__file__).parent / "static"


class ApiError(Exception):
    def __init__(self, msg, status=400, details=None):
        super().__init__(msg)
        self.status, self.details = status, details


class App:
    def __init__(self, backup_dir: Path):
        self.backup_dir = Path(backup_dir)
        self.project_root = self.backup_dir.parent.parent
        self.lock = threading.RLock()
        self.jobs: dict[str, dict] = {}
        self.base: MemoryImage | None = None      # tal como esta en la radio (o en la copia abierta)
        self.work: MemoryImage | None = None      # con las ediciones del usuario
        self.source = ""
        self.demo = None

    # ---- tareas en segundo plano ---------------------------------------
    def start_job(self, kind, fn):
        jid = uuid.uuid4().hex[:8]
        job = {"id": jid, "kind": kind, "status": "running", "done": 0, "total": 1, "msg": "", "log": [],
               "result": None, "error": None}
        self.jobs[jid] = job

        def progress(d, t, m):
            job.update(done=d, total=t, msg=m)

        def log(m):
            job["log"].append(m)

        def run():
            try:
                job["result"] = fn(progress, log)
                job["status"] = "ok"
            except Exception as e:  # noqa: BLE001 - se informa al usuario
                job["status"], job["error"] = "error", "%s: %s" % (type(e).__name__, e)
                job["log"].append(traceback.format_exc(limit=3))
        threading.Thread(target=run, daemon=True).start()
        return job

    def service(self, log):
        def factory(port):
            if port == "DEMO" and self.demo:
                return self.demo
            from ..core.transport import SerialTransport
            return SerialTransport(port)
        return RadioService(self.backup_dir, transport_factory=factory, log=log)

    def enable_demo(self, dump: Path):
        """Radio simulada (puerto DEMO) con un volcado real; las copias van a backups/demo."""
        from ..drivers.baofeng_wp970i import MAGIC_UVS9X3
        from ..testing.fake_baofeng import FakeBaofengRadio
        self.demo = FakeBaofengRadio(dump.read_bytes()[:0x2000], MAGIC_UVS9X3)
        self.backup_dir = self.project_root / "backups" / "demo"

    # ---- espacio de trabajo ------------------------------------------------
    def need_ws(self):
        if not self.work:
            raise ApiError("No hay ninguna radio ni copia abierta")
        return drivers.get_driver(self.work.driver_id)

    def set_workspace(self, img: MemoryImage, source: str):
        with self.lock:
            self.base, self.work, self.source = img, img.copy(), source

    def workspace(self):
        if not self.work:
            return {"open": False}
        d = drivers.get_driver(self.work.driver_id)
        try:
            plan = self.service(lambda m: None).plan(self.base, self.work).to_dict()
            plan_error = None
        except Exception as e:  # noqa: BLE001
            plan, plan_error = None, str(e)
        return {
            "open": True, "source": self.source, "driver": d.describe(),
            "capabilities": d.capabilities().to_dict(), "info": d.info_from_image(self.work),
            "meta": {k: v for k, v in self.work.meta.items() if isinstance(v, (str, int, float, bool))},
            "channels": [c.to_dict() for c in d.channels(self.work)],
            "settings": [s.describe(self.work.data) for s in d.SETTINGS],
            "plan": plan, "plan_error": plan_error, "pmr_subtones": PMR_SUBTONES,
        }

    def list_backups(self):
        root = self.project_root / "backups"
        out = []
        for p in sorted(root.rglob("*.bin"), key=lambda p: p.stat().st_mtime, reverse=True):
            if p.stat().st_size < 256:
                continue
            meta = {}
            side = p.with_suffix(".json")
            if side.exists():
                try:
                    meta = json.loads(side.read_text(encoding="utf-8"))
                except ValueError:
                    pass
            out.append({"path": str(p.relative_to(self.project_root)), "size": p.stat().st_size,
                        "mtime": p.stat().st_mtime, "driver_id": meta.get("driver_id"),
                        "model": meta.get("model"), "firmware": meta.get("firmware")})
        return out[:300]

    def safe_path(self, rel):
        p = (self.project_root / rel).resolve()
        if self.project_root.resolve() not in p.parents:
            raise ApiError("Ruta fuera del proyecto")
        if not p.exists():
            raise ApiError("No existe %s" % rel, 404)
        return p

    # ---- rutas -----------------------------------------------------------------
    def handle(self, method, path, query, body):
        if method == "GET" and path == "/api/status":
            return {"version": __version__, "workspace_open": bool(self.work), "source": self.source}
        if method == "GET" and path == "/api/ports":
            ports = list_ports()
            if self.demo:
                ports.insert(0, {"port": "DEMO", "device": "Radio simulada (no toca hardware)"})
            return ports
        if method == "GET" and path == "/api/drivers":
            return [d.describe() for d in drivers.all_drivers()]
        if method == "GET" and path == "/api/backups":
            return self.list_backups()
        if method == "GET" and path.startswith("/api/jobs/"):
            job = self.jobs.get(path.rsplit("/", 1)[1])
            if not job:
                raise ApiError("Tarea desconocida", 404)
            return {k: v for k, v in job.items() if k != "result"} | {"has_result": job["result"] is not None}
        if method == "GET" and path == "/api/workspace":
            return self.workspace()

        if method == "POST" and path == "/api/read":
            port = body.get("port") or ""
            if not port:
                raise ApiError("Elige un puerto")

            driver_id = body.get("driver_id") or None

            def job(progress, log):
                d, img, bpath = self.service(log).read(port, progress, driver_id=driver_id)
                self.set_workspace(img, "Radio en %s (copia %s)" % (port, Path(bpath).name))
                return {"backup": bpath}
            return self.start_job("read", job)

        if method == "POST" and path == "/api/open":
            p = self.safe_path(body.get("path", ""))
            img = MemoryImage.load(p, driver_id=body.get("driver_id") or None)
            d = drivers.get_driver(img.driver_id)
            img.data = img.data[:d.MEM_SIZE]
            if len(img.data) != d.MEM_SIZE:
                raise ApiError("La copia no tiene el tamano esperado para %s" % d.MODEL)
            self.set_workspace(img, "Copia %s" % body.get("path"))
            return self.workspace()

        if method == "PUT" and path == "/api/channel":
            d = self.need_ws()
            ch = Channel.from_dict(body)
            errs = d.validate_channel(ch)
            if errs:
                raise ApiError("Canal no valido", details=errs)
            with self.lock:
                d.encode_channel(self.work.data, ch)
            return self.workspace()

        if method == "POST" and path == "/api/setting":
            d = self.need_ws()
            try:
                with self.lock:
                    d.setting(body["key"]).write(self.work.data, body["value"])
            except (KeyError, ValueError) as e:
                raise ApiError(str(e))
            return self.workspace()

        if method == "POST" and path == "/api/revert":
            self.need_ws()
            with self.lock:
                self.work = self.base.copy()
            return self.workspace()

        if method == "POST" and path == "/api/write":
            d = self.need_ws()
            port, dry = body.get("port") or "", bool(body.get("dry_run"))
            if not port:
                raise ApiError("Elige un puerto")
            if not body.get("confirm") and not dry:
                raise ApiError("Falta confirmacion")
            base, target = self.base.copy(), self.work.copy()

            def job(progress, log):
                res = self.service(log).write(port, base, target, progress, dry_run=dry)
                if not dry and res.verified:
                    img = MemoryImage.load(res.postwrite_backup, driver_id=d.ID)
                    self.set_workspace(img, "Radio en %s (verificada tras escribir)" % port)
                return {"verified": res.verified, "dry_run": res.dry_run, "prewrite": res.prewrite_backup,
                        "postwrite": res.postwrite_backup, "plan": res.plan.to_dict(),
                        "other_diffs": res.other_diffs}
            return self.start_job("dry_run" if dry else "write", job)

        if method == "GET" and path == "/api/export.csv":
            d = self.need_ws()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["Location", "Name", "Frequency", "Duplex", "Offset", "TxTone", "RxTone",
                        "Power", "Mode", "Skip"])
            for c in d.channels(self.work):
                if c.empty:
                    continue
                off = "" if c.tx_freq is None else "%.6f" % (abs(c.tx_freq - c.rx_freq) / 1e6)
                w.writerow([c.number, c.name, "%.6f" % (c.rx_freq / 1e6), c.duplex, off,
                            c.tx_tone or "", c.rx_tone or "", c.power,
                            "FM" if c.bandwidth == "Wide" else "NFM", "" if c.scan else "S"])
            return ("text/csv; charset=utf-8", buf.getvalue().encode("utf-8"))

        raise ApiError("No encontrado", 404)


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "radiokit"

        def log_message(self, fmt, *args):
            pass

        def _send(self, status, ctype, data: bytes):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status, obj):
            self._send(status, "application/json; charset=utf-8",
                       json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

        def _dispatch(self, method):
            u = urlparse(self.path)
            if not u.path.startswith("/api/"):
                return self._static(u.path)
            # Proteccion basica contra peticiones de otras webs (CSRF/DNS rebinding)
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                return self._json(403, {"error": "Host no permitido"})
            if method != "GET" and self.headers.get("X-Radiokit") != "1":
                return self._json(403, {"error": "Cabecera X-Radiokit requerida"})
            body = {}
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                try:
                    body = json.loads(self.rfile.read(n).decode("utf-8"))
                except ValueError:
                    return self._json(400, {"error": "JSON invalido"})
            try:
                res = app.handle(method, u.path, parse_qs(u.query), body)
                if isinstance(res, tuple):
                    return self._send(200, res[0], res[1])
                return self._json(200, res)
            except ApiError as e:
                return self._json(e.status, {"error": str(e), "details": e.details})
            except Exception as e:  # noqa: BLE001
                return self._json(500, {"error": "%s: %s" % (type(e).__name__, e)})

        def _static(self, path):
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            p = (STATIC / rel).resolve()
            if STATIC.resolve() not in p.parents or not p.is_file():
                return self._send(404, "text/plain", b"404")
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            return self._send(200, ctype, p.read_bytes())

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")
    return Handler


def serve(port: int, backup_dir: Path, open_browser=True, demo_dump: Path | None = None):
    app = App(backup_dir)
    if demo_dump:
        app.enable_demo(Path(demo_dump))
        print("MODO DEMO: puerto DEMO = radio simulada con %s" % demo_dump)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    url = "http://127.0.0.1:%d/" % port
    print("radiokit %s en %s  (Ctrl+C para salir)" % (__version__, url))
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
