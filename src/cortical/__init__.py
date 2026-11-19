"""Cortical — Cross-Platform Zero-Server Agent Control Plane & Declarative Composer."""

__version__ = "0.3.0"
__author__ = "Carlo Cancellieri"

from .config import DEFAULT_CONFIG, load_cortical_config, save_cortical_config
from .privacy.vault import PrivacyVault

__all__ = [
    "__version__",
    "__author__",
    "DEFAULT_CONFIG",
    "load_cortical_config",
    "save_cortical_config",
    "PrivacyVault",
]
