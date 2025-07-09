from datetime import datetime, timedelta
from django.utils import timezone
from fleet.models import (
    Driver, DriverLicense, Customer, Truck, DriverEmployment,
    TruckStatus, TruckType, OwnershipType, EmploymentStatus, DutyStatus
)

def create_example_driver_licenses(tenant):
    """
    Creates example driver licenses with realistic data.
    
    Args:
        tenant: The tenant instance to associate the licenses with
    
    Returns:
        list: List of created driver license instances
    """
    licenses = []
    
    # Example 1: Standard Commercial Driver's License
    cdl_license = DriverLicense.objects.create(
        name="John Robert Smith",
        license_number="CDL123456789",
        date_of_birth=datetime(1985, 6, 15).replace(tzinfo=timezone.utc),
        issued_date=datetime(2020, 1, 10).replace(tzinfo=timezone.utc),
        expiry_date=datetime(2025, 1, 10).replace(tzinfo=timezone.utc),
        gender="M",
        address="456 Oak Street",
        country="USA",
        state="Texas",
        province=None,
        license_type="Class A CDL",
        conditions="Corrective Lenses Required",
        completion_tokens=150,
        prompt_tokens=50,
        total_tokens=200,
        llm_model_name="gpt-4-vision",
        uploaded_file_name="john_smith_cdl.jpg",
        file_save_path="licenses/2024/01/john_smith_cdl.jpg",
        tenant=tenant
    )
    licenses.append(cdl_license)
    
    # Example 2: International Driver's License
    intl_license = DriverLicense.objects.create(
        name="Maria Elena Rodriguez",
        license_number="IDL987654321",
        date_of_birth=datetime(1990, 3, 22).replace(tzinfo=timezone.utc),
        issued_date=datetime(2022, 5, 15).replace(tzinfo=timezone.utc),
        expiry_date=datetime(2027, 5, 15).replace(tzinfo=timezone.utc),
        gender="F",
        address="789 Maple Avenue",
        country="Canada",
        state=None,
        province="Ontario",
        license_type="International CDL",
        conditions="None",
        completion_tokens=180,
        prompt_tokens=60,
        total_tokens=240,
        llm_model_name="gpt-4-vision",
        uploaded_file_name="maria_rodriguez_idl.jpg",
        file_save_path="licenses/2024/01/maria_rodriguez_idl.jpg",
        tenant=tenant
    )
    licenses.append(intl_license)
    
    return licenses

def create_example_drivers(tenant, licenses=None):
    """
    Creates example drivers with associated employment records.
    
    Args:
        tenant: The tenant instance to associate the drivers with
        licenses: Optional list of driver licenses to use
    
    Returns:
        list: List of created driver instances
    """
    drivers = []
    
    # Example 1: Experienced Long-haul Driver
    long_haul_driver = Driver.objects.create(
        first_name="John",
        last_name="Smith",
        date_of_birth=datetime(1985, 6, 15).date(),
        license_number="CDL123456789",
        phone="+1-555-123-4567",
        email="john.smith@example.com",
        emergency_contact={
            "name": "Jane Smith",
            "relationship": "Spouse",
            "phone": "+1-555-987-6543"
        },
        address="456 Oak Street",
        city="Houston",
        state="Texas",
        zip_code="77001",
        country="USA",
        employee_id="EMP-001",
        hire_date=datetime(2020, 1, 15).date(),
        joining_date=timezone.now(),
        still_working=True,
        drivers_license=licenses[0] if licenses else None,
        tenant=tenant
    )
    drivers.append(long_haul_driver)
    
    # Create employment record for long-haul driver
    DriverEmployment.objects.create(
        driver=long_haul_driver,
        employment_status=EmploymentStatus.ACTIVE,
        duty_status=DutyStatus.AVAILABLE,
        current_location="Houston, TX",
        last_location_update=timezone.now(),
        location_history={
            "last_5_locations": [
                "Dallas, TX",
                "Oklahoma City, OK",
                "Kansas City, MO",
                "St. Louis, MO",
                "Houston, TX"
            ]
        },
        max_hours_per_week=60,
        preferred_routes={
            "preferred_states": ["TX", "OK", "MO", "AR"],
            "avoid_cities": ["New York", "Los Angeles"]
        }
    )
    
    # Example 2: Regional Driver
    regional_driver = Driver.objects.create(
        first_name="Maria",
        last_name="Rodriguez",
        date_of_birth=datetime(1990, 3, 22).date(),
        license_number="IDL987654321",
        phone="+1-555-234-5678",
        email="maria.rodriguez@example.com",
        emergency_contact={
            "name": "Carlos Rodriguez",
            "relationship": "Brother",
            "phone": "+1-555-876-5432"
        },
        address="789 Maple Avenue",
        city="Toronto",
        state="Ontario",
        zip_code="M5V 2T6",
        country="Canada",
        employee_id="EMP-002",
        hire_date=datetime(2022, 5, 20).date(),
        joining_date=timezone.now(),
        still_working=True,
        drivers_license=licenses[1] if licenses else None,
        tenant=tenant
    )
    drivers.append(regional_driver)
    
    # Create employment record for regional driver
    DriverEmployment.objects.create(
        driver=regional_driver,
        employment_status=EmploymentStatus.ACTIVE,
        duty_status=DutyStatus.AVAILABLE,
        current_location="Toronto, ON",
        last_location_update=timezone.now(),
        location_history={
            "last_5_locations": [
                "Montreal, QC",
                "Ottawa, ON",
                "Kingston, ON",
                "Hamilton, ON",
                "Toronto, ON"
            ]
        },
        max_hours_per_week=40,
        preferred_routes={
            "preferred_provinces": ["ON", "QC"],
            "max_distance": "500km"
        }
    )
    
    return drivers

def create_example_customers(tenant):
    """
    Creates example customers with diverse profiles.
    
    Args:
        tenant: The tenant instance to associate the customers with
    
    Returns:
        list: List of created customer instances
    """
    customers = []
    
    # Example 1: Large Retail Chain
    retail_customer = Customer.objects.create(
        name="MegaMart Retail Corporation",
        address="100 Commerce Parkway, Suite 1000, Memphis, TN 38120",
        email="logistics@megamart.com",
        phone="+1-888-555-9999",
        tenant=tenant
    )
    customers.append(retail_customer)
    
    # Example 2: Manufacturing Company
    manufacturing_customer = Customer.objects.create(
        name="Industrial Solutions Manufacturing",
        address="2500 Factory Drive, Detroit, MI 48201",
        email="shipping@industrialsolutions.com",
        phone="+1-888-555-8888",
        tenant=tenant
    )
    customers.append(manufacturing_customer)
    
    # Example 3: E-commerce Company
    ecommerce_customer = Customer.objects.create(
        name="FastShip E-commerce Ltd",
        address="888 Digital Avenue, Seattle, WA 98101",
        email="operations@fastship.com",
        phone="+1-888-555-7777",
        tenant=tenant
    )
    customers.append(ecommerce_customer)
    
    return customers

def create_example_trucks(tenant):
    """
    Creates example trucks with various specifications.
    
    Args:
        tenant: The tenant instance to associate the trucks with
    
    Returns:
        list: List of created truck instances
    """
    trucks = []
    
    # Example 1: Modern Long-haul Tractor
    long_haul_truck = Truck.objects.create(
        unit=1001,
        plate="TX12345",
        vin="1HGCM82633A123456",
        make="Peterbilt",
        model="579",
        value=150000.00,
        year=2023,
        country="USA",
        state="Texas",
        registration="REG123456",
        ownership_type=OwnershipType.OWNED,
        tracking="GPS-enabled",
        still_working=True,
        is_trailer=False,
        trailer_number="",
        trailer_capacity="",
        company_pays_fuel_cost=True,
        all_fuel_toll_cards=True,
        ifta_group="Group A",
        terminal="Houston Main",
        tour="National Route",
        weight=15000.0,
        capacity="80000 lbs",
        status=TruckStatus.ACTIVE,
        is_active=True,
        notes="Latest model with advanced safety features and fuel efficiency systems",
        tenant=tenant
    )
    trucks.append(long_haul_truck)
    
    # Example 2: Regional Box Truck
    box_truck = Truck.objects.create(
        unit=2001,
        plate="ON98765",
        vin="2FZHAZAK91L987654",
        make="Freightliner",
        model="M2 106",
        value=85000.00,
        year=2022,
        country="Canada",
        state="Ontario",
        registration="REG987654",
        ownership_type=OwnershipType.LEASED,
        tracking="GPS-enabled",
        still_working=True,
        is_trailer=False,
        trailer_number="",
        trailer_capacity="",
        company_pays_fuel_cost=True,
        all_fuel_toll_cards=True,
        ifta_group="Group B",
        terminal="Toronto East",
        tour="Regional Route",
        weight=12000.0,
        capacity="26000 lbs",
        status=TruckStatus.ACTIVE,
        is_active=True,
        notes="Medium-duty box truck ideal for urban and regional deliveries",
        tenant=tenant
    )
    trucks.append(box_truck)
    
    # Example 3: Refrigerated Trailer
    reefer_trailer = Truck.objects.create(
        unit=3001,
        plate="CA54321",
        vin="3HTWYAZT82J654321",
        make="Utility",
        model="3000R",
        value=75000.00,
        year=2022,
        country="USA",
        state="California",
        registration="REG654321",
        ownership_type=OwnershipType.OWNED,
        tracking="GPS-enabled",
        still_working=True,
        is_trailer=True,
        trailer_number="T3001",
        trailer_capacity="53 ft",
        company_pays_fuel_cost=True,
        all_fuel_toll_cards=True,
        ifta_group="Group C",
        terminal="Los Angeles",
        tour="West Coast Route",
        weight=14000.0,
        capacity="44000 lbs",
        status=TruckStatus.ACTIVE,
        is_active=True,
        notes="Temperature-controlled trailer with advanced cooling system",
        tenant=tenant
    )
    trucks.append(reefer_trailer)
    
    return trucks

# Example usage:
"""
from tenant.models import Tenant
from fleet.examples.fleet_examples import (
    create_example_driver_licenses,
    create_example_drivers,
    create_example_customers,
    create_example_trucks
)

# Get your tenant
tenant = Tenant.objects.get(id='your-tenant-id')

# Create examples
licenses = create_example_driver_licenses(tenant)
drivers = create_example_drivers(tenant, licenses)
customers = create_example_customers(tenant)
trucks = create_example_trucks(tenant)
""" 