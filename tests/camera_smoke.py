"""Optional smoke test for a local camera installation and weights."""
import os
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
os.environ.setdefault("YOLO_CONFIG_DIR",str(ROOT/"models"))
from simulation import Simulation
from cameras import Cameras

if __name__=="__main__":
    sim=Simulation()
    cameras=Cameras(str(ROOT/"models/yolo11n.pt"))
    try:
        for _ in range(20):
            frame=sim.tick()
        cameras.submit(frame)
        for _ in range(90):
            if len(cameras.latest)==4 or cameras.status.startswith("Camera unavailable:"):
                break
            time.sleep(1)
        assert len(cameras.latest)==4,cameras.status
        print({s:len(f["tracks"]) for s,f in cameras.latest.items()})
    finally:
        sim.close()
