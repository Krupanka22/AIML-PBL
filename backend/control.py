"""Discrete rolling-horizon queue optimizer and independent two-phase supervisor."""
from math import inf
from pathlib import Path
import random

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


class MLGreenController:
    """Supervised machine-learning controller for green-duration recommendations."""

    def __init__(self, model_path=None):
        self.model = None
        self.available = False
        self.model_path = model_path or Path(__file__).resolve().parents[1] / "models" / "green_duration.joblib"
        self._load()

    def _load(self):
        try:
            import joblib
            self.model = joblib.load(self.model_path)
            self.available = True
        except (ImportError, FileNotFoundError, OSError):
            self.available = False

    def recommend(self, axis, elapsed, queues, rates, incoming, capacity, waits):
        features = [[
            axis,
            elapsed,
            queues[0],
            queues[1],
            rates[0],
            rates[1],
            sum(incoming.values()) if isinstance(incoming, dict) else incoming,
            capacity,
            waits[0],
            waits[1],
        ]]
        if not self.available:
            return optimize(axis, elapsed, queues, rates, incoming if isinstance(incoming, dict) else {}, capacity, waits)
        try:
            duration = round(float(self.model.predict(features)[0]))
            return max(MIN_GREEN, min(MAX_GREEN, duration))
        except (AttributeError, ValueError, TypeError):
            return optimize(axis, elapsed, queues, rates, incoming if isinstance(incoming, dict) else {}, capacity, waits)

    def train(self, samples=1000):
        try:
            import joblib
            from sklearn.ensemble import RandomForestRegressor
        except ImportError as error:
            raise RuntimeError("Install scikit-learn and joblib to train the signal model") from error

        rng = random.Random(42)
        rows, labels = [], []
        for _ in range(samples):
            axis = rng.randrange(2)
            elapsed = rng.randrange(0, 46)
            queues = [rng.randrange(0, 31), rng.randrange(0, 31)]
            rates = [rng.uniform(0, .8), rng.uniform(0, .8)]
            incoming = {rng.randrange(0, 55): rng.randrange(1, 9) for _ in range(rng.randrange(0, 5))}
            capacity = rng.uniform(.2, 1.6)
            waits = [rng.uniform(0, 60), rng.uniform(0, 60)]
            duration = optimize(axis, elapsed, queues, rates, incoming, capacity, waits)
            rows.append([axis, elapsed, *queues, *rates, sum(incoming.values()), capacity, *waits])
            labels.append(duration)

        self.model = RandomForestRegressor(
            n_estimators=120,
            max_depth=12,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=1,
        )
        self.model.fit(rows, labels)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, self.model_path)
        self.available = True


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

