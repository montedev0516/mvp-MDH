"""Django Tables2 table definitions for the dispatch app."""

from .assignment import AssignmentTable  # noqa
from .dispatch import DispatchTable  # noqa
from .order import OrderTable  # noqa
from .trip import TripTable  # noqa

__all__ = [
    'AssignmentTable',
    'DispatchTable',
    'OrderTable',
    'TripTable',
]
