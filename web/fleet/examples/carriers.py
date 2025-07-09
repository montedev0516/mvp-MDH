from fleet.models import Carrier, CarrierStatus

def create_example_carriers(tenant):
    """
    Creates two example carriers for demonstration purposes.
    
    Args:
        tenant: The tenant instance to associate the carriers with
    
    Returns:
        tuple: A tuple containing the two created carrier instances
    """
    
    # Example 1: A large national carrier
    national_carrier = Carrier.objects.create(
        name="TransNational Logistics",
        legal_name="TransNational Logistics Corporation",
        business_number="TN123456789",
        mc_number="MC987654",
        dot_number="DOT123456",
        email="dispatch@transnational.com",
        phone="+1-888-555-0123",
        website="https://www.transnational-logistics.com",
        address="1234 Transport Way, Suite 500",
        city="Chicago",
        state="Illinois",
        zip_code="60601",
        country="USA",
        total_trucks=150,
        total_drivers=200,
        status=CarrierStatus.ACTIVE,
        is_active=True,
        notes="Large national carrier specializing in long-haul transportation across North America. "
              "Strong safety record and modern fleet.",
        tenant=tenant
    )
    
    # Example 2: A regional carrier
    regional_carrier = Carrier.objects.create(
        name="Pacific Coast Express",
        legal_name="Pacific Coast Express LLC",
        business_number="PCE789012",
        mc_number="MC456789",
        dot_number="DOT789012",
        email="operations@pacificexpress.com",
        phone="+1-855-555-0456",
        website="https://www.pacific-express.com",
        address="789 Harbor Drive",
        city="Seattle",
        state="Washington",
        zip_code="98101",
        country="USA",
        total_trucks=45,
        total_drivers=60,
        status=CarrierStatus.ACTIVE,
        is_active=True,
        notes="Regional carrier focused on West Coast operations. "
              "Specializes in time-sensitive deliveries and refrigerated transport.",
        tenant=tenant
    )
    
    return national_carrier, regional_carrier

# Example usage:
"""
from tenant.models import Tenant
from fleet.examples.carriers import create_example_carriers

# Get your tenant
tenant = Tenant.objects.get(id='your-tenant-id')

# Create the example carriers
national_carrier, regional_carrier = create_example_carriers(tenant)
""" 