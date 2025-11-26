# epicservice/database/models.py

from typing import List, Optional
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    saved_lists: Mapped[List["SavedList"]] = relationship(back_populates="user")
    temp_list_items: Mapped[List["TempList"]] = relationship(back_populates="user")

class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    артикул: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    назва: Mapped[str] = mapped_column(String(255))
    відділ: Mapped[int] = mapped_column(BigInteger)
    група: Mapped[str] = mapped_column(String(100))
    кількість: Mapped[str] = mapped_column(String(50))
    відкладено: Mapped[int] = mapped_column(Integer, default=0)
    
    місяці_без_руху: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    сума_залишку: Mapped[float] = mapped_column(Float, nullable=True, default=0.0)
    ціна: Mapped[float] = mapped_column(Float, nullable=True, default=0.0)
    активний: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

class StockHistory(Base):
    """Історія змін залишків товару."""
    __tablename__ = 'stock_history'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'), index=True)
    articul: Mapped[str] = mapped_column(String(20))
    old_quantity: Mapped[str] = mapped_column(String(50))
    new_quantity: Mapped[str] = mapped_column(String(50))
    change_source: Mapped[str] = mapped_column(String(50)) # 'import', 'user_list', 'manual'
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

class SavedList(Base):
    __tablename__ = 'saved_lists'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    file_name: Mapped[str] = mapped_column(String(100))
    file_path: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=func.now())

    items: Mapped[List["SavedListItem"]] = relationship(back_populates="saved_list", cascade="all, delete-orphan")
    user: Mapped["User"] = relationship(back_populates="saved_lists")

class SavedListItem(Base):
    __tablename__ = 'saved_list_items'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(ForeignKey('saved_lists.id'))
    article_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)

    saved_list: Mapped["SavedList"] = relationship(back_populates="items")

class TempList(Base):
    __tablename__ = 'temp_lists'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    quantity: Mapped[int] = mapped_column(Integer)

    product: Mapped["Product"] = relationship()
    user: Mapped["User"] = relationship(back_populates="temp_list_items")