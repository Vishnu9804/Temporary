from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base
from datetime import datetime

# 0. Client Table for Security/Auth
class ClientAuth(Base):
    __tablename__ = "clients"
    client_id = Column(String, primary_key=True, index=True)
    password = Column(String, nullable=False)
    services = Column(JSONB, nullable=False) # e.g. ["chat", "inventory"]
    
    # NEW COLUMNS ADDED
    name = Column(String, nullable=True)
    region = Column(String, default="US")
    vertical = Column(String, default="Cosmetics")

class Customer(Base):
    __tablename__ = "customers"
    client_id = Column(String, primary_key=True, index=True)
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    phone = Column(String, nullable=True)
    account_created_at = Column(DateTime, default=datetime.utcnow)
    marketing_opt_in = Column(Boolean, default=True)
    loyalty_tier = Column(String, nullable=True)
    beauty_profile = Column(JSONB, nullable=True)

class Product(Base):
    __tablename__ = "products"
    client_id = Column(String, primary_key=True, index=True)
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    category = Column(String)
    price = Column(Numeric)
    cost_price = Column(Numeric)
    min_allowable_price = Column(Numeric, nullable=True)
    competitor_price = Column(Numeric, nullable=True)
    competitor_pricing_data = Column(JSONB, nullable=True)
    discount_percentage = Column(Numeric, nullable=True)
    stock = Column(Integer)
    skin_type = Column(String, nullable=True)
    description = Column(String, nullable=True)
    core_matrix_tags = Column(JSONB, nullable=True)
    key_ingredients = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    ad_creatives = Column(JSONB, nullable=True)

class Order(Base):
    __tablename__ = "orders"
    client_id = Column(String, primary_key=True, index=True)
    id = Column(String, primary_key=True, index=True)
    customer_id = Column(String, index=True)
    status = Column(String)
    return_status = Column(String, default="none")
    tracking_number = Column(String, nullable=True)
    shipping_carrier = Column(String, nullable=True)
    created_at = Column(DateTime)
    subtotal = Column(Numeric)
    discount_applied = Column(Numeric, nullable=True)
    total_amount = Column(Numeric)
    items = Column(JSONB)

class ReturnRMA(Base):
    __tablename__ = "returns"
    client_id = Column(String, primary_key=True, index=True)
    id = Column(String, primary_key=True, index=True)
    order_id = Column(String)
    customer_id = Column(String)
    status = Column(String)
    return_reason = Column(String)
    customer_comment = Column(String, nullable=True)
    created_at = Column(DateTime)
    items = Column(JSONB)

class Restock(Base):
    __tablename__ = "restocks"
    client_id = Column(String, primary_key=True, index=True)
    purchase_id = Column(String, primary_key=True, index=True)
    product_id = Column(String)
    supplier = Column(String)
    quantity_ordered = Column(Integer)
    unit_cost = Column(Numeric, nullable=True)
    total_cost = Column(Numeric)
    order_date = Column(DateTime)
    delivery_date = Column(DateTime, nullable=True)