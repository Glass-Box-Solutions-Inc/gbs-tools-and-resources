"""Evidence-first, deterministic case analysis for extracted and generated case records."""

from case_analysis_engine.analysis import analyze_facts, analyze_paths
from case_analysis_engine.input import load_payload, normalize_paths
from case_analysis_engine.models import AnalysisReport, Evidence, Fact, Finding
from case_analysis_engine.render import render_json, render_markdown
from case_analysis_engine.validation import validate_facts

__all__ = [
    "AnalysisReport",
    "Evidence",
    "Fact",
    "Finding",
    "analyze_facts",
    "analyze_paths",
    "load_payload",
    "normalize_paths",
    "render_json",
    "render_markdown",
    "validate_facts",
]

__version__ = "0.2.0"
