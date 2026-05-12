from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from database import get_db
from models.cart import Cart, CartItem
from models.product import Product
from models.user import User
from schemas.cart import CartItemCreate, CartItemUpdate, CartItemResponse, CartResponse
from auth.jwt import get_current_user

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get("/", response_model=CartResponse)
async def view_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve the current user's shopping cart with all items and product details.
    """
    # Fetch or create cart for user
    result = await db.execute(
        select(Cart).where(Cart.user_id == current_user.id)
    )
    cart = result.scalar_one_or_none()
    if not cart:
        cart = Cart(user_id=current_user.id)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)

    # Load items with product information
    result = await db.execute(
        select(CartItem)
        .options(selectinload(CartItem.product))
        .where(CartItem.cart_id == cart.id)
    )
    items = result.scalars().all()

    cart_items = []
    total_price = 0.0
    for item in items:
        product = item.product
        subtotal = item.quantity * product.price
        total_price += subtotal
        cart_items.append(CartItemResponse(
            id=item.id,
            product_id=product.id,
            product_name=product.name,
            product_price=product.price,
            quantity=item.quantity,
            subtotal=subtotal,
            added_at=item.added_at
        ))

    return CartResponse(
        cart_id=cart.id,
        items=cart_items,
        total_price=round(total_price, 2)
    )


@router.post("/add", response_model=CartItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_cart(
    item_data: CartItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add a product to the cart. If the product already exists in the cart, update its quantity.
    """
    # Validate product exists and has sufficient stock
    result = await db.execute(select(Product).where(Product.id == item_data.product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.stock < item_data.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    # Get or create cart for user
    result = await db.execute(select(Cart).where(Cart.user_id == current_user.id))
    cart = result.scalar_one_or_none()
    if not cart:
        cart = Cart(user_id=current_user.id)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)

    # Check if product already in cart
    result = await db.execute(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.product_id == item_data.product_id
        )
    )
    existing_item = result.scalar_one_or_none()

    if existing_item:
        # Update quantity
        new_quantity = existing_item.quantity + item_data.quantity
        if new_quantity > product.stock:
            raise HTTPException(status_code=400, detail="Quantity exceeds stock")
        existing_item.quantity = new_quantity
        await db.commit()
        await db.refresh(existing_item)
        item = existing_item
    else:
        # Create new cart item
        new_item = CartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=item_data.quantity
        )
        db.add(new_item)
        await db.commit()
        await db.refresh(new_item)
        item = new_item

    # Prepare response
    subtotal = item.quantity * product.price
    return CartItemResponse(
        id=item.id,
        product_id=product.id,
        product_name=product.name,
        product_price=product.price,
        quantity=item.quantity,
        subtotal=subtotal,
        added_at=item.added_at
    )


@router.put("/items/{item_id}", response_model=CartItemResponse)
async def update_cart_item(
    item_id: int,
    item_data: CartItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update the quantity of a specific cart item. Validate ownership and stock.
    """
    # Fetch cart item with product and cart info
    result = await db.execute(
        select(CartItem)
        .options(selectinload(CartItem.product))
        .where(CartItem.id == item_id)
    )
    cart_item = result.scalar_one_or_none()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    # Ensure the item belongs to the current user
    result = await db.execute(
        select(Cart).where(
            Cart.id == cart_item.cart_id,
            Cart.user_id == current_user.id
        )
    )
    cart = result.scalar_one_or_none()
    if not cart:
        raise HTTPException(status_code=403, detail="Not authorized to modify this item")

    # Validate product stock
    product = cart_item.product
    if item_data.quantity > product.stock:
        raise HTTPException(status_code=400, detail="Requested quantity exceeds stock")

    # Update quantity
    cart_item.quantity = item_data.quantity
    await db.commit()
    await db.refresh(cart_item)

    subtotal = cart_item.quantity * product.price
    return CartItemResponse(
        id=cart_item.id,
        product_id=product.id,
        product_name=product.name,
        product_price=product.price,
        quantity=cart_item.quantity,
        subtotal=subtotal,
        added_at=cart_item.added_at
    )


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_cart(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Remove a specific item from the cart.
    """
    # Fetch cart item
    result = await db.execute(
        select(CartItem).where(CartItem.id == item_id)
    )
    cart_item = result.scalar_one_or_none()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    # Verify ownership
    result = await db.execute(
        select(Cart).where(
            Cart.id == cart_item.cart_id,
            Cart.user_id == current_user.id
        )
    )
    cart = result.scalar_one_or_none()
    if not cart:
        raise HTTPException(status_code=403, detail="Not authorized to delete this item")

    await db.delete(cart_item)
    await db.commit()
    # No content response


@router.delete("/clear", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Remove all items from the current user's cart.
    """
    # Fetch cart
    result = await db.execute(
        select(Cart).where(Cart.user_id == current_user.id)
    )
    cart = result.scalar_one_or_none()
    if not cart:
        # Cart is already empty or doesn't exist
        return

    # Delete all items
    result = await db.execute(
        select(CartItem).where(CartItem.cart_id == cart.id)
    )
    items = result.scalars().all()
    for item in items:
        await db.delete(item)
    await db.commit()
    # Optionally delete cart itself? Usually keep cart, just clear items.
    # No content response