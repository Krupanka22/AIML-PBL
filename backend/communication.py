"""One-tick delivery delay, replaceable link observations and simulation-time expiry."""
class LinkBus:
    def __init__(self):
        self.pending = []
        self.latest = {}
        self.version = 0

    def publish(self, now, source, destination, kind, data):
        self.version += 1
        self.pending.append(dict(time=now, version=self.version, source=source,
                                 destination=destination, kind=kind, data=data))

    def receive(self, now, disconnected):
        delivered = []
        self.latest = {k:m for k,m in self.latest.items() if now-m["time"] <= 4 and disconnected not in k[:2]}
        for m in self.pending:
            key = m["source"],m["destination"],m["kind"]
            if disconnected not in key[:2] and now-m["time"]<=4:
                self.latest[key] = m
                delivered.append(m)
        self.pending.clear()
        return delivered
