"""Cross-platform hardware inspection, variable-quantization model sizing, and dynamic `num_ctx` scaling."""

from .context_window import (
    DEFAULT_MAX_CONTEXT_WINDOW,
    DEFAULT_MODEL_CONTEXT_WINDOWS,
    compute_dynamic_num_ctx,
    discover_active_ollama_model,
    estimate_tokens,
    get_configured_max_context_window,
    get_model_context_window,
    inspect_ollama_model_metadata,
    register_model_context_provider,
)
from .models import (
    BUILTIN_MODEL_CATALOG,
    add_custom_model,
    evaluate_model_fit,
    list_all_models,
    pull_model,
    recommend_models_for_hardware,
    remove_custom_model,
)
from .probe import classify_hardware_tier, probe_hardware

__all__ = [
    "BUILTIN_MODEL_CATALOG",
    "DEFAULT_MAX_CONTEXT_WINDOW",
    "DEFAULT_MODEL_CONTEXT_WINDOWS",
    "add_custom_model",
    "classify_hardware_tier",
    "compute_dynamic_num_ctx",
    "discover_active_ollama_model",
    "estimate_tokens",
    "evaluate_model_fit",
    "get_configured_max_context_window",
    "get_model_context_window",
    "inspect_ollama_model_metadata",
    "list_all_models",
    "probe_hardware",
    "pull_model",
    "recommend_models_for_hardware",
    "register_model_context_provider",
    "remove_custom_model",
]
