import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.dependencies import get_current_user, require_admin
from models.category import Category
from models.product import Product
from schemas.product import ProductCreate, ProductUpdate
from services import product_service

# Optional: use aiofiles for async file writes
try:
    import aiofiles
except ImportError:
    aiofiles = None

router = APIRouter(prefix="/products", tags=["products"])
admin_router = APIRouter(prefix="/admin/products", tags=["admin_products"])

templates = Jinja2Templates(directory="templates")

# Media settings
MEDIA_ROOT = Path("static/uploads/products")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
PUBLIC_MEDIA_URL = "/static/uploads/products"


# --------------------- Public endpoints ---------------------
@router.get("/", response_class=HTMLResponse)
async def product_list(
    request: Request,
    page: int = 1,
    per_page: int = 12,
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    db: AsyncSession = Depends(get_async_session),
):
    """
    List products with search, category filter, and pagination.
    Returns an HTML template.
    """
    # Build base query
    query = select(Product).where(Product.is_active == True)
    count_query = select(func.count(Product.id)).where(Product.is_active == True)

    if q:
        # Search by name or description
        search_pattern = f"%{q}%"
        query = query.where(
            (Product.name.ilike(search_pattern)) | (Product.description.ilike(search_pattern))
        )
        count_query = count_query.where(
            (Product.name.ilike(search_pattern)) | (Product.description.ilike(search_pattern))
        )
    if category_id:
        query = query.where(Product.category_id == category_id)
        count_query = count_query.where(Product.category_id == category_id)

    # Pagination
    total = (await db.execute(count_query)).scalar()
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page).order_by(Product.created_at.desc())

    result = await db.execute(query)
    products = result.scalars().all()

    # Get categories for filter
    categories_result = await db.execute(select(Category).where(Category.is_active == True))
    categories = categories_result.scalars().all()

    return templates.TemplateResponse(
        "products/list.html",
        {
            "request": request,
            "products": products,
            "categories": categories,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "q": q,
            "category_id": category_id,
            "title": "Products",
        },
    )


@router.get("/{product_id}/", response_class=HTMLResponse)
async def product_detail(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Show product details with reviews.
    """
    product = await db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")

    # Fetch reviews (assuming a Review model exists)
    from models.review import Review  # lazy import to avoid circular
    reviews_result = await db.execute(
        select(Review).where(Review.product_id == product_id).order_by(Review.created_at.desc())
    )
    reviews = reviews_result.scalars().all()

    return templates.TemplateResponse(
        "products/detail.html",
        {
            "request": request,
            "product": product,
            "reviews": reviews,
            "title": product.name,
        },
    )


# --------------------- Admin CRUD endpoints ---------------------
@admin_router.get("/", response_class=HTMLResponse)
async def admin_product_list(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user=Depends(require_admin),
):
    """
    Admin product list (all products, including inactive).
    """
    query = select(Product)
    count_query = select(func.count(Product.id))

    if q:
        search_pattern = f"%{q}%"
        query = query.where(
            (Product.name.ilike(search_pattern)) | (Product.description.ilike(search_pattern))
        )
        count_query = count_query.where(
            (Product.name.ilike(search_pattern)) | (Product.description.ilike(search_pattern))
        )

    total = (await db.execute(count_query)).scalar()
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page).order_by(Product.created_at.desc())

    result = await db.execute(query)
    products = result.scalars().all()

    return templates.TemplateResponse(
        "admin/products/list.html",
        {
            "request": request,
            "products": products,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "q": q,
            "title": "Admin Products",
        },
    )


@admin_router.get("/create", response_class=HTMLResponse)
async def admin_create_product_form(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user=Depends(require_admin),
):
    """Show create product form."""
    categories = await _get_active_categories(db)
    return templates.TemplateResponse(
        "admin/products/create.html",
        {"request": request, "categories": categories, "title": "Create Product"},
    )


@admin_router.post("/create", response_class=HTMLResponse)
async def admin_create_product(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    stock: int = Form(0),
    category_id: int = Form(None),
    image: Optional[UploadFile] = File(None),
    is_active: bool = Form(True),
    db: AsyncSession = Depends(get_async_session),
    current_user=Depends(require_admin),
):
    """Handle product creation (with optional image upload)."""
    # Validate
    if price <= 0:
        return templates.TemplateResponse(
            "admin/products/create.html",
            {
                "request": request,
                "error": "Price must be greater than 0.",
                "categories": await _get_active_categories(db),
                "title": "Create Product",
            },
            status_code=422,
        )

    # Save image if provided
    image_url = None
    if image and image.filename:
        image_url = await _save_image(image)

    # Create product
    new_product = Product(
        name=name,
        description=description,
        price=price,
        stock=stock,
        category_id=category_id,
        image_url=image_url,
        is_active=is_active,
    )
    db.add(new_product)
    await db.commit()
    await db.refresh(new_product)

    return RedirectResponse(
        url=f"/admin/products/{new_product.id}/edit", status_code=303
    )


@admin_router.get("/{product_id}/edit", response_class=HTMLResponse)
async def admin_edit_product_form(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user=Depends(require_admin),
):
    """Show edit product form."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    categories = await _get_active_categories(db)
    return templates.TemplateResponse(
        "admin/products/edit.html",
        {
            "request": request,
            "product": product,
            "categories": categories,
            "title": "Edit Product",
        },
    )


@admin_router.post("/{product_id}/edit", response_class=HTMLResponse)
async def admin_update_product(
    request: Request,
    product_id: int,
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    stock: int = Form(0),
    category_id: int = Form(None),
    image: Optional[UploadFile] = File(None),
    is_active: bool = Form(True),
    db: AsyncSession = Depends(get_async_session),
    current_user=Depends(require_admin),
):
    """Process product update."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if price <= 0:
        categories = await _get_active_categories(db)
        return templates.TemplateResponse(
            "admin/products/edit.html",
            {
                "request": request,
                "product": product,
                "categories": categories,
                "error": "Price must be greater than 0.",
                "title": "Edit Product",
            },
            status_code=422,
        )

    # Update fields
    product.name = name
    product.description = description
    product.price = price
    product.stock = stock
    product.category_id = category_id
    product.is_active = is_active

    # Handle image replacement
    if image and image.filename:
        # Delete old image if exists
        if product.image_url:
            old_path = MEDIA_ROOT / product.image_url.replace(PUBLIC_MEDIA_URL + "/", "")
            if old_path.exists():
                os.remove(old_path)
        # Save new image
        product.image_url = await _save_image(image)

    await db.commit()
    await db.refresh(product)

    return RedirectResponse(
        url=f"/admin/products/{product_id}/edit", status_code=303
    )


@admin_router.post("/{product_id}/delete")
async def admin_delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user=Depends(require_admin),
):
    """Delete product (hard delete)."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Delete image file if exists
    if product.image_url:
        file_path = MEDIA_ROOT / product.image_url.replace(PUBLIC_MEDIA_URL + "/", "")
        if file_path.exists():
            os.remove(file_path)

    await db.delete(product)
    await db.commit()

    return RedirectResponse(url="/admin/products/", status_code=303)


# --------------------- Helper functions ---------------------
async def _get_active_categories(db: AsyncSession):
    result = await db.execute(select(Category).where(Category.is_active == True))
    return result.scalars().all()


async def _save_image(upload_file: UploadFile) -> str:
    """
    Save an uploaded image to the media directory and return the public URL.
    Uses a unique filename to avoid collisions.
    """
    # Ensure directory exists (already created at module level)
    ext = os.path.splitext(upload_file.filename)[1] if upload_file.filename else ".jpg"
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = MEDIA_ROOT / unique_filename

    # Write file (async if aiofiles available, else sync)
    if aiofiles:
        async with aiofiles.open(str(file_path), "wb") as f:
            content = await upload_file.read()
            await f.write(content)
    else:
        with open(str(file_path), "wb") as f:
            f.write(upload_file.file.read())

    return f"{PUBLIC_MEDIA_URL}/{unique_filename}"