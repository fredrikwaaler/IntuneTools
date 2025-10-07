from __future__ import annotations
import uuid
from pathlib import Path
from utils import render_query_builder, pick_folder
import io
from streamlit.runtime.scriptrunner import add_script_run_ctx
from pdf2markdown import get_cis_recommendation_mappings, get_markdown_from_cis_section
import re
import os
import queue
import threading
from dataclasses import dataclass, asdict, field
from typing import Optional, Tuple, Callable, List, Dict
import streamlit as st

# -------------------------------
# Config & Data
# -------------------------------
DEFAULT_LAYOUT = (20, 40, 40)  # percentages

@dataclass
class ToolInfo:
    def __init__(self, title, tool_name, about, settings, input_builder, outputs, output_builder):
        self.title = title
        self.tool_name = tool_name
        self.about = about
        self.settings = settings
        self.input_builder = input_builder
        self.outputs = outputs
        self.output_builder = output_builder

@dataclass
class PdfDoc2MarkdownSettings:
    gpt_key: str = ""
    toc_start: int = 1
    toc_end: int = 1
    query_rows: List[Dict[str, str]] = field(default_factory=lambda: [{"op": "initial", "text": ""}])
    rec_type: str = ""
    rec_grouping: str = ""
    output_folder: str = os.getcwd()

@dataclass
class PdfDoc2MarkdownOutput:
    mappings: Optional[List[Dict[str, str]]] = None
    output_files: List[Dict] = field(default_factory=lambda: [])


def build_PdfDoc2Markdown_input_section(app):
    with app.form("input_preview_form", clear_on_submit=False):
        st.markdown("#### Section mappings")
        uploaded_pdf = app.file_uploader("Upload PDF", type=["pdf"], accept_multiple_files=False)

        c1, c2 = app.columns(2)
        with c1:
            toc_start = app.number_input("TOC start page (1-based)", min_value=1, step=1,
                                        value=app.session_state.settings.toc_start)
        with c2:
            toc_end = app.number_input("TOC end page (1-based)", min_value=1, step=1,
                                      value=app.session_state.settings.toc_end)

        c1, c2 = app.columns(2)
        with c1:
            rec_type = app.selectbox("Recommendation type", options=["CIS"], index=0, help="Currently only available for CIS.")
        with c2:
            # TODO: Add other here, like "Subsection"
            rec_grouping = app.selectbox("Recommendation grouping", options=["Outermost", "Innermost"], index=0, help="The method for grouping recommendations into markdown tables")

        render_query_builder(app)

        def disabled_submit_sections():
            return ("" in [rec_type, rec_grouping]) or uploaded_pdf is None # TODO: Query rows as well
        submitted_get_sections = app.form_submit_button("Process inputs", disabled=disabled_submit_sections())

        if submitted_get_sections:
            with app.spinner("Mapping sections from table of content..."):
                pdf_file = io.BytesIO(uploaded_pdf.read())
                mapping_output = get_cis_recommendation_mappings(pdf_file, toc_start, toc_end, rec_grouping, app.session_state.settings.query_rows)
                app.session_state.outputs.mappings = mapping_output


    with app.form("output_preview_form", clear_on_submit=False):
        st.markdown("#### Automatic markdown")
        gpt_key = app.text_input("GPT KEY", type="password", help="If your converter uses OpenAI, paste a key here.")

        c1, c2 = app.columns([6, 1])
        with c1:
            output_folder = app.text_input("Output folder", value=app.session_state.settings.output_folder, placeholder="C:\\path\\to\\folder")
        with c2:
            browse_clicked = app.form_submit_button("Browse…")
            if browse_clicked:
                chosen = pick_folder("Choose output folder")
                if chosen:
                    app.session_state.settings.output_folder = chosen
                    app.rerun()

        def disabled_submit_markdown():
            if app.session_state.outputs.mappings is not None:
                return len(app.session_state.outputs.mappings) == 0
            return True
        submitted_auto_markdown = app.form_submit_button("Get markdown", disabled=disabled_submit_markdown())

        if submitted_auto_markdown:
            with app.spinner("Processing pdf to markdown..."):
                job_id = str(uuid.uuid4())
                app.session_state.gen.update({
                    "id": job_id,
                    "running": True,
                    "total": len(app.session_state.outputs.mappings),
                })
                t = threading.Thread(
                    target=run_generation,
                    args=(app, gpt_key, Path(output_folder), job_id),
                    daemon=True,
                )
                add_script_run_ctx(t)
                t.start()
                app.success("Started generation. Files will appear as ready.")

        # Persist to session state
        app.session_state.settings.gpt_key = gpt_key
        app.session_state.settings.pdf_filename = getattr(uploaded_pdf, "name", None)
        app.session_state.settings.toc_start = int(toc_start)
        app.session_state.settings.toc_end = int(toc_end)
        app.session_state.settings.rec_type = rec_type
        app.session_state.settings.rec_grouping = rec_grouping
        app.session_state.settings.output_folder = output_folder


PdfDoc2MarkdownToolInfo = ToolInfo(**{
    "tool_name": "PdfDoc2Markdown",
    "title": "🧰 PdfDoc2Markdown",
    "about": "Convert PDF documents to Markdown tables",
    "settings": PdfDoc2MarkdownSettings(),
    "input_builder": build_PdfDoc2Markdown_input_section,
    "outputs": PdfDoc2MarkdownOutput(),
    "output_builder": None
})

def run_generation(app, gpt_key, out_dir: Path, job_id: str):
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, s in enumerate(st.session_state.outputs.mappings, start=1):
        p = get_markdown_from_cis_section(gpt_key, str(out_dir), s)
        with st.session_state.outputs_lock:
            st.session_state.outputs.output_files.append(
                {"path": str(p), "name": s["name"]}
            )
    # mark done
    st.session_state.gen_job["running"] = False

IntuneAssessmentToolInfo = ToolInfo(**{
    "tool_name": "IntuneAssessmentTool",
    "title": "🧰 Intune Assessment Tool",
    "about": "Tool to compare baseline policies against a customers tenant",
    "settings": None,
    "input_builder": lambda: None,
    "outputs": None,
    "output_builder": None,
})


ACTIVE_TOOL = PdfDoc2MarkdownToolInfo
ALL_TOOLS = {t.tool_name: t for t in [PdfDoc2MarkdownToolInfo, IntuneAssessmentToolInfo]}

# -------------------------------
# UI Helpers
# -------------------------------

def init_state():
    """
    Initializes the application state by setting
    Default Tool: Init tool
    Settings: Settings for Init tool
    Layout: Sets the layout to specified default layout dimensions
    :return:
    """
    if "tool" not in st.session_state:
        st.session_state.tool = ACTIVE_TOOL
    if "settings" not in st.session_state:
        st.session_state.settings = ACTIVE_TOOL.settings
    if "layout" not in st.session_state:
        st.session_state.layout = DEFAULT_LAYOUT
    if "outputs" not in st.session_state:
        st.session_state.outputs = ACTIVE_TOOL.outputs
    if "gen" not in st.session_state:
        st.session_state.gen = {"running": False, "total": 0, "out_dir": ""}
    if "outputs_lock" not in st.session_state:
        st.session_state.outputs_lock = threading.Lock()

# -------------------------------
# Page Setup
# -------------------------------
st.set_page_config(page_title=ACTIVE_TOOL.tool_name, layout="wide")
init_state()

# Light CSS polish
st.markdown(
    """
    <style>
      .section-card { padding: 1rem; border-radius: 1rem; border: 1px solid rgba(0,0,0,0.07); box-shadow: 0 1px 3px rgba(0,0,0,0.06); background: white; }
      .muted { color: rgba(0,0,0,0.6); font-size: 0.9rem; }
      .tight > div > div { padding-top: 0.25rem; padding-bottom: 0.25rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(ACTIVE_TOOL.title)

# Column ratios mapped from percentages to relative weights
l, m, r = st.session_state.layout
cols = st.columns([max(1, l), max(1, m), max(1, r)], gap="large")

# -------------------------------
# Tool Selector (left column)
# -------------------------------
with cols[0]:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.subheader("Tool")
    tool = st.selectbox("Choose a tool", options=list(ALL_TOOLS.keys()), index=0, format_func=lambda x: x, help="Only one tool available for now.")  # TODO: Should be auto-populayed
    tool = ALL_TOOLS[tool]
    st.session_state.tool = tool

    st.divider()
    st.markdown("**About**")
    st.write(
        tool.about
    )
    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------
# Input (middle column)
# -------------------------------
with cols[1]:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.subheader("Input")

    st.session_state.tool.input_builder(st)

    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------
# Output (right column)
# -------------------------------
with cols[2]:
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.subheader("Output")

    if 'outputs' in st.session_state:
        mapping_data = st.session_state.outputs.mappings
        st.markdown("#### Section mappings")
        if mapping_data:
            if isinstance(mapping_data, list) and len(mapping_data) > 0:
                # Enforce column order and missing keys safety
                col_order = ["start", "end", "name"]
                normalized = [
                    {k: (row.get(k) if isinstance(row, dict) else None) for k in col_order}
                    for row in mapping_data
                ]
                # Display as a table/grid
                st.dataframe(normalized, use_container_width=True, hide_index=True)

        else:
            st.caption("No sections mappings yet. Submit the form to populate results.")

        output_files = st.session_state.outputs.output_files
        st.markdown("#### Markdown files")
        if output_files:
            # Optional: auto-refresh every 2s while running
            try:
                from streamlit_autorefresh import st_autorefresh

                if st.session_state.gen["running"]:
                    st_autorefresh(interval=2000, key="gen-refresh")
            except Exception:
                pass  # without this, any user interaction triggers a rerun anyway

            job = st.session_state.gen

            if job["total"]:
                st.write(f"Progress: {len(output_files)} / {job['total']}")
                st.progress(min(1.0, len(output_files) / max(1, job["total"])))

            for i, f in enumerate(output_files):
                with open(f["path"], "rb") as fh:
                    st.download_button(
                        label=f"⬇️ {f['name']}",
                        data=fh,  # stream from disk
                        file_name=f["name"],
                        key=f"dl-{i}",
                    )

            if not job["running"] and job["total"] and len(output_files) == job["total"]:
                st.success("All files generated.")
    else:
        st.caption("Outputs store not initialized.")

    st.markdown("</div>", unsafe_allow_html=True)
