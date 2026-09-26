"""The pytest plugin, registered through the ``pytest11`` entry point: provides ``mediator``."""

import pytest

from .testing import RecordingMediator


@pytest.fixture
def mediator() -> RecordingMediator:
    """Return a new, empty ``RecordingMediator`` for each test.

    Define a ``mediator`` fixture of your own, in a conftest.py, to register what every test
    needs or to pass a resolver.
    """
    return RecordingMediator()
