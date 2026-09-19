from dataclasses import dataclass


@dataclass(frozen=True)
class Move:
    x1: int
    y1: int
    x2: int
    y2: int

    def as_dict(self):
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}

    @classmethod
    def from_dict(cls, data):
        return cls(data["x1"], data["y1"], data["x2"], data["y2"])
