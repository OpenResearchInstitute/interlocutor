"""Tests for Python environment detection."""

from types import SimpleNamespace
import unittest

from runtime_environment import isolated_environment_type


class IsolatedEnvironmentTypeTest(unittest.TestCase):
	def test_detects_standard_venv(self):
		python = SimpleNamespace(prefix="/tmp/project/.venv", base_prefix="/usr")
		self.assertEqual(isolated_environment_type(python, {}), "venv")

	def test_detects_legacy_virtualenv(self):
		python = SimpleNamespace(
			prefix="/tmp/project/.venv",
			base_prefix="/tmp/project/.venv",
			real_prefix="/usr",
		)
		self.assertEqual(isolated_environment_type(python, {}), "virtualenv")

	def test_detects_conda_environment_from_matching_prefix(self):
		python = SimpleNamespace(
			prefix="/opt/conda/envs/interlocutor",
			base_prefix="/opt/conda/envs/interlocutor",
		)
		environ = {"CONDA_PREFIX": "/opt/conda/envs/interlocutor"}
		self.assertEqual(isolated_environment_type(python, environ), "conda")

	def test_detects_virtual_env_from_matching_prefix(self):
		python = SimpleNamespace(
			prefix="/tmp/project/.venv",
			base_prefix="/tmp/project/.venv",
		)
		environ = {"VIRTUAL_ENV": "/tmp/project/.venv"}
		self.assertEqual(isolated_environment_type(python, environ), "virtualenv")

	def test_ignores_stale_environment_variable(self):
		python = SimpleNamespace(prefix="/usr", base_prefix="/usr")
		environ = {"CONDA_PREFIX": "/opt/conda/envs/interlocutor"}
		self.assertIsNone(isolated_environment_type(python, environ))

	def test_system_python_is_not_isolated(self):
		python = SimpleNamespace(prefix="/usr", base_prefix="/usr")
		self.assertIsNone(isolated_environment_type(python, {}))


if __name__ == "__main__":
	unittest.main()
