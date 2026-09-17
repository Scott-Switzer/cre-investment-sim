/**
 * Shared presentational primitives. Deliberately small: the screens carry the
 * specificity, these carry only the repeated chrome.
 */

import { useEffect, useId, type ReactNode } from "react";

export function Panel({
  label,
  children,
  className = "",
  "data-testid": dataTestId,
}: {
  label?: string;
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
}) {
  return (
    <div className={`card card-pad ${className}`.trim()} data-testid={dataTestId}>
      {label ? <span className="panel-label">{label}</span> : null}
      {label ? <div style={{ height: 10 }} /> : null}
      {children}
    </div>
  );
}

export function Kv({
  k,
  v,
  strong = false,
  title,
}: {
  k: string;
  v: ReactNode;
  strong?: boolean;
  title?: string;
}) {
  return (
    <div className="kv">
      <span className="k">{title ? <span className="tooltip" title={title}>{k}</span> : k}</span>
      <span className={`v ${strong ? "hero-num" : ""}`}>{v}</span>
    </div>
  );
}

export function Badge({
  tone = "neutral",
  children,
  pulse = false,
}: {
  tone?: "neutral" | "ok" | "warn" | "bad" | "navy";
  children: ReactNode;
  pulse?: boolean;
}) {
  return (
    <span className={`badge badge-${tone}`}>
      <span className={`dot ${pulse ? "pulse" : ""}`} style={{ background: "currentColor" }} />
      {children}
    </span>
  );
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  width,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}) {
  const titleId = useId();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="modal-scrim"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} style={width ? { width: width } : undefined}>
        <div className="modal-head">
          <h3 id={titleId}>{title}</h3>
          <button type="button" className="drawer-close" onClick={onClose} aria-label="Close">
            Close
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-foot">{footer}</div> : null}
      </div>
    </div>
  );
}

export function Drawer({
  title,
  subtitle,
  onClose,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const titleId = useId();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="drawer-scrim"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="drawer-head">
          <div>
            <h3 id={titleId}>{title}</h3>
            {subtitle ? <div className="sub">{subtitle}</div> : null}
          </div>
          <button type="button" className="drawer-close" onClick={onClose} aria-label="Close drawer">
            Close
          </button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer ? <div style={{ padding: "14px 22px", borderTop: "1px solid var(--slate-200)", background: "var(--white)" }}>{footer}</div> : null}
      </aside>
    </div>
  );
}

export function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="drawer-section">
      <span className="panel-label">{label}</span>
      <div style={{ height: 6 }} />
      {children}
    </div>
  );
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return <div className="error-box" role="alert">{children}</div>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="center-screen">
      <div>
        <div className="spinner" />
        <p className="mt-16" style={{ color: "var(--slate-500)", fontSize: 14, textAlign: "center" }}>
          {label}
        </p>
      </div>
    </div>
  );
}
