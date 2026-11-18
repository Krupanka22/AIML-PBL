# GreenWave AI

A local SUMO traffic-control prototype for the four-intersection corridor in the RVCE project report. Each controller observes a simulated junction, evaluates candidate green durations over a 55-second queue forecast, and passes its plan through a separate phase supervisor. The browser consumes TraCI positions and executed light states.

## Run on Windows

Run the following in PowerShell from the greenwave-ai directory. The supplied workspace already has the simulation environment one directory above it.

~~~powershell
python -m venv ../.venv
../.venv/Scripts/python -m pip install -r requirements.txt
../.venv/Scripts/python backend/main.py --mode cascaded --profile moderate --seed 42
~~~

In a second terminal, start the frontend and open the local URL printed by Vite.

~~~powershell
cd frontend
npm.cmd ci
npm.cmd run dev
~~~

The server listens on 127.0.0.1:8000. Vite proxies the event stream and controls. The simulation advances one second per tick with a 250 ms display interval. EventSource carries snapshots and HTTP POST carries controls. The SVG map uses the corridor's SUMO coordinates. Select a signal to inspect its inputs, current phase, green plan and received link messages.

Modes are fixed, local, and cascaded. Demand profiles are light, moderate, heavy, rush, uneven, and fluctuating. Disturbances affect arrivals, approach speed, lane permissions or messages to and from the selected signal. Restoring normal operation releases buffered north-approach demand.

## Experiments

~~~powershell
../.venv/Scripts/python backend/compare.py --seconds 180 --seed 42
../.venv/Scripts/python backend/main.py --record trial.sqlite
../.venv/Scripts/python backend/main.py --replay trial.sqlite
~~~

Run one server at a time. Stop recording with Ctrl+C before replaying. Each recording uses a new file and stores the configuration, demand, decisions, predictions and displayed frames. Replay reads these frames in time order. Pause and resume work during playback. Restart the playback command to return to the beginning. The comparison command writes comparison.csv in the current directory. Launch it from greenwave-ai so the dashboard can read it.

## Cameras

~~~powershell
../.venv/Scripts/python -m pip install -r vision-requirements.txt
../.venv/Scripts/python backend/main.py --weights models/yolo11n.pt
~~~

Four local overhead camera images are rendered from SUMO positions. A worker applies OpenCV activity gating, YOLO detection, ByteTrack, and a higher-resolution recheck for uncertain boxes. Its queue holds one waiting snapshot. Fresh outbound camera tracks can supply downstream arrival forecasts. SUMO supplies the default forecast on other links. When YOLO returns no boxes, a separately labeled OpenCV colour-segmentation detector processes rendered pixels and supplies boxes to an independent ByteTrack instance. Generic COCO weights do poorly on small schematic vehicles. The smoke run processed all four frames and returned zero YOLO detections. The fallback returned 3, 4, 2 and 2 tracked boxes across cameras A through D. Auto-rickshaw recognition, calibrated tracking accuracy and reliable camera-driven control require suitable labeled footage or training data.

## Verify

~~~powershell
../.venv/Scripts/python -m unittest discover -s tests
../.venv/Scripts/python tests/replay_smoke.py
../.venv/Scripts/python tests/camera_smoke.py
cd frontend
npx.cmd --no-install vite build
~~~

Run the replay check with port 8000 free. The camera check requires the optional vision environment. To regenerate the network, run the following from backend.

~~~powershell
../../.venv/Scripts/python -c "from network import build; build()"
~~~

## Development progress

| Milestone | Files and verification | Remaining work |
|---|---|---|
| 1 · SUMO corridor | backend/network.py, backend/simulation.py, sumo/. Live and comparison runs exercised seeded routes, turns, queues and completed trips. | Calibrate demand to a Bengaluru corridor. |
| 2 · Signal control | backend/control.py and tests/test_corridor.py. Unit and live checks cover green bounds, clearances and phase rotation. | Evaluate fairness over longer runs. |
| 3 · Coordination | backend/communication.py and simulation.py. Live checks cover A–B–C–D forecasts and local fallback during link failure. | Calibrate platoon dispersion and confidence. |
| 4 · MPC | control.py enumerates feasible switch times and models queue growth and service. Comparison trials exercise all modes. | Tune service rates and validate under additional seeds. |
| 5 · Dashboard | backend/main.py and frontend/src/. Vite production build and HTTP event-stream smoke check passed. | Browser interaction and animation QA. |
| 6 · Visualization | Signal inspector, heatmap, vehicle history, aligned arrival highlighting, communications and phase timeline. | Historical event drill-down and richer time-series plots. |
| 7 · VAC | backend/cameras.py and tests/camera_smoke.py. Real inference processed four synthetic camera images. | Validate nonempty tracks, video forecast accuracy and detector/class coverage. |
| 8 · Evaluation | backend/compare.py and comparison.csv measure same-seed traffic outcomes. SQLite replay checked by tests/replay_smoke.py. | Longer trials, edge-resource profiling and annotated vision evaluation. |
| 9 · Integration | Python safety/live tests, recorded SSE replay and frontend production build. | Full acceptance testing, camera-domain validation and performance under sustained load. |

The comparison reports completed-trip times only. Mean approach queue is the time average of the total queue over the corresponding direction across all four signals. Mean maximum wait averages each junction's longest current approach wait. Vehicles still in the network at the end of the experiment can materially affect interpretation.

## Verification notes

Verified with Python 3.10, SUMO/TraCI 1.24, Node 24, and Vite 8.3.8. The local vision smoke test used the installed CPU build of PyTorch 2.9.1, Ultralytics 8.4.3 and OpenCV 4.11 with lap 0.5.12. The dashboard calculates per-frame rendered-box precision and recall at IoU 0.5 for the displayed detector. These synthetic-frame metrics do not establish performance on real traffic video.

During integration, a live request through Vite returned four signal states and moving vehicles. Pause and resume each returned HTTP 204. The browser automation service failed during connection, so visual rendering and click-through remain unverified. The npm audit reported a high-severity picomatch advisory affecting the Vite development dependency chain. Compatible automatic fixes did not clear it.

The checked-in comparison used 180 simulated seconds with seed 42. Each controller issued 426 vehicles and completed 138 trips. Relative to fixed-time control, the cascaded run lowered the mean corridor queue from 45.89 to 18.74 vehicles and raised the cross-road queue from 15.84 to 32.44. Mean travel time for completed trips rose from 52.45 to 75.05 seconds. Full rows are in comparison.csv.
