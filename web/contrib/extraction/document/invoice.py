from typing import List, Optional
from pydantic import BaseModel
from contrib.extraction.oai import MODELS, client

INVOICE_TEMPLATE = """You are an expert at structured data extraction.
                You will be given unstructured text from an invoice from a logistics consigment and
                should convert it into the given structure.
                The Customer name can also be found in the logo or header of the invoice document.
                And it may not be explicitly defined.
                The Order number has various names, synonyms, it could also be found trailing some special char liks `#` or `:`.

                For phone numbers:
                1. Extract and map phone numbers to their specific entities (customer, carrier, pickup contact, delivery contact).
                2. Look for phone numbers near entity names or in contact sections.
                3. Format phone numbers consistently, preserving any country codes.
                4. If a phone number is clearly associated with a specific role (e.g. "Dispatch:", "Customer Service:"), map it to the appropriate entity.
                5. For customer phone, look in the header/footer or billing information sections.

                For each trip in the document:
                1. Extract cargo_details - which describes the type of cargo being shipped (e.g. "Electronics", "Furniture", "Hazardous Materials").
                2. Extract weight - the numerical weight of the cargo (preferably in a consistent unit like kg or lbs).
                3. Extract pickup and delivery information including addresses and dates.

                For load rate and total values:
                1. Look for "Load Rate", "Rate", or similar terms followed by a monetary value.
                2. The load rate is typically the amount being charged for the transportation service.
                3. Look for "Declared Value", "Load Value", or similar terms for the total value of the goods being transported.
                4. Always extract the currency (USD, CAD, etc.) along with the monetary values.
                5. Remove any commas from numerical values and convert to float.
                6. If there are multiple values, use the one explicitly labeled as "Load Rate" for the load_rate.

                Be thorough in finding all relevant information from the document."""


class CustomerDetails(BaseModel):
    customer_name: str
    customer_address: str
    customer_email: str
    customer_phone: str
    customer_others: Optional[List[str]]


class PickupDetails(BaseModel):
    pickup_date: str
    pickup_address: str
    pickup_contact_person: str
    pickup_contact_phone: str
    pickup_details_others: Optional[List[str]]


class DeliveryDetails(BaseModel):
    delivery_date: str
    delivery_address: str
    delivery_contact_person: str
    delivery_contact_phone: str
    delivery_details_others: Optional[List[str]]


class CarrierDetails(BaseModel):
    carrier_name: str
    carrier_contact_person: str
    carrier_contact_phone: str
    carrier_email: str
    carrier_others: Optional[List[str]]


class FreightDetails(BaseModel):
    freight_type: str
    freight_weight: str
    freight_dimensions: str
    freight_value: str
    freight_details_others: Optional[List[str]]


class LoadDetails(BaseModel):
    load_rate: float  # The transportation service charge
    load_amount: float  # Additional charges if any
    load_total: float  # Total amount including all charges
    declared_value: Optional[float] = None  # Value of the goods being transported
    currency: str
    remarks: Optional[str] = None


class Trip(BaseModel):
    pickup_details: PickupDetails
    deliver_to_details: DeliveryDetails
    carrier_details: CarrierDetails
    freight_details: FreightDetails
    load_details: LoadDetails
    cargo_details: Optional[str] = None
    weight: Optional[float] = None

    @property
    def pickup_date(self) -> Optional[str]:
        return self.pickup_details.pickup_date if self.pickup_details else None

    @property
    def pickup_address(self) -> Optional[str]:
        return self.pickup_details.pickup_address if self.pickup_details else None

    @property
    def delivery_date(self) -> Optional[str]:
        return (
            self.deliver_to_details.delivery_date if self.deliver_to_details else None
        )

    @property
    def delivery_address(self) -> Optional[str]:
        return (
            self.deliver_to_details.delivery_address
            if self.deliver_to_details
            else None
        )


class MiscellaneousEntity(BaseModel):
    entity_type: str
    entity_value: str


class OtherDetails(BaseModel):
    names: List[str]
    emails: List[str]
    person_names: List[str]
    contact_numbers: List[str]
    addresses: List[str]
    dates: List[str]
    other: Optional[List[str]]


class OrderInfo(BaseModel):
    order_id: Optional[str]
    invoice_number: Optional[str]
    carrier_confirmation: Optional[str]
    order_confirmation: Optional[str]


class TripResponse(BaseModel):
    order_info: OrderInfo
    customer_details: CustomerDetails
    total_load_details: LoadDetails
    freight_details: FreightDetails
    trips: List[Trip]
    remarks_or_special_instructions: Optional[str]
    miscellaneous_entities: Optional[List[MiscellaneousEntity]]
    other_details: OtherDetails

    class Config:
        extra = "forbid"


def extract_invoice(
    pages: str,
    model: str = MODELS.GPT4o_16k.value,
    temperature: int = 0,
    template: str = INVOICE_TEMPLATE,
    response_format: BaseModel = TripResponse,
):
    completion = client.beta.chat.completions.parse(
        model=model,
        temperature=temperature,
        messages=[
            {
                "role": "system",
                "content": f"""{template} \n{pages}""",
            }
        ],
        response_format=response_format,
        seed=42,
    )
    return completion
