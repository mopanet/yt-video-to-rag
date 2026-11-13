"""Fixtures for every test module (pytest loads this file by itself)."""

import logging

import pytest


@pytest.fixture(autouse=True)
def _restore_the_tool_logger():
    """main() sets the tool's logger to INFO and adds a stderr handler: undo that after each test,
    so log assertions do not depend on which tests ran before."""
    logger = logging.getLogger("video_to_rag")
    level, handlers = logger.level, list(logger.handlers)
    yield
    logger.setLevel(level)
    logger.handlers[:] = handlers
