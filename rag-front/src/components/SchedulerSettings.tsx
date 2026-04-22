import { useEffect, useState } from 'react';
import { Clock, RefreshCw, Filter, Layers, RotateCcw } from 'lucide-react';
import { fetchJSON } from '../api';
import type { SchedulerSettings as SchedulerSettingsType } from '../api';
import './SchedulerSettings.css';

type IntervalUnit = 'minutes' | 'hours' | 'days';

function toUnit(minutes: number): { value: number; unit: IntervalUnit } {
  if (minutes % (60 * 24) === 0) return { value: minutes / (60 * 24), unit: 'days' };
  if (minutes % 60 === 0) return { value: minutes / 60, unit: 'hours' };
  return { value: minutes, unit: 'minutes' };
}

function toMinutes(value: number, unit: IntervalUnit): number {
  if (unit === 'days') return value * 60 * 24;
  if (unit === 'hours') return value * 60;
  return value;
}

export default function SchedulerSettings() {
  const [settings, setSettings] = useState<SchedulerSettingsType | null>(null);
  const [intervalValue, setIntervalValue] = useState(1);
  const [intervalUnit, setIntervalUnit] = useState<IntervalUnit>('hours');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchJSON<SchedulerSettingsType>('/api/scheduler/settings')
      .then(s => {
        setSettings(s);
        const { value, unit } = toUnit(s.interval_minutes);
        setIntervalValue(value);
        setIntervalUnit(unit);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    const payload: SchedulerSettingsType = {
      ...settings,
      interval_minutes: toMinutes(intervalValue, intervalUnit),
    };
    try {
      const updated = await fetchJSON<SchedulerSettingsType>('/api/scheduler/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      setSettings(updated);
      const { value, unit } = toUnit(updated.interval_minutes);
      setIntervalValue(value);
      setIntervalUnit(unit);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="sched-loading">Loading settings…</div>;
  if (!settings) return <div className="sched-error">Failed to load settings: {error}</div>;

  return (
    <div className="sched-panel">
      <div className="sched-card">
        <div className="sched-header">
          <Clock className="sched-header-icon" size={20} />
          <div>
            <h2 className="sched-title">Scheduler Settings</h2>
            <p className="sched-desc">
              Controls when the automatic scrape → classify → notify cycle runs.
            </p>
          </div>
        </div>

        {/* Enabled toggle */}
        <div className="sched-section">
          <label className="sched-toggle-row">
            <span className="sched-field-label">Scheduler enabled</span>
            <input
              type="checkbox"
              className="sched-toggle"
              checked={settings.enabled}
              onChange={e => setSettings({ ...settings, enabled: e.target.checked })}
            />
            <span className={`sched-toggle-label ${settings.enabled ? 'on' : 'off'}`}>
              {settings.enabled ? 'On' : 'Off'}
            </span>
          </label>
          <p className="sched-field-hint">
            When disabled, no automatic scraping or notifications will run.
          </p>
        </div>

        {/* Interval */}
        <div className="sched-section">
          <div className="sched-field-label">
            <RefreshCw size={14} className="sched-field-icon" />
            Run every
          </div>
          <div className="sched-interval-row">
            <input
              type="number"
              className="sched-number-input"
              min={1}
              value={intervalValue}
              onChange={e => setIntervalValue(Math.max(1, parseInt(e.target.value) || 1))}
            />
            <select
              className="sched-select"
              value={intervalUnit}
              onChange={e => setIntervalUnit(e.target.value as IntervalUnit)}
            >
              <option value="minutes">minutes</option>
              <option value="hours">hours</option>
              <option value="days">days</option>
            </select>
            <span className="sched-interval-equiv">
              = {toMinutes(intervalValue, intervalUnit)} min
            </span>
          </div>
        </div>

        <hr className="sched-divider" />

        {/* Processing settings */}
        <div className="sched-section-title">
          <Layers size={15} />
          Processing settings
        </div>

        <div className="sched-section">
          <label className="sched-toggle-row">
            <span className="sched-field-label">
              <Filter size={14} className="sched-field-icon" />
              Keyword pre-filter
            </span>
            <input
              type="checkbox"
              className="sched-toggle"
              checked={settings.use_keyword_filter}
              onChange={e => setSettings({ ...settings, use_keyword_filter: e.target.checked })}
            />
            <span className={`sched-toggle-label ${settings.use_keyword_filter ? 'on' : 'off'}`}>
              {settings.use_keyword_filter ? 'On' : 'Off'}
            </span>
          </label>
          <p className="sched-field-hint">
            Skip the classifier for articles that don't match any keyword. Faster; may miss edge cases.
          </p>
        </div>

        <div className="sched-section">
          <label className="sched-field-label" htmlFor="batch-size">Batch size</label>
          <input
            id="batch-size"
            type="number"
            className="sched-number-input"
            min={1}
            max={500}
            value={settings.batch_size}
            onChange={e => setSettings({ ...settings, batch_size: Math.max(1, parseInt(e.target.value) || 1) })}
          />
          <p className="sched-field-hint">Articles processed per scheduler run (1–500).</p>
        </div>

        <div className="sched-section">
          <label className="sched-toggle-row">
            <span className="sched-field-label">
              <RotateCcw size={14} className="sched-field-icon" />
              Reprocess all articles
            </span>
            <input
              type="checkbox"
              className="sched-toggle"
              checked={settings.reprocess_all}
              onChange={e => setSettings({ ...settings, reprocess_all: e.target.checked })}
            />
            <span className={`sched-toggle-label ${settings.reprocess_all ? 'on' : 'off'}`}>
              {settings.reprocess_all ? 'On' : 'Off'}
            </span>
          </label>
          <p className="sched-field-hint">
            Re-classify articles that have already been processed. Useful after a model update.
          </p>
        </div>

        {error && <p className="sched-error-msg">{error}</p>}

        <div className="sched-actions">
          <button
            className={`sched-save-btn ${saved ? 'saved' : ''}`}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
