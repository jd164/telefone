from app.engine.scrapers.base import BaseScraper
from app.engine.scrapers.tellows import TellowsScraper
from app.engine.scrapers.quem_liga import QuemLigaScraper
from app.engine.scrapers.should_i_answer import ShouldIAnswerScraper
from app.engine.scrapers.unknown_phone import UnknownPhoneScraper
from app.engine.scrapers.search_entity import CommercialEntityVerifier

__all__ = [
    "BaseScraper",
    "TellowsScraper",
    "QuemLigaScraper",
    "ShouldIAnswerScraper",
    "UnknownPhoneScraper",
    "CommercialEntityVerifier",
]
