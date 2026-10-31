

class RecentSnapshots:
    def __init__(self):
        self._items = []

    @property
    def items(self):
        return tuple(self._items)

    def add(self, snapshot):
        self._items = [item for item in self._items if item.snapshot_id != snapshot.snapshot_id]
        self._items.insert(0, snapshot)
        del self._items[10:]
