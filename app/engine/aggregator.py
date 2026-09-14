import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import SearchCache, UserReport, LookupHistory
from app.db.session import AsyncSessionLocal
from app.engine.normalizer import normalize_phone_number
from app.engine.anacom import anacom_db
from app.engine.trusted_directory import lookup_trusted_directory
from app.engine.geographic_matcher import geographic_matcher
from app.core.observability import PipelineTelemetry
from app.engine.scrapers.tellows import TellowsScraper
from app.engine.scrapers.quem_liga import QuemLigaScraper
from app.engine.scrapers.should_i_answer import ShouldIAnswerScraper
from app.engine.scrapers.unknown_phone import UnknownPhoneScraper
from app.engine.scrapers.search_entity import CommercialEntityVerifier
from app.engine.scrapers.dork_engine import SearchDorkEngine
from app.models.schemas import (
    AggregatedIntelligenceResponse,
    NormalizedNumberInfo,
    AnacomInfo,
    ScraperSourceResult,
    CommercialEntityInfo,
    CrowdsourcedComment,
)

logger = logging.getLogger(__name__)


class PhoneIntelligenceAggregator:
    def __init__(self):
        self.tellows = TellowsScraper()
        self.quem_liga = QuemLigaScraper()
        self.should_i_answer = ShouldIAnswerScraper()
        self.unknown_phone = UnknownPhoneScraper()
        self.entity_verifier = CommercialEntityVerifier()
        self.dork_engine = SearchDorkEngine()

    async def aggregate(
        self,
        phone_input: str,
        refresh: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> AggregatedIntelligenceResponse:
        start_time = time.perf_counter()

        # 1. Normalization & libphonenumber analysis
        normalized: NormalizedNumberInfo = normalize_phone_number(phone_input)
        e164 = normalized.e164
        telemetry = PipelineTelemetry(e164)

        # 2. Check SQLite cache unless refresh is requested
        if not refresh and settings.CACHE_ENABLED:
            cached_resp = await self._get_cached_result(e164)
            if cached_resp:
                cached_resp.query_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                telemetry.finish(
                    risk_score=cached_resp.risk_score,
                    risk_level=cached_resp.risk_level,
                    confidence=cached_resp.confidence,
                    matched_by=cached_resp.matched_by,
                    cached=True,
                )
                return cached_resp

        # 3. ANACOM PNN lookup (instant microsecond in-memory match)
        anacom_info: Optional[AnacomInfo] = anacom_db.lookup(e164)
        telemetry.record_layer("anacom", "hit" if anacom_info else "miss")

        # 4. Check Curated Trusted Directory (Official Public Entities, Emergency, Health, Utilities)
        trusted_entry = lookup_trusted_directory(e164, normalized.national_format)
        telemetry.record_layer("trusted_directory", "hit" if trusted_entry else "miss")

        # 5. Check Geographic & Institutional Prefix Fallback (PSP, GNR, Hospitals, Municipalities)
        geo_inference = geographic_matcher.match_institutional_range(e164, normalized.national_format)
        telemetry.record_layer("geographic_matcher", "hit" if geo_inference else "miss")

        # 6. Fetch local community reports from SQLite
        local_reports = await self._get_local_reports(e164)

        # 7. Run asynchronous parallel workers across external databases & dork engines
        sources: List[ScraperSourceResult] = []
        entity_info: Optional[CommercialEntityInfo] = None

        async def run_tellows():
            try:
                res = await self.tellows.query(e164, normalized.national_format)
                telemetry.record_layer("tellows", "ok" if res.success else "fail")
                return res
            except Exception as e:
                telemetry.record_layer("tellows", "fail")
                logger.debug("Tellows worker failed: %s", e)
                return ScraperSourceResult(source_name=self.tellows.source_name, success=False, error_message=str(e))

        async def run_quem_liga():
            try:
                res = await self.quem_liga.query(e164, normalized.national_format)
                telemetry.record_layer("quem_liga", "ok" if res.success else "fail")
                return res
            except Exception as e:
                telemetry.record_layer("quem_liga", "fail")
                logger.debug("QuemLiga worker failed: %s", e)
                return ScraperSourceResult(source_name=self.quem_liga.source_name, success=False, error_message=str(e))

        async def run_should_i_answer():
            try:
                res = await self.should_i_answer.query(e164, normalized.national_format)
                telemetry.record_layer("should_i_answer", "ok" if res.success else "fail")
                return res
            except Exception as e:
                telemetry.record_layer("should_i_answer", "fail")
                logger.debug("ShouldIAnswer worker failed: %s", e)
                return ScraperSourceResult(source_name=self.should_i_answer.source_name, success=False, error_message=str(e))

        async def run_unknown_phone():
            try:
                res = await self.unknown_phone.query(e164, normalized.national_format)
                telemetry.record_layer("unknown_phone", "ok" if res.success else "fail")
                return res
            except Exception as e:
                telemetry.record_layer("unknown_phone", "fail")
                logger.debug("UnknownPhone worker failed: %s", e)
                return ScraperSourceResult(source_name=self.unknown_phone.source_name, success=False, error_message=str(e))

        async def run_verifier():
            try:
                return await self.entity_verifier.verify_entity(e164, normalized.national_format)
            except Exception as e:
                logger.debug("Entity verifier failed: %s", e)
                return CommercialEntityInfo(is_commercial_entity=False)

        async def run_dorks():
            try:
                dork_res = await self.dork_engine.search_dorks(e164, normalized.national_format)
                telemetry.record_layer("dork_engine", "hit" if dork_res and dork_res.is_commercial_entity else "miss")
                return dork_res
            except Exception as e:
                telemetry.record_layer("dork_engine", "fail")
                logger.debug("Dork engine failed: %s", e)
                return None

        worker_results = await asyncio.gather(
            run_tellows(),
            run_quem_liga(),
            run_should_i_answer(),
            run_unknown_phone(),
            run_verifier(),
            run_dorks(),
            return_exceptions=True,
        )

        for i in range(4):
            res = worker_results[i]
            if isinstance(res, ScraperSourceResult):
                sources.append(res)

        entity_info = worker_results[4] if isinstance(worker_results[4], CommercialEntityInfo) else CommercialEntityInfo(is_commercial_entity=False)
        dork_info = worker_results[5] if isinstance(worker_results[5], CommercialEntityInfo) else None

        # Determine Commercial / Institutional Entity Presentation
        if trusted_entry:
            entity_info = CommercialEntityInfo(
                is_commercial_entity=True,
                entity_name=trusted_entry["name"],
                category=trusted_entry.get("category", "Entidade Oficial"),
                website=trusted_entry.get("website"),
                address=trusted_entry.get("address", "Portugal"),
                evidence_snippets=["Registo oficial verificado no Diretório Nacional / Páginas Amarelas."],
            )
        elif dork_info and dork_info.matched_by == "dork_consensus":
            # Multi-source OSINT consensus has specific entity name for the exact number
            entity_info = dork_info
        elif geo_inference:
            entity_info = CommercialEntityInfo(
                is_commercial_entity=True,
                entity_name=geo_inference["entity_hint"],
                category=geo_inference["institution_type"],
                website="https://www.portugal.gov.pt",
                address=geo_inference["district"],
                evidence_snippets=[geo_inference["description"]],
            )
        elif dork_info and dork_info.is_commercial_entity:
            entity_info = dork_info

        # 8. Synthesize Signals & Compute Separated Risk and Confidence
        risk_score, risk_level, confidence, matched_by, category, rec_pt, rec_en = self._synthesize_risk(
            normalized=normalized,
            anacom=anacom_info,
            sources=sources,
            local_reports=local_reports,
            commercial_entity=entity_info,
            is_trusted_directory=trusted_entry is not None,
            geo_inference=geo_inference,
            dork_info=dork_info,
        )

        # Aggregate comments & tags
        all_comments: List[CrowdsourcedComment] = []
        all_tags: List[str] = []
        total_searches = 0
        total_reports = len(local_reports)

        for src in sources:
            if src.success:
                all_comments.extend(src.comments)
                all_tags.extend(src.top_tags)
                total_searches += (src.search_count or 0)
                total_reports += (src.report_count or 0)

        # Include local reports as comments
        for rep in local_reports:
            all_comments.append(
                CrowdsourcedComment(
                    source="Comunidade Local",
                    author=rep.caller_name or "Utilizador",
                    date=rep.created_at.strftime("%Y-%m-%d"),
                    text=rep.comment,
                    tag=rep.category,
                )
            )
            all_tags.append(rep.category)

        unique_tags = list(dict.fromkeys([t for t in all_tags if t]))

        operator_metadata = {
            "assigned_carrier": (
                anacom_info.primary_operators[0]
                if anacom_info and anacom_info.primary_operators
                else normalized.carrier_name or "Desconhecido"
            ),
            "technology": anacom_info.technology if anacom_info else ("Cellular" if normalized.line_type == "MOBILE" else "PSTN"),
            "is_voip_nomadic": anacom_info.is_voip if anacom_info else (normalized.line_type == "VOIP"),
            "service_type": anacom_info.service_type if anacom_info else normalized.line_type,
            "geographic_area": anacom_info.geographic_area if anacom_info else normalized.country_name,
            "anacom_pnn_matched": anacom_info is not None,
        }

        crowdsourced_reports = {
            "total_reports": total_reports,
            "total_searches": total_searches,
            "tags": unique_tags,
            "recent_comments": [c.model_dump() for c in all_comments[:8]],
        }

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        response = AggregatedIntelligenceResponse(
            normalized=normalized,
            anacom=anacom_info,
            risk_level=risk_level,
            risk_score=risk_score,
            confidence=confidence,
            matched_by=matched_by,
            caller_category=category,
            recommendation=rec_pt,
            recommendation_en=rec_en,
            operator_metadata=operator_metadata,
            crowdsourced_reports=crowdsourced_reports,
            commercial_entity=entity_info,
            sources=sources,
            cached=False,
            cached_at=datetime.now(timezone.utc).isoformat(),
            query_duration_ms=duration_ms,
        )

        # 9. Emit structured JSON observability telemetry
        telemetry.finish(
            risk_score=risk_score,
            risk_level=risk_level,
            confidence=confidence,
            matched_by=matched_by,
            cached=False,
        )

        # 10. Persist to cache & search history in background
        asyncio.create_task(self._save_to_cache_and_history(response))

        return response

    def _synthesize_risk(
        self,
        normalized: NormalizedNumberInfo,
        anacom: Optional[AnacomInfo],
        sources: List[ScraperSourceResult],
        local_reports: List[UserReport],
        commercial_entity: Optional[CommercialEntityInfo],
        is_trusted_directory: bool = False,
        geo_inference: Optional[Dict[str, Any]] = None,
        dork_info: Optional[CommercialEntityInfo] = None,
    ) -> Tuple[int, str, str, str, str, str, str]:
        """
        Synthesizes signals with distinct separation between Risk Score (0-100) and Confidence (HIGH/MEDIUM/LOW).
        Risk is locked to 0 ONLY on HIGH confidence exact directory match.
        Medium confidence institutional prefix inference receives a low risk (10) and an inference recommendation.
        """
        # Rule 1: Exact match in curated official directory -> Confidence HIGH, Risk 0
        if is_trusted_directory:
            entity_title = commercial_entity.entity_name if commercial_entity and commercial_entity.entity_name else "Entidade Oficial"
            return (
                0,
                "LOW",
                "HIGH",
                "trusted_directory_exact",
                f"Entidade Oficial ({entity_title})",
                f"Número oficial e verificado ({entity_title}). Contacto legítimo de utilidade pública e segurança.",
                f"Official verified entity ({entity_title}). Legitimate public/police contact line.",
            )

        # Check local user reports
        user_marked_safe = any(r.risk_rating <= 2 for r in local_reports)
        user_marked_danger = any(r.risk_rating >= 8 for r in local_reports)

        # Gather crowdsourced metrics
        total_complaints = 0
        active_spam_scores = []
        for src in sources:
            if src.success:
                complaints_in_src = max(src.report_count or 0, len(src.comments))
                total_complaints += complaints_in_src
                if src.spam_score is not None and src.spam_score > 0:
                    active_spam_scores.append(src.spam_score * 10.0)

        for rep in local_reports:
            total_complaints += 1
            active_spam_scores.append(rep.risk_rating * 10.0)

        comment_texts = []
        for src in sources:
            if src.success:
                for c in src.comments:
                    comment_texts.append(c.text)
        for rep in local_reports:
            comment_texts.append(f"{rep.category} {rep.comment}")

        joined_comments = " ".join(comment_texts).lower()

        # Fraud pattern detection
        fraud_patterns = [
            r"\bmbway\b", r"\bmb\s*way\b", r"\bburla\b", r"\bphishing\b",
            r"\besquema\b", r"\bfalso\s*comprador\b", r"\bfalso\s*banco\b",
            r"\bpedir\s*c[óo]digo\b", r"\bcaixa\s*multibanco\b"
        ]
        has_fraud_keywords = any(re.search(pat, joined_comments) for pat in fraud_patterns)

        # Telemarketing pattern
        telemarketing_patterns = [
            r"\btelemarketing\b", r"\bvendas\b", r"\bcomercial\b", r"\bpromo[çc][ãa]o\b",
            r"\boperadora\b", r"\bcampanha\b"
        ]
        has_sales_keywords = any(re.search(pat, joined_comments) for pat in telemarketing_patterns)

        # Debt collection pattern
        debt_patterns = [r"\bcobran[çc]a\b", r"\brecupera[çc][ãa]o\b", r"\bd[íi]vida\b", r"\bintrum\b"]
        has_debt_keywords = any(re.search(pat, joined_comments) for pat in debt_patterns)

        # Silent pattern
        silent_patterns = [r"\bsilenciosa\b", r"\bping\s*call\b", r"\bdesliga\b", r"\bningu[ée]m\s*fala\b"]
        has_silent_keywords = any(re.search(pat, joined_comments) for pat in silent_patterns)

        is_confirmed_fraud = (
            (total_complaints > 0 and has_fraud_keywords and max(active_spam_scores or [0]) >= 60.0)
            or (user_marked_danger and has_fraud_keywords)
        )

        is_telemarketing = (total_complaints > 0 and (has_sales_keywords or max(active_spam_scores or [0]) >= 50.0))
        is_debt = (total_complaints > 0 and has_debt_keywords)
        is_silent = (total_complaints > 0 and has_silent_keywords)

        # Rule 2A: High-Confidence Dork Consensus (2+ independent sources agree -> HIGH confidence, risk 0-5)
        if dork_info and dork_info.is_commercial_entity and dork_info.matched_by == "dork_consensus" and not is_confirmed_fraud:
            entity_title = dork_info.entity_name or "Entidade Oficial / Força de Segurança"
            consensus_n = dork_info.consensus_count or 2
            return (
                0,
                "LOW",
                "HIGH",
                "dork_consensus",
                f"Entidade Oficial ({entity_title})",
                f"Consenso confirmado por múltiplas fontes independentes ({consensus_n} fontes): {entity_title}. Contacto oficial legítimo.",
                f"Multi-source OSINT consensus confirmed ({consensus_n} sources): {entity_title}. Legitimate official line.",
            )

        # Rule 2B: Geographic & Institutional Prefix Fallback (Confidence: MEDIUM, Risk: 10)
        # If number belongs to a known institutional block (PSP, GNR, hospital, CML) and no confirmed fraud
        if geo_inference and not is_confirmed_fraud:
            entity_hint = geo_inference.get("entity_hint", "Serviço Público")
            district = geo_inference.get("district", "Portugal")
            probable_cat = geo_inference.get("probable_category", f"Possível Força de Segurança ({district})")
            return (
                10,
                "LOW",
                "MEDIUM",
                "geographic_prefix_inference",
                probable_cat,
                f"Inferência de prefixo: número no bloco institucional de {entity_hint} ({district}). Contacto provável de serviço público ou força de segurança.",
                f"Prefix inference: number within institutional block of {entity_hint} ({district}). Probable public safety / governmental line.",
            )

        # Rule 3: Single-Source Dork Inference (Confidence: MEDIUM, Risk: 10)
        if dork_info and dork_info.is_commercial_entity and not is_confirmed_fraud:
            is_police_or_gov = any(
                k in (dork_info.category or "").lower() or k in (dork_info.entity_name or "").lower()
                for k in ["polícia", "psp", "gnr", "segurança pública", "hospital", "câmara municipal", "tribunal", "governo", "justiça", "esquadra", "posto"]
            )
            if is_police_or_gov:
                return (
                    10,
                    "LOW",
                    "MEDIUM",
                    "dork_inference",
                    f"Entidade Oficial ({dork_info.entity_name or 'Serviço Público'})",
                    f"Identificação por pesquisa OSINT (1 fonte independente): provável {dork_info.entity_name}. Contacto oficial legítimo.",
                    f"OSINT identification (1 independent source): probable {dork_info.entity_name}. Official legitimate contact.",
                )


        # Rule 4: Confirmed Fraud
        if is_confirmed_fraud:
            calc_score = max(85.0, sum(active_spam_scores) / len(active_spam_scores))
            confidence = "HIGH" if total_complaints >= 5 else "MEDIUM"
            return (
                int(min(100, round(calc_score))),
                "CRITICAL",
                confidence,
                "crowdsourced_only",
                "Burla / MBWay Phishing",
                "Bloquear imediatamente. Elevada probabilidade de burla financeira (MBWay ou impersonação bancária). Nunca forneça códigos ou dados confidenciais.",
                "Block immediately. High probability of financial scam (MBWay / banking fraud). Never share OTP codes or banking details.",
            )

        # Rule 5: Debt Collection
        if is_debt:
            calc_score = max(68.0, sum(active_spam_scores) / len(active_spam_scores))
            confidence = "HIGH" if total_complaints >= 6 else "MEDIUM"
            return (
                int(min(100, round(calc_score))),
                "HIGH",
                confidence,
                "crowdsourced_only",
                "Cobranças / Gestão de Dívidas",
                "Recomenda-se precaução. Histórico de chamadas de cobrança ou gestão de contencioso.",
                "Caution recommended. History of debt collection or litigation calls.",
            )

        # Rule 6: Silent Call / Robocall
        if is_silent:
            calc_score = max(62.0, sum(active_spam_scores) / len(active_spam_scores))
            confidence = "HIGH" if total_complaints >= 6 else "MEDIUM"
            return (
                int(min(100, round(calc_score))),
                "HIGH",
                confidence,
                "crowdsourced_only",
                "Chamada Silenciosa (Bot / Ping Call)",
                "Chamadas automatizadas silenciosas frequentes (ping calls / robocalls).",
                "Frequent automated silent calls (robocalls).",
            )

        # Rule 7: Telemarketing
        if is_telemarketing:
            calc_score = max(50.0, sum(active_spam_scores) / len(active_spam_scores))
            confidence = "HIGH" if total_complaints >= 6 else "MEDIUM"
            return (
                int(min(100, round(calc_score))),
                "MEDIUM" if calc_score < 60 else "HIGH",
                confidence,
                "crowdsourced_only",
                "Telemarketing / Vendas",
                "Chamada de telemarketing ou promoção comercial indesejada.",
                "Unwanted sales or telemarketing call.",
            )

        # Rule 8: Verified Commercial Business (e.g. from Dork Páginas Amarelas / eInforma)
        if commercial_entity and commercial_entity.is_commercial_entity:
            return (
                10,
                "LOW",
                "MEDIUM",
                "dork_inference",
                f"Empresa Legítima ({commercial_entity.entity_name or 'Comercial'})",
                f"Número legítimo associado a entidade comercial registada ({commercial_entity.entity_name}).",
                f"Legitimate commercial entity ({commercial_entity.entity_name}).",
            )

        # Rule 9: Special ANACOM Regulatory Services
        base_score = 5
        confidence = "LOW"
        matched_by = "anacom_range"
        category = "Número Limpo / Desconhecido"

        if anacom:
            if anacom.service_type == "Toll-Free":
                return (
                    0,
                    "LOW",
                    "HIGH",
                    "anacom_range",
                    "Linha Verde Gratuita",
                    "Número gratuito regulado pela ANACOM (chamada gratuita para o autor).",
                    "Toll-free regulated number by ANACOM.",
                )
            elif anacom.service_type == "Emergency":
                return (
                    0,
                    "LOW",
                    "HIGH",
                    "anacom_range",
                    "Serviço de Emergência",
                    "Linha prioritária oficial de emergência e socorro.",
                    "Official priority emergency line.",
                )
            elif anacom.is_voip:
                base_score = 15
                category = "Número Nómada VoIP (Sem Queixas)"
            elif anacom.service_type == "Premium Rate Mass Calling":
                base_score = 40
                category = "Número de Tarifa Especial / Concurso (760)"
            elif normalized.line_type == "MOBILE":
                category = "Contacto Móvel Pessoal / Sem Queixas"
            elif normalized.line_type == "FIXED_LINE":
                category = "Rede Fixa / Sem Queixas"
        elif normalized.line_type == "MOBILE":
            category = "Contacto Móvel Pessoal / Sem Queixas"
        elif normalized.line_type == "FIXED_LINE":
            category = "Rede Fixa / Sem Queixas"

        # User marked safe
        if user_marked_safe:
            return (
                5,
                "LOW",
                "MEDIUM",
                "crowdsourced_only",
                "Contacto de Confiança (Comunidade)",
                "Número de confiança confirmado por reporte de utilizador local.",
                "Trusted contact confirmed by local community report.",
            )

        # Clean number with no reports
        return (
            base_score,
            "LOW",
            confidence,
            matched_by,
            category,
            "Sem queixas ou denúncias de abuso registadas. Contacto normal sem padrões suspeitos.",
            "No abuse reports or negative feedback found. Clean normal contact.",
        )

    async def _get_cached_result(self, e164: str) -> Optional[AggregatedIntelligenceResponse]:
        try:
            async with AsyncSessionLocal() as session:
                query = select(SearchCache).where(
                    SearchCache.phone_e164 == e164,
                    SearchCache.expires_at > datetime.now(timezone.utc),
                )
                result = await session.execute(query)
                cache_entry = result.scalars().first()
                if cache_entry and cache_entry.data_json:
                    data = json.loads(cache_entry.data_json)
                    resp = AggregatedIntelligenceResponse(**data)
                    resp.cached = True
                    resp.cached_at = cache_entry.created_at.isoformat()
                    return resp
        except Exception as exc:
            logger.debug("Cache lookup failed: %s", exc)
        return None

    async def _get_local_reports(self, e164: str) -> List[UserReport]:
        try:
            async with AsyncSessionLocal() as session:
                query = select(UserReport).where(UserReport.phone_e164 == e164).order_by(UserReport.created_at.desc())
                result = await session.execute(query)
                return list(result.scalars().all())
        except Exception as exc:
            logger.debug("Error fetching local reports: %s", exc)
            return []

    async def _save_to_cache_and_history(self, response: AggregatedIntelligenceResponse):
        try:
            async with AsyncSessionLocal() as session:
                now = datetime.now(timezone.utc)
                expires = now + timedelta(hours=settings.CACHE_TTL_HOURS)

                # Upsert cache
                cached_data_json = response.model_dump_json()
                cache_entry = await session.get(SearchCache, response.normalized.e164)
                if cache_entry:
                    cache_entry.data_json = cached_data_json
                    cache_entry.created_at = now
                    cache_entry.expires_at = expires
                else:
                    new_cache = SearchCache(
                        phone_e164=response.normalized.e164,
                        created_at=now,
                        expires_at=expires,
                        data_json=cached_data_json,
                    )
                    session.add(new_cache)

                # Add to lookup history with confidence and matched_by
                carrier_name = response.operator_metadata.get("assigned_carrier")
                history_entry = LookupHistory(
                    phone_e164=response.normalized.e164,
                    national_format=response.normalized.national_format,
                    country_code=str(response.normalized.country_code),
                    risk_level=response.risk_level,
                    risk_score=response.risk_score,
                    confidence=response.confidence,
                    matched_by=response.matched_by,
                    caller_category=response.caller_category,
                    carrier=carrier_name,
                    searched_at=now,
                )
                session.add(history_entry)
                await session.commit()
        except Exception as exc:
            logger.debug("Error saving to cache/history: %s", exc)


# Global singleton
aggregator = PhoneIntelligenceAggregator()
