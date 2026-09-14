from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SearchCache(Base):
    __tablename__ = "search_cache"

    phone_e164 = Column(String(32), primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    data_json = Column(Text, nullable=False)


class UserReport(Base):
    __tablename__ = "user_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_e164 = Column(String(32), index=True, nullable=False)
    category = Column(String(64), nullable=False)
    caller_name = Column(String(128), nullable=True)
    comment = Column(Text, nullable=False)
    risk_rating = Column(Integer, default=5, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class LookupHistory(Base):
    __tablename__ = "lookup_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_e164 = Column(String(32), index=True, nullable=False)
    national_format = Column(String(32), nullable=True)
    country_code = Column(String(8), nullable=True)
    risk_level = Column(String(16), nullable=False)
    risk_score = Column(Integer, nullable=False)
    confidence = Column(String(16), default="LOW", nullable=True)
    matched_by = Column(String(64), default="anacom_range", nullable=True)
    caller_category = Column(String(64), nullable=False)
    carrier = Column(String(128), nullable=True)
    searched_at = Column(DateTime, default=utcnow, nullable=False)


class DorkCache(Base):
    __tablename__ = "dork_cache"

    phone_e164 = Column(String(32), primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    data_json = Column(Text, nullable=False)

