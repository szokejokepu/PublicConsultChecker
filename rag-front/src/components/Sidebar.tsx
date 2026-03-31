import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Search, Calendar, User, FileX2, SlidersHorizontal, X } from 'lucide-react';
import './Sidebar.css';
import { fetchJSON } from '../api';
import type { Article, ArticleFilters, ArticleListOut } from '../api';

interface SidebarProps {
  selectedId: number | null;
  onSelect: (id: number) => void;
  refreshTrigger: number;
}

const PAGE_SIZE = 50;

const DEFAULT_FILTERS: ArticleFilters = {
  processed: 'any',
  consultation: 'any',
  min_score: '',
};

function filtersActive(f: ArticleFilters) {
  return f.processed !== 'any' || f.consultation !== 'any' || f.min_score !== '';
}

export default function Sidebar({ selectedId, onSelect, refreshTrigger }: SidebarProps) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState('');
  const [currentSearch, setCurrentSearch] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<ArticleFilters>(DEFAULT_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<ArticleFilters>(DEFAULT_FILTERS);

  const loadArticles = async (reset = false) => {
    const newOffset = reset ? 0 : offset;
    const params = new URLSearchParams({
      limit: PAGE_SIZE.toString(),
      offset: newOffset.toString(),
    });
    if (currentSearch) {
      params.set('search', currentSearch);
    } else {
      if (appliedFilters.processed !== 'any') params.set('processed', appliedFilters.processed);
      if (appliedFilters.consultation !== 'any') params.set('consultation', appliedFilters.consultation);
      if (appliedFilters.min_score !== '') params.set('min_score', appliedFilters.min_score);
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
  }, [currentSearch, appliedFilters, refreshTrigger]);

  const doSearch = (e: FormEvent) => {
    e.preventDefault();
    setCurrentSearch(query.trim());
  };

  const applyFilters = () => {
    setAppliedFilters({ ...filters });
    setCurrentSearch('');
    setQuery('');
  };

  const clearFilters = () => {
    setFilters(DEFAULT_FILTERS);
    setAppliedFilters(DEFAULT_FILTERS);
  };

  const hasMore = !currentSearch && offset < total;

  return (
    <aside className="sidebar">
      <div className="sidebar-toolbar">
        <div className="toolbar-row">
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
          <button
            className={`filter-toggle-btn ${showFilters || filtersActive(appliedFilters) ? 'active' : ''}`}
            onClick={() => setShowFilters(v => !v)}
            aria-label="Toggle filters"
            title="Filters"
          >
            <SlidersHorizontal size={16} />
          </button>
        </div>

        {showFilters && (
          <div className="filter-panel">
            <div className="filter-row">
              <label className="filter-label">Processed</label>
              <select
                className="filter-select"
                value={filters.processed}
                onChange={e => setFilters(f => ({ ...f, processed: e.target.value as ArticleFilters['processed'] }))}
              >
                <option value="any">Any</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </div>

            <div className="filter-row">
              <label className="filter-label">Consultation</label>
              <select
                className="filter-select"
                value={filters.consultation}
                onChange={e => setFilters(f => ({ ...f, consultation: e.target.value as ArticleFilters['consultation'] }))}
              >
                <option value="any">Any</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
                <option value="unclassified">Unclassified</option>
              </select>
            </div>

            <div className="filter-row">
              <label className="filter-label">Min score</label>
              <input
                className="filter-input"
                type="number"
                min="0"
                max="1"
                step="0.01"
                placeholder="0.00 – 1.00"
                value={filters.min_score}
                onChange={e => setFilters(f => ({ ...f, min_score: e.target.value }))}
              />
            </div>

            <div className="filter-actions">
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={applyFilters}>
                Apply
              </button>
              {filtersActive(appliedFilters) && (
                <button className="btn btn-outline" onClick={clearFilters} title="Clear filters">
                  <X size={14} /> Clear
                </button>
              )}
            </div>
          </div>
        )}

        {filtersActive(appliedFilters) && !showFilters && (
          <div className="filter-active-hint">
            Filters active
            <button className="filter-clear-inline" onClick={clearFilters}><X size={12} /> Clear</button>
          </div>
        )}
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
