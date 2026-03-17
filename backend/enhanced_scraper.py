# Configuration corrigée pour enhanced_scraper.py
# Basée sur les URLs qui fonctionnent dans scraper_service.py

def get_fixed_sites_config():
    """Configuration corrigée basée sur scraper_service.py qui fonctionne"""
    return {
        "rci_fm": {
            "name": "RCI Guadeloupe",
            "base_url": "https://rci.fm",
            "pages": [
                "https://rci.fm/guadeloupe/infos/toutes-les-infos"  # URL qui fonctionne
            ],
            "selectors": [
                "a[href*='/guadeloupe/infos/']", ".post-title a",
                ".entry-title a", "h2 a", "h3 a"
            ],
            "priority": 1.0,
            "local_weight": 1.0
        },
        "la1ere": {
            "name": "Guadeloupe La 1ère",
            "base_url": "https://la1ere.franceinfo.fr",
            "pages": [
                "https://la1ere.franceinfo.fr/guadeloupe/"  # Sans /actualites/
            ],
            "selectors": [
                "a.teaser__title", ".teaser__title a",
                "article a[href*='/guadeloupe/']",
                "h2 a[href*='/guadeloupe/']"
            ],
            "priority": 0.9,
            "local_weight": 1.0
        },
        "karibinfo": {
            "name": "KaribInfo",
            "base_url": "https://www.karibinfo.com",  # Avec www.
            "pages": [
                "https://www.karibinfo.com/"  # Page d'accueil
            ],
            "selectors": ["h1 a", "h2 a", "h3 a", "article a"],
            "priority": 0.7,
            "local_weight": 0.9
        },
        "france_antilles": {
            "name": "France-Antilles Guadeloupe",
            "base_url": "https://www.guadeloupe.franceantilles.fr",
            "pages": [
                "https://www.guadeloupe.franceantilles.fr/"
            ],
            "selectors": [
                "article h2 a", "article h3 a", ".article-title a",
                ".title a", ".entry-title a", "h2 a", "h3 a"
            ],
            "priority": 0.8,
            "local_weight": 1.0
        }
    }

# Corrections pour les méthodes de validation d'URL
def get_fixed_url_validation():
    """Validation d'URL corrigée selon les patterns qui fonctionnent"""
    def is_valid_article_url(url: str, base_domain: str, site_key: str = "") -> bool:
        if not url:
            return False

        # Patterns à ignorer (alignés avec scraper_service.py)
        ignore_patterns = [
            "/tag/", "/category/", "/author/", "/page/", "/search/",
            "/archives/", "/contact/", "/about/",
            "javascript:", "mailto:", "#", "tel:",
            "/vakans-opeyi", "/tour-cycliste", "/informations-pratiques"
        ]
        
        url_lower = url.lower()
        for pattern in ignore_patterns:
            if pattern in url_lower:
                return False

        # Validation spécifique par site (basée sur scraper_service.py)
        if "rci.fm" in base_domain:
            return "/infos/" in url and len(url.split("/")[-1]) > 10
        elif "la1ere.franceinfo.fr" in base_domain:
            return "/guadeloupe/" in url and url.count("/") >= 4
        elif "karibinfo.com" in base_domain:
            return any(cat in url for cat in ["/news/", "/actualite/", "/politique/", "/societe/", "/economie/"])
        elif "guadeloupe.franceantilles.fr" in base_domain:
            return "/actualite/" in url.lower()

        return True
    
    return is_valid_article_url

# Correction pour la méthode de scraping KaribInfo
def get_fixed_karibinfo_scraper():
    """Méthode de scraping KaribInfo corrigée"""
    def scrape_karibinfo_articles(url: str) -> List[Dict[str, Any]]:
        articles = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            # Utiliser les mêmes sélecteurs que scraper_service.py
            selectors = ["h1 a", "h2 a", "h3 a", "article a"]
            links = []
            for selector in selectors:
                links.extend(soup.select(selector))

            for link in links:
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                # Validation selon scraper_service.py
                if (href.startswith("https://www.karibinfo.com/news/") and
                    len(text) > 15 and
                    "." in text and
                    not any(x in href.lower() for x in ["author/", "category/", "tag/"])):
                    
                    title = self.clean_title(text)
                    if 10 < len(title) < 200:
                        articles.append({
                            "id": self.make_id("karibinfo", href),
                            "title": title,
                            "url": href,
                            "source": "KaribInfo",
                            "site_key": "karibinfo",
                            "scraped_at": datetime.now().isoformat(),
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "scraped_from_page": url
                        })

            # Déduplication
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    unique_articles.append(article)
            
            return unique_articles[:15]
            
        except Exception as e:
            logger.error(f"Erreur scraping KaribInfo: {e}")
            return []
    
    return scrape_karibinfo_articles

# Instructions pour appliquer les corrections
def apply_fixes_to_enhanced_scraper():
    """
    Pour corriger votre enhanced_scraper.py :
    
    1. Remplacer self.sites_config par get_fixed_sites_config()
    2. Remplacer la méthode _is_valid_article_url par get_fixed_url_validation()
    3. Corriger la méthode de scraping KaribInfo avec get_fixed_karibinfo_scraper()
    4. Supprimer DOM Actu de la configuration (site non accessible)
    
    Cela alignera l'enhanced scraper sur les URLs qui fonctionnent 
    dans votre scraper_service.py
    """
    pass