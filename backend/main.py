import csv
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from cameras import Cameras
from simulation import Simulation
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--mode", choices=["fixed","local","cascaded"], default="cascaded")
parser.add_argument("--profile", choices=["light","moderate","heavy","rush","uneven","fluctuating"], default="moderate")


parser.add_argument('--weights')
parser.add_argument('--record', help='Save a new SQLite experiment')
parser.add_argument('--replay', help='Play back a recorded SQLite experiment')


def serve():
    args = parser.parse_args()
    if args.replay and args.record:
        parser.error("Choose one of --record or --replay")
    db = None
    if args.record:
        Path(args.record).touch(exist_ok=False)
        db = sqlite3.connect(args.record)
        db.execute("create table frames(t integer primary key, data text)")
        db.execute("create table config(data text)")
        db.execute("insert into config values (?)",(json.dumps(vars(args)),))
        db.commit()
    replay = None
    if args.replay:
        db = sqlite3.connect(Path(args.replay).resolve().as_uri()+"?mode=ro",uri=True)
        replay = iter(db.execute("select data from frames order by t"))
    cameras = Cameras(args.weights)
    sim = None if replay is not None else Simulation(args.seed,args.mode,args.profile)
    condition = threading.Condition()
    state = {}
    command = {"action":"normal","target":"A","paused":False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/comparison":
                path = Path(__file__).resolve().parents[1]/"comparison.csv"
                if not path.exists():
                    return self.send_error(404)
                with path.open(newline="") as source:
                    rows = list(csv.DictReader(source))
                self.send_response(200)
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(json.dumps(rows).encode())
                return
            if self.path != "/events":
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.end_headers()
            last = -1
            try:
                while True:
                    with condition:
                        condition.wait_for(lambda: state and state["time"] != last)
                        snapshot = state
                    last = snapshot["time"]
                    self.wfile.write(("data: "+json.dumps(snapshot)+"\n\n").encode())
                    self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                pass

        def do_POST(self):
            if self.path != "/control":
                return self.send_error(404)
            try:
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if data["action"] not in ["normal","cross","corridor","offline","reduce","slow","block"] or data["target"] not in list("ABCD") or type(data["paused"]) != bool:
                    raise ValueError()
            except (ValueError,KeyError,TypeError):
                return self.send_error(400)
            with condition:
                command.update(data)
            self.send_response(204)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1",8000),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        while True:
            started = time.monotonic()
            with condition:
                action,target,paused = command["action"],command["target"],command["paused"]
            if not paused:
                if replay is not None:
                    row = next(replay,None)
                    if row is None:
                        time.sleep(.25)
                        continue
                    frame = json.loads(row[0])
                else:
                    sim.action,sim.target = action,target
                    sim.camera_frames = cameras.latest
                    frame = sim.tick()
                    cameras.submit(frame)
                    frame = {**frame,"cameraStatus":cameras.status,"cameras":cameras.latest}
                    if db:
                        db.execute("insert into frames values (?,?)",(sim.n,json.dumps(frame)))
                        db.commit()
                with condition:
                    state = frame
                    condition.notify_all()
            time.sleep(max(0, .25 - (time.monotonic()-started)))
    finally:
        server.shutdown()
        if sim:
            sim.close()
        if db:
            db.close()


if __name__ == "__main__":
    serve()

