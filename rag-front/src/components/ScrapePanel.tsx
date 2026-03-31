import { useState, useEffect } from 'react';
import type { FormEvent } from 'react';
import { Network, Loader2, Play, Cpu } from 'lucide-react';
import './ScrapePanel.css';
import { fetchJSON } from '../api';
import type { ScrapeRequest, JobOut } from '../api';

export default function ScrapePanel({ onJobDone }: { onJobDone: () => void }) {
  const [url, setUrl] = useState('');
  const [selector, setSelector] = useState('');
  const [maxPages, setMaxPages] = useState('');
  const [workers, setWorkers] = useState('8');
  
  const [submitting, setSubmitting] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobOut | null>(null);

  const [processing, setProcessing] = useState(false);
  const [activeProcessJobId, setActiveProcessJobId] = useState<string | null>(null);
  const [processJobStatus, setProcessJobStatus] = useState<JobOut | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    
    try {
      const payload: ScrapeRequest = {
        url,
        selector: selector || undefined,
        workers: parseInt(workers) || 8
      };
      if (maxPages) {
        payload.max_pages = parseInt(maxPages);
      }
      
      const job = await fetchJSON<JobOut>('/api/scrape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      setActiveJobId(job.job_id);
      setJobStatus(job);
    } catch (err: any) {
      console.error(err);
      alert('Failed to start scrape: ' + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => {
    if (!activeJobId) return;

    const interval = setInterval(async () => {
      try {
        const job = await fetchJSON<JobOut>(`/api/scrape/${activeJobId}`);
        setJobStatus(job);

        if (job.status === 'done' || job.status === 'failed') {
          clearInterval(interval);
          setActiveJobId(null);
          if (job.status === 'done') {
            onJobDone();
          }
        }
      } catch (err) {
        console.error("Failed to fetch job status", err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeJobId, onJobDone]);

  const handleProcess = async () => {
    setProcessing(true);
    try {
      const job = await fetchJSON<JobOut>('/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ batch_size: 32 }),
      });
      setActiveProcessJobId(job.job_id);
      setProcessJobStatus(job);
    } catch (err: any) {
      console.error(err);
      alert('Failed to start processing: ' + err.message);
    } finally {
      setProcessing(false);
    }
  };

  useEffect(() => {
    if (!activeProcessJobId) return;

    const interval = setInterval(async () => {
      try {
        const job = await fetchJSON<JobOut>(`/api/process/${activeProcessJobId}`);
        setProcessJobStatus(job);

        if (job.status === 'done' || job.status === 'failed') {
          clearInterval(interval);
          setActiveProcessJobId(null);
        }
      } catch (err) {
        console.error("Failed to fetch process job status", err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeProcessJobId]);

  const getBadgeClass = (status: string) => {
    switch(status) {
      case 'pending': return 'bg-warning';
      case 'running': return 'bg-primary';
      case 'done': return 'bg-success';
      case 'failed': return 'bg-danger';
      default: return 'bg-warning';
    }
  };

  return (
    <div className="scrape-panel">
      
      <div className="scrape-form-card">
        <div className="scrape-header">
          <h2 className="scrape-title"><Network size={20} className="app-brand-icon" /> Start a New Scrape</h2>
          <p className="scrape-desc">Target an article listing page and we will crawl through its pagination to index the content into our RAG pipeline.</p>
        </div>
        
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Seed URL <span style={{color: 'var(--danger)'}}>*</span></label>
            <input 
              className="input" 
              type="url" 
              required 
              placeholder="https://example.com/blog..." 
              value={url}
              onChange={e => setUrl(e.target.value)}
              disabled={!!activeJobId || submitting}
            />
          </div>
          
          <div className="form-group">
            <label className="form-label">Article Link Selector</label>
            <input 
              className="input" 
              type="text" 
              placeholder=".comunicate_presa_right h2 a" 
              value={selector}
              onChange={e => setSelector(e.target.value)}
              disabled={!!activeJobId || submitting}
            />
          </div>
          
          <div className="form-grid">
            <div className="form-group">
              <label className="form-label">Max Pages</label>
              <input 
                className="input" 
                type="number" 
                min="1" 
                placeholder="Unlimited" 
                value={maxPages}
                onChange={e => setMaxPages(e.target.value)}
                disabled={!!activeJobId || submitting}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Parallel Workers</label>
              <input 
                className="input" 
                type="number" 
                min="1" 
                max="32" 
                value={workers}
                onChange={e => setWorkers(e.target.value)}
                disabled={!!activeJobId || submitting}
              />
            </div>
          </div>
          
          <div className="form-actions">
            <button 
              type="submit" 
              className="btn btn-primary" 
              disabled={!!activeJobId || submitting || !url}
            >
              {submitting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} fill="currentColor" />}
              Start Scrape Job
            </button>
          </div>
        </form>
      </div>

      <div className="scrape-form-card">
        <div className="scrape-header">
          <h2 className="scrape-title"><Cpu size={20} className="app-brand-icon" /> Process All Articles</h2>
          <p className="scrape-desc">Run the NLP pipeline on every article that hasn't been analysed yet. Already-processed articles are skipped automatically.</p>
        </div>
        <div className="form-actions">
          <button
            className="btn btn-primary"
            onClick={handleProcess}
            disabled={!!activeProcessJobId || processing}
          >
            {(processing || activeProcessJobId) ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} fill="currentColor" />}
            {activeProcessJobId ? 'Processing…' : 'Process All'}
          </button>
        </div>
      </div>

      {processJobStatus && (
        <div className={`job-status-card animate-fade-in ${processJobStatus.status}`}>
          <div className="job-header">
            <div className="job-state-container">
              <span className={`job-badge ${getBadgeClass(processJobStatus.status)}`}>
                {processJobStatus.status}
              </span>
              <span style={{ fontWeight: 500, color: '#1e293b' }}>
                {processJobStatus.status === 'pending' && 'Waiting to start...'}
                {processJobStatus.status === 'running' && 'Pipeline running...'}
                {processJobStatus.status === 'done' && 'Processing Complete!'}
                {processJobStatus.status === 'failed' && 'Processing Failed.'}
              </span>
              {(processJobStatus.status === 'running' || processJobStatus.status === 'pending') && (
                <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent-primary)' }} />
              )}
            </div>
            <span className="job-id">job_{processJobStatus.job_id.slice(0, 8)}...</span>
          </div>

          {processJobStatus.summary && Object.keys(processJobStatus.summary).length > 0 && (
            <div className="job-summary">
              <strong>Processed:</strong> {processJobStatus.summary.processed} &bull;{' '}
              <strong>Keyword matched:</strong> {processJobStatus.summary.matched} &bull;{' '}
              <strong>Consultations found:</strong> {processJobStatus.summary.classified_positive}
            </div>
          )}

          {processJobStatus.error && (
            <div style={{ color: 'var(--danger)', fontSize: '0.9rem', marginTop: '0.5rem' }}>
              <strong>Error:</strong> {processJobStatus.error}
            </div>
          )}
        </div>
      )}

      {jobStatus && (
        <div className={`job-status-card animate-fade-in ${jobStatus.status}`}>
          <div className="job-header">
            <div className="job-state-container">
              <span className={`job-badge ${getBadgeClass(jobStatus.status)}`}>
                {jobStatus.status}
              </span>
              <span style={{ fontWeight: 500, color: '#1e293b' }}>
                {jobStatus.status === 'pending' && 'Waiting to start...'}
                {jobStatus.status === 'running' && 'Crawling in progress...'}
                {jobStatus.status === 'done' && 'Scrape Completed!'}
                {jobStatus.status === 'failed' && 'Scrape Failed.'}
              </span>
              {(jobStatus.status === 'running' || jobStatus.status === 'pending') && (
                <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent-primary)' }} />
              )}
            </div>
            <span className="job-id">job_{jobStatus.job_id.slice(0, 8)}...</span>
          </div>
          
          {jobStatus.summary && Object.keys(jobStatus.summary).length > 0 && (
            <div className="job-summary">
              <strong>Saved:</strong> {jobStatus.summary.saved} &bull; 
              <strong> Skipped:</strong> {jobStatus.summary.skipped} &bull; 
              <strong> Failed:</strong> {jobStatus.summary.failed}
            </div>
          )}
          
          {jobStatus.error && (
            <div style={{ color: 'var(--danger)', fontSize: '0.9rem', marginTop: '0.5rem' }}>
              <strong>Error:</strong> {jobStatus.error}
            </div>
          )}
        </div>
      )}
      
    </div>
  );
}
