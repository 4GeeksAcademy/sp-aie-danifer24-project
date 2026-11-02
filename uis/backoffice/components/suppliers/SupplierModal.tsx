"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

export function SupplierModal({ title, onClose, busy, children }: {
  title: string;
  onClose: () => void;
  busy: boolean;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  return (
    <dialog ref={dialog} className="modal" aria-labelledby="modal-title" onCancel={(event) => {
      event.preventDefault();
      if (!busy) onClose();
    }}>
      <div className="modal-heading">
        <h2 id="modal-title">{title}</h2>
        <button type="button" className="icon-button" title="Cerrar" aria-label="Cerrar" onClick={onClose} disabled={busy}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}