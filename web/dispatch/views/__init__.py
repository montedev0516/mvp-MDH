from .dispatch import (
    DispatchCreateView,  # noqa
    DispatchDetailView,  # noqa
    DispatchListView,  # noqa
    DispatchUpdateView,  # noqa
    DispatchDeleteView,
)
from .order import (
    OrderCreateView,  # noqa
    OrderDetailView,  # noqa
    OrderEditView,  # noqa
    OrderListView,  # noqa
    OrderDeleteView,  # noqa
    OrderFileUploadView,
    OrderFileDownloadView,
    OrderPDFView,
)
from .trip import (
    TripCreateView,  # noqa
    TripUpdateView,  # noqa
    TripListView,  # noqa
    TripDetailView,
    TripDeleteView,
)
from .assignment import (
    AssignmentListView,
    AssignmentDetailView,
    AssignmentCreateView,
    AssignmentUpdateView,
    AssignmentDeleteView,
)
from .invoice import DispatchInvoiceView

__all__ = [
    'OrderListView',
    'OrderCreateView',
    'OrderDetailView',
    'OrderEditView',
    'OrderDeleteView',
    'OrderFileUploadView',
    'OrderFileDownloadView',
    'OrderPDFView',
    'TripListView',
    'TripCreateView',
    'TripDetailView',
    'TripUpdateView',
    'TripDeleteView',
    'DispatchListView',
    'DispatchCreateView',
    'DispatchDetailView',
    'DispatchUpdateView',
    'DispatchDeleteView',
    'DispatchInvoiceView',
    'AssignmentListView',
    'AssignmentDetailView',
    'AssignmentCreateView',
    'AssignmentUpdateView',
    'AssignmentDeleteView',
]
