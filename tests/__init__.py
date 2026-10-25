"""Behavioral tests for the offline core."""

import importlib


def require_module(test, name):
    """Make the initial missing-package RED failure explicit."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        test.fail(f"Required core module is not implemented: {error.name}")
