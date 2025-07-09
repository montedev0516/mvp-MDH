# TBD
import pandas as pd
import numpy as np
from uuid import UUID
from expense.models import BVD
import logging

logger = logging.getLogger("django")

mapping = {
    "Company Name": "company_name",
    "Card#": "card_number",
    "Driver Name": "driver_name",
    "Date": "date",
    "Unit #": "unit",
    "Time": "time",
    "Site #": "site_number",
    "Site Name": "site_name",
    "Site City": "site_city",
    "Prov/ST": "prov_st",
    "Quantity": "quantity",
    "UOM": "uom",
    "Retail PPU": "retail_ppu",
    "Billed PPU": "billed_ppu",
    "PreTax AMT": "pre_tax_amt",
    "PST": "pst",
    "GST": "gst",
    "HST": "hst",
    "QST": "qst",
    "Discount": "discount",
    "Final Amount": "final_amount",
    "Currency": "currency",
    "Odometer": "odometer",
    "Auth Code": "auth_code",
}


class BVDDataImporter:
    # Async function to perform bulk insert
    @staticmethod
    async def bulk_insert_bvds(db, bvds: list[BVD]):
        db.add_all(bvds)
        await db.flush()

    @staticmethod
    def process_bvd_file(filepath: str, tenant_id: str) -> list[BVD]:
        df = pd.read_csv(filepath)
        df.rename(columns=mapping, inplace=True)
        df["tenant_id"] = tenant_id
        # Fix card_number, site_number, tenant_id to str
        df["card_number"] = df["card_number"].astype(str)
        df["site_number"] = df["site_number"].astype(str)
        # Fix date to datetime
        df["date"] = pd.to_datetime(df["date"], format="mixed")
        # Fix qst to float
        df["qst"] = df["qst"].astype(float)
        df["driver_name"] = df["driver_name"].replace({np.nan: ""})
        # Replace NaN with None (which translates to NULL in SQL)
        df = df.replace({np.nan: None})
        bvds = df.to_dict(orient="records")
        bvds_orm = []
        for bvd in bvds:
            bvd_orm_object = BVD(**bvd)
            bvds_orm.append(bvd_orm_object)
        return bvds_orm

    @staticmethod
    async def run(db, filepath: str, tenant_id: UUID):
        try:
            logger.info("Importing BVD data from %s", filepath)
            bvds = BVDDataImporter.process_bvd_file(filepath, tenant_id)
            logger.info("Bulk inserting %s BVD records", len(bvds))

            await BVDDataImporter.bulk_insert_bvds(db, bvds)

            logger.info("BVD data import completed")
            return "Data Import Success!"
        except Exception as e:
            logger.error("Error importing BVD data: %s", str(e))
            raise  # Re-raise the exception to be handled in the router
