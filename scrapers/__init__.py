from .base import BaseScraper
from .boss import BossScraper
from .zhilian import ZhilianScraper
from .qiancheng import QianchengScraper
from .tongcheng import TongchengScraper
from .yupao import YupaoScraper
from .liepin import LiepinScraper

SCRAPERS = {
    'boss': BossScraper,
    'zhilian': ZhilianScraper,
    'qiancheng': QianchengScraper,
    'tongcheng': TongchengScraper,
    'yupao': YupaoScraper,
    'liepin': LiepinScraper,
}

def get_scraper(platform: str) -> BaseScraper:
    """Get scraper instance by platform name."""
    scraper_class = SCRAPERS.get(platform)
    if not scraper_class:
        raise ValueError(f"Unknown platform: {platform}")
    return scraper_class()