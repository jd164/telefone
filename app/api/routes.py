from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import UserReport, LookupHistory, SearchCache
from app.db.session import get_db
from app.engine.aggregator import aggregator
from app.engine.anacom import anacom_db
from app.engine.normalizer import normalize_phone_number
from app.models.schemas import (
    AggregatedIntelligenceResponse,
    UserReportCreate,
    UserReportResponse,
    LookupHistoryItem,
    HealthCheckResponse,
    AnacomInfo,
)

router = APIRouter()


@router.get("/lookup", response_model=AggregatedIntelligenceResponse, summary="Analyze Phone Number")
async def lookup_phone_number(
    number: str = Query(..., description="Phone number to investigate (e.g. +351912345678, 213456789)"),
    refresh: bool = Query(False, description="Force fresh scrape and bypass cache"),
    db: AsyncSession = Depends(get_db),
):
    """
    Main orchestrator endpoint:
    1. Normalizes number via Google libphonenumber.
    2. Checks SQLite cache (TTL: 24h).
    3. Resolves ANACOM PNN prefix allocation & carrier metadata.
    4. Executes asynchronous scrapers (Tellows, Ligaram-me, ShouldIAnswer, DuckDuckGo entity).
    5. Computes synthesized risk score (0-100) and actionable safety recommendation.
    """
    if not number or not number.strip():
        raise HTTPException(status_code=400, detail="Phone number must not be empty.")

    try:
        response = await aggregator.aggregate(phone_input=number, refresh=refresh, session=db)
        return response
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Intelligence aggregation error: {str(exc)}")


@router.post("/report", response_model=UserReportResponse, summary="Submit User Community Report")
async def submit_report(
    report: UserReportCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Allows users to report unknown/incoming numbers (e.g. MBWay Scam, Telemarketing, Silent call).
    Immediately updates the database and purges old cache for real-time intelligence.
    """
    norm = normalize_phone_number(report.phone_number)
    e164 = norm.e164

    new_report = UserReport(
        phone_e164=e164,
        category=report.category,
        caller_name=report.caller_name,
        comment=report.comment.strip(),
        risk_rating=report.risk_rating,
    )
    db.add(new_report)

    # Invalidate search cache for this number so next lookup synthesizes the new report
    cache_entry = await db.get(SearchCache, e164)
    if cache_entry:
        await db.delete(cache_entry)

    await db.commit()
    await db.refresh(new_report)

    return new_report


@router.get("/reports/{number}", response_model=List[UserReportResponse], summary="List Reports for a Number")
async def list_reports_for_number(
    number: str,
    db: AsyncSession = Depends(get_db),
):
    norm = normalize_phone_number(number)
    query = (
        select(UserReport)
        .where(UserReport.phone_e164 == norm.e164)
        .order_by(desc(UserReport.created_at))
        .limit(50)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/history", response_model=List[LookupHistoryItem], summary="Get Recent Lookup History")
async def get_history(
    limit: int = Query(15, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(LookupHistory).order_by(desc(LookupHistory.searched_at)).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/anacom/prefixes", summary="List ANACOM National Numbering Plan (PNN) Rules")
async def list_anacom_prefixes():
    return {
        "authority": "ANACOM (Portugal)",
        "total_rules": anacom_db.total_prefixes,
        "rules": anacom_db.prefix_rules,
    }


@router.get("/health", response_model=HealthCheckResponse, summary="Health Check")
async def health_check(db: AsyncSession = Depends(get_db)):
    db_ok = True
    try:
        await db.execute(select(1))
    except Exception:
        db_ok = False

    return HealthCheckResponse(
        status="healthy" if db_ok else "degraded",
        version=settings.APP_VERSION,
        anacom_prefixes_loaded=anacom_db.total_prefixes,
        database_connected=db_ok,
    )


@router.get("/admin/directory-stats", summary="Admin Directory Statistics (Curated vs Scraped)")
async def admin_directory_stats():
    from app.engine.trusted_directory import paginas_amarelas_db
    from app.engine.geographic_matcher import police_scraper, geographic_matcher

    stats = paginas_amarelas_db.get_directory_stats()
    stats["last_scraper_run"] = {
        "scraped": police_scraper.last_scraped_count,
        "failed": police_scraper.last_failed_count,
    }
    stats["active_institutional_blocks"] = len(geographic_matcher.active_blocks)
    return stats


@router.get("/admin/coverage-report", summary="Admin Police & Public Service Coverage Report by District")
async def admin_coverage_report():
    from app.engine.geographic_matcher import geographic_matcher
    return geographic_matcher.get_coverage_report()

