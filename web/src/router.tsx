import { type MouseEvent, useEffect, useState } from "react";

import { locale, localizedPath, splitPath } from "./i18n";

/** The page's path without its language ("/ca/movilidad" -> "/movilidad"). */
function currentPath(): string {
  return splitPath(window.location.pathname).path;
}

/** The current path without its language, kept in sync with the browser's back and forward buttons. */
export function usePath(): string {
  const [path, setPath] = useState(currentPath);
  useEffect(() => {
    const onChange = () => setPath(currentPath());
    window.addEventListener("popstate", onChange);
    return () => window.removeEventListener("popstate", onChange);
  }, []);
  return path;
}

/** Opens a page (a path without language) in the language of the current one. */
export function navigate(path: string) {
  if (path === currentPath()) return;
  window.history.pushState(null, "", localizedPath(locale(), path));
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
    <a
      href={localizedPath(locale(), to)}
      className={className}
      onClick={handle}
      aria-current={currentPath() === to ? "page" : undefined}
    >
      {children}
    </a>
  );
}
