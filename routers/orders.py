from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime

from app.database import get_db
from app.models import Order, OrderItem, Cart, CartItem, Product, ShippingAddress, User
from app.schemas.order import OrderCreate, OrderResponse, OrderItemResponse, OrderStatusUpdate
from app.schemas.user import UserResponse
from app.dependencies.auth import get_current_user, require_admin
from app.services.order import create_order_from_cart, validate_stock

router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("/checkout", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def checkout(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new order from the current user's cart.
    """
    # Load cart with items and related product
    stmt = (
        select(Cart)
        .where(Cart.user_id == current_user.id)
        .options(selectinload(Cart.items).selectinload(CartItem.product))
    )
    result = await db.execute(stmt)
    cart = result.scalar_one_or_none()

    if not cart or not cart.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart is empty",
        )

    # Validate stock availability
    stock_errors = validate_stock(cart.items)
    if stock_errors:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"insufficient_stock": stock_errors},
        )

    # Create order (also reduces stock and clears cart)
    order = await create_order_from_cart(db, cart, current_user)
    await db.commit()
    await db.refresh(order, ["items", "shipping_address"])

    return order


@router.get("/", response_model=List[OrderResponse])
async def list_my_orders(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve order history for the current user.
    """
    stmt = (
        select(Order)
        .where(Order.user_id == current_user.id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.shipping_address),
        )
        .order_by(Order.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    orders = result.scalars().all()
    return orders


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order_detail(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a specific order by ID (user can only see their own orders unless admin).
    """
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.shipping_address),
        )
    )
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Non-admins can only view their own orders
    if order.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")

    return order


# Admin endpoints
@router.get("/admin/", response_model=List[OrderResponse])
async def list_all_orders(
    skip: int = 0,
    limit: int = 20,
    status_filter: str = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Admin: list all orders with optional status filter.
    """
    query = (
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.shipping_address),
            selectinload(Order.user),
        )
        .order_by(Order.created_at.desc())
    )
    if status_filter:
        query = query.where(Order.status == status_filter)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    orders = result.scalars().all()
    return orders


@router.put("/admin/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: int,
    status_update: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Admin: update order status (e.g., pending -> paid -> shipped -> delivered).
    """
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.shipping_address),
        )
    )
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Simple status transition validation
    allowed_transitions = {
        "pending": ["paid", "cancelled"],
        "paid": ["shipped", "refunded"],
        "shipped": ["delivered"],
        "delivered": [],
        "cancelled": [],
        "refunded": [],
    }
    if status_update.status not in allowed_transitions.get(order.status, []):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition from '{order.status}' to '{status_update.status}'",
        )

    order.status = status_update.status
    await db.commit()
    await db.refresh(order)
    return order