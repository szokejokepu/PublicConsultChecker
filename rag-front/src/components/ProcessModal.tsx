import { useState } from 'react';
import { X, Cpu } from 'lucide-react';
import './ProcessModal.css';

export interface ProcessConfig {
  use_keyword_filter: boolean;
  reprocess_all?: boolean;
}

interface ProcessModalProps {
  title: string;
  showReprocessAll?: boolean;
  onConfirm: (config: ProcessConfig) => void;
  onClose: () => void;
}

export default function ProcessModal({ title, showReprocessAll = false, onConfirm, onClose }: ProcessModalProps) {
  const [useKeywordFilter, setUseKeywordFilter] = useState(true);
  const [reprocessAll, setReprocessAll] = useState(false);

  const handleConfirm = () => {
    onConfirm({ use_keyword_filter: useKeywordFilter, reprocess_all: reprocessAll });
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <Cpu size={18} />
            {title}
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <label className="modal-option">
            <input
              type="checkbox"
              checked={useKeywordFilter}
              onChange={e => setUseKeywordFilter(e.target.checked)}
            />
            <div className="modal-option-text">
              <span className="modal-option-label">Use keyword filter</span>
              <span className="modal-option-desc">
                Only classify articles that contain public-consultation keywords.
                Uncheck to run the classifier on all articles.
              </span>
            </div>
          </label>

          {showReprocessAll && (
            <label className="modal-option">
              <input
                type="checkbox"
                checked={reprocessAll}
                onChange={e => setReprocessAll(e.target.checked)}
              />
              <div className="modal-option-text">
                <span className="modal-option-label">Reprocess already processed articles</span>
                <span className="modal-option-desc">
                  Run the pipeline on all articles, overwriting any existing analysis.
                </span>
              </div>
            </label>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleConfirm}>Run</button>
        </div>
      </div>
    </div>
  );
}
