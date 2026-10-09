"""Hermes Office 3D — a read-only, privacy-preserving 3D visualization of live
Hermes Agent sessions.

The public package surface is intentionally tiny:

* :mod:`hermes_office.adapter`  — turns observable Hermes session data into a
  sanitized office payload (no titles, previews, paths, ids or transcripts).
* :mod:`hermes_office.server`   — a stdlib HTTP server that proxies the local
  Hermes API server-side and serves the 3D front-end same-origin.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
