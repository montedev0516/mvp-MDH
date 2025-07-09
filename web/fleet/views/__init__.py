from .carrier import (
    CarrierListView,
    CarrierDetailView,
    CarrierCreateView,
    CarrierUpdateView,
    CarrierDeleteView,
)
from .truck import (
    TruckListView,
    TruckDetailView,
    TruckCreateView,
    TruckUpdateView,
    TruckDeleteView,
)
from .driver import (
    DriverView,
    DriverDetailView,
    DriverCreateView,
    DriverUpdateView,
    DriverDeleteView,
)

__all__ = [
    # Carrier views
    "CarrierListView",
    "CarrierDetailView",
    "CarrierCreateView",
    "CarrierUpdateView",
    "CarrierDeleteView",
    # Truck views
    "TruckListView",
    "TruckDetailView",
    "TruckCreateView",
    "TruckUpdateView",
    "TruckDeleteView",
    # Driver views
    "DriverView",
    "DriverDetailView",
    "DriverCreateView",
    "DriverUpdateView",
    "DriverDeleteView",
]