#!/usr/bin/env python3
"""Lokales Quiz-Spiel (ähnlich Kahoot) – nur Python-Standardbibliothek.

Start:  python3 server.py
Seiten: /host  (Spielbildschirm am PC)   /play (Handy)   /admin (Fragerunden verwalten)
"""
import argparse
import json
import os
import socket
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import qr

BASE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE, "web")
DB_DIR = os.path.join(BASE, "DB")

DEFAULT_SETTINGS = {
    "read_time": 3,         # Sekunden Lesezeit, bevor Antworten freigegeben werden
    "result_time": 5,       # Sekunden: richtige Antwort + Punkte dieser Frage
    "scoreboard_time": 6,   # Sekunden: Gesamtpunktestand zwischen den Fragen
    "points_first": 1000,   # Punkte für die erste richtige Antwort
    "points_step": 100,     # Abzug je weiterem Platz
    "points_min": 100,      # Mindestpunkte für jede richtige Antwort
    "max_players": 60,
    "title": "Feuerwehr-Quiz",  # Name, der auf Bildschirm und Handys erscheint (z. B. "FF Musterstadt Quiz")
}

ADMIN_REMOTE = False
LOCAL_IPS = {"127.0.0.1", "::1"}
PORT = 8000


# ---------------------------------------------------------------- JSON-Speicher
def db_path(name):
    return os.path.join(DB_DIR, name)


def read_json(name, default):
    try:
        with open(db_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(name, data):
    os.makedirs(DB_DIR, exist_ok=True)
    tmp = db_path(name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, db_path(name))


SAMPLE_QUIZ = {
    "id": "beispiel",
    "name": "Beispiel-Quiz",
    "questions": [
        {"type": "yesno", "text": "Die Erde ist rund.", "options": ["Ja", "Nein"], "correct": [0], "time": 10},
        {"type": "multi", "text": "Wie heißt die Hauptstadt von Frankreich?",
         "options": ["Berlin", "Paris", "Madrid", "Rom"], "correct": [1], "time": 15},
        {"type": "multi", "text": "Welche dieser Tiere sind Säugetiere?",
         "options": ["Delfin", "Haifisch", "Fledermaus", "Forelle"], "correct": [0, 2], "time": 20},
        {"type": "yesno", "text": "Python ist eine Schlange und eine Programmiersprache.",
         "options": ["Ja", "Nein"], "correct": [0], "time": 10},
    ],
}


SAMPLE_FIRE = {
    "id": "feuerwehr",
    "name": "Feuerwehr-Grundlagen",
    "questions": [
        {"type": "multi", "text": "Welche Nummer wählst du im Notfall für die Feuerwehr?",
         "options": ["110", "112", "115", "116 117"], "correct": [1], "time": 15},
        {"type": "yesno", "text": "Brennendes Fett darf mit Wasser gelöscht werden.",
         "options": ["Ja", "Nein"], "correct": [1], "time": 10},
        {"type": "multi", "text": "Welche Dinge braucht ein Feuer (Verbrennungsdreieck)?",
         "options": ["Brennstoff", "Sauerstoff", "Zündenergie (Wärme)", "Wasser"], "correct": [0, 1, 2], "time": 20},
        {"type": "multi", "text": "Zu welcher Brandklasse gehören Brände fester Stoffe wie Holz oder Papier?",
         "options": ["Brandklasse A", "Brandklasse B", "Brandklasse C", "Brandklasse D"], "correct": [0], "time": 15},
        {"type": "yesno", "text": "Ein Feuerlöscher darf nach einem Einsatz, auch wenn er nur teilweise entleert wurde, einfach zurückgehängt werden.",
         "options": ["Ja", "Nein"], "correct": [1], "time": 15},
    ],
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    stored = read_json("settings.json", None)
    if isinstance(stored, dict):
        for k, v in stored.items():
            if k not in s:
                continue
            if isinstance(s[k], str):
                if isinstance(v, str) and v.strip():
                    s[k] = v.strip()[:40]
            elif isinstance(v, (int, float)) and v >= 0:
                s[k] = v
    if stored != s:
        write_json("settings.json", s)
    return s


def clean_quiz(data, quiz_id=None):
    """Prüft und normalisiert eine Fragerunde. Wirft ValueError mit deutscher Meldung."""
    if not isinstance(data, dict):
        raise ValueError("Ungültige Daten")
    name = str(data.get("name", "")).strip()[:80]
    if not name:
        raise ValueError("Bitte einen Namen für die Fragerunde angeben.")
    raw = data.get("questions")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Mindestens eine Frage nötig.")
    if len(raw) > 100:
        raise ValueError("Maximal 100 Fragen pro Runde.")
    questions = []
    for n, q in enumerate(raw, 1):
        if not isinstance(q, dict):
            raise ValueError(f"Frage {n}: ungültig.")
        text = str(q.get("text", "")).strip()[:300]
        if not text:
            raise ValueError(f"Frage {n}: Fragetext fehlt.")
        typ = q.get("type")
        try:
            t = int(q.get("time", 20))
        except (TypeError, ValueError):
            t = 20
        t = max(5, min(120, t))
        correct = q.get("correct")
        if not isinstance(correct, list):
            raise ValueError(f"Frage {n}: richtige Antwort fehlt.")
        if typ == "yesno":
            options = ["Ja", "Nein"]
        elif typ == "multi":
            opts = q.get("options")
            if not isinstance(opts, list) or len(opts) != 4:
                raise ValueError(f"Frage {n}: genau 4 Antworten nötig.")
            options = [str(o).strip()[:120] for o in opts]
            if not all(options):
                raise ValueError(f"Frage {n}: alle 4 Antworten müssen ausgefüllt sein.")
        else:
            raise ValueError(f"Frage {n}: unbekannter Typ.")
        try:
            correct = sorted({int(c) for c in correct})
        except (TypeError, ValueError):
            raise ValueError(f"Frage {n}: richtige Antwort ungültig.")
        if not correct or any(c < 0 or c >= len(options) for c in correct):
            raise ValueError(f"Frage {n}: mindestens eine richtige Antwort wählen.")
        if typ == "yesno" and len(correct) != 1:
            raise ValueError(f"Frage {n}: bei Ja/Nein genau eine richtige Antwort.")
        questions.append({"type": typ, "text": text, "options": options, "correct": correct, "time": t})
    return {"id": quiz_id or uuid.uuid4().hex[:8], "name": name, "questions": questions}


class Quizzes:
    def __init__(self):
        self.lock = threading.Lock()
        if not os.path.exists(db_path("quizzes.json")):
            write_json("quizzes.json", [SAMPLE_FIRE, SAMPLE_QUIZ])

    def all(self):
        return read_json("quizzes.json", [])

    def get(self, qid):
        return next((q for q in self.all() if q["id"] == qid), None)

    def save(self, data):
        with self.lock:
            items = self.all()
            qid = data.get("id") if isinstance(data, dict) else None
            existing = next((i for i, q in enumerate(items) if q["id"] == qid), None)
            quiz = clean_quiz(data, qid if existing is not None else None)
            if existing is None:
                items.append(quiz)
            else:
                items[existing] = quiz
            write_json("quizzes.json", items)
            return quiz

    def delete(self, qid):
        with self.lock:
            items = [q for q in self.all() if q["id"] != qid]
            write_json("quizzes.json", items)


# ---------------------------------------------------------------- Spiellogik
class Game:
    ACTIVE = ("read", "answer", "result", "scoreboard")

    def __init__(self, quizzes, settings):
        self.lock = threading.RLock()
        self.quizzes = quizzes
        self.s = settings
        self.quiz_id = None
        self.reset()

    # -- Zustand
    def reset(self):
        """Zurück in die Lobby: Spieler, Punkte und Antworten werden gelöscht."""
        self.phase = "lobby"
        self.paused = False
        self.quiz = None
        self.q_index = -1
        self.phase_end = None
        self.remaining = 0.0
        self.duration = 0.0
        self.players = {}
        self.answers = {}
        self.persist()

    def persist(self):
        write_json("session.json", {
            "phase": self.phase, "quiz_id": self.quiz_id, "q_index": self.q_index,
            "players": self.players, "answers": self.answers,
        })

    def question(self):
        if self.quiz and 0 <= self.q_index < len(self.quiz["questions"]):
            return self.quiz["questions"][self.q_index]
        return None

    def time_left(self):
        if self.paused or self.phase_end is None:
            return max(0.0, self.remaining)
        return max(0.0, self.phase_end - time.time())

    def _begin(self, phase, duration):
        self.phase = phase
        self.duration = float(duration)
        if self.paused:
            self.remaining = float(duration)
            self.phase_end = None
        else:
            self.phase_end = time.time() + duration
        self.persist()

    # -- Steuerung
    def select(self, quiz_id):
        with self.lock:
            if self.phase != "lobby":
                raise ValueError("Auswahl nur in der Lobby möglich.")
            if quiz_id is not None and not self.quizzes.get(quiz_id):
                raise ValueError("Fragerunde nicht gefunden.")
            self.quiz_id = quiz_id

    def start(self):
        with self.lock:
            if self.phase != "lobby":
                raise ValueError("Das Spiel läuft bereits.")
            quiz = self.quizzes.get(self.quiz_id) if self.quiz_id else None
            if not quiz:
                raise ValueError("Bitte zuerst eine Fragerunde auswählen.")
            if not self.players:
                raise ValueError("Noch keine Spieler beigetreten.")
            self.quiz = quiz
            for p in self.players.values():
                p["score"], p["gain"] = 0, 0
            self.q_index = -1
            self.paused = False
            self._next_question()

    def pause(self):
        with self.lock:
            if self.phase in self.ACTIVE and not self.paused:
                self.remaining = self.time_left()
                self.paused = True
                self.phase_end = None

    def resume(self):
        with self.lock:
            if self.paused:
                self.paused = False
                self.phase_end = time.time() + self.remaining

    def skip(self):
        with self.lock:
            if self.phase in self.ACTIVE:
                self._advance()

    def stop(self):
        with self.lock:
            self.reset()

    def _next_question(self):
        self.q_index += 1
        self.answers = {}
        if self.q_index >= len(self.quiz["questions"]):
            for p in self.players.values():
                p["gain"] = 0
            self.phase, self.phase_end, self.remaining = "finished", None, 0.0
            self.paused = False
            self.persist()
            return
        self._begin("read", self.s["read_time"])

    def _advance(self):
        if self.phase == "read":
            self._begin("answer", self.question()["time"])
        elif self.phase == "answer":
            self._score()
            self._begin("result", self.s["result_time"])
        elif self.phase == "result":
            self._begin("scoreboard", self.s["scoreboard_time"])
        elif self.phase == "scoreboard":
            self._next_question()

    def _score(self):
        q = self.question()
        correct = set(q["correct"])
        right = sorted(
            (a["t"], pid) for pid, a in self.answers.items() if set(a["choice"]) == correct
        )
        for p in self.players.values():
            p["gain"] = 0
        for rank, (_, pid) in enumerate(right, 1):
            pts = max(self.s["points_min"], self.s["points_first"] - (rank - 1) * self.s["points_step"])
            pts = int(pts)
            self.answers[pid].update(correct=True, rank=rank, points=pts)
            if pid in self.players:
                self.players[pid]["gain"] = pts
                self.players[pid]["score"] += pts
        for a in self.answers.values():
            a.setdefault("correct", False)

    def tick(self):
        with self.lock:
            if self.paused or self.phase not in self.ACTIVE:
                return
            if self.phase == "answer":
                now = time.time()
                online = [pid for pid, p in self.players.items() if now - p.get("seen", 0) < 15]
                if online and all(pid in self.answers for pid in online):
                    self._advance()
                    return
            if self.time_left() <= 0:
                self._advance()

    # -- Spieler
    def join(self, name, pid=None):
        name = " ".join(str(name).split())[:20]
        if not name:
            raise ValueError("Bitte einen Namen eingeben.")
        with self.lock:
            if pid and pid in self.players:
                self.players[pid]["seen"] = time.time()
                return pid, self.players[pid]["name"]
            if self.phase == "finished":
                raise ValueError("Das Spiel ist beendet.")
            if len(self.players) >= self.s["max_players"]:
                raise ValueError("Das Spiel ist voll.")
            taken = {p["name"].lower() for p in self.players.values()}
            base, n = name, 1
            while name.lower() in taken:
                n += 1
                name = f"{base} {n}"
            pid = uuid.uuid4().hex
            self.players[pid] = {"name": name, "score": 0, "gain": 0, "seen": time.time()}
            self.persist()
            return pid, name

    def answer(self, pid, choice):
        with self.lock:
            q = self.question()
            if pid not in self.players:
                raise ValueError("Unbekannter Spieler.")
            if self.phase != "answer" or self.paused:
                raise ValueError("Gerade keine Antwort möglich.")
            if pid in self.answers:
                raise ValueError("Du hast schon geantwortet.")
            if not isinstance(choice, list) or not choice:
                raise ValueError("Keine Auswahl.")
            try:
                choice = sorted({int(c) for c in choice})
            except (TypeError, ValueError):
                raise ValueError("Ungültige Auswahl.")
            if any(c < 0 or c >= len(q["options"]) for c in choice):
                raise ValueError("Ungültige Auswahl.")
            if len(q["correct"]) == 1 and len(choice) != 1:
                raise ValueError("Bitte genau eine Antwort wählen.")
            self.answers[pid] = {"choice": choice, "t": time.time()}
            self.persist()

    # -- Sichten für die Oberflächen
    def ranking(self):
        order = sorted(self.players.items(), key=lambda kv: (-kv[1]["score"], kv[1]["name"].lower()))
        out, last, rank = [], None, 0
        for i, (pid, p) in enumerate(order, 1):
            if p["score"] != last:
                rank, last = i, p["score"]
            out.append((pid, p, rank))
        return out

    def _public_q(self, q, with_correct=False):
        d = {"text": q["text"], "type": q["type"], "options": q["options"],
             "multiple": len(q["correct"]) > 1}
        if with_correct:
            d["correct"] = q["correct"]
        return d

    def host_state(self, join_url):
        with self.lock:
            q = self.question()
            show = self.phase in ("result", "scoreboard")
            d = {
                "phase": self.phase, "paused": self.paused, "title": self.s["title"],
                "time_left": round(self.time_left(), 2), "duration": self.duration,
                "join_url": join_url,
                "quiz": {"id": self.quiz_id, "name": (self.quiz or self.quizzes.get(self.quiz_id) or {}).get("name")}
                if self.quiz_id else None,
                "q_index": self.q_index,
                "total": len(self.quiz["questions"]) if self.quiz else 0,
                "answered": len(self.answers),
                "players": [
                    {"name": p["name"], "score": p["score"], "gain": p["gain"], "rank": r,
                     "answered": pid in self.answers,
                     "answer_rank": self.answers.get(pid, {}).get("rank") if show else None,
                     "correct": self.answers.get(pid, {}).get("correct") if show else None}
                    for pid, p, r in self.ranking()
                ],
            }
            if self.phase == "lobby":
                d["quizzes"] = [{"id": z["id"], "name": z["name"], "count": len(z["questions"])}
                                for z in self.quizzes.all()]
            if q and self.phase in self.ACTIVE:
                d["question"] = self._public_q(q, with_correct=show)
                if show:
                    counts = [0] * len(q["options"])
                    for a in self.answers.values():
                        for c in a["choice"]:
                            counts[c] += 1
                    d["counts"] = counts
            return d

    def play_state(self, pid):
        with self.lock:
            p = self.players.get(pid)
            d = {"phase": self.phase, "paused": self.paused, "joined": p is not None, "title": self.s["title"],
                 "time_left": round(self.time_left(), 2), "duration": self.duration,
                 "q_index": self.q_index, "total": len(self.quiz["questions"]) if self.quiz else 0}
            if not p:
                return d
            p["seen"] = time.time()
            rank = next((r for i, _, r in self.ranking() if i == pid), None)
            d.update(name=p["name"], score=p["score"], rank=rank, players=len(self.players))
            q = self.question()
            if q and self.phase in ("read", "answer", "result", "scoreboard"):
                d["question"] = self._public_q(q, with_correct=self.phase in ("result", "scoreboard"))
                a = self.answers.get(pid)
                d["my_choice"] = a["choice"] if a else None
                if self.phase in ("result", "scoreboard"):
                    d["result"] = {"answered": a is not None, "correct": bool(a and a.get("correct")),
                                   "points": p["gain"], "answer_rank": a.get("rank") if a else None}
            return d


# ---------------------------------------------------------------- HTTP
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
                ".ico": "image/x-icon"}
PAGES = {"/host": "host.html", "/play": "play.html", "/admin": "admin.html"}


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def own_ips():
    ips = set(LOCAL_IPS)
    ips.add(lan_ip())
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return ips


class Handler(BaseHTTPRequestHandler):
    server_version = "QuizServer"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    # -- Hilfsfunktionen
    def is_local(self):
        return ADMIN_REMOTE or self.client_address[0] in self.server.local_ips

    def send_bytes(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code=200):
        self.send_bytes(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")

    def fail(self, msg, code=400):
        self.send_json({"error": msg}, code)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            raise ValueError("Anfrage zu groß")
        raw = self.rfile.read(n) if n else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("Ungültige Daten")
        return data

    def join_url(self):
        return f"http://{lan_ip()}:{PORT}/play"

    def send_static(self, name):
        path = os.path.normpath(os.path.join(WEB_DIR, name))
        if not path.startswith(WEB_DIR + os.sep) or not os.path.isfile(path):
            return self.fail("Nicht gefunden", 404)
        with open(path, "rb") as f:
            body = f.read()
        self.send_bytes(200, body, STATIC_TYPES.get(os.path.splitext(path)[1], "application/octet-stream"))

    # -- GET
    def do_GET(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)
        game = self.server.game
        try:
            if p == "/":
                return self.send_bytes(302, b"", "text/plain", {"Location": "/play"})
            if p in PAGES:
                if p == "/admin" and not self.is_local():
                    return self.send_bytes(403, "Admin ist nur am Spiel-PC erreichbar.".encode(), "text/plain; charset=utf-8")
                return self.send_static(PAGES[p])
            if p.startswith("/static/"):
                return self.send_static(p[len("/static/"):])
            if p == "/qr.svg":
                return self.send_bytes(200, qr.make_svg(self.join_url()).encode(), "image/svg+xml")
            if p == "/api/host/state":
                return self.send_json(game.host_state(self.join_url()))
            if p == "/api/play/state":
                return self.send_json(game.play_state(qs.get("pid", [""])[0]))
            if p == "/api/quizzes":
                if not self.is_local():
                    return self.fail("Nur am Spiel-PC erlaubt.", 403)
                return self.send_json(self.server.quizzes.all())
            self.fail("Nicht gefunden", 404)
        except Exception as e:  # noqa: BLE001
            self.fail(f"Serverfehler: {e}", 500)

    # -- POST
    def do_POST(self):
        p = urlparse(self.path).path
        game = self.server.game
        try:
            data = self.body()
            if p == "/api/join":
                pid, name = game.join(data.get("name", ""), data.get("pid"))
                return self.send_json({"pid": pid, "name": name})
            if p == "/api/answer":
                game.answer(data.get("pid"), data.get("choice"))
                return self.send_json({"ok": True})
            # alles Weitere nur am Spiel-PC
            if not self.is_local():
                return self.fail("Nur am Spiel-PC erlaubt.", 403)
            if p == "/api/quizzes":
                return self.send_json(self.server.quizzes.save(data))
            if p == "/api/quizzes/delete":
                qid = data.get("id")
                with game.lock:
                    if game.phase != "lobby" and game.quiz and game.quiz["id"] == qid:
                        return self.fail("Diese Runde läuft gerade.")
                    self.server.quizzes.delete(qid)
                    if game.quiz_id == qid:
                        game.quiz_id = None
                return self.send_json({"ok": True})
            if p == "/api/control":
                a = data.get("action")
                if a == "select":
                    game.select(data.get("quiz_id"))
                elif a == "start":
                    if data.get("quiz_id"):
                        game.select(data["quiz_id"])
                    game.start()
                elif a in ("pause", "resume", "skip", "stop"):
                    getattr(game, a)()
                else:
                    return self.fail("Unbekannte Aktion.")
                return self.send_json({"ok": True})
            self.fail("Nicht gefunden", 404)
        except ValueError as e:
            self.fail(str(e))
        except Exception as e:  # noqa: BLE001
            self.fail(f"Serverfehler: {e}", 500)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    global ADMIN_REMOTE, PORT, DB_DIR
    ap = argparse.ArgumentParser(description="Lokales Quiz-Spiel")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--db", default=DB_DIR, help="Ordner für die JSON-Dateien (Standard: ./DB)")
    ap.add_argument("--admin-remote", action="store_true",
                    help="Admin/Steuerung auch von anderen Geräten erlauben (Standard: nur am Spiel-PC)")
    ap.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    args = ap.parse_args()
    ADMIN_REMOTE, PORT, DB_DIR = args.admin_remote, args.port, os.path.abspath(args.db)

    quizzes = Quizzes()
    game = Game(quizzes, load_settings())
    srv = Server(("0.0.0.0", PORT), Handler)
    srv.game, srv.quizzes, srv.local_ips = game, quizzes, own_ips()

    def ticker():
        while True:
            time.sleep(0.1)
            try:
                game.tick()
            except Exception as e:  # noqa: BLE001
                print("Tick-Fehler:", e)

    threading.Thread(target=ticker, daemon=True).start()
    ip = lan_ip()
    print("=" * 56)
    print(" Quiz-Server läuft")
    print(f"  Spielbildschirm (PC):  http://localhost:{PORT}/host")
    print(f"  Admin (Fragen):        http://localhost:{PORT}/admin")
    print(f"  Handys:                http://{ip}:{PORT}/play  (QR-Code im Spielbildschirm)")
    print(f"  Daten:                 {DB_DIR}")
    print(" Beenden mit Strg+C")
    print("=" * 56)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}/host")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
