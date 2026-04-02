import { useEffect, useState } from 'react';
import { Trash2, ExternalLink, PenTool, LayoutTemplate, Cpu, Loader2 } from 'lucide-react';
import './ArticleDetail.css';
import { fetchJSON } from '../api';
import type { Article, Analysis } from '../api';
import ProcessModal from './ProcessModal';
import type { ProcessConfig } from './ProcessModal';

export default function ArticleDetail({ 
  articleId, 
  onDeleted 
}: { 
  articleId: number | null, 
  onDeleted: () => void 
}) {
  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [showModal, setShowModal] = useState(false);

  const loadArticle = async (id: number) => {
    setLoading(true);
    try {
      const data = await fetchJSON<Article>(`/api/articles/${id}`);
      setArticle(data);
    } catch (e) {
      console.error("Failed to load article detail", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!articleId) {
      setArticle(null);
      return;
    }
    loadArticle(articleId);
  }, [articleId]);

  const handleProcess = async (config: ProcessConfig) => {
    if (!articleId) return;
    setProcessing(true);
    try {
      await fetchJSON(`/api/articles/${articleId}/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      await loadArticle(articleId);
    } catch (e) {
      console.error("Failed to process article", e);
      alert('Processing failed');
    } finally {
      setProcessing(false);
    }
  };

  const handleDelete = async () => {
    if (!articleId) return;
    if (!window.confirm('Are you sure you want to permanently delete this article?')) return;
    try {
      await fetchJSON(`/api/articles/${articleId}`, { method: 'DELETE' });
      onDeleted();
    } catch (e) {
      console.error("Failed to delete", e);
      alert('Delete failed');
    }
  };

  if (!articleId) {
    return (
      <div className="article-placeholder">
        <LayoutTemplate size={64} strokeWidth={1} color="#cbd5e1" />
        <p>Select an article from the sidebar to view its incredibly formatted contents.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="article-detail-container">
        <div className="article-header">
          <div className="skeleton skeleton-title"></div>
          <div className="skeleton skeleton-text" style={{width: '40%'}}></div>
        </div>
        <div className="article-body">
          <div className="skeleton skeleton-text"></div>
          <div className="skeleton skeleton-text"></div>
          <div className="skeleton skeleton-text"></div>
          <div className="skeleton skeleton-text"></div>
          <div className="skeleton skeleton-text"></div>
          <div className="skeleton skeleton-text"></div>
        </div>
      </div>
    );
  }

  if (!article) return null;

  return (
    <div className="article-detail-container">
      <header className="article-header">
        <h1 className="article-title">{article.title || 'Untitled Article'}</h1>
        
        <div className="article-meta">
          {article.author && (
             <div className="meta-icon">
               <PenTool size={16} />
               <span>By {article.author}</span>
             </div>
          )}
          {article.date && (
            <span>Published: <strong>{article.date}</strong></span>
          )}
          <span>Scraped: {new Date(article.scraped_at).toLocaleString()}</span>
          {article.url && (
            <a 
              href={article.url} 
              target="_blank" 
              rel="noopener noreferrer"
              className="meta-link"
              title={article.url}
            >
              <ExternalLink size={16} />
              Original Source
            </a>
          )}
        </div>

        <div className="article-actions">
          <button className="btn btn-outline" onClick={() => setShowModal(true)} disabled={processing}>
            {processing ? <Loader2 size={16} className="animate-spin" /> : <Cpu size={16} />}
            {processing ? 'Processing…' : article.analysis ? 'Reprocess' : 'Process'}
          </button>
          {showModal && (
            <ProcessModal
              title={article.analysis ? 'Reprocess Article' : 'Process Article'}
              onConfirm={handleProcess}
              onClose={() => setShowModal(false)}
            />
          )}
          <button className="btn btn-danger" onClick={handleDelete}>
            <Trash2 size={16} /> Delete Article
          </button>
        </div>
      </header>

      <div className="article-body">
        {article.content || <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>No extractable content found.</span>}
      </div>

      <AnalysisPanel analysis={article.analysis} />
    </div>
  );
}

function AnalysisPanel({ analysis }: { analysis: Analysis | null }) {
  if (!analysis) {
    return (
      <div className="analysis-panel analysis-panel--empty">
        <span className="analysis-badge analysis-badge--neutral">Not yet processed</span>
      </div>
    );
  }

  const consultationLabel =
    analysis.is_public_consultation === null
      ? 'Not classified'
      : analysis.is_public_consultation
      ? 'Yes'
      : 'No';
  const consultationClass =
    analysis.is_public_consultation === null
      ? 'analysis-badge--neutral'
      : analysis.is_public_consultation
      ? 'analysis-badge--positive'
      : 'analysis-badge--negative';

  return (
    <div className="analysis-panel">
      <h3 className="analysis-title">Analysis</h3>
      <div className="analysis-grid">

        <div className="analysis-row">
          <span className="analysis-label">Keyword match</span>
          <span className={`analysis-badge ${analysis.keyword_matched ? 'analysis-badge--positive' : 'analysis-badge--negative'}`}>
            {analysis.keyword_matched ? 'Matched' : 'No match'}
          </span>
          {analysis.keyword_matched && analysis.matched_keywords.length > 0 && (
            <div className="analysis-keywords">
              {analysis.matched_keywords.map(kw => (
                <span key={kw} className="analysis-keyword-tag">{kw}</span>
              ))}
            </div>
          )}
        </div>

        <div className="analysis-row">
          <span className="analysis-label">Public consultation</span>
          <span className={`analysis-badge ${consultationClass}`}>{consultationLabel}</span>
          {analysis.classifier_score !== null && (
            <span className="analysis-score">score: {analysis.classifier_score.toFixed(3)}</span>
          )}
        </div>

        {(analysis.extracted_date || analysis.extracted_time || analysis.extracted_place || analysis.extracted_subject) && (
          <div className="analysis-entities">
            <span className="analysis-label">Extracted entities</span>
            <table className="analysis-entity-table">
              <tbody>
                {analysis.extracted_date && <tr><td>Date</td><td>{analysis.extracted_date}</td></tr>}
                {analysis.extracted_time && <tr><td>Time</td><td>{analysis.extracted_time}</td></tr>}
                {analysis.extracted_place && <tr><td>Place</td><td>{analysis.extracted_place}</td></tr>}
                {analysis.extracted_subject && <tr><td>Subject</td><td>{analysis.extracted_subject}</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        <div className="analysis-row">
          <span className="analysis-label">Notification</span>
          {analysis.notified_at
            ? <span className="analysis-badge analysis-badge--positive">Sent {new Date(analysis.notified_at).toLocaleString()}</span>
            : <span className="analysis-badge analysis-badge--neutral">Not yet sent</span>
          }
        </div>

        <div className="analysis-footer">
          Processed: {new Date(analysis.processed_at).toLocaleString()}
        </div>

      </div>
    </div>
  );
}
