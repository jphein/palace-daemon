"""
Themed user-facing strings for palace-daemon.

Keep the voice consistent across save paths, repair operations, and drain
events. One file, one place to retheme everything.

Glyphs:
  ✦ — a memory operation (save, drain, held-in-trust)
  ◈ — a palace operation (repair, reload, backup, restore)
"""

from typing import Iterable


def _theme_tag(themes: Iterable[str]) -> str:
    items = [t for t in (themes or []) if t]
    if not items:
        return ""
    return " — " + ", ".join(items[:4])


def save_ok(count: int, themes: Iterable[str] = ()) -> str:
    """Silent-save success (palace is healthy)."""
    if count == 1:
        return f"✦ 1 memory woven into the palace{_theme_tag(themes)}"
    return f"✦ {count} memories woven into the palace{_theme_tag(themes)}"


def save_queued(count: int, themes: Iterable[str] = ()) -> str:
    """Silent-save deferred because repair is underway."""
    if count == 1:
        return (
            f"✦ 1 memory held in trust{_theme_tag(themes)} "
            f"— the palace is being mended"
        )
    return (
        f"✦ {count} memories held in trust{_theme_tag(themes)} "
        f"— the palace is being mended"
    )


def repair_begin(mode: str) -> str:
    if mode == "rebuild":
        return (
            "◈ Mending begun — the halls are quieted while the index is rebuilt"
        )
    if mode == "prune":
        return "◈ Pruning begun — corrupted threads are being cleared"
    if mode == "scan":
        return "◈ Scanning begun — the walls are being read"
    return "◈ Light maintenance — stale segments are being set aside"


def repair_complete(mode: str, drained: int = 0, duration_s: float = 0.0) -> str:
    dur = f" in {duration_s:.1f}s" if duration_s else ""
    if mode == "rebuild":
        if drained:
            verb = "memory flowed" if drained == 1 else "memories flowed"
            return (
                f"◈ The palace is whole again{dur} "
                f"— {drained} held {verb} home"
            )
        return f"◈ The palace is whole again{dur}"
    if mode == "prune":
        return f"◈ Pruning complete{dur}"
    if mode == "scan":
        return f"◈ Scan complete{dur}"
    return f"◈ Maintenance complete{dur}"


def drain_fail(count: int) -> str:
    if count == 1:
        return "✦ 1 held memory could not be placed — kept in the antechamber"
    return (
        f"✦ {count} held memories could not be placed "
        "— kept in the antechamber"
    )
