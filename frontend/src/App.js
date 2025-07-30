import React, { useState, useEffect } from 'react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardStats, setDashboardStats] = useState({});
  const [articles, setArticles] = useState([]);
  const [transcriptions, setTranscriptions] = useState([]);
  const [digest, setDigest] = useState(null);
  const [schedulerStatus, setSchedulerStatus] = useState({});
  const [loading, setLoading] = useState(false);
  const [backgroundTasks, setBackgroundTasks] = useState({});
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [error, setError] = useState(null);
  
  // Nouveaux états pour la recherche et les commentaires
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchSuggestions, setSearchSuggestions] = useState([]);
  const [comments, setComments] = useState([]);
  const [commentsAnalysis, setCommentsAnalysis] = useState(null);
  const [socialStats, setSocialStats] = useState({});
  
  // États pour la recherche sociale
  const [socialSearchQuery, setSocialSearchQuery] = useState('');
  const [socialSearchResults, setSocialSearchResults] = useState(null);
  const [socialSearchLoading, setSocialSearchLoading] = useState(false);
  
  // États pour les transcriptions par sections
  const [transcriptionSections, setTranscriptionSections] = useState({
    "7H RCI": [],
    "7H Guadeloupe Première": [],
    "Autres": []
  });
  const [transcriptionStatus, setTranscriptionStatus] = useState({
    sections: {},
    global_status: { any_in_progress: false, total_sections: 2, active_sections: 0 }
  });
  const [socialSearchError, setSocialSearchError] = useState(null);
  
  // États pour la recherche automatique
  const [autoSearchCompleted, setAutoSearchCompleted] = useState(false);
  const [autoSearchResults, setAutoSearchResults] = useState({});

  // Fonction utilitaire pour les appels API avec timeout et gestion d'erreur
  const apiCall = async (url, options = {}) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 secondes timeout

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        }
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        throw new Error('Délai d\'attente dépassé (30s)');
      }
      throw error;
    }
  };

  // Charger les statistiques du dashboard avec cache
  const loadDashboardStats = async () => {
    try {
      const data = await apiCall(`${BACKEND_URL}/api/dashboard-stats`);
      if (data.success) {
        setDashboardStats(data.stats);
      }
    } catch (error) {
      console.error('Erreur chargement stats:', error);
      setError('Erreur chargement des statistiques');
    }
  };

  // Charger les données selon l'onglet actif avec cache intelligent
  const loadTabData = async (tab, date = null, force = false) => {
    if (loading) return; // Éviter les appels multiples
    
    setLoading(true);
    setError(null);
    
    try {
      const targetDate = date || selectedDate;
      
      switch (tab) {
        case 'articles':
          const articlesUrl = targetDate !== new Date().toISOString().split('T')[0] 
            ? `${BACKEND_URL}/api/articles/${targetDate}`
            : `${BACKEND_URL}/api/articles`;
          
          const articlesData = await apiCall(articlesUrl);
          if (articlesData.success) {
            setArticles(articlesData.articles);
          }
          break;
          
        case 'transcription':
          const transcriptionsUrl = targetDate !== new Date().toISOString().split('T')[0]
            ? `${BACKEND_URL}/api/transcriptions/${targetDate}`
            : `${BACKEND_URL}/api/transcriptions`;
          
          const transcriptionsData = await apiCall(transcriptionsUrl);
          if (transcriptionsData.success) {
            setTranscriptions(transcriptionsData.transcriptions);
          }
          break;
          
        case 'digest':
          const digestUrl = targetDate !== new Date().toISOString().split('T')[0]
            ? `${BACKEND_URL}/api/digest/${targetDate}`
            : `${BACKEND_URL}/api/digest`;
          
          const digestData = await apiCall(digestUrl);
          if (digestData.success) {
            setDigest(digestData.digest);
          } else {
            setDigest(null);
          }
          break;
          
        case 'scheduler':
          const schedulerData = await apiCall(`${BACKEND_URL}/api/scheduler/status`);
          if (schedulerData.success) {
            setSchedulerStatus(schedulerData);
          }
          break;
          
        case 'search':
          // Charger les suggestions de recherche si pas de query spécifique
          if (!searchQuery || searchQuery.trim().length < 2) {
            await loadSearchSuggestions();
          } else {
            // Effectuer une recherche si une query existe
            await handleSearch(searchQuery);
          }
          break;
          
        case 'comments':
          // Charger les commentaires et les stats sociales
          await loadComments();
          await loadSocialStats();
          break;
      }
    } catch (error) {
      console.error(`Erreur chargement ${tab}:`, error);
      setError(`Erreur chargement ${tab}: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardStats();
    if (activeTab !== 'dashboard') {
      loadTabData(activeTab);
    }
    
    // Charger des données spécifiques pour certains onglets
    if (activeTab === 'search') {
      loadSearchSuggestions();
    } else if (activeTab === 'comments') {
      loadSocialStats();
    } else if (activeTab === 'transcription') {
      loadTranscriptionSections();
      loadTranscriptionStatus();
      
      // Auto-actualisation des transcriptions toutes les 30 secondes
      const transcriptionInterval = setInterval(() => {
        loadTranscriptionSections();
        loadTranscriptionStatus();
      }, 30000); // 30 secondes
      
      // Nettoyer l'interval quand on quitte l'onglet
      return () => clearInterval(transcriptionInterval);
    }
    
    // Lancer la recherche automatique au premier chargement
    if (!autoSearchCompleted) {
      performAutoSearch();
    }
  }, [activeTab, selectedDate, autoSearchCompleted]);

  // Actions optimisées avec traitement en arrière-plan
  const scrapeArticlesNow = async () => {
    if (backgroundTasks.scraping) return;
    
    setBackgroundTasks(prev => ({ ...prev, scraping: true }));
    
    try {
      // Démarrer le scraping en arrière-plan
      const response = await apiCall(`${BACKEND_URL}/api/articles/scrape-now`, { method: 'POST' });
      
      if (response.success) {
        alert(`✅ ${response.message}`);
        
        // Vérifier le statut périodiquement
        const checkStatus = async () => {
          try {
            const statusData = await apiCall(`${BACKEND_URL}/api/articles/scrape-status`);
            if (statusData.success && statusData.result) {
              const result = statusData.result;
              if (result.success !== undefined) {
                // Scraping terminé
                setBackgroundTasks(prev => ({ ...prev, scraping: false }));
                if (result.success) {
                  alert(`🎉 Scraping terminé ! ${result.total_articles} articles récupérés`);
                  loadTabData('articles', null, true);
                  loadDashboardStats();
                } else {
                  alert(`⚠️ Scraping terminé avec erreurs: ${result.error}`);
                }
                return;
              }
            }
            // Continuer à vérifier
            setTimeout(checkStatus, 10000); // Vérifier toutes les 10 secondes
          } catch (error) {
            console.error('Erreur vérification statut scraping:', error);
            setBackgroundTasks(prev => ({ ...prev, scraping: false }));
          }
        };
        
        setTimeout(checkStatus, 10000); // Première vérification après 10s
      }
    } catch (error) {
      alert(`❌ Erreur scraping: ${error.message}`);
      setBackgroundTasks(prev => ({ ...prev, scraping: false }));
    }
  };

  const captureRadioNow = async () => {
    if (backgroundTasks.capturing) return;
    
    setBackgroundTasks(prev => ({ ...prev, capturing: true }));
    
    try {
      const response = await apiCall(`${BACKEND_URL}/api/transcriptions/capture-now`, { method: 'POST' });
      
      if (response.success) {
        alert(`✅ ${response.message}`);
        
        // Vérifier le statut périodiquement
        const checkStatus = async () => {
          try {
            const statusData = await apiCall(`${BACKEND_URL}/api/transcriptions/capture-status`);
            if (statusData.success && statusData.result) {
              const result = statusData.result;
              if (result.success !== undefined) {
                // Capture terminée
                setBackgroundTasks(prev => ({ ...prev, capturing: false }));
                if (result.success) {
                  alert(`🎉 Capture terminée ! ${result.streams_success} flux traités`);
                  loadTabData('transcription', null, true);
                  loadDashboardStats();
                } else {
                  alert(`⚠️ Capture terminée avec erreurs: ${result.error}`);
                }
                return;
              }
            }
            // Continuer à vérifier
            setTimeout(checkStatus, 15000); // Vérifier toutes les 15 secondes
          } catch (error) {
            console.error('Erreur vérification statut capture:', error);
            setBackgroundTasks(prev => ({ ...prev, capturing: false }));
          }
        };
        
        setTimeout(checkStatus, 15000); // Première vérification après 15s
      }
    } catch (error) {
      alert(`❌ Erreur capture: ${error.message}`);
      setBackgroundTasks(prev => ({ ...prev, capturing: false }));
    }
  };

  // Charger les transcriptions par sections
  const loadTranscriptionSections = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/transcriptions/sections`);
      const data = await response.json();
      if (data.success) {
        setTranscriptionSections(data.sections);
      }
    } catch (error) {
      console.error('Erreur chargement sections transcriptions:', error);
    }
  };

  // Charger le statut des transcriptions
  const loadTranscriptionStatus = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/transcriptions/status`);
      const data = await response.json();
      if (data.success) {
        setTranscriptionStatus(data.status);
      }
    } catch (error) {
      console.error('Erreur chargement statut transcriptions:', error);
    }
  };

  // Lancer la capture d'une section spécifique
  const captureSection = async (section) => {
    try {
      setLoading(true);
      const response = await fetch(`${BACKEND_URL}/api/transcriptions/capture-now?section=${section}`, {
        method: 'POST'
      });
      const data = await response.json();
      if (data.success) {
        alert(`✅ ${data.message}`);
        // Actualiser le statut
        setTimeout(() => {
          loadTranscriptionStatus();
        }, 1000);
      } else {
        alert(`❌ Erreur: ${data.error || 'Erreur inconnue'}`);
      }
    } catch (error) {
      console.error('Erreur capture section:', error);
      alert('❌ Erreur lors du lancement de la capture');
    } finally {
      setLoading(false);
    }
  };

  const createDigestNow = async () => {
    setLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/digest/create-now`, { method: 'POST' });
      if (response.success) {
        alert('✅ Digest créé avec succès !');
        loadTabData('digest', null, true);
        loadDashboardStats();
      }
    } catch (error) {
      alert(`❌ Erreur création digest: ${error.message}`);
    }
    setLoading(false);
  };

  const runSchedulerJob = async (jobId) => {
    setLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/scheduler/run-job/${jobId}`, { method: 'POST' });
      if (response.success) {
        alert(`✅ Job ${jobId} exécuté avec succès !`);
        loadTabData('scheduler');
        loadDashboardStats();
      } else {
        alert(`❌ Erreur job ${jobId}: ${response.message}`);
      }
    } catch (error) {
      alert(`❌ Erreur exécution job: ${error.message}`);
    }
    setLoading(false);
  };

  const uploadAudio = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${BACKEND_URL}/api/transcribe`, {
        method: 'POST',
        body: formData
      });
      
      const data = await response.json();
      if (data.success) {
        alert('✅ Transcription réussie !');
        loadTabData('transcription', null, true);
        loadDashboardStats();
      } else {
        throw new Error(data.detail || 'Erreur transcription');
      }
    } catch (error) {
      alert(`❌ Erreur transcription: ${error.message}`);
    }
    setLoading(false);
  };

  const invalidateCache = async () => {
    try {
      await apiCall(`${BACKEND_URL}/api/cache/invalidate`, { method: 'POST' });
      alert('✅ Cache vidé avec succès !');
      // Recharger les données
      loadDashboardStats();
      if (activeTab !== 'dashboard') {
        loadTabData(activeTab, null, true);
      }
    } catch (error) {
      alert(`❌ Erreur vidage cache: ${error.message}`);
    }
  };

  // Recherche automatique des sujets prioritaires au démarrage
  const performAutoSearch = async () => {
    if (autoSearchCompleted) return;
    
    const prioritySubjects = ['cd971', 'Guy Losbar', 'département guadeloupe', 'GUSR', 'Ary Chalus'];
    const results = {};
    
    console.log('🔍 Démarrage de la recherche automatique des sujets prioritaires...');
    
    for (const subject of prioritySubjects) {
      try {
        console.log(`Recherche automatique: ${subject}`);
        const response = await apiCall(`${BACKEND_URL}/api/search?q=${encodeURIComponent(subject)}`);
        if (response.success) {
          results[subject] = {
            total_results: response.total_results,
            articles_count: response.articles ? response.articles.length : 0,
            social_posts_count: response.social_posts ? response.social_posts.length : 0
          };
        }
        // Petit délai entre les recherches pour éviter la surcharge
        await new Promise(resolve => setTimeout(resolve, 500));
      } catch (error) {
        console.warn(`Erreur recherche automatique pour "${subject}":`, error.message);
        results[subject] = { error: error.message };
      }
    }
    
    setAutoSearchResults(results);
    setAutoSearchCompleted(true);
    console.log('✅ Recherche automatique terminée:', results);
  };

  // Fonction de recherche sociale spécifique
  const handleSocialSearch = async (query) => {
    if (!query || query.trim().length < 2) {
      setSocialSearchError('Veuillez saisir au moins 2 caractères');
      return;
    }
    
    setSocialSearchLoading(true);
    setSocialSearchError(null);
    
    try {
      console.log(`🔍 Recherche sociale pour: "${query}"`);
      
      // Lancer le scraping pour ce sujet spécifique
      const scrapingResponse = await apiCall(`${BACKEND_URL}/api/social/scrape-keyword`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: query })
      });
      
      if (scrapingResponse.success) {
        // Attendre un peu pour que le scraping se termine
        await new Promise(resolve => setTimeout(resolve, 3000));
        
        // Rechercher les résultats
        const searchResponse = await apiCall(`${BACKEND_URL}/api/search?q=${encodeURIComponent(query)}&social_only=true`);
        
        if (searchResponse.success) {
          setSocialSearchResults({
            query: query,
            social_posts: searchResponse.social_posts || [],
            total_results: searchResponse.total_results || 0,
            scraped_at: new Date().toISOString()
          });
        } else {
          setSocialSearchError(searchResponse.error || 'Erreur lors de la recherche');
        }
      } else {
        setSocialSearchError(scrapingResponse.error || 'Erreur lors du scraping');
      }
    } catch (error) {
      console.error('Erreur recherche sociale:', error);
      setSocialSearchError(`Erreur: ${error.message}`);
    } finally {
      setSocialSearchLoading(false);
    }
  };

  // Fonction de recherche
  const handleSearch = async (query) => {
    if (!query || query.trim().length < 2) {
      setSearchResults(null);
      return;
    }

    setSearchLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/search?q=${encodeURIComponent(query.trim())}`);
      if (response.success) {
        setSearchResults(response);
      } else {
        setError(`Erreur de recherche: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur de recherche: ${error.message}`);
    } finally {
      setSearchLoading(false);
    }
  };

  // Charger les suggestions de recherche
  const loadSearchSuggestions = async (query = '') => {
    try {
      const response = await apiCall(`${BACKEND_URL}/api/search/suggestions?q=${encodeURIComponent(query)}`);
      if (response.success) {
        setSearchSuggestions(response.suggestions);
      }
    } catch (error) {
      console.warn('Erreur suggestions:', error.message);
    }
  };

  // Charger les commentaires (posts des réseaux sociaux)
  const loadComments = async () => {
    setLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/comments`);
      if (response.success) {
        setComments(response.comments);
      } else {
        setError(`Erreur commentaires: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur commentaires: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Analyser les commentaires par entité
  const analyzeComments = async () => {
    setLoading(true);
    try {
      const response = await apiCall(`${BACKEND_URL}/api/comments/analyze`, { method: 'POST' });
      if (response.success) {
        setCommentsAnalysis(response.analysis);
      } else {
        setError(`Erreur analyse commentaires: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur analyse commentaires: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Charger les stats des réseaux sociaux
  const loadSocialStats = async () => {
    try {
      const response = await apiCall(`${BACKEND_URL}/api/social/stats`);
      if (response.success) {
        setSocialStats(response.stats);
      }
    } catch (error) {
      console.warn('Erreur stats réseaux sociaux:', error.message);
    }
  };

  // Lancer le scraping des réseaux sociaux
  const startSocialScraping = async () => {
    try {
      const response = await apiCall(`${BACKEND_URL}/api/social/scrape-now`, { method: 'POST' });
      if (response.success) {
        setBackgroundTasks(prev => ({
          ...prev,
          socialScraping: { status: 'running', message: response.message }
        }));
        // Recharger les stats après quelques secondes
        setTimeout(() => {
          loadSocialStats();
          loadComments();
        }, 30000);
      } else {
        setError(`Erreur scraping social: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur scraping social: ${error.message}`);
    }
  };

  return (
    <div className="app">
      {/* Header avec effet glass */}
      <header className="glass-header">
        <div className="main-container">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center space-x-4">
              <h1 className="text-3xl font-bold" style={{ color: '#2c3e50' }}>
                🏝️ Veille Média Guadeloupe
              </h1>
            </div>

            <div className="text-sm" style={{ color: '#34495e' }}>
              Dernière MAJ: {new Date().toLocaleDateString('fr-FR', { 
                day: 'numeric', 
                month: 'short', 
                hour: '2-digit', 
                minute: '2-digit' 
              })}
            </div>
          </div>
        </div>
      </header>

      {/* Barre de statut des tâches en arrière-plan */}
      {(backgroundTasks.scraping || backgroundTasks.capturing) && (
        <div className="glass-card" style={{ margin: '1rem', padding: '1rem' }}>
          <div className="main-container">
            <div className="flex items-center gap-4 text-sm">
              {backgroundTasks.scraping && (
                <div className="flex items-center gap-2">
                  <div className="loading-spinner" style={{ width: '20px', height: '20px' }}></div>
                  <span style={{ color: '#2c3e50' }}>Scraping en cours... (2-3 min)</span>
                </div>
              )}
              {backgroundTasks.capturing && (
                <div className="flex items-center gap-2">
                  <div className="loading-spinner" style={{ width: '20px', height: '20px' }}></div>
                  <span style={{ color: '#2c3e50' }}>Capture radio en cours... (3-5 min)</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Navigation avec effet glass */}
      <nav className="glass-header">
        <div className="main-container">
          <div className="nav-container">
            {[
              { id: 'dashboard', name: '📊 Dashboard', icon: '📊' },
              { id: 'search', name: '🔍 Recherche', icon: '🔍' },
              { id: 'articles', name: '📰 Articles', icon: '📰' },
              { id: 'comments', name: '💬 Réseaux Sociaux', icon: '💬' },
              { id: 'transcription', name: '📻 Radio', icon: '📻' },
              { id: 'digest', name: '📋 Digest', icon: '📋' }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (tab.id === 'search') {
                    loadSearchSuggestions();
                  } else if (tab.id === 'comments') {
                    loadComments();
                    loadSocialStats();
                  }
                }}
                className={`nav-tab ${activeTab === tab.id ? 'active' : ''}`}
              >
                {tab.name}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="main-container">
        {/* Affichage des erreurs */}
        {error && (
          <div className="alert error">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="hover:opacity-75" style={{ color: '#e74c3c' }}>✕</button>
          </div>
        )}

        {/* Loading overlay */}
        {loading && (
          <div className="loading-overlay">
            <div className="loading-content">
              <div className="loading-spinner"></div>
              <p>Traitement en cours...</p>
            </div>
          </div>
        )}

        {/* Dashboard */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            <h2 className="text-3xl font-bold mb-6" style={{ color: '#2c3e50' }}>📊 Vue d'ensemble - Guadeloupe</h2>
            
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-label">Articles Aujourd'hui</div>
                <div className="stat-value">{dashboardStats.today_articles || 0}</div>
                <div className="stat-sublabel">Total: {dashboardStats.total_articles || 0}</div>
              </div>

              <div className="stat-card">
                <div className="stat-label">Radio Aujourd'hui</div>
                <div className="stat-value">{dashboardStats.today_transcriptions || 0}</div>
                <div className="stat-sublabel">Total: {dashboardStats.total_transcriptions || 0}</div>
              </div>

              <div className="stat-card">
                <div className="stat-label">Digests</div>
                <div className="stat-value">{dashboardStats.total_digests || 0}</div>
                <div className="stat-sublabel">Résumés quotidiens</div>
              </div>

              <div className="stat-card">
                <div className="stat-label">Cache Hit Ratio</div>
                <div className="stat-value">
                  {dashboardStats.cache_stats?.cache_hit_ratio?.toFixed(1) || 0}%
                </div>
                <div className="stat-sublabel">
                  {dashboardStats.cache_stats?.valid_cached_keys || 0} clés actives
                </div>
              </div>
            </div>

            {/* Résultats de recherche automatique */}
            {autoSearchCompleted && Object.keys(autoSearchResults).length > 0 && (
              <div className="glass-card">
                <h3 className="text-xl font-bold mb-4" style={{ color: '#2c3e50' }}>📈 Veille Automatique - Sujets Prioritaires</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
                  {Object.entries(autoSearchResults).map(([subject, result]) => (
                    <div key={subject} className="glass-card" style={{ padding: '1rem' }}>
                      <h4 className="font-semibold mb-2" style={{ color: '#2c3e50' }}>{subject}</h4>
                      {result.error ? (
                        <p className="text-sm" style={{ color: '#e74c3c' }}>Erreur</p>
                      ) : (
                        <div className="text-sm" style={{ color: '#34495e' }}>
                          <p>📰 {result.articles_count || 0} articles</p>
                          <p>💬 {result.social_posts_count || 0} posts</p>
                          <p className="font-medium" style={{ color: '#2c3e50' }}>Total: {result.total_results || 0}</p>
                        </div>
                      )}
                      <button
                        onClick={() => {
                          setSearchQuery(subject);
                          handleSearch(subject);
                          setActiveTab('search');
                        }}
                        className="glass-button primary"
                        style={{ marginTop: '0.5rem', padding: '0.5rem 1rem', fontSize: '0.8rem' }}
                      >
                        🔍 Voir détails
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Barre de recherche */}
            <div className="glass-card">
              <h3 className="text-xl font-bold mb-4" style={{ color: '#2c3e50' }}>🔍 Recherche Rapide</h3>
              <div className="flex gap-4 flex-col md:flex-row">
                <div className="flex-1">
                  <div className="relative">
                    <input
                      type="text"
                      placeholder="Rechercher Guy Losbar, CD971, articles..."
                      value={searchQuery}
                      onChange={(e) => {
                        setSearchQuery(e.target.value);
                        if (e.target.value.length >= 2) {
                          loadSearchSuggestions(e.target.value);
                        }
                      }}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          handleSearch(searchQuery);
                          setActiveTab('search');
                        }
                      }}
                      className="glass-input pl-10"
                    />
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <svg className="w-5 h-5 text-white opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                      </svg>
                    </div>
                    
                    {/* Suggestions de recherche */}
                    {searchSuggestions.length > 0 && searchQuery.length >= 2 && (
                      <div className="absolute top-full left-0 w-full mt-1 glass-card z-50">
                        {searchSuggestions.map((suggestion, index) => (
                          <button
                            key={index}
                            onClick={() => {
                              setSearchQuery(suggestion);
                              handleSearch(suggestion);
                              setActiveTab('search');
                              setSearchSuggestions([]);
                            }}
                            className="w-full text-left px-4 py-2 hover:bg-white hover:bg-opacity-10 first:rounded-t-lg last:rounded-b-lg"
                            style={{ color: '#2c3e50' }}
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => {
                    handleSearch(searchQuery);
                    setActiveTab('search');
                  }}
                  disabled={searchLoading}
                  className="glass-button primary"
                >
                  {searchLoading ? '⏳' : '🔍'} Rechercher
                </button>
              </div>
              
              {/* Suggestions populaires */}
              <div className="mt-4">
                <p className="text-sm mb-2" style={{ color: '#7f8c8d' }}>Recherches populaires :</p>
                <div className="flex flex-wrap gap-2">
                  {['cd971', 'Guy Losbar', 'département guadeloupe', 'GUSR', 'Ary Chalus', 'Budget départemental'].map((term) => (
                    <button
                      key={term}
                      onClick={() => {
                        setSearchQuery(term);
                        handleSearch(term);
                        setActiveTab('search');
                      }}
                      className="glass-button"
                      style={{ padding: '0.5rem 1rem', fontSize: '0.8rem' }}
                    >
                      {term}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="glass-card">
              <h3 className="text-xl font-bold mb-4" style={{ color: '#2c3e50' }}>🚀 Actions Automatiques</h3>
              <div className="actions-grid">
                <button
                  onClick={scrapeArticlesNow}
                  disabled={backgroundTasks.scraping}
                  className={`glass-button ${backgroundTasks.scraping ? '' : 'primary'}`}
                >
                  {backgroundTasks.scraping ? '⏳ Scraping...' : '📰 Scraper Articles'}
                </button>
                <button
                  onClick={captureRadioNow}
                  disabled={backgroundTasks.capturing}
                  className={`glass-button ${backgroundTasks.capturing ? '' : 'success'}`}
                >
                  {backgroundTasks.capturing ? '⏳ Capture...' : '📻 Capturer Radio'}
                </button>
                <button
                  onClick={createDigestNow}
                  className="glass-button primary"
                >
                  📄 Créer Digest
                </button>
                <label className="glass-button success cursor-pointer text-center">
                  🎤 Upload Audio
                  <input type="file" accept="audio/*" onChange={uploadAudio} className="hidden" />
                </label>
              </div>
            </div>
          </div>
        )}

        {/* Articles */}
        {activeTab === 'articles' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-800">📰 Articles de Guadeloupe</h2>
              <button
                onClick={scrapeArticlesNow}
                disabled={backgroundTasks.scraping}
                className={`px-6 py-2 rounded-lg font-semibold transition-colors ${
                  backgroundTasks.scraping
                    ? 'bg-gray-400 text-gray-700 cursor-not-allowed'
                    : 'bg-blue-500 hover:bg-blue-600 text-white'
                }`}
              >
                {backgroundTasks.scraping ? '⏳ Scraping...' : '🔄 Scraper Maintenant'}
              </button>
            </div>

            <div className="bg-white p-4 rounded-lg shadow-md">
              <p className="text-sm text-gray-600">
                <strong>Sources automatiques :</strong> France-Antilles, RCI.fm, La 1ère, KaribInfo | 
                <strong> Programmé :</strong> Tous les jours à 10H00 |
                <strong> Cache :</strong> 5 minutes
              </p>
            </div>

            <div className="grid gap-6">
              {articles.map(article => (
                <div key={article.id} className="bg-white p-6 rounded-xl shadow-lg hover:shadow-xl transition-shadow">
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="text-xl font-bold text-gray-800 flex-1">
                      <a href={article.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800">
                        {article.title}
                      </a>
                    </h3>
                    <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-medium ml-4">
                      {article.source}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-sm text-gray-500">
                    <span>Scrapé le {new Date(article.scraped_at).toLocaleString('fr-FR')}</span>
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-500 hover:text-blue-600 font-medium"
                    >
                      🔗 Lire l'article
                    </a>
                  </div>
                </div>
              ))}
              {articles.length === 0 && !loading && (
                <div className="text-center py-12 text-gray-500">
                  <div className="text-6xl mb-4">📰</div>
                  <p className="text-xl">Aucun article pour cette date</p>
                  <p>Le scraping automatique a lieu tous les jours à 10H</p>
                  <button
                    onClick={scrapeArticlesNow}
                    disabled={backgroundTasks.scraping}
                    className="mt-4 bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                  >
                    {backgroundTasks.scraping ? '⏳ Scraping...' : '🔄 Lancer le scraping'}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Transcriptions Radio */}
        {activeTab === 'transcription' && (
          <div className="space-y-6">
            {/* En-tête avec statut global */}
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-2xl font-bold text-gray-800">📻 Transcriptions Radio</h2>
                <div className="flex items-center gap-2 mt-1">
                  <div className={`w-3 h-3 rounded-full ${transcriptionStatus.global_status.any_in_progress ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`}></div>
                  <span className="text-sm text-gray-600">
                    {transcriptionStatus.global_status.any_in_progress 
                      ? `${transcriptionStatus.global_status.active_sections} transcription(s) en cours`
                      : 'Aucune transcription en cours'
                    }
                  </span>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={captureRadioNow}
                  disabled={backgroundTasks.capturing}
                  className={`px-6 py-2 rounded-lg font-semibold transition-colors ${
                    backgroundTasks.capturing
                      ? 'bg-gray-400 text-gray-700 cursor-not-allowed'
                      : 'bg-green-500 hover:bg-green-600 text-white'
                  }`}
                >
                  {backgroundTasks.capturing ? '⏳ Capture...' : '📻 Capturer Tout'}
                </button>
                <button
                  onClick={() => {
                    loadTranscriptionSections();
                    loadTranscriptionStatus();
                  }}
                  className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                >
                  🔄 Actualiser
                </button>
                <label className="bg-orange-500 hover:bg-orange-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors cursor-pointer">
                  📤 Upload Audio
                  <input type="file" accept="audio/*" onChange={uploadAudio} className="hidden" />
                </label>
              </div>
            </div>

            {/* Sections de transcription prédéfinies */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Section 7H RCI */}
              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-blue-500">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="text-xl font-bold text-gray-800">🎙️ 7H RCI</h3>
                    <p className="text-sm text-gray-600">RCI Guadeloupe - Journal matinal</p>
                    <p className="text-xs text-gray-500">07:00 - 07:20 (20 min)</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {transcriptionStatus.sections?.rci_7h?.in_progress && (
                      <div className="flex items-center gap-1 text-green-600">
                        <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                        <span className="text-xs">En cours...</span>
                      </div>
                    )}
                    <button
                      onClick={() => captureSection('rci')}
                      disabled={loading || transcriptionStatus.sections?.rci_7h?.in_progress}
                      className="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded text-sm font-semibold transition-colors disabled:bg-gray-400"
                    >
                      📻 Capturer
                    </button>
                  </div>
                </div>
                <div className="space-y-3">
                  {transcriptionSections["7H RCI"]?.length > 0 ? (
                    transcriptionSections["7H RCI"].slice(0, 3).map(t => (
                      <div key={t.id} className="bg-gray-50 p-3 rounded-lg">
                        {/* Résumé IA ou transcription brute */}
                        <p className="text-sm text-gray-700 font-medium">
                          {t.ai_summary || `"${t.transcription_text.substring(0, 100)}..."`}
                        </p>
                        
                        {/* Mots-clés et sujets */}
                        {t.ai_keywords && t.ai_keywords.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {t.ai_keywords.slice(0, 4).map((keyword, idx) => (
                              <span key={idx} className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">
                                {keyword}
                              </span>
                            ))}
                          </div>
                        )}
                        
                        {/* Score de pertinence */}
                        {t.ai_relevance_score && (
                          <div className="flex items-center gap-2 mt-2">
                            <div className="flex">
                              {[1,2,3,4,5].map(star => (
                                <span key={star} className={`text-xs ${
                                  star <= (t.ai_relevance_score * 5) ? 'text-yellow-400' : 'text-gray-300'
                                }`}>⭐</span>
                              ))}
                            </div>
                            <span className="text-xs text-gray-500">
                              Pertinence: {Math.round(t.ai_relevance_score * 100)}%
                            </span>
                          </div>
                        )}
                        
                        <p className="text-xs text-gray-500 mt-2">
                          {new Date(t.captured_at || t.uploaded_at).toLocaleString('fr-FR')}
                        </p>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-6 text-gray-500">
                      <div className="text-2xl mb-2">📻</div>
                      <p className="text-sm">Aucune transcription aujourd'hui</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Section 7H Guadeloupe Première */}
              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-green-500">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="text-xl font-bold text-gray-800">🌴 7H Guadeloupe Première</h3>
                    <p className="text-sm text-gray-600">Guadeloupe Première - Actualités matinales</p>
                    <p className="text-xs text-gray-500">07:00 - 07:30 (30 min)</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress && (
                      <div className="flex items-center gap-1 text-green-600">
                        <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                        <span className="text-xs">En cours...</span>
                      </div>
                    )}
                    <button
                      onClick={() => captureSection('guadeloupe')}
                      disabled={loading || transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress}
                      className="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded text-sm font-semibold transition-colors disabled:bg-gray-400"
                    >
                      📻 Capturer
                    </button>
                  </div>
                </div>
                <div className="space-y-3">
                  {transcriptionSections["7H Guadeloupe Première"]?.length > 0 ? (
                    transcriptionSections["7H Guadeloupe Première"].slice(0, 3).map(t => (
                      <div key={t.id} className="bg-gray-50 p-3 rounded-lg">
                        {/* Résumé IA ou transcription brute */}
                        <p className="text-sm text-gray-700 font-medium">
                          {t.ai_summary || `"${t.transcription_text.substring(0, 100)}..."`}
                        </p>
                        
                        {/* Mots-clés et sujets */}
                        {t.ai_keywords && t.ai_keywords.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {t.ai_keywords.slice(0, 4).map((keyword, idx) => (
                              <span key={idx} className="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">
                                {keyword}
                              </span>
                            ))}
                          </div>
                        )}
                        
                        {/* Score de pertinence */}
                        {t.ai_relevance_score && (
                          <div className="flex items-center gap-2 mt-2">
                            <div className="flex">
                              {[1,2,3,4,5].map(star => (
                                <span key={star} className={`text-xs ${
                                  star <= (t.ai_relevance_score * 5) ? 'text-yellow-400' : 'text-gray-300'
                                }`}>⭐</span>
                              ))}
                            </div>
                            <span className="text-xs text-gray-500">
                              Pertinence: {Math.round(t.ai_relevance_score * 100)}%
                            </span>
                          </div>
                        )}
                        
                        <p className="text-xs text-gray-500 mt-2">
                          {new Date(t.captured_at || t.uploaded_at).toLocaleString('fr-FR')}
                        </p>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-6 text-gray-500">
                      <div className="text-2xl mb-2">🌴</div>
                      <p className="text-sm">Aucune transcription aujourd'hui</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Section Autres */}
            {transcriptionSections["Autres"]?.length > 0 && (
              <div className="bg-white p-6 rounded-xl shadow-lg">
                <h3 className="text-xl font-bold text-gray-800 mb-4">📤 Fichiers Uploadés</h3>
                <div className="grid gap-4">
                  {transcriptionSections["Autres"].map(transcription => (
                    <div key={transcription.id} className="bg-gray-50 p-4 rounded-lg">
                      <div className="flex justify-between items-start mb-2">
                        <h4 className="font-semibold text-gray-800">{transcription.filename}</h4>
                        <div className="flex gap-2">
                          <span className="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">
                            {Math.round(transcription.duration_seconds || 0)}s
                          </span>
                          <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">
                            {transcription.language || 'fr'}
                          </span>
                        </div>
                      </div>
                      
                      {/* Résumé IA ou transcription brute */}
                      <div className="bg-white p-3 rounded border-l-2 border-gray-300 mb-2">
                        <p className="text-gray-700 font-medium">
                          {transcription.ai_summary || `"${transcription.transcription_text || 'Transcription vide'}"`}
                        </p>
                      </div>
                      
                      {/* Mots-clés */}
                      {transcription.ai_keywords && transcription.ai_keywords.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-2">
                          {transcription.ai_keywords.slice(0, 5).map((keyword, idx) => (
                            <span key={idx} className="bg-purple-100 text-purple-800 px-2 py-1 rounded-full text-xs">
                              {keyword}
                            </span>
                          ))}
                        </div>
                      )}
                      
                      {/* Score de pertinence */}
                      {transcription.ai_relevance_score && (
                        <div className="flex items-center gap-2 mb-2">
                          <div className="flex">
                            {[1,2,3,4,5].map(star => (
                              <span key={star} className={`text-xs ${
                                star <= (transcription.ai_relevance_score * 5) ? 'text-yellow-400' : 'text-gray-300'
                              }`}>⭐</span>
                            ))}
                          </div>
                          <span className="text-xs text-gray-500">
                            Pertinence: {Math.round(transcription.ai_relevance_score * 100)}%
                          </span>
                        </div>
                      )}
                      
                      <p className="text-xs text-gray-500">
                        Uploadé le {new Date(transcription.uploaded_at).toLocaleString('fr-FR')}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Message si aucune transcription */}
            {Object.values(transcriptionSections).every(section => section.length === 0) && !loading && (
              <div className="text-center py-12 text-gray-500">
                <div className="text-6xl mb-4">📻</div>
                <p className="text-xl mb-2">Aucune transcription pour aujourd'hui</p>
                <p className="mb-4">La capture automatique a lieu tous les jours à 7H</p>
                <div className="flex justify-center gap-4">
                  <button
                    onClick={() => captureSection('rci')}
                    className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                  >
                    📻 Capturer 7H RCI
                  </button>
                  <button
                    onClick={() => captureSection('guadeloupe')}
                    className="bg-green-500 hover:bg-green-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                  >
                    📻 Capturer Guadeloupe 1ère
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Digest Quotidien */}
        {activeTab === 'digest' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-800">📄 Digest Quotidien</h2>
              <div className="flex gap-2">
                <button
                  onClick={createDigestNow}
                  className="bg-purple-500 hover:bg-purple-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                >
                  📄 Créer Digest
                </button>
                {digest && (
                  <>
                    <a
                      href={`${BACKEND_URL}/api/digest/${selectedDate}/pdf`}
                      className="bg-red-500 hover:bg-red-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                    >
                      📄 Télécharger PDF
                    </a>
                    <a
                      href={`${BACKEND_URL}/api/digest/${selectedDate}/html`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="bg-gray-500 hover:bg-gray-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                    >
                      🔗 Version HTML
                    </a>
                  </>
                )}
              </div>
            </div>

            <div className="bg-white p-4 rounded-lg shadow-md">
              <p className="text-sm text-gray-600">
                <strong>Résumé automatique :</strong> Articles + Transcriptions radio formatés | 
                <strong> Programmé :</strong> Tous les jours à 12H00 |
                <strong> Cache :</strong> 15 minutes
              </p>
            </div>

            {digest ? (
              <div className="bg-white p-6 rounded-xl shadow-lg">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-bold text-gray-800">
                    Digest du {new Date(digest.date).toLocaleDateString('fr-FR')}
                  </h3>
                  <div className="text-sm text-gray-500">
                    {digest.articles_count} articles • {digest.transcriptions_count} transcriptions
                  </div>
                </div>
                <div 
                  className="prose max-w-none"
                  dangerouslySetInnerHTML={{ __html: digest.digest_html }}
                />
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500">
                <div className="text-6xl mb-4">📄</div>
                <p className="text-xl">Aucun digest pour cette date</p>
                <p>Cliquez sur "Créer Digest" pour générer le résumé</p>
              </div>
            )}
          </div>
        )}

        {/* Planificateur */}
        {activeTab === 'scheduler' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold text-gray-800">⏰ Planificateur Automatique</h2>
            
            {schedulerStatus.jobs && (
              <div className="grid gap-6">
                <div className="bg-white p-6 rounded-xl shadow-lg">
                  <h3 className="text-lg font-bold text-gray-800 mb-4">📅 Tâches Programmées</h3>
                  <div className="space-y-4">
                    {schedulerStatus.jobs.map(job => (
                      <div key={job.id} className="flex justify-between items-center p-4 border border-gray-200 rounded-lg">
                        <div>
                          <h4 className="font-semibold text-gray-800">{job.name}</h4>
                          <p className="text-sm text-gray-600">
                            Prochaine exécution: {job.next_run ? new Date(job.next_run).toLocaleString('fr-FR') : 'Non programmée'}
                          </p>
                        </div>
                        <button
                          onClick={() => runSchedulerJob(job.id)}
                          className="bg-indigo-500 hover:bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                        >
                          ▶️ Exécuter
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                {schedulerStatus.recent_logs && (
                  <div className="bg-white p-6 rounded-xl shadow-lg">
                    <h3 className="text-lg font-bold text-gray-800 mb-4">📋 Logs Récents</h3>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {schedulerStatus.recent_logs.map((log, index) => (
                        <div 
                          key={index} 
                          className={`p-3 rounded-lg text-sm ${
                            log.success ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
                          }`}
                        >
                          <div className="flex justify-between items-start">
                            <span className="font-medium">{log.job_name}</span>
                            <span className="text-xs opacity-75">
                              {new Date(log.timestamp).toLocaleString('fr-FR')}
                            </span>
                          </div>
                          {log.details && <p className="mt-1 opacity-90">{log.details}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Page de Recherche */}
        {activeTab === 'search' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-800">🔍 Recherche</h2>
              <div className="text-sm text-gray-600">
                Recherche dans articles et réseaux sociaux
              </div>
            </div>

            {/* Barre de recherche étendue */}
            <div className="bg-white p-6 rounded-xl shadow-lg">
              <div className="flex gap-4">
                <div className="flex-1">
                  <input
                    type="text"
                    placeholder="Rechercher dans les articles et réseaux sociaux..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSearch(searchQuery)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                  />
                </div>
                <button
                  onClick={() => handleSearch(searchQuery)}
                  disabled={searchLoading}
                  className="px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white rounded-lg font-semibold transition-colors disabled:opacity-50"
                >
                  {searchLoading ? '⏳' : '🔍'} Rechercher
                </button>
              </div>
              
              {/* Suggestions populaires */}
              <div className="mt-4">
                <p className="text-sm text-gray-600 mb-2">Recherches populaires :</p>
                <div className="flex flex-wrap gap-2">
                  {['cd971', 'Guy Losbar', 'département guadeloupe', 'GUSR', 'Ary Chalus', 'Budget départemental'].map((term) => (
                    <button
                      key={term}
                      onClick={() => {
                        setSearchQuery(term);
                        handleSearch(term);
                      }}
                      className="px-3 py-1 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-full text-sm transition-colors"
                    >
                      {term}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Résultats de recherche */}
            {searchResults && (
              <div className="space-y-6">
                <div className="bg-blue-50 p-4 rounded-lg">
                  <h3 className="font-semibold text-blue-800">
                    {searchResults.total_results} résultats pour "{searchResults.query}"
                  </h3>
                  <p className="text-sm text-blue-600 mt-1">
                    Recherché dans : {searchResults.searched_in.join(', ')}
                  </p>
                </div>

                {/* Articles trouvés */}
                {searchResults.articles && searchResults.articles.length > 0 && (
                  <div className="bg-white rounded-xl shadow-lg">
                    <div className="p-6 border-b border-gray-200">
                      <h3 className="text-lg font-bold text-gray-800">
                        📰 Articles ({searchResults.articles.length})
                      </h3>
                    </div>
                    <div className="p-6 space-y-4">
                      {searchResults.articles.map((article, index) => (
                        <div key={index} className="border-l-4 border-blue-500 pl-4">
                          <h4 className="font-semibold text-gray-800">
                            <a 
                              href={article.url} 
                              target="_blank" 
                              rel="noopener noreferrer"
                              className="hover:text-blue-600 transition-colors"
                            >
                              {article.title}
                            </a>
                          </h4>
                          <p className="text-sm text-gray-600 mt-1">
                            {article.source} • {new Date(article.scraped_at).toLocaleDateString('fr-FR')}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Posts réseaux sociaux trouvés */}
                {searchResults.social_posts && searchResults.social_posts.length > 0 && (
                  <div className="bg-white rounded-xl shadow-lg">
                    <div className="p-6 border-b border-gray-200">
                      <h3 className="text-lg font-bold text-gray-800">
                        📱 Réseaux Sociaux ({searchResults.social_posts.length})
                      </h3>
                    </div>
                    <div className="p-6 space-y-4">
                      {searchResults.social_posts.map((post, index) => (
                        <div key={index} className="border border-gray-200 rounded-lg p-4">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-sm font-medium text-gray-800">@{post.author}</span>
                            <span className="text-xs text-gray-500">• {post.platform}</span>
                            <span className="text-xs text-gray-500">
                              • {new Date(post.created_at).toLocaleDateString('fr-FR')}
                            </span>
                          </div>
                          <p className="text-gray-700">{post.content}</p>
                          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                            <span>❤️ {post.engagement?.total || 0}</span>
                            {post.demo_data && <span className="bg-yellow-100 text-yellow-800 px-2 py-1 rounded">DEMO</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Suggestions si aucun résultat */}
                {searchResults.total_results === 0 && searchResults.suggestions && (
                  <div className="bg-gray-50 p-6 rounded-lg text-center">
                    <p className="text-gray-600 mb-4">Aucun résultat trouvé.</p>
                    <div>
                      <p className="text-sm text-gray-600 mb-2">Essayez ces suggestions :</p>
                      <div className="flex flex-wrap justify-center gap-2">
                        {searchResults.suggestions.map((suggestion, index) => (
                          <button
                            key={index}
                            onClick={() => {
                              setSearchQuery(suggestion);
                              handleSearch(suggestion);
                            }}
                            className="px-3 py-1 bg-white border border-gray-300 rounded-full text-sm hover:bg-gray-100 transition-colors"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Page Commentaires */}
        {activeTab === 'comments' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold" style={{ color: '#2c3e50' }}>💬 Réseaux Sociaux</h2>
              <div className="flex gap-2">
                <button
                  onClick={startSocialScraping}
                  className="glass-button primary"
                >
                  📱 Scraper Réseaux
                </button>
                <button
                  onClick={analyzeComments}
                  className="glass-button success"
                >
                  📊 Analyser Sentiment
                </button>
              </div>
            </div>

            {/* Barre de recherche spécifique aux réseaux sociaux */}
            <div className="glass-card">
              <h3 className="text-lg font-bold mb-4" style={{ color: '#2c3e50' }}>🔍 Recherche sur les Réseaux Sociaux</h3>
              
              {/* Erreur de recherche sociale */}
              {socialSearchError && (
                <div className="alert error mb-4">
                  <span>{socialSearchError}</span>
                  <button onClick={() => setSocialSearchError(null)} className="hover:opacity-75" style={{ color: '#e74c3c' }}>✕</button>
                </div>
              )}

              <div className="flex gap-4 flex-col md:flex-row">
                <div className="flex-1">
                  <input
                    type="text"
                    placeholder="Rechercher un sujet spécifique sur les réseaux sociaux..."
                    value={socialSearchQuery}
                    onChange={(e) => setSocialSearchQuery(e.target.value)}
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        handleSocialSearch(socialSearchQuery);
                      }
                    }}
                    className="glass-input"
                    disabled={socialSearchLoading}
                  />
                </div>
                <button
                  onClick={() => handleSocialSearch(socialSearchQuery)}
                  disabled={socialSearchLoading || socialSearchQuery.trim().length < 2}
                  className="glass-button primary"
                >
                  {socialSearchLoading ? '⏳ Recherche...' : '🔍 Rechercher & Scraper'}
                </button>
              </div>
              
              {/* Suggestions de recherche sociale */}
              <div className="mt-4">
                <p className="text-sm mb-2" style={{ color: '#7f8c8d' }}>Suggestions de recherche :</p>
                <div className="flex flex-wrap gap-2">
                  {['Politique Guadeloupe', 'Éducation 971', 'Santé départementale', 'Transports publics', 'Environnement Antilles'].map((term) => (
                    <button
                      key={term}
                      onClick={() => {
                        setSocialSearchQuery(term);
                        handleSocialSearch(term);
                      }}
                      className="glass-button"
                      style={{ padding: '0.5rem 1rem', fontSize: '0.8rem' }}
                      disabled={socialSearchLoading}
                    >
                      {term}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Résultats de recherche sociale */}
            {socialSearchResults && (
              <div className="glass-card">
                <h3 className="text-lg font-bold mb-4" style={{ color: '#2c3e50' }}>
                  📊 Résultats pour "{socialSearchResults.query}" ({socialSearchResults.total_results})
                </h3>
                
                {socialSearchResults.social_posts && socialSearchResults.social_posts.length > 0 ? (
                  <div className="space-y-4">
                    {socialSearchResults.social_posts.map((post, index) => (
                      <div key={index} className="article-card">
                        <div className="flex justify-between items-start mb-2">
                          <div className="flex items-center gap-2">
                            <span className="article-source">
                              {post.platform === 'twitter' ? '🐦 Twitter' : 
                               post.platform === 'facebook' ? '👥 Facebook' : 
                               post.platform === 'instagram' ? '📸 Instagram' : '📱 Social'}
                            </span>
                            <span className="text-sm" style={{ color: '#7f8c8d' }}>
                              @{post.author || 'Anonyme'}
                            </span>
                          </div>
                          <span className="text-xs" style={{ color: '#7f8c8d' }}>
                            {new Date(post.created_at).toLocaleDateString('fr-FR')}
                          </span>
                        </div>
                        
                        <p className="mb-3" style={{ color: '#2c3e50' }}>
                          {post.content}
                        </p>
                        
                        {post.engagement && (
                          <div className="flex gap-4 text-sm" style={{ color: '#7f8c8d' }}>
                            <span>❤️ {post.engagement.likes || 0}</span>
                            <span>🔄 {post.engagement.retweets || 0}</span>
                            <span>💬 {post.engagement.replies || 0}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <div className="text-4xl mb-2">🔍</div>
                    <p style={{ color: '#7f8c8d' }}>Aucun résultat trouvé pour cette recherche</p>
                  </div>
                )}
              </div>
            )}

            {/* Statistiques des réseaux sociaux */}
            {socialStats && Object.keys(socialStats).length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-white p-4 rounded-lg shadow">
                  <h3 className="text-lg font-semibold text-gray-800">Total Posts</h3>
                  <p className="text-2xl font-bold text-blue-600">{socialStats.total_today || 0}</p>
                </div>
                <div className="bg-white p-4 rounded-lg shadow">
                  <h3 className="text-lg font-semibold text-gray-800">Twitter</h3>
                  <p className="text-2xl font-bold text-blue-400">{socialStats.by_platform?.twitter || 0}</p>
                </div>
                <div className="bg-white p-4 rounded-lg shadow">
                  <h3 className="text-lg font-semibold text-gray-800">Facebook</h3>
                  <p className="text-2xl font-bold text-blue-800">{socialStats.by_platform?.facebook || 0}</p>
                </div>
                <div className="bg-white p-4 rounded-lg shadow">
                  <h3 className="text-lg font-semibold text-gray-800">Instagram</h3>
                  <p className="text-2xl font-bold text-pink-500">{socialStats.by_platform?.instagram || 0}</p>
                </div>
              </div>
            )}

            {/* Analyse de sentiment par entité */}
            {commentsAnalysis && (
              <div className="bg-white rounded-xl shadow-lg">
                <div className="p-6 border-b border-gray-200">
                  <h3 className="text-lg font-bold text-gray-800">
                    📊 Analyse Sentiment par Entité ({commentsAnalysis.total_comments} commentaires analysés)
                  </h3>
                </div>
                <div className="p-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {Object.entries(commentsAnalysis.by_entity || {}).map(([entity, data]) => (
                      <div key={entity} className="border border-gray-200 rounded-lg p-4">
                        <h4 className="font-semibold text-gray-800 mb-2">{entity}</h4>
                        <div className="space-y-2">
                          <div className="flex justify-between text-sm">
                            <span>Mentions:</span>
                            <span className="font-medium">{data.total_mentions}</span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span>Sentiment moyen:</span>
                            <span className={`font-medium ${
                              data.average_sentiment > 0.1 ? 'text-green-600' : 
                              data.average_sentiment < -0.1 ? 'text-red-600' : 'text-gray-600'
                            }`}>
                              {data.average_sentiment > 0.1 ? '😊' : data.average_sentiment < -0.1 ? '😟' : '😐'} 
                              {data.average_sentiment.toFixed(3)}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-green-600">+{data.sentiment_distribution.positive}</span>
                            <span className="text-red-600">-{data.sentiment_distribution.negative}</span>
                            <span className="text-gray-600">={data.sentiment_distribution.neutral}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Liste des commentaires */}
            <div className="bg-white rounded-xl shadow-lg">
              <div className="p-6 border-b border-gray-200">
                <h3 className="text-lg font-bold text-gray-800">
                  💬 Commentaires Récents ({comments.length})
                </h3>
              </div>
              <div className="p-6">
                {comments.length > 0 ? (
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {comments.map((comment, index) => (
                      <div key={index} className="border border-gray-200 rounded-lg p-4">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-gray-800">@{comment.author}</span>
                            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                              {comment.platform}
                            </span>
                            {comment.demo_data && (
                              <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded">
                                DEMO
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 text-xs text-gray-500">
                            <span>{new Date(comment.created_at).toLocaleDateString('fr-FR')}</span>
                            {comment.sentiment_summary && (
                              <span className={`px-2 py-1 rounded ${
                                comment.sentiment_summary.polarity === 'positive' ? 'bg-green-100 text-green-800' :
                                comment.sentiment_summary.polarity === 'negative' ? 'bg-red-100 text-red-800' :
                                'bg-gray-100 text-gray-800'
                              }`}>
                                {comment.sentiment_summary.polarity === 'positive' ? '😊' : 
                                 comment.sentiment_summary.polarity === 'negative' ? '😟' : '😐'}
                                {comment.sentiment_summary.score?.toFixed(2)}
                              </span>
                            )}
                          </div>
                        </div>
                        <p className="text-gray-700 mb-2">{comment.content}</p>
                        <div className="flex items-center gap-4 text-xs text-gray-500">
                          <span>❤️ {comment.engagement?.total || 0}</span>
                          <span>🔑 {comment.keyword_searched}</span>
                          {comment.political_figure && (
                            <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded">
                              👤 {comment.political_figure}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12 text-gray-500">
                    <div className="text-6xl mb-4">💬</div>
                    <p className="text-xl">Aucun commentaire disponible</p>
                    <p>Lancez le scraping des réseaux sociaux pour récupérer des données</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;