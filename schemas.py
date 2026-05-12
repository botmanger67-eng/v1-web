from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator
from decimal import Decimal
import re

# ───────────────────────────────────────────
# Enums (could be moved to models.py if preferred)
# ───────────────────────────────────────────
from enum import Enum

class ProductCategory(str, Enum):
    electronics = "electronics"
    clothing = "clothing"
    home = "home"
    books = "books"
    sports = "sports"
    other = "other"

class OrderStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"

# ───────────────────────────────────────────
# User Schemas
# ───────────────────────────────────────────
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class UserUpdate(BaseModel):
    """Admin endpoint for updating user details"""
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None

# ───────────────────────────────────────────
# Product Schemas
# ───────────────────────────────────────────
class ProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    price: Decimal = Field(..., gt=0, decimal_places=2)
    stock: int = Field(0, ge=0)
    category: ProductCategory
    image_url: Optional[str] = Field(None, max_length=500)

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    stock: Optional[int] = Field(None, ge=0)
    category: Optional[ProductCategory] = None
    image_url: Optional[str] = Field(None, max_length=500)

class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class ProductList(BaseModel):
    """Wrapper for paginated product listing"""
    items: List[ProductResponse]
    total: int
    page: int
    page_size: int

# ───────────────────────────────────────────
# Category Schemas
# ───────────────────────────────────────────
class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class CategoryCreate(CategoryBase):
    pass

class CategoryResponse(CategoryBase):
    id: int

    model_config = {"from_attributes": True}

# ───────────────────────────────────────────
# Cart Schemas
# ───────────────────────────────────────────
class CartItemBase(BaseModel):
    product_id: int
    quantity: int = Field(1, ge=1)

class CartItemCreate(CartItemBase):
    pass

class CartItemResponse(CartItemBase):
    id: int
    product: ProductResponse

    model_config = {"from_attributes": True}

class CartResponse(BaseModel):
    items: List[CartItemResponse]
    total_price: Decimal

# ───────────────────────────────────────────
# Order Schemas
# ───────────────────────────────────────────
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(1, ge=1)

class OrderCreate(BaseModel):
    shipping_address: str = Field(..., min_length=10, max_length=500)
    items: List[OrderItemCreate] = Field(..., min_length=1)

class OrderItemResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal

    model_config = {"from_attributes": True}

class OrderResponse(BaseModel):
    id: int
    user_id: int
    status: OrderStatus
    shipping_address: str
    total_amount: Decimal
    created_at: datetime
    items: List[OrderItemResponse]

    model_config = {"from_attributes": True}

class OrderStatusUpdate(BaseModel):
    status: OrderStatus

class OrderHistoryResponse(BaseModel):
    orders: List[OrderResponse]
    total: int
    page: int
    page_size: int

# ───────────────────────────────────────────
# Review Schemas
# ───────────────────────────────────────────
class ReviewCreate(BaseModel):
    product_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)

class ReviewResponse(BaseModel):
    id: int
    user_id: int
    username: str
    product_id: int
    rating: int
    comment: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

# ───────────────────────────────────────────
# Admin Dashboard Schemas
# ───────────────────────────────────────────
class SalesSummary(BaseModel):
    total_orders: int
    total_revenue: Decimal
    average_order_value: Decimal
    top_selling_products: List[dict]  # e.g., [{"product_id": 1, "name": "...", "total_sold": 10}]

class DashboardStats(BaseModel):
    total_products: int
    total_users: int
    total_orders: int
    revenue_today: Decimal
    revenue_this_month: Decimal
    sales_summary: SalesSummary

# ───────────────────────────────────────────
# Generic Pagination Schema
# ───────────────────────────────────────────
class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[BaseModel]  # usage: subclass or use as generic

# ───────────────────────────────────────────
# Token Schema (for JWT)
# ───────────────────────────────────────────
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds