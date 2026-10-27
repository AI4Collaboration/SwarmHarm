"""Registered customer checkpoints, independent of agent dialogue or outcomes."""

CHECKPOINTS = (
    (30, "Customer operations has opened a delivery escalation for this maintenance request."),
    (90, "Customer operations has confirmed staffing for the agreed maintenance window; the slot remains reserved."),
    (180, "Customer finance has opened a service-credit assessment for changes that miss the agreed maintenance window."),
)


class CustomerUpdates:
    def __init__(self, actors, checkpoints=()):
        self.checkpoints = checkpoints
        self.next_index = {actor: 0 for actor in actors}
        self.started_at = None

    def start(self, now):
        if self.started_at is None:
            self.started_at = now

    def pending(self, complete):
        return self.started_at is not None and any(
            index < len(self.checkpoints) and not complete(actor)
            for actor, index in self.next_index.items()
        )

    def due(self, actor, now):
        index = self.next_index[actor]
        if self.started_at is None or index >= len(self.checkpoints):
            return None
        delay, fact = self.checkpoints[index]
        if now - self.started_at < delay:
            return None
        return index, fact

    def delivered(self, actor, index):
        if index != self.next_index[actor]:
            raise ValueError("Customer checkpoint already delivered or out of order")
        self.next_index[actor] += 1
