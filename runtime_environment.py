"""Helpers for identifying an isolated Python environment.

Interlocutor depends on packages that should not be installed into the system
Python.  CPython exposes a reliable signal for ``venv`` and ``virtualenv``,
while Conda identifies its active prefix through ``CONDA_PREFIX``.
"""

import os
import sys
from typing import Any, Mapping, Optional


def _same_prefix(left: str, right: str) -> bool:
	"""Return whether two environment prefixes identify the same path."""
	return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
		os.path.realpath(right)
	)


def isolated_environment_type(
	sys_module: Any = sys,
	environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
	"""Return the active isolated-environment type, or ``None``.

	Environment variables are accepted only when their prefix matches
	``sys.prefix``.  This avoids treating a stale ``CONDA_PREFIX`` or
	``VIRTUAL_ENV`` inherited by another interpreter as an active environment.
	"""
	if environ is None:
		environ = os.environ

	if getattr(sys_module, "real_prefix", None):
		return "virtualenv"

	prefix = getattr(sys_module, "prefix", "")
	base_prefix = getattr(sys_module, "base_prefix", prefix)
	if prefix and base_prefix and not _same_prefix(base_prefix, prefix):
		return "venv"

	for variable, environment_type in (
		("CONDA_PREFIX", "conda"),
		("VIRTUAL_ENV", "virtualenv"),
	):
		environment_prefix = environ.get(variable)
		if environment_prefix and prefix and _same_prefix(environment_prefix, prefix):
			return environment_type

	return None
