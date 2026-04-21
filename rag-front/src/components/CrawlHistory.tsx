import { useEffect, useState } from 'react';
import { fetchJSON } from '../api';
import type { CrawlSessionOut, SessionArticle } from '../api';
import './CrawlHistory.css';

interface Props {
  onSelectArticle: (id: number) => void;
}

export default function CrawlHistory({ onSelectArticle }: Props) {
  const [sessions, setSessions] = useState<CrawlSessionOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<CrawlSessionOut | null>(null);
  const [sessionArticles, setSessionArticles] = useState<SessionArticle[]>([]);
  const [articlesLoading, setArticlesLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchJSON<CrawlSessionOut[]>('/api/crawl-sessions?limit=100')
      .then(setSessions)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const openSession = async (session: CrawlSessionOut) => {
    setSelectedSession(session);
    setSessionArticles([]);
    setArticlesLoading(true);
    try {
      const articles = await fetchJSON<SessionArticle[]>(`/api/crawl-sessions/${session.id}/articles`);
      setSessionArticles(articles);
    } catch {
      setSessionArticles([]);
    } finally {
      setArticlesLoading(false);
    }
  };

  const closeModal = () => setSelectedSession(null);

  const handleArticleClick = (id: number) => {
    closeModal();
    onSelectArticle(id);
  };

  if (loading) return <div className="crawl-history-loading">Loading crawl history…</div>;
  if (error) return <div className="crawl-history-error">Error: {error}</div>;

  return (
    <div className="crawl-history">
      <h2 className="crawl-history-title">Crawl History</h2>
      {sessions.length === 0 ? (
        <p className="crawl-history-empty">No crawl sessions yet.</p>
      ) : (
        <table className="crawl-table">
          <thead>
            <tr>
              <th>Date / Time</th>
              <th>Source</th>
              <th>URL</th>
              <th>Status</th>
              <th>Saved</th>
              <th>Skipped</th>
              <th>Failed</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map(s => (
              <tr key={s.id} className="crawl-row" onClick={() => openSession(s)}>
                <td className="crawl-date">{s.triggered_at.slice(0, 16).replace('T', ' ')}</td>
                <td>
                  <span className={`crawl-source-badge ${s.trigger_source}`}>
                    {s.trigger_source === 'scheduler' ? 'Automatic' : 'Manual'}
                  </span>
                </td>
                <td className="crawl-url" title={s.config_url}>
                  {s.config_url.length > 50 ? s.config_url.slice(0, 50) + '…' : s.config_url}
                </td>
                <td>
                  <span className={`crawl-status-badge ${s.status}`}>{s.status}</span>
                </td>
                <td className="crawl-count">{s.saved ?? '—'}</td>
                <td className="crawl-count">{s.skipped ?? '—'}</td>
                <td className="crawl-count">{s.failed ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedSession && (
        <div className="crawl-modal-overlay" onClick={closeModal}>
          <div className="crawl-modal" onClick={e => e.stopPropagation()}>
            <button className="crawl-modal-close" onClick={closeModal}>✕</button>
            <h3 className="crawl-modal-title">Crawl Session #{selectedSession.id}</h3>
            <div className="crawl-modal-meta">
              <div><span className="meta-label">Triggered:</span> {selectedSession.triggered_at.slice(0, 19).replace('T', ' ')}</div>
              <div><span className="meta-label">Source:</span>
                <span className={`crawl-source-badge ${selectedSession.trigger_source}`}>
                  {selectedSession.trigger_source === 'scheduler' ? 'Automatic' : 'Manual'}
                </span>
              </div>
              <div><span className="meta-label">URL:</span> <a href={selectedSession.config_url} target="_blank" rel="noreferrer">{selectedSession.config_url}</a></div>
              <div><span className="meta-label">Status:</span>
                <span className={`crawl-status-badge ${selectedSession.status}`}>{selectedSession.status}</span>
              </div>
              {selectedSession.finished_at && (
                <div><span className="meta-label">Finished:</span> {selectedSession.finished_at.slice(0, 19).replace('T', ' ')}</div>
              )}
              {selectedSession.error && (
                <div className="crawl-modal-error"><span className="meta-label">Error:</span> {selectedSession.error}</div>
              )}
              <div className="crawl-modal-counts">
                <span>Saved: <strong>{selectedSession.saved ?? '—'}</strong></span>
                <span>Skipped: <strong>{selectedSession.skipped ?? '—'}</strong></span>
                <span>Failed: <strong>{selectedSession.failed ?? '—'}</strong></span>
              </div>
            </div>

            <h4 className="crawl-modal-articles-title">Articles saved in this session</h4>
            {articlesLoading ? (
              <p className="crawl-modal-loading">Loading articles…</p>
            ) : sessionArticles.length === 0 ? (
              <p className="crawl-modal-empty">No articles linked to this session.</p>
            ) : (
              <ul className="crawl-modal-articles">
                {sessionArticles.map(a => (
                  <li key={a.id} className="crawl-modal-article" onClick={() => handleArticleClick(a.id)}>
                    <span className="crawl-modal-article-title">{a.title || '(no title)'}</span>
                    <span className="crawl-modal-article-date">{a.scraped_at.slice(0, 10)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
