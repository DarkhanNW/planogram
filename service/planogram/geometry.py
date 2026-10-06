from pydantic import BaseModel


class Box(BaseModel):
    """An axis-aligned rectangle in Shelf Photo pixels."""

    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center_y(self) -> float:
        return self.y + self.h / 2

    def clipped(self, width: int, height: int) -> "Box | None":
        x, y = max(self.x, 0), max(self.y, 0)
        right, bottom = min(self.right, width), min(self.bottom, height)
        if right <= x or bottom <= y:
            return None
        return Box(x=x, y=y, w=right - x, h=bottom - y)

    @staticmethod
    def union(boxes: "list[Box]") -> "Box":
        x, y = min(b.x for b in boxes), min(b.y for b in boxes)
        right, bottom = max(b.right for b in boxes), max(b.bottom for b in boxes)
        return Box(x=x, y=y, w=right - x, h=bottom - y)
