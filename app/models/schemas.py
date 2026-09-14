from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PhoneLookupRequest(BaseModel):
    number: str = Field(..., description="Phone number to analyze (any format, e.g. +351912345678 or 912345678)")
    refresh: bool = Field(False, description="Bypass cache and force fresh scraping")


class NormalizedNumberInfo(BaseModel):
    raw_input: str
    e164: str
    national_format: str
    international_format: str
    country_code: int
    country_name: str
    region_code: str
    line_type: str
    is_valid: bool
    is_possible: bool
    carrier_name: Optional[str] = None


class AnacomInfo(BaseModel):
    matched_prefix: Optional[str] = None
    service_type: Optional[str] = None
    designation: Optional[str] = None
    geographic_area: Optional[str] = None
    primary_operators: List[str] = Field(default_factory=list)
    technology: Optional[str] = None
    is_voip: bool = False
    base_risk_modifier: int = 0
    notes: Optional[str] = None


class CrowdsourcedComment(BaseModel):
    source: str
    author: Optional[str] = None
    date: Optional[str] = None
    text: str
    tag: Optional[str] = None


class ScraperSourceResult(BaseModel):
    source_name: str
    success: bool
    spam_score: Optional[float] = None  # Normalized 0.0 - 10.0 scale
    search_count: Optional[int] = 0
    report_count: Optional[int] = 0
    top_tags: List[str] = Field(default_factory=list)
    comments: List[CrowdsourcedComment] = Field(default_factory=list)
    error_message: Optional[str] = None


class CommercialEntityInfo(BaseModel):
    is_commercial_entity: bool = False
    entity_name: Optional[str] = None
    category: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    evidence_snippets: List[str] = Field(default_factory=list)
    confidence: Optional[str] = None
    matched_by: Optional[str] = None
    consensus_count: int = 0


class AggregatedIntelligenceResponse(BaseModel):
    normalized: NormalizedNumberInfo
    anacom: Optional[AnacomInfo] = None
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    risk_score: int  # 0 to 100
    confidence: str = "LOW"  # HIGH, MEDIUM, LOW
    matched_by: str = "anacom_range"  # trusted_directory_exact, geographic_prefix_inference, anacom_range, dork_inference, crowdsourced_only
    caller_category: str  # e.g., Telemarketing, Burla / MBWay, Cobranças, Empresa Legítima, Desconhecido
    recommendation: str
    recommendation_en: str
    operator_metadata: Dict[str, Any] = Field(default_factory=dict)
    crowdsourced_reports: Dict[str, Any] = Field(default_factory=dict)
    commercial_entity: Optional[CommercialEntityInfo] = None
    sources: List[ScraperSourceResult] = Field(default_factory=list)
    cached: bool = False
    cached_at: Optional[str] = None
    query_duration_ms: float = 0.0


class UserReportCreate(BaseModel):
    phone_number: str
    category: str = Field(..., description="Category: Telemarketing, Burla / MBWay, Cobranças, Chamada Silenciosa, Empresa Legítima, Outro")
    caller_name: Optional[str] = None
    comment: str = Field(..., min_length=3, max_length=1000)
    risk_rating: int = Field(5, ge=1, le=10, description="Risk rating from 1 (Safe) to 10 (High Risk/Fraud)")


class UserReportResponse(BaseModel):
    id: int
    phone_e164: str
    category: str
    caller_name: Optional[str]
    comment: str
    risk_rating: int
    created_at: datetime


class LookupHistoryItem(BaseModel):
    id: int
    phone_e164: str
    national_format: Optional[str]
    country_code: Optional[str]
    risk_level: str
    risk_score: int
    confidence: Optional[str] = "LOW"
    matched_by: Optional[str] = "anacom_range"
    caller_category: str
    carrier: Optional[str]
    searched_at: datetime


class HealthCheckResponse(BaseModel):
    status: str
    version: str
    anacom_prefixes_loaded: int
    database_connected: bool
