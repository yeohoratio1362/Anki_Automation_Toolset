from dataclasses import dataclass, field
from typing import Set, List

@dataclass
class Note:
    # Represents Anki Note
    nid: int
    tags: Set[str] = field(default_factory=set)
    fields: List[str] = field(default_factory=list)

    @classmethod
    def from_db_row(cls, row):
        # Initialize note class
        nid, tags_str, flds_str = row
        # Cleanly parse spaced tags into a unique set
        tags = set(t for t in tags_str.split(" ") if t)
        # Anki separates field contents with unit separator control characters (\x1f)
        fields = flds_str.split("\x1f")
        return cls(nid=nid, tags=tags, fields=fields)

    @property
    def primary_field(self) -> str:
        # Helper to get the first field (usually the front of the card)
        return self.fields[0] if self.fields else ""

    @property
    def tags_string(self) -> str:
        # Formats the tags back into Anki's database
        return f" {' '.join(sorted(self.tags))} " if self.tags else ""


@dataclass
class Card:
    # Represents an Anki Card containing review history and deck information
    cid: int
    nid: int
    did: int
    deck_name: str = ""
    reviews: int = 0
    fails: int = 0
    avg_time_ms: float = 0.0

    @classmethod
    def from_db_row(cls, row, deck_name=""):
        # Initialize card class
        cid, nid, did, total, fails, avg_time = row
        return cls(
            cid=cid,
            nid=nid,
            did=did,
            deck_name=deck_name,
            reviews=total,
            fails=fails,
            avg_time_ms=avg_time
        )

    @property
    def fail_rate(self) -> float:
        # Calculates card failure rate
        if self.reviews == 0:
            return 0.0
        return self.fails / self.reviews

    @property
    def fail_percentage(self) -> float:
        return self.fail_rate * 100.0

    @property
    def avg_time_sec(self) -> float:
        # SQLite milliseconds review logs to seconds
        return self.avg_time_ms / 1000.0
