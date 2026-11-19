"""Zero-cloud-token ROI analytics, local Auto-Tuner, comparative benchmarks & static HTML configurator."""

from .benchmark import run_comparative_benchmark
from .dashboard import export_static_dashboard, render_static_help_html, render_static_settings_html
from .roi import build_roi_report, collect_local_runs, collect_remote_transcript_usage, format_roi_markdown
from .tuner import analyze_and_tune

__all__ = [
    "analyze_and_tune",
    "build_roi_report",
    "collect_local_runs",
    "collect_remote_transcript_usage",
    "export_static_dashboard",
    "format_roi_markdown",
    "render_static_help_html",
    "render_static_settings_html",
    "run_comparative_benchmark",
]
