from django.db import models
from models.models import BaseModel

class Customer(BaseModel):
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=255)
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.name} {self.email}"
    
    def get_orders(self):
        return self.orders.all().order_by("-created_at")