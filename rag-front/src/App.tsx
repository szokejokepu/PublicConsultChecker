import { useEffect, useState } from 'react';
import { Layout, FileText, Database, Clock } from 'lucide-react';
import './App.css';
import { fetchJSON } from './api';
import type { StatsOut } from './api';
import Sidebar from './components/Sidebar';
import ArticleDetail from './components/ArticleDetail';
import ScrapePanel from './components/ScrapePanel';

export default function App() {
  const [stats, setStats] = useState<StatsOut | null>(null);
  const [activeTab, setActiveTab] = useState<'detail' | 'scrape'>('detail');
  const [selectedArticleId, setSelectedArticleId] = useState<number | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const loadStats = async () => {
    try {
      const s = await fetchJSON<StatsOut>('/api/stats');
      setStats(s);
    } catch (e) {
      console.error("Failed to load stats", e);
    }
  };

  useEffect(() => {
    loadStats();
  }, [refreshTrigger]);

  const triggerRefresh = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  const handleSelectArticle = (id: number) => {
    setSelectedArticleId(id);
    setActiveTab('detail');
  };

  return (
    <div className="app-container">
      {/* Premium Dark Header */}
      <header className="app-header">
        <div className="app-brand">
          <Layout className="app-brand-icon" size={24} />
          <span>Nucleus Scraper</span>
        </div>
        <div className="app-stats">
          <div className="stat-item">
            <FileText size={16} />
            <span>Articles: <span className="stat-value">{stats?.total_articles ?? '—'}</span></span>
          </div>
          <div className="stat-item">
            <Database size={16} />
            <span>Sources: <span className="stat-value">{stats?.unique_sources ?? '—'}</span></span>
          </div>
          <div className="stat-item">
            <Clock size={16} />
            <span>Last scraped: <span className="stat-value">
              {stats?.newest_scraped_at ? stats.newest_scraped_at.slice(0, 16).replace('T', ' ') : 'Never'}
            </span></span>
          </div>
        </div>
      </header>

      {/* Main Layout Grid */}
      <div className="app-layout">
        <main className="main-content">
          <nav className="main-nav">
            <div 
              className={`nav-item ${activeTab === 'detail' ? 'active' : ''}`}
              onClick={() => setActiveTab('detail')}
            >
              Article Reading
            </div>
            <div 
              className={`nav-item ${activeTab === 'scrape' ? 'active' : ''}`}
              onClick={() => setActiveTab('scrape')}
            >
              Scraping Tasks
            </div>
          </nav>

          <div className="content-panel">
            {activeTab === 'detail' && (
              <div className="article-layout">
                <Sidebar 
                  selectedId={selectedArticleId} 
                  onSelect={handleSelectArticle} 
                  refreshTrigger={refreshTrigger}
                />
                <div className="scrollable-content">
                  <ArticleDetail 
                    articleId={selectedArticleId} 
                    onDeleted={() => {
                      setSelectedArticleId(null);
                      triggerRefresh();
                    }}
                  />
                </div>
              </div>
            )}
            {activeTab === 'scrape' && (
              <div className="scrollable-content">
                <ScrapePanel onJobDone={triggerRefresh} />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
