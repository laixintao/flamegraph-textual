import json
import logging
from typing import Dict, List, Optional

from rich.text import Text

from flamegraph_textual.models import Frame, Profile, SampleType

logger = logging.getLogger(__name__)

_UNIT_MAP = {
    "microseconds": ("time", "microseconds"),
    "milliseconds": ("time", "milliseconds"),
    "nanoseconds": ("time", "nanoseconds"),
    "seconds": ("time", "seconds"),
    "bytes": ("memory", "bytes"),
    "none": ("samples", "count"),
}


class SpeedscopeFrame(Frame):
    def __init__(self, name, _id, file=None, line=None, **kwargs):
        super().__init__(name, _id, **kwargs)
        self.file = file
        self.line = line

    def render_one_frame_detail(self, frame, sample_index: int, sample_unit: str):
        parts = [frame.name]
        if frame.file:
            loc = frame.file
            if frame.line is not None:
                loc = f"{loc}:{frame.line}"
            parts.append(f"  {loc}")
        return [Text("\n".join(parts) + "\n")]


class SpeedscopeParser:
    def __init__(self, filename) -> None:
        self.filename = filename
        self.next_id = 0
        self.root = SpeedscopeFrame("root", _id=self._next_id(), values=[0])
        self.root.root = self.root
        self.highest = 0
        self.id_store: Dict[int, Frame] = {self.root._id: self.root}

    def _next_id(self) -> int:
        i = self.next_id
        self.next_id += 1
        return i

    def parse(self, data: bytes) -> Profile:
        doc = json.loads(data)
        shared_frames: List[dict] = doc["shared"]["frames"]
        profiles: List[dict] = doc["profiles"]
        active_idx: int = doc.get("activeProfileIndex", 0)
        profile_doc = profiles[active_idx]

        unit = profile_doc.get("unit", "none")
        sample_type_name, sample_unit = _UNIT_MAP.get(unit, ("samples", unit))

        profile_type = profile_doc["type"]
        if profile_type == "sampled":
            total_sample = self._parse_sampled(profile_doc, shared_frames)
        elif profile_type == "evented":
            total_sample = self._parse_evented(profile_doc, shared_frames)
        else:
            raise ValueError(f"Unknown speedscope profile type: {profile_type!r}")

        return Profile(
            filename=self.filename,
            root_stack=self.root,
            highest_lines=self.highest,
            total_sample=total_sample,
            sample_types=[SampleType(sample_type_name, sample_unit)],
            id_store=self.id_store,
        )

    def _build_chain(
        self, frame_indices: List[int], shared_frames: List[dict], value: int
    ) -> Optional[SpeedscopeFrame]:
        """Build a linked chain of SpeedscopeFrames (outermost first) from frame indices."""
        if not frame_indices:
            return None

        head = None
        prev = None
        depth = len(frame_indices)

        for idx in frame_indices:
            raw = shared_frames[idx]
            frame = SpeedscopeFrame(
                name=raw["name"],
                _id=self._next_id(),
                file=raw.get("file"),
                line=raw.get("line"),
                values=[value],
                root=self.root,
            )
            self.id_store[frame._id] = frame
            if prev is not None:
                prev.children = [frame]
                frame.parent = prev
            else:
                head = frame
            prev = frame

        if depth > self.highest:
            self.highest = depth

        return head

    def _parse_sampled(self, profile: dict, shared_frames: List[dict]) -> int:
        samples: List[List[int]] = profile["samples"]
        weights: List[float] = profile["weights"]
        total = 0

        for stack, weight in zip(samples, weights):
            if not stack or weight <= 0:
                continue
            iweight = int(weight)
            chain_head = self._build_chain(stack, shared_frames, iweight)
            if chain_head:
                self.root.pile_up(chain_head)
                self.root.values[0] += iweight
                total += 1

        return total

    def _parse_evented(self, profile: dict, shared_frames: List[dict]) -> int:
        # stack entries: [frame_idx, start_at, children_total_duration]
        stack: List[List] = []
        total = 0

        for event in profile["events"]:
            etype = event["type"]
            at = event["at"]
            frame_idx = event["frame"]

            if etype == "O":
                stack.append([frame_idx, at, 0])
            elif etype == "C":
                if not stack:
                    logger.warning("Unmatched close event for frame %d at %s", frame_idx, at)
                    continue
                entry = stack.pop()
                open_frame_idx, start_at, children_dur = entry
                total_dur = at - start_at
                self_dur = total_dur - children_dur

                # Propagate this frame's total duration to the parent
                if stack:
                    stack[-1][2] += total_dur

                if self_dur <= 0:
                    continue

                iself = int(self_dur)
                # Build chain: frames still on stack (outermost-first) + closed frame
                frame_indices = [e[0] for e in stack] + [open_frame_idx]
                chain_head = self._build_chain(frame_indices, shared_frames, iself)
                if chain_head:
                    self.root.pile_up(chain_head)
                    self.root.values[0] += iself
                    total += 1

        return total

    @classmethod
    def validate(cls, content: bytes) -> bool:
        try:
            doc = json.loads(content)
        except Exception:
            return False

        if not isinstance(doc, dict):
            return False

        schema = doc.get("$schema", "")
        if "speedscope" in schema:
            return True

        if "profiles" in doc and "shared" in doc:
            shared = doc["shared"]
            if isinstance(shared, dict) and "frames" in shared:
                return True

        return False
