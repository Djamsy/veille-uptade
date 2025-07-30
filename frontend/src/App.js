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

  // États pour l'analyse de sentiment et prédiction des réactions
  const [sentimentText, setSentimentText] = useState('');
  const [sentimentResult, setSentimentResult] = useState(null);
  const [sentimentLoading, setSentimentLoading] = useState(false);
  const [reactionPrediction, setReactionPrediction] = useState(null);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [sentimentMode, setSentimentMode] = useState('sync'); // 'sync' ou 'async'

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
        // Actualiser le statut immédiatement
        setTimeout(() => {
          loadTranscriptionStatus();
        }, 1000);
        
        // Actualiser les sections après le temps estimé de completion (3-5 min)
        setTimeout(() => {
          loadTranscriptionSections();
          loadTranscriptionStatus();
        }, 180000); // 3 minutes
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

  // Analyser le sentiment d'un texte
  const analyzeSentiment = async (useAsync = false) => {
    if (!sentimentText.trim()) {
      setError('Veuillez entrer un texte à analyser');
      return;
    }

    setSentimentLoading(true);
    setSentimentResult(null);
    setError(null);

    try {
      const response = await apiCall(`${BACKEND_URL}/api/sentiment/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          text: sentimentText.trim(),
          async: useAsync 
        })
      });

      if (response.success) {
        if (response.async) {
          // Mode asynchrone - polling du statut
          setSentimentResult({ 
            mode: 'async', 
            status: 'processing', 
            hash: response.text_hash,
            message: response.message 
          });
          pollSentimentStatus(response.text_hash);
        } else {
          // Mode synchrone ou cache hit
          setSentimentResult(response);
        }
      } else {
        setError(`Erreur analyse sentiment: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur analyse sentiment: ${error.message}`);
    } finally {
      setSentimentLoading(false);
    }
  };

  // Polling du statut pour l'analyse asynchrone
  const pollSentimentStatus = async (textHash) => {
    let attempts = 0;
    const maxAttempts = 15;

    const poll = async () => {
      attempts++;
      try {
        const response = await apiCall(`${BACKEND_URL}/api/sentiment/status/${textHash}`);
        
        if (response.success && response.status === 'completed') {
          setSentimentResult(response);
          setSentimentLoading(false);
        } else if (response.status === 'not_found') {
          // Réessayer l'analyse (probablement en cache maintenant)
          analyzeSentiment(true);
        } else if (attempts < maxAttempts) {
          setTimeout(poll, 2000);
        } else {
          setError('Timeout: analyse plus longue que prévue');
          setSentimentLoading(false);
        }
      } catch (error) {
        setError(`Erreur vérification statut: ${error.message}`);
        setSentimentLoading(false);
      }
    };

    setTimeout(poll, 2000);
  };

  // Prédire la réaction de la population
  const predictReaction = async () => {
    if (!sentimentText.trim()) {
      setError('Veuillez entrer un texte pour la prédiction');
      return;
    }

    setPredictionLoading(true);
    setReactionPrediction(null);
    setError(null);

    try {
      const response = await apiCall(`${BACKEND_URL}/api/sentiment/predict-reaction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          text: sentimentText.trim(),
          context: { source: 'frontend_test' }
        })
      });

      if (response.success) {
        setReactionPrediction(response.prediction);
      } else {
        setError(`Erreur prédiction réaction: ${response.error}`);
      }
    } catch (error) {
      setError(`Erreur prédiction réaction: ${error.message}`);
    } finally {
      setPredictionLoading(false);
    }
  };

  // Utiliser un exemple de texte
  const useSentimentExample = (example) => {
    setSentimentText(example);
    setSentimentResult(null);
    setReactionPrediction(null);
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
      {/* Header style Apple moderne */}
      <header className="glass-header">
        <div className="header-content">
          <div>
            <h1 className="header-title">
              🏝️ Veille Média Guadeloupe
            </h1>
          </div>
          <div className="header-subtitle">
            Dernière MAJ: {new Date().toLocaleDateString('fr-FR', { 
              day: 'numeric', 
              month: 'short', 
              hour: '2-digit', 
              minute: '2-digit' 
            })}
          </div>
        </div>
      </header>

      {/* Barre de statut des tâches - Style Apple moderne */}
      {(backgroundTasks.scraping || backgroundTasks.capturing) && (
        <div className="content-section">
          <div className="glass-card animate-slide-in" style={{ padding: '1.5rem', marginBottom: '1rem' }}>
            <div className="flex items-center gap-6">
              {backgroundTasks.scraping && (
                <div className="flex items-center gap-3">
                  <div className="animate-pulse">
                    <div style={{ 
                      width: '8px', 
                      height: '8px', 
                      background: '#3b82f6', 
                      borderRadius: '50%',
                      boxShadow: '0 0 20px rgba(59, 130, 246, 0.6)'
                    }}></div>
                  </div>
                  <span className="status-indicator status-info">
                    🔄 Scraping en cours... (2-3 min)
                  </span>
                </div>
              )}
              {backgroundTasks.capturing && (
                <div className="flex items-center gap-3">
                  <div className="animate-pulse">
                    <div style={{ 
                      width: '8px', 
                      height: '8px', 
                      background: '#f59e0b', 
                      borderRadius: '50%',
                      boxShadow: '0 0 20px rgba(245, 158, 11, 0.6)'
                    }}></div>
                  </div>
                  <span className="status-indicator status-warning">
                    📻 Capture radio en cours... (3-5 min)
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Navigation style Apple moderne */}
      <div className="content-section">
        <nav className="tab-navigation">
          {[
            { id: 'dashboard', name: 'Dashboard', icon: 'dashboard' },
            { id: 'search', name: 'Recherche', icon: 'search' },
            { id: 'articles', name: 'Articles', icon: 'articles' },
            { id: 'sentiment', name: 'Analyse Sentiment', icon: 'sentiment' },
            { id: 'comments', name: 'Réseaux Sociaux', icon: 'social' },
            { id: 'transcription', name: 'Radio', icon: 'radio' },
            { id: 'digest', name: 'Digest', icon: 'digest' }
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
              className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            >
              {tab.name}
            </button>
          ))}
        </nav>
      </div>

      {/* Main Content style Apple moderne */}
      <main className="content-section">
        {/* Affichage des erreurs - Style Apple */}
        {error && (
          <div className="glass-card animate-slide-in" style={{ 
            padding: '1rem', 
            marginBottom: '2rem',
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span className="status-indicator status-error">{error}</span>
              <button 
                onClick={() => setError(null)} 
                className="btn-secondary"
                style={{ padding: '0.5rem', minWidth: 'auto' }}
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Loading overlay - Style Apple */}
        {loading && (
          <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(13, 17, 23, 0.8)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999
          }}>
            <div className="glass-card animate-fade-in" style={{ padding: '2rem', textAlign: 'center' }}>
              <div className="animate-pulse" style={{ 
                width: '40px', 
                height: '40px', 
                background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)', 
                borderRadius: '50%',
                margin: '0 auto 1rem'
              }}></div>
              <p style={{ color: '#e2e8f0' }}>Traitement en cours...</p>
            </div>
          </div>
        )}

        {/* Dashboard moderne */}
        {activeTab === 'dashboard' && (
          <div className="animate-slide-in">
            <div className="section-header">
              <h2 className="section-title">📊 Vue d'ensemble - Guadeloupe</h2>
              <p className="section-subtitle">Surveillance médiatique en temps réel</p>
            </div>
            
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', 
              gap: '1.5rem',
              marginBottom: '3rem'
            }}>
              <div className="glass-card radio-priority-card animate-slide-in" style={{ padding: '2rem' }}>
                <div className="priority-badge" style={{ marginBottom: '1rem' }}>
                  🎙️ PRIORITÉ ABSOLUE
                </div>
                <div style={{ fontSize: '2.5rem', fontWeight: '700', color: '#fbbf24', marginBottom: '0.5rem' }}>
                  {dashboardStats.today_transcriptions || 0}
                </div>
                <div style={{ color: '#e2e8f0', marginBottom: '0.5rem' }}>Radio Locale Aujourd'hui</div>
                <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                  Total: {dashboardStats.total_transcriptions || 0}
                </div>
              </div>

              <div className="glass-card animate-slide-in" style={{ padding: '2rem' }}>
                <div style={{ fontSize: '2rem', fontWeight: '700', color: '#3b82f6', marginBottom: '0.5rem' }}>
                  {dashboardStats.today_articles || 0}
                </div>
                <div style={{ color: '#e2e8f0', marginBottom: '0.5rem' }}>📰 Articles Presse</div>
                <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                  Total: {dashboardStats.total_articles || 0}
                </div>
              </div>

              <div className="glass-card animate-slide-in" style={{ padding: '2rem' }}>
                <div style={{ fontSize: '2rem', fontWeight: '700', color: '#8b5cf6', marginBottom: '0.5rem' }}>
                  {dashboardStats.total_digests || 0}
                </div>
                <div style={{ color: '#e2e8f0', marginBottom: '0.5rem' }}>📋 Digests</div>
                <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                  Résumés quotidiens
                </div>
              </div>

              <div className="glass-card animate-slide-in" style={{ padding: '2rem' }}>
                <div style={{ fontSize: '2rem', fontWeight: '700', color: '#22c55e', marginBottom: '0.5rem' }}>
                  {dashboardStats.cache_stats?.cache_hit_ratio?.toFixed(1) || 0}%
                </div>
                <div style={{ color: '#e2e8f0', marginBottom: '0.5rem' }}>⚡ Cache Performance</div>
                <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                  Optimisation système
                </div>
              </div>
            </div>

            {/* Résultats de recherche automatique */}
            {autoSearchCompleted && Object.keys(autoSearchResults).length > 0 && (
              <div className="glass-card animate-slide-in" style={{ padding: '2rem' }}>
                <h3 className="section-title" style={{ fontSize: '1.5rem', marginBottom: '2rem' }}>
                  📈 Veille Automatique - Sujets Prioritaires
                </h3>
                <div style={{ 
                  display: 'grid', 
                  gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', 
                  gap: '1rem' 
                }}>
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
          <div className="animate-slide-in">
            <div className="section-header">
              <h2 className="section-title">📰 Articles de Guadeloupe</h2>
              <p className="section-subtitle">Sources : France-Antilles, RCI.fm, La 1ère, KaribInfo</p>
            </div>

            <div className="glass-card" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                <div style={{ color: '#6b7280', fontSize: '0.9rem' }}>
                  <strong>Programmé :</strong> Tous les jours à 10H00 | <strong>Cache :</strong> 5 minutes
                </div>
                <button
                  onClick={scrapeArticlesNow}
                  disabled={backgroundTasks.scraping}
                  className={backgroundTasks.scraping ? 'btn-secondary' : 'btn-primary'}
                  style={{ opacity: backgroundTasks.scraping ? 0.6 : 1 }}
                >
                  {backgroundTasks.scraping ? '⏳ Scraping...' : '🔄 Scraper Maintenant'}
                </button>
              </div>
            </div>

            <div className="article-list">
              {articles.map(article => (
                <article key={article.id} className="article-item">
                  {/* Titre de l'article */}
                  <header className="article-information">
                    <a href={article.url} target="_blank" rel="noopener noreferrer">
                      {article.title}
                    </a>
                  </header>
                  
                  {/* Résumé de l'article */}
                  <div className="article-explication">
                    {article.summary || article.ai_summary || "Résumé non disponible"}
                  </div>

                  {/* Métadonnées et actions */}
                  <footer className="article-meta">
                    <span className="article-source">{article.source}</span>
                    <span className="article-date">
                      {new Date(article.published_at || article.scraped_at).toLocaleDateString('fr-FR', {
                        day: 'numeric',
                        month: 'short',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                    {article.sentiment_score && (
                      <span className={`article-sentiment ${
                        article.sentiment_score > 0.1 
                          ? 'positive' 
                          : article.sentiment_score < -0.1 
                            ? 'negative' 
                            : 'neutral'
                      }`}>
                        {article.sentiment_score > 0.1 ? 'Positif' : article.sentiment_score < -0.1 ? 'Négatif' : 'Neutre'}
                      </span>
                    )}
                  </footer>

                  {/* Actions sur l'article */}
                  <div className="article-actions">
                    <a href={article.url} target="_blank" rel="noopener noreferrer" className="article-action-btn">
                      Lire l'article
                    </a>
                    {article.ai_summary && (
                      <button className="article-action-btn">
                        Résumé IA
                      </button>
                    )}
                  </div>
                </article>
              ))}
              
              {articles.length === 0 && !loading && (
                <div className="articles-empty-state">
                  <div className="articles-empty-icon">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWith="1.5">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14,2 14,8 20,8"/>
                      <line x1="16" y1="13" x2="8" y2="13"/>
                      <line x1="16" y1="17" x2="8" y2="17"/>
                      <polyline points="10,9 9,9 8,9"/>
                    </svg>
                  </div>
                  <h3 className="articles-empty-title">Aucun article disponible</h3>
                  <p className="articles-empty-description">
                    Lancez un scraping pour récupérer les derniers articles de Guadeloupe
                  </p>
                </div>
              )}

              {loading && articles.length === 0 && (
                <>
                  {[...Array(3)].map((_, index) => (
                    <div key={index} className="article-skeleton">
                      <div className="skeleton-line title"></div>
                      <div className="skeleton-line content"></div>
                      <div className="skeleton-line content"></div>
                      <div className="skeleton-line content"></div>
                      <div className="skeleton-line meta"></div>
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        )}

        {/* Transcriptions Radio */}
        {activeTab === 'transcription' && (
          <div className="animate-slide-in">
            {/* En-tête avec statut global */}
            <div className="section-header">
              <h2 className="section-title">📻 Transcriptions Radio</h2>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1rem', marginTop: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <div style={{ 
                    width: '8px', 
                    height: '8px', 
                    borderRadius: '50%',
                    background: transcriptionStatus.global_status.any_in_progress ? '#10b981' : '#9ca3af',
                    animation: transcriptionStatus.global_status.any_in_progress ? 'pulse 2s infinite' : 'none'
                  }}></div>
                  <span style={{ color: '#6b7280', fontSize: '0.9rem' }}>
                    {transcriptionStatus.global_status.any_in_progress 
                      ? `${transcriptionStatus.global_status.active_sections} transcription(s) en cours`
                      : 'Aucune transcription en cours'
                    }
                  </span>
                </div>
                {transcriptionStatus.global_status.any_in_progress && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#3b82f6', animation: 'pulse 2s infinite' }}></div>
                    <span style={{ color: '#3b82f6', fontSize: '0.8rem' }}>Auto-actualisation (30s)</span>
                  </div>
                )}
              </div>
            </div>

            {/* Boutons d'action */}
            <div className="glass-card" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <button
                  onClick={captureRadioNow}
                  disabled={backgroundTasks.capturing}
                  className={backgroundTasks.capturing ? 'btn-secondary' : 'btn-primary'}
                  style={{ opacity: backgroundTasks.capturing ? 0.6 : 1 }}
                >
                  {backgroundTasks.capturing ? '⏳ Capture...' : '📻 Capturer Tout'}
                </button>
                <button
                  onClick={() => {
                    loadTranscriptionSections();
                    loadTranscriptionStatus();
                  }}
                  className="btn-secondary"
                >
                  🔄 Actualiser
                </button>
                <label className="btn-primary cursor-pointer">
                  📤 Upload Audio
                  <input type="file" accept="audio/*" onChange={uploadAudio} style={{ display: 'none' }} />
                </label>
              </div>
            </div>

            {/* Sections de transcription prédéfinies */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '2rem', marginBottom: '3rem' }}>
              {/* Section 7H RCI */}
              <div className="glass-card radio-priority-card" style={{ padding: '2rem' }}>
                <div className="priority-badge" style={{ marginBottom: '1.5rem' }}>
                  🎙️ PRIORITÉ ABSOLUE
                </div>
                {/* Information */}
                <div style={{ marginBottom: '1.5rem' }}>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: '600', marginBottom: '0.5rem', color: '#1a1a1a' }}>
                    🎙️ 7H RCI
                  </h3>
                  <div style={{ color: '#6b7280', fontSize: '0.9rem' }}>
                    RCI Guadeloupe - Journal matinal | 07:00 - 07:20 (20 min)
                  </div>
                </div>

                {/* Statut et actions */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                  <div>
                    {transcriptionStatus.sections?.rci_7h?.in_progress ? (
                      <div className="status-indicator status-warning">
                        <div style={{ width: '6px', height: '6px', background: '#f59e0b', borderRadius: '50%', animation: 'pulse 2s infinite' }}></div>
                        {transcriptionStatus.sections?.rci_7h?.step_details || 'En cours...'}
                      </div>
                    ) : (
                      <div className="status-indicator status-success">
                        ✅ Prêt à capturer
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => captureSection('rci')}
                    disabled={loading || transcriptionStatus.sections?.rci_7h?.in_progress}
                    className={transcriptionStatus.sections?.rci_7h?.in_progress ? 'btn-secondary' : 'btn-primary'}
                    style={{ opacity: transcriptionStatus.sections?.rci_7h?.in_progress ? 0.6 : 1 }}
                  >
                    📻 Capturer
                  </button>
                </div>

                {/* Transcriptions */}
                <div className="transcription-list">
                  {transcriptionSections["7H RCI"]?.length > 0 ? (
                    transcriptionSections["7H RCI"].slice(0, 2).map(t => (
                      <div key={t.id} className="transcription-item" style={{ padding: '1.5rem' }}>
                        {/* Information */}
                        <div className="transcription-information">
                          📻 {t.stream_name} - {new Date(t.captured_at).toLocaleDateString('fr-FR')}
                        </div>
                        
                        {/* Explication */}
                        <div className="transcription-explication">
                          {t.gpt_analysis || t.ai_summary || `"${t.transcription_text?.substring(0, 150)}..."`}
                        </div>

                        {/* Métadonnées */}
                        <div className="transcription-meta">
                          <span style={{ color: '#f59e0b', fontWeight: '500' }}>
                            {t.transcription_method === 'segmented_openai_whisper_api' ? '🎬 Segmenté' : '🎤 Simple'}
                          </span>
                          <span>{new Date(t.captured_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>
                          {t.segments_count && (
                            <span>{t.segments_count} segments</span>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="glass-card" style={{ padding: '2rem', textAlign: 'center' }}>
                      <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>📻</div>
                      <p style={{ color: '#6b7280' }}>Aucune transcription aujourd'hui</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Section 7H Guadeloupe Première */}
              <div className="glass-card" style={{ padding: '2rem' }}>
                {/* Information */}
                <div style={{ marginBottom: '1.5rem' }}>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: '600', marginBottom: '0.5rem', color: '#1a1a1a' }}>
                    📻 7H Guadeloupe Première
                  </h3>
                  <div style={{ color: '#6b7280', fontSize: '0.9rem' }}>
                    Guadeloupe Première - Actualités matinales | 07:00 - 07:30 (30 min)
                  </div>
                </div>

                {/* Statut et actions */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                  <div>
                    {transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress ? (
                      <div className="status-indicator status-warning">
                        <div style={{ width: '6px', height: '6px', background: '#f59e0b', borderRadius: '50%', animation: 'pulse 2s infinite' }}></div>
                        {transcriptionStatus.sections?.guadeloupe_premiere_7h?.step_details || 'En cours...'}
                      </div>
                    ) : (
                      <div className="status-indicator status-info">
                        ✅ Prêt à capturer
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => captureSection('guadeloupe')}
                    disabled={loading || transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress}
                    className={transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress ? 'btn-secondary' : 'btn-primary'}
                    style={{ opacity: transcriptionStatus.sections?.guadeloupe_premiere_7h?.in_progress ? 0.6 : 1 }}
                  >
                    📻 Capturer
                  </button>
                </div>

                {/* Transcriptions */}
                <div className="transcription-list">
                  {transcriptionSections["7H Guadeloupe Première"]?.length > 0 ? (
                    transcriptionSections["7H Guadeloupe Première"].slice(0, 2).map(t => (
                      <div key={t.id} className="transcription-item" style={{ padding: '1.5rem' }}>
                        {/* Information */}
                        <div className="transcription-information">
                          📻 {t.stream_name} - {new Date(t.captured_at).toLocaleDateString('fr-FR')}
                        </div>
                        
                        {/* Explication */}
                        <div className="transcription-explication">
                          {t.gpt_analysis || t.ai_summary || `"${t.transcription_text?.substring(0, 150)}..."`}
                        </div>

                        {/* Métadonnées */}
                        <div className="transcription-meta">
                          <span style={{ color: '#3b82f6', fontWeight: '500' }}>
                            {t.transcription_method === 'segmented_openai_whisper_api' ? '🎬 Segmenté' : '🎤 Simple'}
                          </span>
                          <span>{new Date(t.captured_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>
                          {t.segments_count && (
                            <span>{t.segments_count} segments</span>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="glass-card" style={{ padding: '2rem', textAlign: 'center' }}>
                      <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>📻</div>
                      <p style={{ color: '#6b7280' }}>Aucune transcription aujourd'hui</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Toutes les transcriptions du jour */}
            <div className="glass-card" style={{ padding: '2rem' }}>
              <h3 style={{ fontSize: '1.25rem', fontWeight: '600', marginBottom: '1.5rem', color: '#1a1a1a' }}>
                📋 Toutes les transcriptions du jour
              </h3>
              
              <div className="transcription-list">
                {Object.entries(transcriptionSections).map(([sectionName, transcriptions]) => 
                  transcriptions?.map(t => (
                    <div key={t.id} className="transcription-item">
                      {/* Information */}
                      <div className="transcription-information">
                        📻 {t.stream_name || sectionName} - {new Date(t.captured_at || t.uploaded_at).toLocaleDateString('fr-FR')}
                      </div>
                      
                      {/* Explication */}
                      <div className="transcription-explication">
                        {t.gpt_analysis || t.ai_summary || `"${t.transcription_text?.substring(0, 200)}..."`}
                      </div>

                      {/* Métadonnées */}
                      <div className="transcription-meta">
                        <span className="article-source">{sectionName}</span>
                        <span>{new Date(t.captured_at || t.uploaded_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>
                        {t.segments_count && (
                          <span style={{ color: '#f59e0b', fontWeight: '500' }}>🎬 {t.segments_count} segments</span>
                        )}
                        {t.ai_relevance_score && (
                          <span style={{ color: '#10b981', fontWeight: '500' }}>
                            ⭐ {Math.round(t.ai_relevance_score * 100)}%
                          </span>
                        )}
                      </div>
                    </div>
                  ))
                )}
                
                {Object.values(transcriptionSections).every(section => !section || section.length === 0) && (
                  <div className="glass-card" style={{ padding: '3rem', textAlign: 'center' }}>
                    <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📻</div>
                    <p style={{ color: '#6b7280', fontSize: '1.1rem' }}>Aucune transcription disponible</p>
                    <p style={{ color: '#9ca3af', fontSize: '0.9rem', marginTop: '0.5rem' }}>
                      Capturez ou uploadez des fichiers audio pour commencer
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Search */}
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
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      if (e.target.value.length >= 2) {
                        loadSearchSuggestions(e.target.value);
                      }
                    }}
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        handleSearch(searchQuery);
                      }
                    }}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  
                  {/* Suggestions de recherche */}
                  {searchSuggestions.length > 0 && searchQuery.length >= 2 && (
                    <div className="absolute top-full left-0 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
                      {searchSuggestions.map((suggestion, index) => (
                        <button
                          key={index}
                          onClick={() => {
                            setSearchQuery(suggestion);
                            handleSearch(suggestion);
                            setSearchSuggestions([]);
                          }}
                          className="w-full text-left px-4 py-2 hover:bg-gray-100 first:rounded-t-lg last:rounded-b-lg"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => handleSearch(searchQuery)}
                  disabled={searchLoading}
                  className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold transition-colors disabled:opacity-50"
                >
                  {searchLoading ? '⏳ Recherche...' : '🔍 Rechercher'}
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

        {/* Analyse de Sentiment et Prédiction des Réactions */}
        {activeTab === 'sentiment' && (
          <div className="animate-slide-in">
            <div className="section-header">
              <h2 className="section-title">🧠 Analyse de Sentiment & Anticipation Réactions</h2>
              <p className="section-subtitle">Analyse GPT contextuelle pour la Guadeloupe</p>
            </div>

            {/* Interface d'analyse */}
            <div className="glass-card animate-slide-in" style={{ padding: '2rem', marginBottom: '2rem' }}>
              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ 
                  display: 'block', 
                  marginBottom: '0.5rem', 
                  color: '#e2e8f0', 
                  fontWeight: '600' 
                }}>
                  Texte à analyser :
                </label>
                <textarea
                  value={sentimentText}
                  onChange={(e) => setSentimentText(e.target.value)}
                  placeholder="Entrez un texte d'actualité, une déclaration politique, ou un événement local..."
                  rows="4"
                  style={{
                    width: '100%',
                    padding: '1rem',
                    borderRadius: '12px',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    background: 'rgba(15, 23, 42, 0.8)',
                    color: '#e2e8f0',
                    fontSize: '1rem',
                    resize: 'vertical'
                  }}
                />
              </div>

              {/* Exemples rapides */}
              <div style={{ marginBottom: '1.5rem' }}>
                <p style={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '0.875rem' }}>
                  💡 Exemples Guadeloupe :
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  {[
                    "Guy Losbar annonce de nouveaux investissements pour le développement durable",
                    "Le Conseil Départemental vote le budget pour soutenir les familles en difficulté",
                    "Grave accident de la route en Guadeloupe, plusieurs blessés dans un état critique",
                    "Excellent festival de musique créole à Pointe-à-Pitre",
                    "CD971 lance une politique sociale ambitieuse pour les jeunes"
                  ].map((example, i) => (
                    <button
                      key={i}
                      onClick={() => useSentimentExample(example)}
                      style={{
                        padding: '0.5rem 1rem',
                        background: 'rgba(59, 130, 246, 0.1)',
                        border: '1px solid rgba(59, 130, 246, 0.3)',
                        borderRadius: '6px',
                        color: '#93c5fd',
                        fontSize: '0.75rem',
                        cursor: 'pointer',
                        transition: 'all 0.2s'
                      }}
                      onMouseOver={(e) => {
                        e.target.style.background = 'rgba(59, 130, 246, 0.2)';
                      }}
                      onMouseOut={(e) => {
                        e.target.style.background = 'rgba(59, 130, 246, 0.1)';
                      }}
                    >
                      {example.length > 50 ? example.substring(0, 50) + '...' : example}
                    </button>
                  ))}
                </div>
              </div>

              {/* Boutons d'action */}
              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                <button
                  onClick={() => analyzeSentiment(false)}
                  disabled={sentimentLoading || !sentimentText.trim()}
                  className="btn-primary"
                  style={{ 
                    opacity: sentimentLoading || !sentimentText.trim() ? 0.5 : 1,
                    cursor: sentimentLoading || !sentimentText.trim() ? 'not-allowed' : 'pointer'
                  }}
                >
                  {sentimentLoading ? '⏳ Analyse...' : '📊 Analyse Synchrone (3-8s)'}
                </button>
                
                <button
                  onClick={() => analyzeSentiment(true)}
                  disabled={sentimentLoading || !sentimentText.trim()}
                  className="btn-secondary"
                  style={{ 
                    opacity: sentimentLoading || !sentimentText.trim() ? 0.5 : 1,
                    cursor: sentimentLoading || !sentimentText.trim() ? 'not-allowed' : 'pointer'
                  }}
                >
                  {sentimentLoading ? '⏳ Traitement...' : '⚡ Analyse Asynchrone (instantané si cache)'}
                </button>

                <button
                  onClick={predictReaction}
                  disabled={predictionLoading || !sentimentText.trim()}
                  className="btn-accent"
                  style={{ 
                    opacity: predictionLoading || !sentimentText.trim() ? 0.5 : 1,
                    cursor: predictionLoading || !sentimentText.trim() ? 'not-allowed' : 'pointer'
                  }}
                >
                  {predictionLoading ? '⏳ Prédiction...' : '🔮 Prédire la Réaction Population'}
                </button>
              </div>
            </div>

            {/* Résultats de l'analyse de sentiment */}
            {sentimentResult && (
              <div className="glass-card animate-slide-in" style={{ padding: '2rem', marginBottom: '2rem' }}>
                <h3 className="section-title" style={{ marginBottom: '1.5rem' }}>
                  📊 Résultats de l'Analyse de Sentiment
                </h3>

                {sentimentResult.mode === 'async' && sentimentResult.status === 'processing' ? (
                  <div style={{ textAlign: 'center', padding: '2rem' }}>
                    <div className="animate-pulse" style={{
                      width: '40px',
                      height: '40px',
                      background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
                      borderRadius: '50%',
                      margin: '0 auto 1rem'
                    }}></div>
                    <p style={{ color: '#e2e8f0' }}>⏳ {sentimentResult.message}</p>
                    <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                      Hash: {sentimentResult.hash}
                    </p>
                  </div>
                ) : sentimentResult.analysis ? (
                  <div>
                    {/* Sentiment principal */}
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '1rem', 
                      marginBottom: '2rem',
                      padding: '1.5rem',
                      background: 'rgba(15, 23, 42, 0.6)',
                      borderRadius: '12px'
                    }}>
                      <div style={{
                        fontSize: '3rem',
                        background: sentimentResult.analysis.basic_sentiment.polarity === 'positive' ? 'linear-gradient(135deg, #10b981, #34d399)' : 
                                   sentimentResult.analysis.basic_sentiment.polarity === 'negative' ? 'linear-gradient(135deg, #ef4444, #f87171)' : 
                                   'linear-gradient(135deg, #6b7280, #9ca3af)',
                        borderRadius: '50%',
                        width: '80px',
                        height: '80px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}>
                        {sentimentResult.analysis.basic_sentiment.polarity === 'positive' ? '😊' : 
                         sentimentResult.analysis.basic_sentiment.polarity === 'negative' ? '😞' : '😐'}
                      </div>
                      <div>
                        <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#e2e8f0', marginBottom: '0.5rem' }}>
                          Sentiment: {sentimentResult.analysis.basic_sentiment.polarity} 
                          ({sentimentResult.analysis.basic_sentiment.score > 0 ? '+' : ''}{sentimentResult.analysis.basic_sentiment.score})
                        </div>
                        <div style={{ color: '#94a3b8' }}>
                          Intensité: {sentimentResult.analysis.basic_sentiment.intensity} • 
                          Confiance: {Math.round(sentimentResult.analysis.basic_sentiment.confidence * 100)}% •
                          Urgence: {sentimentResult.analysis.contextual_analysis.urgency_level}
                        </div>
                      </div>
                    </div>

                    {/* Contexte Guadeloupe */}
                    {sentimentResult.analysis.contextual_analysis.guadeloupe_relevance && (
                      <div style={{ marginBottom: '2rem' }}>
                        <h4 style={{ color: '#fbbf24', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          🏝️ Contexte Guadeloupe
                        </h4>
                        <p style={{ 
                          color: '#e2e8f0', 
                          lineHeight: '1.6',
                          padding: '1rem',
                          background: 'rgba(251, 191, 36, 0.1)',
                          borderRadius: '8px',
                          borderLeft: '4px solid #fbbf24'
                        }}>
                          {sentimentResult.analysis.contextual_analysis.guadeloupe_relevance}
                        </p>
                        {sentimentResult.analysis.contextual_analysis.local_impact && (
                          <p style={{ 
                            color: '#94a3b8', 
                            fontSize: '0.875rem',
                            marginTop: '0.5rem',
                            fontStyle: 'italic'
                          }}>
                            <strong>Impact local:</strong> {sentimentResult.analysis.contextual_analysis.local_impact}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Parties prenantes */}
                    {(sentimentResult.analysis.stakeholders.personalities.length > 0 || sentimentResult.analysis.stakeholders.institutions.length > 0) && (
                      <div style={{ marginBottom: '2rem' }}>
                        <h4 style={{ color: '#8b5cf6', marginBottom: '1rem' }}>👥 Parties Prenantes Identifiées</h4>
                        <div style={{ display: 'flex', gap: '2rem' }}>
                          {sentimentResult.analysis.stakeholders.personalities.length > 0 && (
                            <div>
                              <p style={{ color: '#e2e8f0', marginBottom: '0.5rem', fontSize: '0.875rem' }}>Personnalités:</p>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                {sentimentResult.analysis.stakeholders.personalities.map((person, i) => (
                                  <span key={i} style={{
                                    padding: '0.25rem 0.75rem',
                                    background: 'rgba(139, 92, 246, 0.2)',
                                    border: '1px solid rgba(139, 92, 246, 0.3)',
                                    borderRadius: '12px',
                                    color: '#c4b5fd',
                                    fontSize: '0.875rem'
                                  }}>
                                    {person}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          {sentimentResult.analysis.stakeholders.institutions.length > 0 && (
                            <div>
                              <p style={{ color: '#e2e8f0', marginBottom: '0.5rem', fontSize: '0.875rem' }}>Institutions:</p>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                {sentimentResult.analysis.stakeholders.institutions.map((institution, i) => (
                                  <span key={i} style={{
                                    padding: '0.25rem 0.75rem',
                                    background: 'rgba(59, 130, 246, 0.2)',
                                    border: '1px solid rgba(59, 130, 246, 0.3)',
                                    borderRadius: '12px',
                                    color: '#93c5fd',
                                    fontSize: '0.875rem'
                                  }}>
                                    {institution}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Thèmes et émotions */}
                    <div style={{ marginBottom: '2rem' }}>
                      <h4 style={{ color: '#10b981', marginBottom: '1rem' }}>📋 Analyse Thématique</h4>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                        <div>
                          <p style={{ color: '#e2e8f0', marginBottom: '0.5rem', fontSize: '0.875rem' }}>Thèmes:</p>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                            {sentimentResult.analysis.thematic_breakdown.themes.map((theme, i) => (
                              <span key={i} style={{
                                padding: '0.25rem 0.5rem',
                                background: 'rgba(16, 185, 129, 0.2)',
                                borderRadius: '6px',
                                color: '#6ee7b7',
                                fontSize: '0.75rem'
                              }}>
                                {theme}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <p style={{ color: '#e2e8f0', marginBottom: '0.5rem', fontSize: '0.875rem' }}>Émotions:</p>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                            {sentimentResult.analysis.thematic_breakdown.emotions.map((emotion, i) => (
                              <span key={i} style={{
                                padding: '0.25rem 0.5rem',
                                background: 'rgba(245, 158, 11, 0.2)',
                                borderRadius: '6px',
                                color: '#fbbf24',
                                fontSize: '0.75rem'
                              }}>
                                {emotion}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Recommandations */}
                    {sentimentResult.analysis.recommendations.suggested_actions.length > 0 && (
                      <div style={{ marginBottom: '2rem' }}>
                        <h4 style={{ color: '#06b6d4', marginBottom: '1rem' }}>💡 Recommandations</h4>
                        <ul style={{ listStyle: 'none', padding: 0 }}>
                          {sentimentResult.analysis.recommendations.suggested_actions.map((action, i) => (
                            <li key={i} style={{
                              padding: '0.75rem',
                              background: 'rgba(6, 182, 212, 0.1)',
                              borderRadius: '8px',
                              borderLeft: '4px solid #06b6d4',
                              color: '#e2e8f0',
                              marginBottom: '0.5rem'
                            }}>
                              • {action}
                            </li>
                          ))}
                        </ul>
                        {sentimentResult.analysis.recommendations.follow_up_needed && (
                          <p style={{ 
                            color: '#fbbf24', 
                            fontSize: '0.875rem',
                            marginTop: '1rem',
                            fontWeight: '600'
                          }}>
                            ⚠️ Suivi recommandé
                          </p>
                        )}
                      </div>
                    )}

                    {/* Alertes */}
                    {sentimentResult.analysis.recommendations.alerts.length > 0 && (
                      <div style={{
                        padding: '1rem',
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        borderRadius: '8px',
                        marginBottom: '2rem'
                      }}>
                        <h4 style={{ color: '#f87171', marginBottom: '0.5rem' }}>⚠️ Alertes</h4>
                        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                          {sentimentResult.analysis.recommendations.alerts.map((alert, i) => (
                            <li key={i} style={{ color: '#fca5a5', marginBottom: '0.25rem' }}>
                              • {alert}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Métadonnées */}
                    <div style={{ 
                      padding: '1rem',
                      background: 'rgba(75, 85, 99, 0.1)',
                      borderRadius: '8px',
                      fontSize: '0.875rem',
                      color: '#9ca3af'
                    }}>
                      <strong>Métadonnées:</strong> 
                      Méthode: {sentimentResult.metadata?.method || 'N/A'} | 
                      Temps: {sentimentResult.processing_time || sentimentResult.metadata?.processing_time || 'N/A'} | 
                      Mots: {sentimentResult.metadata?.word_count || 'N/A'} | 
                      {sentimentResult.metadata?.analyzed_at && `Analysé: ${new Date(sentimentResult.metadata.analyzed_at).toLocaleString('fr-FR')}`}
                      {sentimentResult.cached && ' | 📋 Résultat en cache'}
                    </div>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: '2rem', color: '#94a3b8' }}>
                    <p>Format de réponse inattendu</p>
                  </div>
                )}
              </div>
            )}

            {/* Prédiction des réactions */}
            {reactionPrediction && (
              <div className="glass-card animate-slide-in" style={{ padding: '2rem' }}>
                <h3 className="section-title" style={{ marginBottom: '1.5rem' }}>
                  🔮 Anticipation de la Réaction de la Population
                </h3>

                {/* Réaction globale */}
                <div style={{
                  textAlign: 'center',
                  padding: '2rem',
                  background: 'rgba(15, 23, 42, 0.6)',
                  borderRadius: '12px',
                  marginBottom: '2rem'
                }}>
                  <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>
                    {reactionPrediction.population_reaction.overall_reaction === 'très positive' ? '🎉' :
                     reactionPrediction.population_reaction.overall_reaction === 'positive' ? '😊' :
                     reactionPrediction.population_reaction.overall_reaction === 'neutre' ? '😐' :
                     reactionPrediction.population_reaction.overall_reaction === 'négative' ? '😞' : '😡'}
                  </div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#e2e8f0', marginBottom: '0.5rem' }}>
                    Réaction Globale: {reactionPrediction.population_reaction.overall_reaction}
                  </div>
                  <div style={{ color: '#94a3b8' }}>
                    Score: {reactionPrediction.population_reaction.overall_score} | 
                    Polarisation: {reactionPrediction.population_reaction.polarization_risk} | 
                    Confiance: {Math.round(reactionPrediction.confidence * 100)}%
                  </div>
                </div>

                {/* Réactions par segment */}
                <div style={{ marginBottom: '2rem' }}>
                  <h4 style={{ color: '#8b5cf6', marginBottom: '1rem' }}>👥 Réactions par Segment de Population</h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                    {Object.entries(reactionPrediction.population_reaction.by_demographic).map(([segment, data]) => (
                      <div key={segment} style={{
                        padding: '1rem',
                        background: 'rgba(75, 85, 99, 0.1)',
                        borderRadius: '8px',
                        border: '1px solid rgba(139, 92, 246, 0.2)'
                      }}>
                        <div style={{ fontWeight: 'bold', color: '#e2e8f0', marginBottom: '0.5rem' }}>
                          {segment.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </div>
                        <div style={{ color: '#c4b5fd', marginBottom: '0.5rem' }}>
                          {data.reaction_label} ({data.reaction_score})
                        </div>
                        <div style={{ fontSize: '0.875rem', color: '#94a3b8' }}>
                          Engagement: {data.engagement_likelihood}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '0.5rem' }}>
                          Préoccupations: {data.key_concerns.join(', ')}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Données sources */}
                <div style={{ marginBottom: '2rem' }}>
                  <h4 style={{ color: '#10b981', marginBottom: '1rem' }}>📊 Sources de Données Utilisées</h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                    <div style={{
                      padding: '1rem',
                      background: 'rgba(16, 185, 129, 0.1)',
                      borderRadius: '8px'
                    }}>
                      <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#6ee7b7' }}>
                        {reactionPrediction.data_sources.similar_articles}
                      </div>
                      <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>Articles similaires</div>
                    </div>
                    <div style={{
                      padding: '1rem',
                      background: 'rgba(59, 130, 246, 0.1)',
                      borderRadius: '8px'
                    }}>
                      <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#93c5fd' }}>
                        {reactionPrediction.data_sources.similar_social_posts}
                      </div>
                      <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>Posts réseaux sociaux</div>
                    </div>
                  </div>
                </div>

                {/* Recommandations stratégiques */}
                {reactionPrediction.strategic_recommendations.length > 0 && (
                  <div>
                    <h4 style={{ color: '#f59e0b', marginBottom: '1rem' }}>🎯 Recommandations Stratégiques</h4>
                    <div style={{ display: 'grid', gap: '0.5rem' }}>
                      {reactionPrediction.strategic_recommendations.map((recommendation, i) => (
                        <div key={i} style={{
                          padding: '1rem',
                          background: 'rgba(245, 158, 11, 0.1)',
                          borderRadius: '8px',
                          borderLeft: '4px solid #f59e0b',
                          color: '#e2e8f0'
                        }}>
                          {recommendation}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

      </main>
    </div>
  );
}

export default App;