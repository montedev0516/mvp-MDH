from .assignment import AssignmentForm  # noqa
from .dispatch import DispatchForm, DispatchDetailForm  # noqa
from .order import OrderForm, OrderUpdateForm  # noqa
from .trip import TripForm  # noqa
from .upload import FileUploadForm  # noqa

__all__ = [
    'AssignmentForm',
    'DispatchForm',
    'DispatchDetailForm',
    'OrderForm',
    'OrderUpdateForm',
    'TripForm',
    'FileUploadForm',
]