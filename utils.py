from typing import List
import tkinter as tk
from tkinter import filedialog
from uuid import uuid4

def pick_folder(title="Select a folder"):
    # Opens a native OS dialog on the machine running the Streamlit server
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # bring dialog to front
    path = filedialog.askdirectory(title=title, mustexist=False)  # allow creating new folder
    root.destroy()
    return path or ""

def render_query_builder(app):
    """Renders the dynamic Search_query UI and updates session state.


    UX spec:
    - Always show a text box.
    - A ⊕ button after it adds another row.
    - Every additional row begins with an operator select (and/or) then a text box.
    - Can be repeated indefinitely.
    """
    rows = app.session_state.settings.query_rows

    # Ensure every row has a stable unique id
    for row in rows:
        if "id" not in row:
            row["id"] = str(uuid4())

    app.markdown("**Search_query**")


    to_delete: List[int] = []
    add_requested = False


    for i, row in enumerate(rows):
        rid = row["id"]  # stable id for this row
        cols = app.columns([2 if i > 0 else 0.0001, 7, 1, 1], gap="small")


        # Operator (rows after the first)
        if i == 0:
            cols[0].markdown("&nbsp;", unsafe_allow_html=True)
        else:
            row["op"] = cols[0].selectbox(
                " ",
                options=["and", "or"],
                index=0 if row.get("op", "and") == "and" else 1,
                key=f"op_{i}",
                label_visibility="collapsed",
            )


        # Text input
        row["text"] = cols[1].text_input(
            "Search term",
            value=row.get("text", ""),
            key=f"q_{i}",
            placeholder="Type a term...",
            label_visibility="collapsed",
        )


        # Add (+) only on the last row
        if i == len(rows) - 1:
            if cols[2].form_submit_button(f"⊕ {i}", use_container_width=True):
                add_requested = True
        else:
            cols[2].markdown("&nbsp;", unsafe_allow_html=True)


        # Remove (−) except on the first row
        if i > 0:
            if cols[3].form_submit_button(f"− {i}", use_container_width=True):
                to_delete.append(i)
        else:
            cols[3].markdown("&nbsp;", unsafe_allow_html=True)


    # Apply add/remove after rendering to avoid key clashes
    if to_delete:
        for idx in sorted(to_delete, reverse=True):
            del rows[idx]
    if add_requested:
        rows.append({"id": str(uuid4()), "op": "or", "text": ""})


    # Build combined query string
    parts: List[str] = []
    for i, row in enumerate(rows):
        t = (row.get("text") or "").strip()
        if not t:
            continue
        if i == 0:
            parts.append(t)
        else:
            parts.append(f" {row.get('op','and')} {t}")
    combined = "".join(parts)


    # Persist
    app.session_state.settings.query_rows = rows

    # Preview
    app.caption("Combined query (preview):")
    app.code(combined or "", language="text")

from typing import List, Dict

def evaluate_query(line: str, query_rows: List[Dict], *, case_sensitive: bool = False) -> bool:
    """
    Evaluate a sequence of query rows against a line of text.
    Precedence: AND binds tighter than OR.

    query_rows example:
      [{"op": "initial", "text": "L1"},
       {"op": "and",     "text": "L2"},
       {"op": "or",      "text": "L3"}]

    Returns True iff:
      (L1 in line AND L2 in line) OR (L3 in line)

    Notes:
    - 'initial' (spelled \"initial\" or the common typo \"inital\") and missing ops
      are treated like the first term (no operator before it).
    - Empty/blank text rows are ignored.
    - If no valid terms remain, returns True (match-all).
    """

    # Normalize line for case sensitivity
    haystack = line if case_sensitive else line.lower()

    # Build groups of AND-terms separated by OR
    groups: List[List[str]] = [[]]
    for i, row in enumerate(query_rows or []):
        if row["op"] and row["text"]:
            term = (row.get("text") or "").strip()
            if not term:
                continue

            op = (row.get("op") or "").strip().lower()
            is_initial = (i == 0) or op in ("initial", "inital", "")
            if is_initial or op == "and":
                groups[-1].append(term if case_sensitive else term.lower())
            elif op == "or":
                groups.append([term if case_sensitive else term.lower()])
            else:
                # Unknown operator -> treat as AND
                groups[-1].append(term if case_sensitive else term.lower())

    # Remove empties
    groups = [g for g in groups if g]

    # No terms => match everything
    if not groups:
        return True

    # Evaluate: any( all(term in line) for group in groups )
    return any(all(t in haystack for t in group) for group in groups)
