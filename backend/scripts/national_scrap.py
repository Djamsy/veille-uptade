"""
Service de scraping des sites d'actualités NATIONALES (FR) – orienté Outre-mer & intérêt institutionnel
- Sources médias généralistes ouvertes + sources institutionnelles (gouv)
- Sélection/filtrage d’URL par règles (pas de JS, pas de pages auteur/tag)
- Dédup et heuristiques de pertinence (focus Outre-mer / Département / Infrastructures)
- Sauvegarde MongoDB (collection configurable, défaut: articles_nationaux)

USAGE (manuel):
    python -m national_news_scraper
ou
    from national_news_scraper import national_scraper; national_scraper.run()
"""

import os
import re
import time
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from urllib.parse import urljoin, urlparse
import concurrent.futures
from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class NationalNewsScraper:
    def __init__(self) -> None:
        # ---------------- Mongo ----------------
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/veille_media")
        try:
            if "mongodb+srv://" in MONGO_URL or "atlas" in MONGO_URL.lower():
                import certifi
                self.client = MongoClient(
                    MONGO_URL,
                    tlsCAFile=certifi.where(),
                    serverSelectionTimeoutMS=20000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=20000,
                    maxPoolSize=20,
                    retryWrites=True,
                    retryReads=True,
                )
            else:
                self.client = MongoClient(
                    MONGO_URL,
                    serverSelectionTimeoutMS=20000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=20000,
                    maxPoolSize=20,
                    retryWrites=True,
                    retryReads=True,
                )
            self.client.admin.command("ping")
            logger.info("✅ Scraper NATION connecté à MongoDB")
            try:
                dbname = MONGO_URL.rsplit("/", 1)[-1].split("?")[0] or "veille_media"
                if "mongodb+srv://" in MONGO_URL and ("?" in dbname or not dbname):
                    dbname = os.environ.get("MONGO_DB_NAME", "veille_media")
            except Exception:
                dbname = os.environ.get("MONGO_DB_NAME", "veille_media")
            self.db = self.client[dbname]
            collection_name = os.environ.get("NATIONAL_ARTICLES_COLLECTION", "articles_nationaux")
            self.articles_collection = self.db[collection_name]
            logger.info(f"🗄️  Collection d'articles (national): {collection_name}")
        except Exception as e:
            logger.error(f"❌ Erreur connection MongoDB pour scraper national: {e}")
            raise

        # ---------------- Sources ----------------
        # NB: on privilégie des pages liste publiques et stables (peu de JS / peu de paywall)
        self.sites_config: Dict[str, Dict[str, Any]] = {
            # === Médias nationaux ===
            "franceinfo": {
                "name": "franceinfo (France)",
                "url": "https://www.francetvinfo.fr/",
                "selectors": ["a[href*='/france/']", "a[href*='/politique/']", "a[href*='/societe/']"],
                "base_url": "https://www.francetvinfo.fr",
                "kind": "media",
            },
            "france24": {
                "name": "France 24 (France)",
                "url": "https://www.france24.com/fr/france/",
                "selectors": ["a[href*='/fr/france/']"],
                "base_url": "https://www.france24.com",
                "kind": "media",
            },
            "20minutes": {
                "name": "20 Minutes",
                "url": "https://www.20minutes.fr/societe/",
                "selectors": ["article a", "h2 a", "h3 a", "a[href*='/politique/']"],
                "base_url": "https://www.20minutes.fr",
                "kind": "media",
            },
            "huffpost": {
                "name": "HuffPost FR",
                "url": "https://www.huffingtonpost.fr/actualites/",
                "selectors": ["a[href*='/politique/']", "a[href*='/societe/']", "h2 a", "h3 a"],
                "base_url": "https://www.huffingtonpost.fr",
                "kind": "media",
            },
            "ouestfrance": {
                "name": "Ouest-France (National)",
                "url": "https://www.ouest-france.fr/politique/",
                "selectors": ["a[href*='/politique/']"],
                "base_url": "https://www.ouest-france.fr",
                "kind": "media",
            },
            "outremer360": {
                "name": "Outre-mer 360",
                "url": "https://outremers360.com/",
                "selectors": ["h2 a", "h3 a", "article a", "a[href*='/politique/']", "a[href*='/societe/']"],
                "base_url": "https://outremers360.com",
                "kind": "media",
                "extra_flags": {"focus_outremer": True},
            },
            # === Pôle Outre-mer de France Télévisions ===
            "la1ere_outremer": {
                "name": "La 1ère (Outre-mer)",
                "url": "https://la1ere.francetvinfo.fr/",
                "selectors": ["a[href*='/outre-mer/']", "a[href*='/societe/']", "a[href*='/politique/']"],
                "base_url": "https://la1ere.francetvinfo.fr",
                "kind": "media",
                "extra_flags": {"focus_outremer": True},
            },
            # === Institutionnel national ===
            "gouvernement": {
                "name": "Gouvernement.fr",
                "url": "https://www.gouvernement.fr/actualites",
                "selectors": ["a[href*='/actualites']", "h2 a", "h3 a"],
                "base_url": "https://www.gouvernement.fr",
                "kind": "institutionnel",
            },
            "economie_gouv": {
                "name": "Économie, Finances (Bercy)",
                "url": "https://www.economie.gouv.fr/actualites",
                "selectors": ["a[href*='/actualites']", "h2 a", "h3 a"],
                "base_url": "https://www.economie.gouv.fr",
                "kind": "institutionnel",
            },
            "interieur_gouv": {
                "name": "Intérieur (Sécurité / Préfectures)",
                "url": "https://www.interieur.gouv.fr/actualites",
                "selectors": ["a[href*='/actualites']", "h2 a", "h3 a"],
                "base_url": "https://www.interieur.gouv.fr",
                "kind": "institutionnel",
            },
            "ecologie_gouv": {
                "name": "Transition écologique",
                "url": "https://www.ecologie.gouv.fr/actualites",
                "selectors": ["a[href*='/actualites']", "h2 a", "h3 a"],
                "base_url": "https://www.ecologie.gouv.fr",
                "kind": "institutionnel",
            },
        }

        # UA Rotation
        self.headers_list: List[Dict[str, str]] = [
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            },
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "fr,en-US;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            },
        ]
        self.current_header_index = 0

        # Heuristiques de focus (mêmes thèmes que ton backend)
        self.focus_departement_terms = [
            "smgeag", "eau", "assainissement", "routes", "rd", "pont", "gabarre",
            "sargasses", "social", "handicap", "enfance", "risques", "ouragan", "séisme",
        ]
        self.focus_outremer_terms = [
            "outre-mer", "guadeloupe", "martinique", "guyane", "réunion", "mayotte",
            "saint-martin", "saint-barth", "polynésie", "nouvelle-calédonie", "wallis",
        ]

    # --------------- Utils ---------------
    def get_next_headers(self) -> Dict[str, str]:
        h = self.headers_list[self.current_header_index]
        self.current_header_index = (self.current_header_index + 1) % len(self.headers_list)
        return h

    def clean_title(self, title: str) -> str:
        if not title:
            return ""
        title = re.sub(r"[\n\r\t]+", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        prefixes = [
            "LIRE AUSSI:", "VOIR AUSSI:", "À LIRE:", "VIDÉO:", "PHOTO:", "EN DIRECT:", "BREAKING:", "URGENT:",
        ]
        for p in prefixes:
            if title.upper().startswith(p):
                title = title[len(p):].strip()
        return title

    def normalize_title(self, title: str) -> str:
        if not title:
            return ""
        normalized = re.sub(r"[^\w\s]", " ", title.lower())
        return re.sub(r"\s+", " ", normalized).strip()

    def make_id(self, site_key: str, url: str) -> str:
        return f"{site_key}_{hashlib.md5(url.encode('utf-8')).hexdigest()}"

    def is_valid_article_url(self, url: str, base_domain: str, site_key: str) -> bool:
        if not url:
            return False
        ignore = [
            "/tag/", "/category/", "/auteur/", "/author/", "/page/", "/search/", "/recherche/", "#", "mailto:",
            "javascript:", "/newsletter", "/podcasts", "/videos", "/video/", "/live/", "/en-direct/",
        ]
        for pat in ignore:
            if pat in url.lower():
                return False
        parsed = urlparse(url)
        if parsed.netloc and (base_domain not in parsed.netloc):
            return False
        u = url.lower()
        if site_key == "franceinfo":
            return ("/france/" in u or "/politique/" in u or "/societe/" in u) and len(u) - len(u.rstrip("/")) == 0
        if site_key == "france24":
            return "/fr/france/" in u and u.count("/") > 4
        if site_key == "20minutes":
            return ("/societe/" in u or "/politique/" in u) and not u.endswith("/societe/")
        if site_key == "huffpost":
            return any(seg in u for seg in ["/politique/", "/societe/"]) and u.count("/") > 4
        if site_key == "ouestfrance":
            return "/politique/" in u and u.count("/") > 5
        if site_key == "outremer360":
            return any(seg in u for seg in ["/politique/", "/societe/", "/actualites/"]) and u.count("/") > 4
        if site_key == "la1ere_outremer":
            return any(seg in u for seg in ["/outre-mer/", "/societe/", "/politique/"]) and u.count("/") > 4
        if site_key in {"gouvernement", "economie_gouv", "interieur_gouv", "ecologie_gouv"}:
            return "/actualites" in u and not u.rstrip("/").endswith("/actualites")
        return True

    def _score_article(self, title: str, url: str, site_key: str) -> Dict[str, Any]:
        t = (title or "").lower()
        score = 0
        tags: List[str] = []
        # Outre-mer
        if any(k in t for k in self.focus_outremer_terms):
            score += 2; tags.append("outre-mer")
        # Département
        if any(k in t for k in self.focus_departement_terms):
            score += 2; tags.append("departement")
        # politiques publiques
        if any(k in t for k in ["budget", "plan", "décret", "loi", "arrêté", "circulaire", "appel d'offres", "marché"]):
            score += 1; tags.append("politiques_publiques")
        if site_key in {"gouvernement","economie_gouv","interieur_gouv","ecologie_gouv"}:
            score += 2; tags.append("institutionnel")
        return {"relevance": min(1.0, score/4), "tags": sorted(set(tags))}

    # --------------- Site-specific scrapers (optionnels) ---------------
    def scrape_generic(self, url: str, site_key: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            links = []
            for sel in config.get("selectors", []):
                try:
                    links.extend(soup.select(sel))
                except Exception as e:
                    logger.debug(f"Sélecteur KO {sel}: {e}")

            # fallback: toutes les balises <a>
            if not links:
                links = soup.find_all("a", href=True)

            seen, uniq = set(), []
            for a in links:
                href = a.get("href") or ""
                text = a.get_text(strip=True)
                if not href or not text or len(text) < 8:
                    continue
                full_url = href if href.startswith("http") else urljoin(config["base_url"], href)
                if full_url in seen:
                    continue
                seen.add(full_url)
                if not self.is_valid_article_url(full_url, config["base_url"], site_key):
                    continue
                title = self.clean_title(text)
                if len(title) < 10 or len(title) > 220:
                    continue
                sc = self._score_article(title, full_url, site_key)
                uniq.append({
                    "id": self.make_id(site_key, full_url),
                    "title": title,
                    "url": full_url,
                    "source": config["name"],
                    "site_key": site_key,
                    "scraped_at": datetime.now().isoformat(),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "scraped_from_page": url,
                    "relevance": sc["relevance"],
                    "tags": sc["tags"],
                    "kind": config.get("kind", "media"),
                    **(config.get("extra_flags") or {}),
                })

            logger.info(f"✅ {config['name']}: {len(uniq)} liens candidats")
            return uniq[:40]
        except Exception as e:
            logger.error(f"❌ Erreur scraping {config.get('name', site_key)}: {e}")
            return []

    # --------------- Orchestrateurs ---------------
    def scrape_page(self, url: str, site_key: str) -> List[Dict[str, Any]]:
        cfg = self.sites_config[site_key]
        return self.scrape_generic(url, site_key, cfg)

    def scrape_site(self, site_key: str) -> List[Dict[str, Any]]:
        cfg = self.sites_config[site_key]
        pages = [cfg["url"], *cfg.get("additional_pages", [])]
        out: List[Dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futs = {pool.submit(self.scrape_page, u, site_key): u for u in pages}
            for fut in concurrent.futures.as_completed(futs):
                try:
                    out.extend(fut.result())
                except Exception as e:
                    logger.warning(f"Erreur page {futs[fut]}: {e}")
        # dédoublonne par URL
        seen, unique = set(), []
        for a in out:
            if a["url"] not in seen:
                seen.add(a["url"])
                unique.append(a)
        logger.info(f"📦 {cfg['name']}: {len(unique)} articles uniques")
        return unique

    # --------------- Doublons & Sauvegarde ---------------
    def is_duplicate_article(self, a: Dict[str, Any]) -> bool:
        try:
            if self.articles_collection.find_one({"id": a["id"]}):
                return True
            if a.get("url") and self.articles_collection.find_one({"url": a["url"]}):
                return True
            return False
        except Exception as e:
            logger.warning(f"Dup check KO: {e}")
            return False

    def _remove_similar_titles(self) -> int:
        try:
            since = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            recent = list(self.articles_collection.find({"date": {"$gte": since}}).sort("scraped_at", -1))
            removed = 0
            processed = set()
            for i, a1 in enumerate(recent):
                if a1["_id"] in processed:
                    continue
                for a2 in recent[i+1:]:
                    if a2["_id"] in processed:
                        continue
                    if a1.get("source") == a2.get("source"):
                        t1 = self.normalize_title(a1.get("title", ""))
                        t2 = self.normalize_title(a2.get("title", ""))
                        if SequenceMatcher(None, t1, t2).ratio() >= 0.92:
                            older = a2 if a1.get("scraped_at", "") > a2.get("scraped_at", "") else a1
                            self.articles_collection.delete_one({"_id": older["_id"]})
                            processed.add(older["_id"]); removed += 1
            return removed
        except Exception as e:
            logger.warning(f"Sim titles KO: {e}")
            return 0

    # --------------- Run all ---------------
    def scrape_all_sites(self) -> Dict[str, Any]:
        logger.info("🚀 Scraping INFOS NATIONALES…")
        start = time.time()
        all_articles: List[Dict[str, Any]] = []
        results: Dict[str, Any] = {
            "success": True,
            "scraped_at": datetime.now().isoformat(),
            "sites_scraped": 0,
            "total_articles": 0,
            "articles_by_site": {},
            "duplicates_by_site": {},
            "errors": [],
            "execution_time_seconds": 0,
        }

        for site_key, cfg in self.sites_config.items():
            try:
                logger.info(f"🔍 {cfg['name']} …")
                arts = self.scrape_site(site_key)
                saved, dups = 0, 0
                for a in arts:
                    try:
                        if not self.is_duplicate_article(a):
                            self.articles_collection.update_one({"id": a["id"]}, {"$set": a}, upsert=True)
                            saved += 1
                        else:
                            dups += 1
                    except Exception as e:
                        logger.warning(f"Save KO: {e}")
                results["articles_by_site"][site_key] = saved
                results["duplicates_by_site"][site_key] = dups
                results["sites_scraped"] += 1
                all_articles.extend([x for x in arts if not self.is_duplicate_article(x)])
                time.sleep(1)
            except Exception as e:
                msg = f"Erreur {cfg['name']}: {e}"
                logger.error(msg)
                results["errors"].append(msg)

        try:
            removed_sim = self._remove_similar_titles()
            if removed_sim:
                logger.info(f"🧹 {removed_sim} doublons supprimés par similarité de titre")
        except Exception:
            pass

        results["total_articles"] = len(all_articles)
        results["total_duplicates"] = sum(results["duplicates_by_site"].values())
        results["articles"] = all_articles
        results["execution_time_seconds"] = round(time.time() - start, 2)

        # Invalidation cache (si disponible)
        try:
            try:
                from backend._attic.cache_service import cache_invalidate  # type: ignore
            except Exception:
                try:
                    from backend._attic.cache_service import cache_invalidate  # type: ignore
                except Exception:
                    cache_invalidate = None  # type: ignore
            if cache_invalidate:
                cache_invalidate("articles_nationaux")
                logger.info("🗑️ Cache national invalidé")
        except Exception as e:
            logger.warning(f"Cache invalidation KO: {e}")

        logger.info(
            f"📊 National OK: {results['total_articles']} articles uniques, {results['total_duplicates']} doublons évités en {results['execution_time_seconds']}s"
        )
        return results

    # Compat backend
    def run(self) -> Dict[str, Any]:
        return self.scrape_all_sites()

    # --------------- Helpers lecture ---------------
    def get_todays_articles(self) -> List[Dict[str, Any]]:
        today = datetime.now().strftime("%Y-%m-%d")
        return list(self.articles_collection.find({"date": today}, {"_id": 0}).sort("scraped_at", -1).limit(200))

    def get_articles_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        return list(self.articles_collection.find({"date": date_str}, {"_id": 0}).sort("scraped_at", -1).limit(200))

    def get_scraping_stats(self) -> Dict[str, Any]:
        try:
            total = self.articles_collection.count_documents({})
            today = datetime.now().strftime("%Y-%m-%d")
            today_count = self.articles_collection.count_documents({"date": today})
            pipeline = [{"$group": {"_id": "$site_key", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
            by_site = {x["_id"]: x["count"] for x in self.articles_collection.aggregate(pipeline)}
            last = self.articles_collection.find_one({}, sort=[("scraped_at", -1)])
            return {
                "total_articles": total,
                "today_articles": today_count,
                "articles_by_site": by_site,
                "last_scrape": last["scraped_at"] if last else "Jamais",
            }
        except Exception as e:
            logger.error(f"Erreur stats scraping national: {e}")
            return {"error": str(e)}


# Instance globale
national_scraper = NationalNewsScraper()


def run_daily_national_scraping() -> Dict[str, Any]:
    logger.info("⏰ Lancement scraping national (manuel)")
    return national_scraper.scrape_all_sites()


if __name__ == "__main__":
    result = national_scraper.scrape_all_sites()
    print(json.dumps(result, indent=2, ensure_ascii=False))
