from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import Product, Category, Order, OrderItem, User
from auth import get_current_admin
from schemas import OrderStatusEnum  # assuming this exists

import logging
from typing import Optional

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────
@router.get("/", name="admin_dashboard")
@router.get("/dashboard", name="admin_dashboard")
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    # total sales (sum of order totals where status is not cancelled)
    total_sales_result = await db.execute(
        select(func.coalesce(func.sum(Order.total_amount), 0)).where(
            Order.status != OrderStatusEnum.CANCELLED
        )
    )
    total_sales = total_sales_result.scalar()

    # total orders
    total_orders_result = await db.execute(
        select(func.count(Order.id))
    )
    total_orders = total_orders_result.scalar()

    # total users
    total_users_result = await db.execute(
        select(func.count(User.id))
    )
    total_users = total_users_result.scalar()

    # total products
    total_products_result = await db.execute(
        select(func.count(Product.id))
    )
    total_products = total_products_result.scalar()

    # total categories
    total_categories_result = await db.execute(
        select(func.count(Category.id))
    )
    total_categories = total_categories_result.scalar()

    # recent orders (last 10)
    recent_orders_result = await db.execute(
        select(Order)
        .order_by(Order.created_at.desc())
        .limit(10)
    )
    recent_orders = recent_orders_result.scalars().all()

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "user": current_user,
            "total_sales": total_sales,
            "total_orders": total_orders,
            "total_users": total_users,
            "total_products": total_products,
            "total_categories": total_categories,
            "recent_orders": recent_orders,
        },
    )

# ──────────────────────────────────────────────
# Product management
# ──────────────────────────────────────────────
@router.get("/products", name="admin_products")
async def admin_products(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    category_id: Optional[int] = None,
):
    query = select(Product).options(selectinload(Product.category))
    if category_id:
        query = query.where(Product.category_id == category_id)
    query = query.order_by(Product.id.desc())
    result = await db.execute(query)
    products = result.scalars().all()

    categories_result = await db.execute(select(Category).order_by(Category.name))
    categories = categories_result.scalars().all()

    return templates.TemplateResponse(
        "admin/products.html",
        {
            "request": request,
            "user": current_user,
            "products": products,
            "categories": categories,
            "selected_category": category_id,
        },
    )

@router.get("/products/create", name="admin_product_create")
async def admin_product_create_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    categories_result = await db.execute(select(Category).order_by(Category.name))
    categories = categories_result.scalars().all()
    return templates.TemplateResponse(
        "admin/product_form.html",
        {
            "request": request,
            "user": current_user,
            "product": None,
            "categories": categories,
        },
    )

@router.post("/products/create", name="admin_product_create_post")
async def admin_product_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    stock: int = Form(0),
    category_id: int = Form(...),
    image_url: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    # validate category exists
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    product = Product(
        name=name,
        description=description,
        price=price,
        stock=stock,
        category_id=category_id,
        image_url=image_url,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return RedirectResponse(
        url=router.url_path_for("admin_products"),
        status_code=status.HTTP_303_SEE_OTHER,
    )

@router.get("/products/{product_id}/edit", name="admin_product_edit")
async def admin_product_edit_form(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    categories_result = await db.execute(select(Category).order_by(Category.name))
    categories = categories_result.scalars().all()
    return templates.TemplateResponse(
        "admin/product_form.html",
        {
            "request": request,
            "user": current_user,
            "product": product,
            "categories": categories,
        },
    )

@router.post("/products/{product_id}/edit", name="admin_product_edit_post")
async def admin_product_edit(
    request: Request,
    product_id: int,
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    stock: int = Form(0),
    category_id: int = Form(...),
    image_url: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    product.name = name
    product.description = description
    product.price = price
    product.stock = stock
    product.category_id = category_id
    product.image_url = image_url

    await db.commit()
    await db.refresh(product)
    return RedirectResponse(
        url=router.url_path_for("admin_products"),
        status_code=status.HTTP_303_SEE_OTHER,
    )

@router.post("/products/{product_id}/delete", name="admin_product_delete")
async def admin_product_delete(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.delete(product)
    await db.commit()
    return RedirectResponse(
        url=router.url_path_for("admin_products"),
        status_code=status.HTTP_303_SEE_OTHER,
    )

# ──────────────────────────────────────────────
# Category management
# ──────────────────────────────────────────────
@router.get("/categories", name="admin_categories")
async def admin_categories(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    result = await db.execute(select(Category).order_by(Category.name))
    categories = result.scalars().all()
    return templates.TemplateResponse(
        "admin/categories.html",
        {"request": request, "user": current_user, "categories": categories},
    )

@router.get("/categories/create", name="admin_category_create")
async def admin_category_create_form(
    request: Request,
    current_user: User = Depends(get_current_admin),
):
    return templates.TemplateResponse(
        "admin/category_form.html",
        {"request": request, "user": current_user, "category": None},
    )

@router.post("/categories/create", name="admin_category_create_post")
async def admin_category_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    # Check for duplicate name
    existing = await db.execute(
        select(Category).where(Category.name == name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Category name already exists")

    category = Category(name=name, description=description)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return RedirectResponse(
        url=router.url_path_for("admin_categories"),
        status_code=status.HTTP_303_SEE_OTHER,
    )

@router.get("/categories/{category_id}/edit", name="admin_category_edit")
async def admin_category_edit_form(
    request: Request,
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return templates.TemplateResponse(
        "admin/category_form.html",
        {"request": request, "user": current_user, "category": category},
    )

@router.post("/categories/{category_id}/edit", name="admin_category_edit_post")
async def admin_category_edit(
    request: Request,
    category_id: int,
    name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check for duplicate name (exclude current)
    existing = await db.execute(
        select(Category).where(Category.name == name, Category.id != category_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Category name already exists")

    category.name = name
    category.description = description
    await db.commit()
    await db.refresh(category)
    return RedirectResponse(
        url=router.url_path_for("admin_categories"),
        status_code=status.HTTP_303_SEE_OTHER,
    )

@router.post("/categories/{category_id}/delete", name="admin_category_delete")
async def admin_category_delete(
    request: Request,
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check if category has products
    products_count = await db.execute(
        select(func.count(Product.id)).where(Product.category_id == category_id)
    )
    if products_count.scalar() > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete category with associated products. Remove products first.",
        )

    await db.delete(category)
    await db.commit()
    return RedirectResponse(
        url=router.url_path_for("admin_categories"),
        status_code=status.HTTP_303_SEE_OTHER,
    )

# ──────────────────────────────────────────────
# Order management
# ──────────────────────────────────────────────
@router.get("/orders", name="admin_orders")
async def admin_orders(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    status_filter: Optional[str] = None,
):
    query = select(Order).options(selectinload(Order.user), selectinload(Order.items))
    if status_filter:
        query = query.where(Order.status == status_filter)
    query = query.order_by(Order.created_at.desc())
    result = await db.execute(query)
    orders = result.scalars().all()

    return templates.TemplateResponse(
        "admin/orders.html",
        {
            "request": request,
            "user": current_user,
            "orders": orders,
            "current_filter": status_filter,
            "statuses": [s.value for s in OrderStatusEnum],
        },
    )

@router.post("/orders/{order_id}/status", name="admin_order_update_status")
async def admin_order_update_status(
    request: Request,
    order_id: int,
    new_status: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Validate status
    try:
        order.status = OrderStatusEnum(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order status")

    await db.commit()
    await db.refresh(order)
    return RedirectResponse(
        url=router.url_path_for("admin_orders"),
        status_code=status.HTTP_303_SEE_OTHER,
    )

# ──────────────────────────────────────────────
# User management
# ──────────────────────────────────────────────
@router.get("/users", name="admin_users")
async def admin_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "user": current_user, "users": users},
    )

@router.post("/users/{user_id}/toggle-active", name="admin_user_toggle_active")
async def admin_user_toggle_active(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deactivating yourself
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    user.is_active = not user.is_active
    await db.commit()
    return RedirectResponse(
        url=router.url_path_for("admin_users"),
        status_code=status.HTTP_303_SEE_OTHER,
    )