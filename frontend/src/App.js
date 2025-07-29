import React, { useState, useEffect } from 'react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardStats, setDashboardStats] = useState({});
  const [articles, setArticles] = useState([]);
  const [transcriptions, setTranscriptions] = useState([]);
  const [socialPosts, setSocialPosts] = useState([]);
  const [sentimentAnalyses, setSentimentAnalyses] = useState([]);
  const [loading, setLoading] = useState(false);

  // Charger les statistiques du dashboard
  const loadDashboardStats = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/dashboard-stats`);
      const data = await response.json();
      if (data.success) {
        setDashboardStats(data.stats);
      }
    } catch (error) {
      console.error('Erreur chargement stats:', error);
    }
  };

  // Charger les données selon l'onglet actif
  const loadTabData = async (tab) => {
    setLoading(true);
    try {
      switch (tab) {
        case 'articles':
          const articlesRes = await fetch(`${BACKEND_URL}/api/articles`);
          const articlesData = await articlesRes.json();
          if (articlesData.success) setArticles(articlesData.articles);
          break;
        case 'transcription':
          const transcriptionsRes = await fetch(`${BACKEND_URL}/api/transcriptions`);
          const transcriptionsData = await transcriptionsRes.json();
          if (transcriptionsData.success) setTranscriptions(transcriptionsData.transcriptions);
          break;
        case 'social':
          const socialRes = await fetch(`${BACKEND_URL}/api/social-posts`);
          const socialData = await socialRes.json();
          if (socialData.success) setSocialPosts(socialData.posts);
          break;
        case 'sentiment':
          const sentimentRes = await fetch(`${BACKEND_URL}/api/sentiment-analyses`);
          const sentimentData = await sentimentRes.json();
          if (sentimentData.success) setSentimentAnalyses(sentimentData.analyses);
          break;
      }
    } catch (error) {
      console.error('Erreur chargement données:', error);
    }
    setLoading(false);
  };

  useEffect(() => {
    loadDashboardStats();
    if (activeTab !== 'dashboard') {
      loadTabData(activeTab);
    }
  }, [activeTab]);

  // Fonctions d'action
  const fetchArticles = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/articles/fetch`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        setArticles(data.articles);
        loadDashboardStats();
        alert('✅ Articles récupérés avec succès !');
      }
    } catch (error) {
      alert('❌ Erreur lors de la récupération des articles');
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
        setTranscriptions([data.transcription, ...transcriptions]);
        loadDashboardStats();
        alert('✅ Transcription réussie !');
      }
    } catch (error) {
      alert('❌ Erreur lors de la transcription');
    }
    setLoading(false);
  };

  const fetchSocialPosts = async () => {
    const keywords = prompt('Entrez les mots-clés à rechercher:');
    if (!keywords) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('keywords', keywords);

    try {
      const response = await fetch(`${BACKEND_URL}/api/social-posts/fetch`, {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      if (data.success) {
        setSocialPosts(data.posts);
        loadDashboardStats();
        alert('✅ Posts récupérés avec succès !');
      }
    } catch (error) {
      alert('❌ Erreur lors de la récupération des posts');
    }
    setLoading(false);
  };

  const analyzeSentiment = async () => {
    const text = prompt('Entrez le texte à analyser:');
    if (!text) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('text', text);

    try {
      const response = await fetch(`${BACKEND_URL}/api/analyze-sentiment`, {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      if (data.success) {
        setSentimentAnalyses([data.analysis, ...sentimentAnalyses]);
        loadDashboardStats();
        alert(`✅ Sentiment analysé: ${data.analysis.sentiment_label}`);
      }
    } catch (error) {
      alert('❌ Erreur lors de l\'analyse de sentiment');
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <header className="bg-white shadow-lg border-b-4 border-indigo-500">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold text-gray-800 flex items-center">
              📺 <span className="ml-2">Veille Média</span>
            </h1>
            <div className="text-sm text-gray-600">
              Dernière mise à jour: {new Date().toLocaleString('fr-FR')}
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-indigo-600 shadow-md">
        <div className="container mx-auto px-6">
          <div className="flex space-x-1">
            {[
              { id: 'dashboard', label: '📊 Dashboard', icon: '📊' },
              { id: 'articles', label: '📰 Articles', icon: '📰' },
              { id: 'transcription', label: '🎤 Transcription', icon: '🎤' },
              { id: 'social', label: '📱 Réseaux Sociaux', icon: '📱' },
              { id: 'sentiment', label: '😊 Sentiment', icon: '😊' }
            ].map(tab => (
              <button
                key={tab.id}
                className={`px-6 py-3 font-semibold transition-all duration-200 ${
                  activeTab === tab.id
                    ? 'bg-white text-indigo-600 border-b-4 border-indigo-600'
                    : 'text-white hover:bg-indigo-500'
                }`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        {loading && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white p-6 rounded-lg shadow-xl">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
              <p className="mt-4 text-center text-gray-600">Chargement...</p>
            </div>
          </div>
        )}

        {/* Dashboard */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">📊 Vue d'ensemble</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-blue-500">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-blue-600 text-sm font-semibold uppercase tracking-wide">Articles</p>
                    <p className="text-3xl font-bold text-gray-900">{dashboardStats.total_articles || 0}</p>
                  </div>
                  <div className="text-blue-500 text-4xl">📰</div>
                </div>
              </div>

              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-green-500">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-green-600 text-sm font-semibold uppercase tracking-wide">Transcriptions</p>
                    <p className="text-3xl font-bold text-gray-900">{dashboardStats.total_transcriptions || 0}</p>
                  </div>
                  <div className="text-green-500 text-4xl">🎤</div>
                </div>
              </div>

              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-purple-500">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-purple-600 text-sm font-semibold uppercase tracking-wide">Posts Sociaux</p>
                    <p className="text-3xl font-bold text-gray-900">{dashboardStats.total_social_posts || 0}</p>
                  </div>
                  <div className="text-purple-500 text-4xl">📱</div>
                </div>
              </div>

              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-orange-500">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-orange-600 text-sm font-semibold uppercase tracking-wide">Analyses Sentiment</p>
                    <p className="text-3xl font-bold text-gray-900">{dashboardStats.total_sentiment_analyses || 0}</p>
                  </div>
                  <div className="text-orange-500 text-4xl">😊</div>
                </div>
              </div>
            </div>

            <div className="bg-white p-6 rounded-xl shadow-lg">
              <h3 className="text-xl font-bold text-gray-800 mb-4">🚀 Actions Rapides</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <button
                  onClick={fetchArticles}
                  className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-3 rounded-lg font-semibold transition-colors"
                >
                  📰 Récupérer Articles
                </button>
                <button
                  onClick={fetchSocialPosts}
                  className="bg-purple-500 hover:bg-purple-600 text-white px-4 py-3 rounded-lg font-semibold transition-colors"
                >
                  📱 Scanner Social
                </button>
                <button
                  onClick={analyzeSentiment}
                  className="bg-orange-500 hover:bg-orange-600 text-white px-4 py-3 rounded-lg font-semibold transition-colors"
                >
                  😊 Analyser Sentiment
                </button>
                <label className="bg-green-500 hover:bg-green-600 text-white px-4 py-3 rounded-lg font-semibold transition-colors cursor-pointer text-center">
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
              <h2 className="text-2xl font-bold text-gray-800">📰 Articles de Presse</h2>
              <button
                onClick={fetchArticles}
                className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
              >
                🔄 Actualiser
              </button>
            </div>

            <div className="grid gap-6">
              {articles.map(article => (
                <div key={article.id} className="bg-white p-6 rounded-xl shadow-lg hover:shadow-xl transition-shadow">
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="text-xl font-bold text-gray-800 flex-1">{article.title}</h3>
                    <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-medium ml-4">
                      {article.source}
                    </span>
                  </div>
                  <p className="text-gray-600 mb-4">{article.content}</p>
                  <div className="flex justify-between items-center text-sm text-gray-500">
                    <span>Par {article.author}</span>
                    <span>{new Date(article.date).toLocaleString('fr-FR')}</span>
                  </div>
                  {article.url && (
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block mt-3 text-blue-500 hover:text-blue-600 font-medium"
                    >
                      🔗 Voir l'article complet
                    </a>
                  )}
                </div>
              ))}
              {articles.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                  <div className="text-6xl mb-4">📰</div>
                  <p className="text-xl">Aucun article pour le moment</p>
                  <p>Cliquez sur "Actualiser" pour récupérer les derniers articles</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Transcription */}
        {activeTab === 'transcription' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-800">🎤 Transcription Audio</h2>
              <label className="bg-green-500 hover:bg-green-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors cursor-pointer">
                📤 Upload Audio
                <input type="file" accept="audio/*" onChange={uploadAudio} className="hidden" />
              </label>
            </div>

            <div className="bg-white p-6 rounded-xl shadow-lg">
              <h3 className="text-lg font-bold text-gray-800 mb-3">Formats supportés</h3>
              <div className="flex flex-wrap gap-2">
                {['MP3', 'WAV', 'M4A', 'OGG', 'FLAC'].map(format => (
                  <span key={format} className="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm">
                    {format}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid gap-6">
              {transcriptions.map(transcription => (
                <div key={transcription.id} className="bg-white p-6 rounded-xl shadow-lg">
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="text-xl font-bold text-gray-800">{transcription.filename}</h3>
                    <div className="flex gap-2">
                      <span className="bg-green-100 text-green-800 px-3 py-1 rounded-full text-sm">
                        {transcription.language || 'fr'}
                      </span>
                      <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm">
                        {transcription.duration}
                      </span>
                    </div>
                  </div>
                  <div className="bg-gray-50 p-4 rounded-lg mb-3">
                    <p className="text-gray-700 italic">"{transcription.transcription}"</p>
                  </div>
                  <div className="text-sm text-gray-500">
                    {new Date(transcription.date).toLocaleString('fr-FR')}
                  </div>
                </div>
              ))}
              {transcriptions.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                  <div className="text-6xl mb-4">🎤</div>
                  <p className="text-xl">Aucune transcription pour le moment</p>
                  <p>Uploadez un fichier audio pour commencer</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Social Media */}
        {activeTab === 'social' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-800">📱 Réseaux Sociaux</h2>
              <button
                onClick={fetchSocialPosts}
                className="bg-purple-500 hover:bg-purple-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
              >
                🔍 Rechercher
              </button>
            </div>

            <div className="grid gap-6">
              {socialPosts.map(post => (
                <div key={post.id} className="bg-white p-6 rounded-xl shadow-lg">
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="text-xl font-bold text-gray-800 flex-1">{post.title}</h3>
                    <span className="bg-purple-100 text-purple-800 px-3 py-1 rounded-full text-sm font-medium ml-4">
                      {post.platform}
                    </span>
                  </div>
                  <p className="text-gray-600 mb-4">{post.content}</p>
                  <div className="flex justify-between items-center text-sm text-gray-500">
                    <div className="flex items-center gap-4">
                      <span>Par {post.author}</span>
                      {post.upvotes && (
                        <span className="flex items-center gap-1">
                          👍 {post.upvotes}
                        </span>
                      )}
                    </div>
                    <span>{new Date(post.date).toLocaleString('fr-FR')}</span>
                  </div>
                  {post.url && (
                    <a
                      href={post.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block mt-3 text-purple-500 hover:text-purple-600 font-medium"
                    >
                      🔗 Voir le post original
                    </a>
                  )}
                </div>
              ))}
              {socialPosts.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                  <div className="text-6xl mb-4">📱</div>
                  <p className="text-xl">Aucun post pour le moment</p>
                  <p>Cliquez sur "Rechercher" pour scanner les réseaux sociaux</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Sentiment Analysis */}
        {activeTab === 'sentiment' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-800">😊 Analyse de Sentiment</h2>
              <button
                onClick={analyzeSentiment}
                className="bg-orange-500 hover:bg-orange-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
              >
                ➕ Nouvelle Analyse
              </button>
            </div>

            <div className="grid gap-6">
              {sentimentAnalyses.map(analysis => (
                <div key={analysis.id} className="bg-white p-6 rounded-xl shadow-lg">
                  <div className="flex justify-between items-start mb-4">
                    <div className="flex-1">
                      <p className="text-gray-700 mb-3">"{analysis.text}"</p>
                    </div>
                    <div className="ml-4 text-center">
                      <div className={`text-3xl mb-1 ${
                        analysis.sentiment_label === 'Positif' ? 'text-green-500' :
                        analysis.sentiment_label === 'Négatif' ? 'text-red-500' : 'text-gray-500'
                      }`}>
                        {analysis.sentiment_label === 'Positif' ? '😊' :
                         analysis.sentiment_label === 'Négatif' ? '😞' : '😐'}
                      </div>
                      <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                        analysis.sentiment_label === 'Positif' ? 'bg-green-100 text-green-800' :
                        analysis.sentiment_label === 'Négatif' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
                      }`}>
                        {analysis.sentiment_label}
                      </span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center text-sm text-gray-500">
                    <div className="flex gap-4">
                      <span>Score: {analysis.sentiment_score.toFixed(2)}</span>
                      <span>Confiance: {(analysis.confidence * 100).toFixed(1)}%</span>
                    </div>
                    <span>{new Date(analysis.date).toLocaleString('fr-FR')}</span>
                  </div>
                </div>
              ))}
              {sentimentAnalyses.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                  <div className="text-6xl mb-4">😊</div>
                  <p className="text-xl">Aucune analyse pour le moment</p>
                  <p>Cliquez sur "Nouvelle Analyse" pour analyser un texte</p>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;