"""A bounded, asynchronous camera worker. One persistent ByteTrack tracker per camera."""
import base64
import queue
import threading
import time
from pathlib import Path


class Cameras:
    def __init__(self, weights):
        self.frames = queue.Queue(1)
        self.latest = {}
        self.status = "Detector unavailable; configure --weights to enable camera inference"
        if weights:
            if not Path(weights).is_file():
                raise FileNotFoundError(weights)
            threading.Thread(target=self.run,args=(weights,),daemon=True).start()

    def submit(self,frame):
        if self.frames.empty():
            try:
                self.frames.put_nowait(frame)
            except queue.Full:
                pass

    def run(self,weights):
        try:
            import cv2
            import numpy as np
            from ultralytics import YOLO
            from ultralytics.engine.results import Boxes
            from ultralytics.trackers.byte_tracker import BYTETracker
            from types import SimpleNamespace
            params=SimpleNamespace(track_high_thresh=.5,track_low_thresh=.1,new_track_thresh=.6,
                                   track_buffer=30,match_thresh=.8,fuse_score=True)
            fallback={s:BYTETracker(params) for s in "ABCD"}
            models = {s:YOLO(weights) for s in "ABCD"}
            previous = {}
            positions = {}
            run_dir = str(Path(__file__).resolve().parents[1]/"results"/"vision")
            self.status = "Rendered cameras / YOLO / ByteTrack"
            while True:
                frame = self.frames.get()
                for s,model in models.items():
                    start = time.perf_counter()
                    x,y = frame["junctions"][s]
                    image = np.full((384,384,3),(38,57,44),np.uint8)
                    cv2.rectangle(image,(0,169),(383,215),(63,65,64),-1)
                    cv2.rectangle(image,(169,0),(215,383),(63,65,64),-1)
                    truth=[]
                    for v in frame["vehicles"]:
                        cx,cy=192+(v["x"]-x)*3,192-(v["y"]-y)*3
                        if 0<=cx<384 and 0<=cy<384:
                            length={"bus":36,"truck":27,"motorcycle":6,"auto":9,"car":14}[v["kind"]]
                            box=cv2.boxPoints(((cx,cy),(6,length),v["angle"])).astype(int)
                            x0,y0,w,h=cv2.boundingRect(box)
                            truth.append((max(0,x0),max(0,y0),min(384,x0+w),min(384,y0+h)))
                            cv2.fillConvexPoly(image,box,(172,188,205))
                    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
                    activity=s not in previous or np.any(cv2.absdiff(gray,previous[s])>20)
                    previous[s]=gray
                    tracks=[]
                    detector="YOLO"
                    yolo_count=None
                    if activity or frame["time"]%5==0:
                        result=model.track(image,persist=True,tracker="bytetrack.yaml",project=run_dir,classes=[2,3,5,7],verbose=False)[0]
                        if len(result.boxes) and result.boxes.conf.min().item()<.45:
                            # Recheck uncertain frames at higher resolution without advancing tracker twice.
                            refined=model.predict(image,imgsz=960,project=run_dir,classes=[2,3,5,7],verbose=False)[0]
                            refined_count=len(refined.boxes)
                        else:
                            refined_count=None
                        for b in result.boxes:
                            tracks.append(dict(label=result.names[int(b.cls.item())],track=int(b.id.item()) if b.id is not None else None,
                                               confidence=float(b.conf.item()),box=b.xyxy[0].tolist()))
                        yolo_count=len(tracks)
                        image=result.plot()
                        if not tracks:
                            # The synthetic camera has a known vehicle paint colour. Segment actual
                            # pixels and track the resulting boxes independently of SUMO identifiers.
                            detector="OpenCV colour segmentation + ByteTrack"
                            mask=cv2.inRange(image,np.array([170,186,203]),np.array([174,190,207]))
                            contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                            rows=[]
                            for contour in contours:
                                x0,y0,w,h=cv2.boundingRect(contour)
                                if w*h>=12:
                                    rows.append([x0,y0,x0+w,y0+h,1.,0])
                            boxes=Boxes(np.asarray(rows,dtype=np.float32).reshape(-1,6),gray.shape)
                            for entry in fallback[s].update(boxes,image):
                                x0,y0,x1,y1=entry[:4].astype(int)
                                tid=int(entry[4])
                                tracks.append(dict(label="vehicle",track=tid,confidence=None,box=[int(x0),int(y0),int(x1),int(y1)]))
                                cv2.rectangle(image,(x0,y0),(x1,y1),(121,235,156),1)
                                cv2.putText(image,str(tid),(x0,max(10,y0-2)),cv2.FONT_HERSHEY_SIMPLEX,.35,(121,235,156),1)
                        stage="tracking"
                    else:
                        stage="activity gate"
                        refined_count=None
                    departures = []
                    for obj in tracks:
                        if obj["track"] is None:
                            continue
                        x1,y1,x2,y2=obj["box"]
                        cx,cy=(x1+x2)/2,(y1+y2)/2
                        key = s,detector,obj["track"]
                        prev = positions.get(key)
                        positions[key] = frame["time"],cx,cy
                        if prev is None or prev[0]>=frame["time"] or abs(cy-192)>22:
                            continue
                        velocity=(cx-prev[1])/(3*(frame["time"]-prev[0]))
                        if abs(velocity)<1:
                            continue
                        sign=1 if velocity>0 else -1
                        if (prev[1]-192)*sign<24<=(cx-192)*sign:
                            dest=chr(ord(s)+sign)
                            if dest in "ABCD":
                                eta=frame["time"]+round((300-abs(cx-192)/3)/abs(velocity))
                                departures.append(dict(source=s,destination=dest,count=1,members=[f'camera-{s}-{obj["track"]}'],
                                                       arrival=eta,window=[eta-3,eta+3],confidence=obj["confidence"]))
                    positions={k:v for k,v in positions.items() if frame["time"]-v[0]<60}
                    # Match each image-space reference box at most once.
                    unmatched=list(truth)
                    matches=0
                    for obj in tracks:
                        x1,y1,x2,y2=obj["box"]
                        scores=[]
                        for a,b,c,d in unmatched:
                            overlap=max(0,min(x2,c)-max(x1,a))*max(0,min(y2,d)-max(y1,b))
                            union=(x2-x1)*(y2-y1)+(c-a)*(d-b)-overlap
                            scores.append(overlap/max(1,union))
                        if scores and max(scores)>=.5:
                            unmatched.pop(scores.index(max(scores)))
                            matches+=1
                    ok,jpeg=cv2.imencode(".jpg",image)
                    if ok:
                        self.latest={**self.latest,s:dict(time=frame["time"],detector=detector,yolo_count=yolo_count,departures=departures,tracks=tracks,stage=stage,refined_count=refined_count,
                                                       precision=matches/len(tracks) if tracks else None,recall=matches/len(truth) if truth else None,
                                                       count_error=len(tracks)-len(truth),latency_ms=round(1000*(time.perf_counter()-start),1),
                                                       image=base64.b64encode(jpeg).decode())}
        except Exception as exc:
            self.status=f"Camera unavailable: {exc}"

