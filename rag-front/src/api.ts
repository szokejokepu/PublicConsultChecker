export async function fetchJSON<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let errorMsg = `${r.status} ${r.statusText}`;
    try {
      const errJson = await r.json();
      if (errJson.detail) errorMsg = errJson.detail;
    } catch {
      // ignore JSON parse error for error responses without JSON
    }
    throw new Error(errorMsg);
  }
  if (r.status === 204) return null as any;
  return r.json();
}

export interface Analysis {
  keyword_matched: boolean;
  matched_keywords: string[];
  is_public_consultation: boolean | null;
  classifier_score: number | null;
  extracted_date: string | null;
  extracted_time: string | null;
  extracted_place: string | null;
  extracted_subject: string | null;
  processed_at: string;
  notified_at: string | null;
}

export interface Article {
  id: number;
  url: string;
  title: string | null;
  author: string | null;
  date: string | null;
  content: string | null;
  source_url: string | null;
  scraped_at: string;
  starred: boolean;
  analysis: Analysis | null;
}

export interface ArticleListOut {
  articles: Article[];
  total: number;
}

export interface ArticleFilters {
  processed: 'any' | 'yes' | 'no';
  consultation: 'any' | 'yes' | 'no' | 'unclassified';
  min_score: string;
  starred: 'any' | 'yes' | 'no';
}

export interface StatsOut {
  total_articles: number;
  unique_sources: number;
  newest_scraped_at: string | null;
}

export interface ScrapeRequest {
  url: string;
  selector?: string;
  max_pages?: number;
  workers: number;
}

export interface JobOut {
  job_id: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  summary: any;
  error: string | null;
}
