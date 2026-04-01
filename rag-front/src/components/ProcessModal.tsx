import { useState } from 'react';
import { X, Cpu } from 'lucide-react';
import './ProcessModal.css';

export interface ProcessConfig {
  use_keyword_filter: boolean;
}

interface ProcessModalProps {
  title: string;
  onConfirm: (config: ProcessConfig) => void;
  onClose: () => void;
}

export default function ProcessModal({ title, onConfirm, onClose }: ProcessModalProps) {
  const [useKeywordFilter, setUseKeywordFilter] = useState(true);

  const handleConfirm = () => {
    onConfirm({ use_keyword_filter: useKeywordFilter });
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
        </div>

        <div className="modal-footer">
          <button className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleConfirm}>Run</button>
        </div>
      </div>
    </div>
  );
}
