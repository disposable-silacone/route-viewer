from fastapi import APIRouter

from app.db.repositories import CustomerRepository
from app.db.session import SessionLocal


router = APIRouter()


@router.get("")
def list_customers() -> dict:
    with SessionLocal() as db:
        repo = CustomerRepository(db)
        customers = repo.list_with_activity_counts()
        return {"customers": customers}
