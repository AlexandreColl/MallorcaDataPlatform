import { type MouseEvent, useEffect, useState } from "react";

/** The current path, kept in sync with the browser's back and forward buttons. */
export function usePath(): string {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onChange = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onChange);
    return () => window.removeEventListener("popstate", onChange);
  }, []);
  return path;
}

export function navigate(path: string) {
  if (path === window.location.pathname) return;
  window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo({ top: 0 });
}

/** A link that changes page without reloading; a middle or ctrl click still opens a new tab. */
export function Link({ to, className, children, onClick }: {
  to: string;
  className?: string;
  children: React.ReactNode;
  onClick?: () => void;
}) {
  const handle = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(to);
    onClick?.();
  };
  return (
    <a href={to} className={className} onClick={handle} aria-current={window.location.pathname === to ? "page" : undefined}>
      {children}
    </a>
  );
}
