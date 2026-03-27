import { useEffect, useState } from 'react';
import { Trash2, ExternalLink, PenTool, LayoutTemplate } from 'lucide-react';
import './ArticleDetail.css';
import { fetchJSON } from '../api';
import type { Article } from '../api';

export default function ArticleDetail({ 
  articleId, 
  onDeleted 
}: { 
  articleId: number | null, 
  onDeleted: () => void 
}) {
  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!articleId) {
      setArticle(null);
      return;
    }
    const load = async () => {
      setLoading(true);
      try {
        const data = await fetchJSON<Article>(`/api/articles/${articleId}`);
        setArticle(data);
      } catch (e) {
        console.error("Failed to load article detail", e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [articleId]);

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
          <button className="btn btn-danger" onClick={handleDelete}>
            <Trash2 size={16} /> Delete Article
          </button>
        </div>
      </header>

      <div className="article-body">
        {article.content || <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>No extractable content found.</span>}
      </div>
    </div>
  );
}
