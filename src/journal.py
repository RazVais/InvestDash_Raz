"""Trading journal persistence — the only module that reads/writes JOURNAL_FILE.

Both the AI journal tab and the stops tab append to the same file, so all
writes go through here. A corrupt file is never overwritten: reads raise
JournalReadError and callers must not save until the user fixes the file.
"""

import json
import os
import shutil
from typing import Dict, List

from src.config import JOURNAL_FILE
from src.logger import get_logger

_log = get_logger(__name__)


class JournalReadError(Exception):
    """The journal file exists but could not be parsed."""


def load_journal() -> List[Dict]:
    """Return all journal entries (newest first). [] if the file doesn't exist.

    Raises JournalReadError on a corrupt file after copying it to .bak.
    """
    if not JOURNAL_FILE.exists():
        return []
    try:
        entries = json.loads(JOURNAL_FILE.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("journal root is not a list")
        return entries
    except Exception as exc:
        backup = JOURNAL_FILE.with_name(JOURNAL_FILE.name + ".bak")
        try:
            shutil.copy2(JOURNAL_FILE, backup)
        except Exception:
            _log.error("Could not back up corrupt journal", exc_info=True)
        _log.error("Journal file unreadable — writes blocked", exc_info=True)
        raise JournalReadError(str(exc)) from exc


def save_journal(entries: List[Dict]) -> None:
    """Atomically replace the journal file with entries."""
    tmp = JOURNAL_FILE.with_name(JOURNAL_FILE.name + ".tmp")
    tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, JOURNAL_FILE)
    _sync_session(entries)


def prepend_entry(entry: Dict) -> bool:
    """Add entry at the top of the journal. Returns False (no write) if the file is corrupt."""
    try:
        entries = load_journal()
    except JournalReadError:
        return False
    entries.insert(0, entry)
    save_journal(entries)
    return True


def _sync_session(entries: List[Dict]) -> None:
    """Keep the AI journal tab's in-session copy current, so its next save
    doesn't drop entries written by another tab."""
    try:
        import streamlit as st
        if "tj_trades" in st.session_state:
            st.session_state.tj_trades = list(entries)
    except Exception:
        pass
