# from pydantic import BaseModel, Field
# from typing import Optional, List
# from enum import Enum
# from datetime import datetime


# class QuotationStatus(str, Enum):
#     PARSED = "Parsed"
#     NEEDS_REVIEW = "Needs Review"
#     APPROVED = "Approved"
#     EXPIRED = "Expired"


# class QuotationItem(BaseModel):
#     item_name: Optional[str] = None
#     quantity: Optional[str] = None
#     unit_price: Optional[str] = None
#     total: Optional[str] = None
#     remarks: Optional[str] = None
#     item_type: Optional[str] = None        # "As Specified" | "Alternatives" etc.


# class QuotationModel(BaseModel):
#     quotation_number: Optional[str] = None  # e.g. PTC-Q-2024-154
#     project_id: Optional[str] = None        # e.g. PRJ-2026-0001
#     rfqId: Optional[str] = None      # e.g. Marina Bay Hotel
#     vendorId: Optional[str] = None          # e.g. Premium Textiles
#     total_amount: Optional[str] = None      # e.g. USD 68,750
#     currency: Optional[str] = None          # e.g. USD
#     valid_until: Optional[str] = None       # e.g. Mar 23, 2026
#     payment_terms: Optional[str] = None     # e.g. 40% advance, 60% on delivery
#     delivery_terms: Optional[str] = None    # e.g. DDP Dubai, custom made 5-6 weeks
#     items: List[QuotationItem] = []
#     status: QuotationStatus = QuotationStatus.PARSED
#     missing_fields: List[str] = []
#     batch_id: Optional[str] = None
#     source_file: Optional[str] = None
#     raw_data: Optional[dict] = {}
#     created_at: datetime = Field(default_factory=datetime.utcnow)
#     updated_at: datetime = Field(default_factory=datetime.utcnow)


# class QuotationUploadResponse(BaseModel):
#     batch_id: str
#     project_id: str
#     total_quotations: int
#     parsed: int
#     needs_review: int
#     message: str




from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class QuotationStatus(str, Enum):
    PARSED = "Parsed"
    NEEDS_REVIEW = "Needs Review"
    APPROVED = "Approved"
    EXPIRED = "Expired"


class QuotationItem(BaseModel):
    item_name: Optional[str] = None
    description: Optional[str] = None
    commodity: Optional[str] = None
    quantity: Optional[str] = None
    unit_price: Optional[str] = None
    total: Optional[str] = None
    remarks: Optional[str] = None
    item_type: Optional[str] = None


class QuotationModel(BaseModel):
    quotation_number: Optional[str] = None
    project_id: Optional[str] = None
    rfqId: Optional[str] = None
    vendorId: Optional[str] = None
    total_amount: Optional[str] = None
    currency: Optional[str] = None
    valid_until: Optional[str] = None
    payment_terms: Optional[str] = None
    delivery_terms: Optional[str] = None
    items: List[QuotationItem] = []
    status: QuotationStatus = QuotationStatus.PARSED
    missing_fields: List[str] = []
    batch_id: Optional[str] = None
    source_file: Optional[str] = None
    raw_data: Optional[dict] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class QuotationUploadResponse(BaseModel):
    batch_id: str
    project_id: str
    rfqId: Optional[str] = None
    vendorId: Optional[str] = None
    total_amount: Optional[str] = None
    currency: Optional[str] = None
    valid_until: Optional[str] = None
    payment_terms: Optional[str] = None
    delivery_terms: Optional[str] = None
    total_quotations: int
    parsed: int
    needs_review: int
    message: str