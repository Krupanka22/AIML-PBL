"""Capture an SSE frame and check the same frame survives SQLite replay."""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def read_frame(flag,path):
    process=subprocess.Popen([sys.executable,str(ROOT/"backend/main.py"),flag,str(path)])
    try:
        for attempt in range(40):
            try:
                response=urllib.request.urlopen("http://127.0.0.1:8000/events",timeout=4)
                break
            except OSError:
                if process.poll() is not None or attempt==39:
                    raise
                time.sleep(.2)
        with response:
            return json.loads(response.readline().decode().removeprefix("data: "))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__=="__main__":
    import sqlite3
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"trial.sqlite"
        live=read_frame("--record",path)
        recorded=read_frame("--replay",path)
        with sqlite3.connect(path) as connection:
            first=json.loads(connection.execute("select data from frames order by t limit 1").fetchone()[0])
        connection.close()
        assert first==recorded and live["signals"].keys()==recorded["signals"].keys()
        print("SSE and recorded-frame replay passed")
