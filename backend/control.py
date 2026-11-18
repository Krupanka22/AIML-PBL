"""Discrete rolling-horizon queue optimizer and independent two-phase supervisor."""
from math import inf

MIN_GREEN, MAX_GREEN, YELLOW, CLEAR = 10, 45, 3, 2


def optimize(axis, elapsed, queues, rates, arrivals, capacity, waits):
    best = (inf, MIN_GREEN)
    for duration in range(max(MIN_GREEN, elapsed), MAX_GREEN + 1):
        q = list(queues)
        cost = 0
        for t in range(55):
            green = axis if t < duration-elapsed else (1-axis if t >= duration-elapsed+YELLOW+CLEAR else None)
            for k in (0, 1):
                q[k] += rates[k] + (arrivals.get(t, 0) if k == 0 else 0)
                if k == green:
                    q[k] = max(0, q[k] - (capacity if k == 0 else 1.6))
            cost += sum(n*n*(1 + wait/MAX_GREEN) for n, wait in zip(q, waits))
        best = min(best, (cost, duration))
    return best[1]


class Supervisor:
    def __init__(self):
        self.axis, self.start, self.plan = 0, 0, 20
        self.stage = "green"

    def advance(self, now, recommendation, opposing_wait):
        elapsed = now-self.start
        self.plan = max(MIN_GREEN, min(MAX_GREEN, recommendation))
        if opposing_wait >= 40:
            self.plan = MIN_GREEN
        if self.stage == "green" and elapsed >= self.plan:
            self.stage = "yellow"
        elif self.stage == "yellow" and elapsed >= YELLOW:
            self.stage = "clear"
        elif self.stage == "clear" and elapsed >= CLEAR:
            self.axis = 1-self.axis
            self.stage, self.plan = "green", 20
        else:
            return
        self.start = now

