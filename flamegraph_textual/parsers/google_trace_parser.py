import json
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from rich.text import Text

from flamegraph_textual.models import Frame, Profile, SampleType

logger = logging.getLogger(__name__)

_DISPLAY_UNIT_MAP = {
    "ms": ("time", "milliseconds"),
    "us": ("time", "microseconds"),
    "ns": ("time", "nanoseconds"),
}


class GoogleTraceFrame(Frame):
    def render_one_frame_detail(self, frame, sample_index: int, sample_unit: str):
        return [Text(f"{frame.name}\n")]


class GoogleTraceParser:
    def __init__(self, filename) -> None:
        self.filename = filename
        self.next_id = 0
        self.root = GoogleTraceFrame("root", _id=self._next_id(), values=[0])
        self.root.root = self.root
        self.highest = 0
        self.id_store: Dict[int, Frame] = {self.root._id: self.root}

    def _next_id(self) -> int:
        i = self.next_id
        self.next_id += 1
        return i

    def parse(self, data: bytes) -> Profile:
        doc = json.loads(data)

        if isinstance(doc, list):
            events = doc
            display_time_unit = "us"
        else:
            events = doc.get("traceEvents", [])
            display_time_unit = doc.get("displayTimeUnit", "us")

        # Collect thread/process names from metadata events
        thread_names: Dict[Tuple[int, int], str] = {}
        process_names: Dict[int, str] = {}
        for ev in events:
            if not isinstance(ev, dict) or ev.get("ph") != "M":
                continue
            pid = ev.get("pid", 0)
            tid = ev.get("tid", 0)
            args = ev.get("args") or {}
            meta_name = ev.get("name", "")
            if meta_name == "thread_name":
                thread_names[(pid, tid)] = args.get("name", f"{pid}:{tid}")
            elif meta_name == "process_name":
                process_names[pid] = args.get("name", str(pid))

        # Group B/E/X events by (pid, tid)
        thread_events: Dict[Tuple[int, int], List[dict]] = defaultdict(list)
        for ev in events:
            if isinstance(ev, dict) and ev.get("ph") in ("B", "E", "X"):
                pid = ev.get("pid", 0)
                tid = ev.get("tid", 0)
                thread_events[(pid, tid)].append(ev)

        sample_type_name, sample_unit = _DISPLAY_UNIT_MAP.get(
            display_time_unit, ("time", "microseconds")
        )
        total_sample = 0

        for (pid, tid) in sorted(thread_events.keys()):
            thread_name = thread_names.get((pid, tid))
            if thread_name is None:
                proc = process_names.get(pid)
                thread_name = f"{proc} (tid={tid})" if proc else f"pid={pid} tid={tid}"

            thread_frame, n_samples = self._process_thread(
                thread_events[(pid, tid)], thread_name
            )
            if thread_frame.children:
                self.root.pile_up(thread_frame)
                self.root.values[0] += thread_frame.values[0]
                total_sample += n_samples

        return Profile(
            filename=self.filename,
            root_stack=self.root,
            highest_lines=self.highest,
            total_sample=total_sample,
            sample_types=[SampleType(sample_type_name, sample_unit)],
            id_store=self.id_store,
        )

    def _process_thread(
        self, events: List[dict], thread_name: str
    ) -> Tuple[GoogleTraceFrame, int]:
        """Process all events for one thread. Returns (thread_frame, sample_count)."""
        thread_frame = GoogleTraceFrame(
            thread_name, _id=self._next_id(), values=[0], root=self.root
        )
        self.id_store[thread_frame._id] = thread_frame

        # Convert X events into synthetic B/E pairs; keep original B/E events.
        normalized: List[dict] = []
        for ev in events:
            ph = ev.get("ph")
            if ph == "X":
                ts = ev.get("ts", 0)
                dur = ev.get("dur", 0)
                name = ev.get("name", "")
                normalized.append({"ph": "B", "name": name, "ts": ts, "_dur": dur})
                normalized.append({"ph": "E", "name": name, "ts": ts + dur})
            elif ph in ("B", "E"):
                normalized.append(ev)

        # Sort: ascending ts; at equal ts, B before E;
        # among B events at same ts, larger original duration first (outer frame).
        normalized.sort(
            key=lambda e: (e.get("ts", 0), 0 if e["ph"] == "B" else 1, -(e.get("_dur", 0)))
        )

        # stack entries: [name, start_ts, children_total_duration]
        stack: List[List] = []
        sample_count = 0

        for ev in normalized:
            ph = ev["ph"]
            if ph == "B":
                stack.append([ev.get("name", ""), ev.get("ts", 0), 0])
            elif ph == "E":
                if not stack:
                    continue
                name, start_ts, children_dur = stack.pop()
                total_dur = ev.get("ts", 0) - start_ts
                self_dur = total_dur - children_dur

                if stack:
                    stack[-1][2] += total_dur

                if self_dur <= 0:
                    continue

                iself = int(self_dur)
                frame_names = [e[0] for e in stack] + [name]
                chain_head = self._build_chain(frame_names, iself)
                if chain_head:
                    thread_frame.pile_up(chain_head)
                    thread_frame.values[0] += iself
                    sample_count += 1

        return thread_frame, sample_count

    def _build_chain(
        self, names: List[str], value: int
    ) -> Optional[GoogleTraceFrame]:
        """Build a linked chain of frames outermost-first from function names."""
        if not names:
            return None

        # Depth in full tree = 1 (thread frame) + len(names)
        total_depth = 1 + len(names)
        if total_depth > self.highest:
            self.highest = total_depth

        head: Optional[GoogleTraceFrame] = None
        prev: Optional[GoogleTraceFrame] = None
        for name in names:
            frame = GoogleTraceFrame(
                name=name,
                _id=self._next_id(),
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

        return head

    @classmethod
    def validate(cls, content: bytes) -> bool:
        try:
            doc = json.loads(content)
        except Exception:
            return False

        if isinstance(doc, list):
            events = doc
        elif isinstance(doc, dict):
            if "traceEvents" not in doc:
                return False
            events = doc["traceEvents"]
        else:
            return False

        if not isinstance(events, list):
            return False

        # Must have at least one B/E/X event
        return any(
            isinstance(e, dict) and e.get("ph") in ("B", "E", "X")
            for e in events[:200]
        )
