import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Search, Calendar, User, FileX2 } from 'lucide-react';
import './Sidebar.css';
import { fetchJSON } from '../api';
import type { Article, ArticleListOut } from '../api';

interface SidebarProps {
  selectedId: number | null;
  onSelect: (id: number) => void;
  refreshTrigger: number;
}

const PAGE_SIZE = 50;

export default function Sidebar({ selectedId, onSelect, refreshTrigger }: SidebarProps) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState('');
  const [currentSearch, setCurrentSearch] = useState('');

  const loadArticles = async (reset = false) => {
    const newOffset = reset ? 0 : offset;
    const params = new URLSearchParams({ 
      limit: PAGE_SIZE.toString(), 
      offset: newOffset.toString() 
    });
    if (currentSearch) {
      params.set('search', currentSearch);
    }
    
    try {
      const data = await fetchJSON<ArticleListOut>(`/api/articles?${params}`);
      setArticles(prev => reset ? data.articles : [...prev, ...data.articles]);
      setTotal(data.total);
      setOffset(newOffset + data.articles.length);
    } catch (e) {
      console.error("Failed to load articles", e);
    }
  };

  useEffect(() => {
    loadArticles(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSearch, refreshTrigger]);

  const doSearch = (e: FormEvent) => {
    e.preventDefault();
    setCurrentSearch(query.trim());
  };

  const hasMore = !currentSearch && offset < total;

  return (
    <aside className="sidebar">
      <div className="sidebar-toolbar">
        <form className="search-box" onSubmit={doSearch}>
          <input
            className="search-input"
            type="text"
            placeholder="Search articles..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <button type="submit" className="search-btn" aria-label="Search">
            <Search size={18} />
          </button>
        </form>
      </div>

      <div className="article-list">
        {articles.length === 0 && (
          <div className="empty-state animate-fade-in">
            <FileX2 size={48} strokeWidth={1} />
            <p>No articles found matching your criteria.</p>
          </div>
        )}

        {articles.map(a => (
          <div 
            key={a.id} 
            className={`article-item animate-fade-in ${a.id === selectedId ? 'active' : ''}`}
            onClick={() => onSelect(a.id)}
          >
            <div className="article-item-title" title={a.title || a.url}>
              {a.title || a.url}
            </div>
            <div className="article-item-meta">
              {a.date && (
                <div className="meta-icon">
                  <Calendar size={14} />
                  <span>{a.date}</span>
                </div>
              )}
              {a.author && (
                <div className="meta-icon">
                  <User size={14} />
                  <span>{a.author}</span>
                </div>
              )}
            </div>
          </div>
        ))}
        
        {hasMore && (
          <div className="load-more">
            <button className="btn btn-outline" onClick={() => loadArticles(false)}>
              Load more
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
