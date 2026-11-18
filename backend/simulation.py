import math
import random
import traci
from network import SIGNALS, NETWORK, KINDS, binary, build, itinerary
from control import MLGreenController, MIN_GREEN, Supervisor, optimize
from communication import LinkBus

ORIGINS = ["W", "E"] + [s+d for s in SIGNALS for d in "NS"]


class Simulation:
    def __init__(self, seed=42, mode="cascaded", profile="moderate"):
        if not (NETWORK / "corridor.net.xml").exists():
            build()
        traci.start([binary("sumo"), "-n", str(NETWORK/"corridor.net.xml"), "-r", str(NETWORK/"types.xml"),
                     "--seed", str(seed), "--no-step-log", "true", "--time-to-teleport", "-1"])
        self.rng, self.mode, self.profile = random.Random(seed), mode, profile
        self.flow = []
        self.n = self.issued = self.completed = self.entered = 0
        self.supervisors = {s: Supervisor() for s in SIGNALS}
        self.ml_controller = MLGreenController()
        self.links = {s: traci.trafficlight.getControlledLinks(s) for s in SIGNALS}
        self.axes = {s: [int(link[0][0].split("_")[0].endswith(("N","S"))) for link in links]
                     for s, links in self.links.items()}
        self.failures = {}
        self.recommend = dict.fromkeys(SIGNALS, 20)
        self.action, self.target = "normal", "A"
        self.events = []
        self.bus = LinkBus()
        self.routes = {}
        self.vehicle_forecasts = {}
        self.error_sum = self.error_count = 0
        self.camera_frames = {}
        self.camera_forecasts = {}
        self.last_disturbance = None
        self.pending = []
        self.boundary = traci.simulation.getNetBoundary()
        for s in SIGNALS:
            self.apply(s)

    def apply(self, s):
        sup = self.supervisors[s]
        # Permissive green preserves SUMO's yielding rules for opposing turns.
        state = "".join(("g" if sup.stage == "green" else "y") if axis == sup.axis and sup.stage != "clear"
                        else "r" for axis in self.axes[s])
        traci.trafficlight.setRedYellowGreenState(s, state)

    def tick(self):
        if self.last_disturbance != (self.action,self.target):
            for s in SIGNALS:
                for lane in set(traci.trafficlight.getControlledLanes(s)):
                    traci.lane.setMaxSpeed(lane, 4 if self.action=="slow" and s==self.target else 15)
                    traci.lane.setDisallowed(lane, ["passenger","motorcycle","bus","truck"] if self.action=="block" and lane==s+"N_"+s+"_0" and s==self.target else [])
            self.last_disturbance = self.action,self.target
        demand_log = []
        self.n += 1
        for origin in ORIGINS:
            corridor = origin in ("W", "E")
            rate = (.08 if corridor else .022) * (1+.25*math.sin(self.n/55))
            rate *= {"light":.45,"moderate":1,"heavy":1.65,"rush":1.3+.6*math.sin(self.n/90),
                     "uneven":1.8 if origin == "W" else .55,"fluctuating":self.rng.uniform(.3,1.8)}[self.profile]
            if self.action == "corridor" and corridor or self.action == "cross" and origin.startswith(self.target):
                rate *= 3
            if self.action == "reduce":
                rate *= .35
            if self.rng.random() < rate:
                name = str(self.issued)
                route = itinerary(self.rng, origin)
                traci.route.add(name, route)
                self.routes[name] = route
                self.pending.append((name,route,self.rng.choices(list(KINDS), [46,32,6,13,3])[0]))
                demand_log.append(dict(id=name,route=route,kind=self.pending[-1][2]))
                self.issued += 1
        delayed = []
        for name,route,kind in self.pending:
            if self.action=="block" and route[0]==self.target+"N_"+self.target:
                delayed.append((name,route,kind))
            else:
                traci.vehicle.add(name,name,typeID=kind,departLane="best")
        self.pending = delayed
        traci.simulationStep()
        self.entered += traci.simulation.getDepartedNumber()
        self.completed += traci.simulation.getArrivedNumber()
        for v in traci.simulation.getArrivedIDList():
            self.routes.pop(v,None)
            self.vehicle_forecasts.pop(v,None)
        self.flow.append((traci.simulation.getDepartedNumber(),traci.simulation.getArrivedNumber()))
        self.flow=self.flow[-60:]
        vehicle_wait=0
        vehicles, groups, queued_turns = [], {}, {}
        queues = {s:[0,0] for s in SIGNALS}
        counts = {s:[0,0] for s in SIGNALS}
        wait = {s:[0,0] for s in SIGNALS}
        current = {}
        for v in traci.vehicle.getIDList():
            edge = traci.vehicle.getRoadID(v)
            speed = traci.vehicle.getSpeed(v)
            x,y = traci.vehicle.getPosition(v)
            vehicles.append(dict(id=v,x=x,y=y,speed=speed,angle=traci.vehicle.getAngle(v),kind=traci.vehicle.getTypeID(v)))
            current[v] = edge
            vehicle_wait+=traci.vehicle.getWaitingTime(v)
            pending = self.vehicle_forecasts.get(v)
            if pending and edge.startswith(":"+pending[0]+"_"):
                self.error_sum += abs(self.n-pending[1])
                self.error_count += 1
                del self.vehicle_forecasts[v]
            if edge.startswith(":"):
                continue
            a,b = edge.split("_")
            if b not in SIGNALS:
                continue
            k = int(a.endswith(("N","S")))
            if k==0 and speed<.1:
                route=self.routes[v]
                index=route.index(edge)+1
                if index<len(route):
                    turn=b,route[index].split("_")[1]
                    queued_turns[turn]=queued_turns.get(turn,0)+1
            counts[b][k] += 1
            queues[b][k] += int(speed < .1)
            wait[b][k] = max(wait[b][k],traci.vehicle.getWaitingTime(v))
            if a in SIGNALS and speed > 1:
                lane = traci.vehicle.getLaneID(v)
                eta = (traci.lane.getLength(lane)-traci.vehicle.getLanePosition(v))/speed
                groups.setdefault((a,b),[]).append((round(eta),v))
        predictions = []
        for (a,b), members in groups.items():
            cluster = []
            for eta,v in sorted(members):
                if cluster and eta-cluster[-1][0] > 4:
                    predictions.append(self.packet(a,b,cluster))
                    cluster = []
                cluster.append((eta,v))
            predictions.append(self.packet(a,b,cluster))
        for packet in predictions:
            for v in packet["members"]:
                self.vehicle_forecasts.setdefault(v,(packet["destination"],packet["arrival"]))
        for source,cam in self.camera_frames.items():
            if self.n-cam["time"]<=5:
                for packet in cam["departures"]:
                    self.camera_forecasts[packet["members"][0]]=packet
        self.camera_forecasts={k:p for k,p in self.camera_forecasts.items() if p["window"][1]>=self.n}
        camera_links={(p["source"],p["destination"]) for p in self.camera_forecasts.values()}
        predictions=[p for p in predictions if (p["source"],p["destination"]) not in camera_links]+list(self.camera_forecasts.values())
        disconnected = self.target if self.action == "offline" else None
        messages = self.bus.receive(self.n, disconnected)
        for a,b in zip(SIGNALS,SIGNALS[1:]):
            for source,destination in ((a,b),(b,a)):
                if disconnected in (source,destination):
                    continue
                self.bus.publish(self.n,source,destination,"observed",[p for p in predictions if p["source"]==source and p["destination"]==destination])
                self.bus.publish(self.n,source,destination,"feedback",queues[source][0])
                phase=self.supervisors[source]
                if phase.axis==0 and phase.stage=="green":
                    queued=queued_turns.get((source,destination),0)
                    if queued:
                        self.bus.publish(self.n,source,destination,"planned",dict(expected=min(queued,max(0,phase.plan-self.n+phase.start)),green_end=phase.start+phase.plan))
        info = {}
        for s in SIGNALS:
            sup = self.supervisors[s]
            mail = [m for m in self.bus.latest.values() if m["destination"]==s]
            incoming = [p for m in mail if m["kind"]=="observed" for p in m["data"] if p["window"][1]>=self.n]
            rates = [min(.8,(counts[s][k]-queues[s][k])/30) for k in (0,1)]
            arrivals = {}
            downstream = [m["data"] for m in mail if m["kind"]=="feedback"]
            capacity = 1.6
            if self.mode == "cascaded":
                for p in incoming:
                    offset = max(0,p["arrival"]-self.n)
                    arrivals[offset] = arrivals.get(offset,0)+p["count"]
                capacity = max(.2,1.6-max(downstream,default=0)/24)
            if sup.stage == "green" and (self.n-sup.start <= 1 or self.n-sup.start >= MIN_GREEN):
                try:
                    if self.mode == "fixed":
                        self.recommend[s] = 25
                    elif self.mode in ("local", "cascaded", "ml"):
                        self.recommend[s] = self.ml_controller.recommend(
                            sup.axis,
                            self.n-sup.start,
                            queues[s],
                            rates,
                            arrivals,
                            capacity,
                            wait[s],
                        )
                    else:
                        self.recommend[s] = optimize(sup.axis,self.n-sup.start,queues[s],rates,arrivals,capacity,wait[s])
                    self.failures.pop(s,None)
                except (ValueError,ArithmeticError,RuntimeError):
                    self.recommend[s] = MIN_GREEN
                    self.failures[s] = "Optimizer unavailable; rotating after minimum green"
            before = sup.stage
            sup.advance(self.n,self.recommend[s],0 if self.mode=="fixed" else wait[s][1-sup.axis])
            if self.mode=="fixed" and sup.stage=="green":
                sup.plan=self.recommend[s]=25
            if before != sup.stage:
                self.events.append(dict(time=self.n,signal=s,stage=sup.stage))
            self.apply(s)
            info[s] = dict(stage=sup.stage,axis=sup.axis,elapsed=self.n-sup.start,queue=queues[s],wait=wait[s],
                           recommended=self.recommend[s],approved=sup.plan,incoming=incoming,capacity=capacity,
                           reason=self.failures.get(s) or (
                               "Fixed cycle baseline"
                               if self.mode=="fixed"
                               else "Random-Forest ML recommendation trained on 55-second queue-cost outcomes"
                               if self.mode in ("local","cascaded","ml") and self.ml_controller.available
                               else "ML model unavailable; rolling-horizon queue-cost fallback"
                           ),
                           minimum_remaining=max(0,MIN_GREEN-(self.n-sup.start)) if sup.stage=="green" else 0,
                           green_end=sup.start+sup.plan if sup.stage=="green" else None,
                           fairness=wait[s][1-sup.axis]>=40,
                           state=traci.trafficlight.getRedYellowGreenState(s))
        self.events = self.events[-50:]
        return dict(time=self.n,vehicles=vehicles,signals=info,predictions=predictions,messages=messages,events=self.events,
                    entered=self.entered,completed=self.completed,boundary=self.boundary,
                    junctions={s:traci.junction.getPosition(s) for s in SIGNALS},prediction_matches=self.error_count,arrival_mae=self.error_sum/self.error_count if self.error_count else None,metrics=dict(speed=sum(v["speed"] for v in vehicles)/max(1,len(vehicles)),
                                 wait=vehicle_wait/max(1,len(vehicles)),queue=sum(map(sum,queues.values())),
                                 entered_min=sum(t[0] for t in self.flow),throughput=sum(t[1] for t in self.flow),
                                 density=len(vehicles)/10.8),mode=self.mode,demand=demand_log,disturbance=self.action,target=self.target)

    def packet(self,a,b,group):
        return dict(source=a,destination=b,count=len(group),members=[v for _,v in group],
                    arrival=self.n+round(sum(t for t,_ in group)/len(group)),window=[self.n+group[0][0],self.n+group[-1][0]])

    def close(self):
        traci.close()


