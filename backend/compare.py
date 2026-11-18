"""Run equal-demand controller trials and export measured metrics."""
import argparse
import csv
from collections import Counter
from simulation import Simulation, traci


def trial(mode, seed, seconds, profile):
    sim = Simulation(seed, mode, profile)
    started, previous, durations, directions = {}, {}, set(), set()
    stopped = turns = collisions = 0
    queue = [0,0]
    delays = [0,0]
    trips = []
    try:
        for _ in range(seconds):
            frame = sim.tick()
            for v in traci.simulation.getDepartedIDList():
                started[v] = sim.n
                route = traci.vehicle.getRoute(v)
                turns += any((edge.split("_")[0].endswith(("N","S")) or edge.endswith(("N","S"))) for edge in route) and len(route)>2
            for v in traci.simulation.getArrivedIDList():
                trips.append(sim.n-started.pop(v))
            speeds = {v["id"]:v["speed"] for v in frame["vehicles"]}
            stopped += sum(speed < .1 <= previous.get(v,0) for v,speed in speeds.items())
            previous = speeds
            collisions += traci.simulation.getCollidingVehiclesNumber()
            for signal, obs in frame["signals"].items():
                for k in range(2):
                    queue[k] += obs["queue"][k]
                    delays[k] += obs["wait"][k]
                if obs["stage"] == "green":
                    directions.add((signal,obs["axis"]))
                    durations.add(obs["approved"])
        return dict(mode=mode,seed=seed,seconds=seconds,issued=sim.issued,entered=sim.entered,completed=len(trips),
                    mean_trip_seconds=round(sum(trips)/len(trips),2) if trips else None,stops=stopped,
                    mean_corridor_queue=queue[0]/seconds,mean_cross_queue=queue[1]/seconds,
                    mean_max_corridor_wait=delays[0]/(4*seconds),mean_max_cross_wait=delays[1]/(4*seconds),
                    serviced_phases=len(directions),distinct_plans=len(durations),turning_routes=turns,collisions=collisions)
    finally:
        sim.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    for i, mode in enumerate(("fixed","local","cascaded")):
        row = trial(mode,args.seed,args.seconds,"moderate")
        print(row,flush=True)
        with open("comparison.csv","w" if i==0 else "a",newline="") as out:
            writer = csv.DictWriter(out,fieldnames=row)
            if i==0:
                writer.writeheader()
            writer.writerow(row)
