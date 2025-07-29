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
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);

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
  const loadTabData = async (tab, date = null) => {
    setLoading(true);
    try {
      const targetDate = date || selectedDate;
      
      switch (tab) {
        case 'articles':
          let articlesUrl = `${BACKEND_URL}/api/articles`;
          if (targetDate !== new Date().toISOString().split('T')[0]) {
            articlesUrl = `${BACKEND_URL}/api/articles/${targetDate}`;
          }
          const articlesRes = await fetch(articlesUrl);
          const articlesData = await articlesRes.json();
          if (articlesData.success) setArticles(articlesData.articles);
          break;
          
        case 'transcription':
          let transcriptionsUrl = `${BACKEND_URL}/api/transcriptions`;
          if (targetDate !== new Date().toISOString().split('T')[0]) {
            transcriptionsUrl = `${BACKEND_URL}/api/transcriptions/${targetDate}`;
          }
          const transcriptionsRes = await fetch(transcriptionsUrl);
          const transcriptionsData = await transcriptionsRes.json();
          if (transcriptionsData.success) setTranscriptions(transcriptionsData.transcriptions);
          break;
          
        case 'digest':
          let digestUrl = `${BACKEND_URL}/api/digest`;
          if (targetDate !== new Date().toISOString().split('T')[0]) {
            digestUrl = `${BACKEND_URL}/api/digest/${targetDate}`;
          }
          const digestRes = await fetch(digestUrl);
          const digestData = await digestRes.json();
          if (digestData.success) setDigest(digestData.digest);
          break;
          
        case 'scheduler':
          const schedulerRes = await fetch(`${BACKEND_URL}/api/scheduler/status`);
          const schedulerData = await schedulerRes.json();
          if (schedulerData.success) setSchedulerStatus(schedulerData);
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
  }, [activeTab, selectedDate]);

  // Actions manuelles
  const scrapeArticlesNow = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/articles/scrape-now`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        alert(`✅ Scraping réussi ! ${data.result.total_articles} articles récupérés`);
        loadTabData('articles');
        loadDashboardStats();
      }
    } catch (error) {
      alert('❌ Erreur lors du scraping');
    }
    setLoading(false);
  };

  const captureRadioNow = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/transcriptions/capture-now`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        alert(`✅ Capture réussie ! ${data.result.streams_success} flux capturés`);
        loadTabData('transcription');
        loadDashboardStats();
      }
    } catch (error) {
      alert('❌ Erreur lors de la capture');
    }
    setLoading(false);
  };

  const createDigestNow = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/digest/create-now`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        alert('✅ Digest créé avec succès !');
        loadTabData('digest');
        loadDashboardStats();
      }
    } catch (error) {
      alert('❌ Erreur lors de la création du digest');
    }
    setLoading(false);
  };

  const runSchedulerJob = async (jobId) => {
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/scheduler/run-job/${jobId}`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        alert(`✅ Job ${jobId} exécuté avec succès !`);
        loadTabData('scheduler');
        loadDashboardStats();
      } else {
        alert(`❌ Erreur job ${jobId}: ${data.message}`);
      }
    } catch (error) {
      alert('❌ Erreur lors de l\'exécution du job');
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
        loadTabData('transcription');
        loadDashboardStats();
      }
    } catch (error) {
      alert('❌ Erreur lors de la transcription');
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
              🏝️ <span className="ml-2">Veille Média Guadeloupe</span>
            </h1>
            <div className="flex items-center gap-4">
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
              <div className="text-sm text-gray-600">
                Dernière mise à jour: {new Date().toLocaleString('fr-FR')}
              </div>
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
              { id: 'articles', label: '📰 Articles Guadeloupe', icon: '📰' },
              { id: 'transcription', label: '📻 Radio', icon: '📻' },
              { id: 'digest', label: '📄 Digest Quotidien', icon: '📄' },
              { id: 'scheduler', label: '⏰ Planificateur', icon: '⏰' }
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
              <p className="mt-4 text-center text-gray-600">Traitement en cours...</p>
            </div>
          </div>
        )}

        {/* Dashboard */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">📊 Vue d'ensemble - Guadeloupe</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-blue-500">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-blue-600 text-sm font-semibold uppercase tracking-wide">Articles Aujourd'hui</p>
                    <p className="text-3xl font-bold text-gray-900">{dashboardStats.today_articles || 0}</p>
                    <p className="text-xs text-gray-500">Total: {dashboardStats.total_articles || 0}</p>
                  </div>
                  <div className="text-blue-500 text-4xl">📰</div>
                </div>
              </div>

              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-green-500">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-green-600 text-sm font-semibold uppercase tracking-wide">Radio Aujourd'hui</p>
                    <p className="text-3xl font-bold text-gray-900">{dashboardStats.today_transcriptions || 0}</p>
                    <p className="text-xs text-gray-500">Total: {dashboardStats.total_transcriptions || 0}</p>
                  </div>
                  <div className="text-green-500 text-4xl">📻</div>
                </div>
              </div>

              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-purple-500">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-purple-600 text-sm font-semibold uppercase tracking-wide">Digests</p>
                    <p className="text-3xl font-bold text-gray-900">{dashboardStats.total_digests || 0}</p>
                    <p className="text-xs text-gray-500">Résumés quotidiens</p>
                  </div>
                  <div className="text-purple-500 text-4xl">📄</div>
                </div>
              </div>

              <div className="bg-white p-6 rounded-xl shadow-lg border-l-4 border-orange-500">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-orange-600 text-sm font-semibold uppercase tracking-wide">Jobs Programmés</p>
                    <p className="text-3xl font-bold text-gray-900">{dashboardStats.scheduler_jobs || 0}</p>
                    <p className="text-xs text-gray-500">Tâches automatiques</p>
                  </div>
                  <div className="text-orange-500 text-4xl">⏰</div>
                </div>
              </div>
            </div>

            <div className="bg-white p-6 rounded-xl shadow-lg">
              <h3 className="text-xl font-bold text-gray-800 mb-4">🚀 Actions Automatiques</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <button
                  onClick={scrapeArticlesNow}
                  className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-3 rounded-lg font-semibold transition-colors"
                >
                  📰 Scraper Articles
                </button>
                <button
                  onClick={captureRadioNow}
                  className="bg-green-500 hover:bg-green-600 text-white px-4 py-3 rounded-lg font-semibold transition-colors"
                >
                  📻 Capturer Radio
                </button>
                <button
                  onClick={createDigestNow}
                  className="bg-purple-500 hover:bg-purple-600 text-white px-4 py-3 rounded-lg font-semibold transition-colors"
                >
                  📄 Créer Digest
                </button>
                <label className="bg-orange-500 hover:bg-orange-600 text-white px-4 py-3 rounded-lg font-semibold transition-colors cursor-pointer text-center">
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
                className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
              >
                🔄 Scraper Maintenant
              </button>
            </div>

            <div className="bg-white p-4 rounded-lg shadow-md">
              <p className="text-sm text-gray-600">
                <strong>Sources automatiques :</strong> France-Antilles, RCI.fm, La 1ère, KaribInfo | 
                <strong> Programmé :</strong> Tous les jours à 10H00
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
              {articles.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                  <div className="text-6xl mb-4">📰</div>
                  <p className="text-xl">Aucun article pour cette date</p>
                  <p>Le scraping automatique a lieu tous les jours à 10H</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Transcriptions Radio */}
        {activeTab === 'transcription' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-800">📻 Transcriptions Radio</h2>
              <div className="flex gap-2">
                <button
                  onClick={captureRadioNow}
                  className="bg-green-500 hover:bg-green-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                >
                  📻 Capturer Maintenant
                </button>
                <label className="bg-orange-500 hover:bg-orange-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors cursor-pointer">
                  📤 Upload Audio
                  <input type="file" accept="audio/*" onChange={uploadAudio} className="hidden" />
                </label>
              </div>
            </div>

            <div className="bg-white p-4 rounded-lg shadow-md">
              <p className="text-sm text-gray-600">
                <strong>Flux automatiques :</strong> 2 radios guadeloupéennes | 
                <strong> Programmé :</strong> Tous les jours à 7H00 (7H00-7H20 et 7H00-7H30)
              </p>
            </div>

            <div className="grid gap-6">
              {transcriptions.map(transcription => (
                <div key={transcription.id} className="bg-white p-6 rounded-xl shadow-lg">
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="text-xl font-bold text-gray-800">
                      {transcription.stream_name || transcription.filename}
                    </h3>
                    <div className="flex gap-2">
                      <span className="bg-green-100 text-green-800 px-3 py-1 rounded-full text-sm">
                        {Math.round(transcription.duration_seconds || 0)}s
                      </span>
                      <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm">
                        {transcription.language || 'fr'}
                      </span>
                    </div>
                  </div>
                  <div className="bg-gray-50 p-4 rounded-lg mb-3">
                    <p className="text-gray-700 italic">"{transcription.transcription_text}"</p>
                  </div>
                  <div className="text-sm text-gray-500">
                    {transcription.captured_at ? 
                      `Capturé le ${new Date(transcription.captured_at).toLocaleString('fr-FR')}` :
                      `Uploadé le ${new Date(transcription.uploaded_at).toLocaleString('fr-FR')}`
                    }
                  </div>
                </div>
              ))}
              {transcriptions.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                  <div className="text-6xl mb-4">📻</div>
                  <p className="text-xl">Aucune transcription pour cette date</p>
                  <p>La capture automatique a lieu tous les jours à 7H</p>
                </div>
              )}
            </div>
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
                  <a
                    href={`${BACKEND_URL}/api/digest/${selectedDate}/html`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="bg-gray-500 hover:bg-gray-600 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
                  >
                    🔗 Version HTML
                  </a>
                )}
              </div>
            </div>

            <div className="bg-white p-4 rounded-lg shadow-md">
              <p className="text-sm text-gray-600">
                <strong>Résumé automatique :</strong> Articles + Transcriptions radio formatés | 
                <strong> Programmé :</strong> Tous les jours à 12H00
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
      </main>
    </div>
  );
}

export default App;