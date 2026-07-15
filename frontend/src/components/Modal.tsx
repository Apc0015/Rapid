import { X } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';

interface ModalProps {
  id?: string;
  open: boolean;
  title: string;
  context?: string;
  description?: string;
  size?: 'small' | 'large';
  onClose: () => void;
  children: ReactNode;
  labelledBy?: string;
}

export function Modal({ id, open, title, context, description, size = 'large', onClose, children, labelledBy }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = labelledBy ?? `dialog-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      id={id}
      ref={dialogRef}
      className={`product-dialog ${size === 'small' ? 'small-dialog' : 'meeting-dialog'}`}
      aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClose={onClose}
    >
      <div className="dialog-content">
        <div className="dialog-head">
          <div>
            {context ? <p className="auth-kicker">{context}</p> : null}
            <h2 id={titleId}>{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          <button className="icon-button icon-only" type="button" aria-label="Close dialog" title="Close" onClick={onClose}>
            <X size={15} aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
