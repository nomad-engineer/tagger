// Per-device memory of what the user had open: the last library and, for each
// library, its filter expression and active dataset. The backend holds a single
// shared "current library" for every client, so this lives in the browser
// (localStorage) to let each device come back to its own view.

import type { SortBy } from './store';

const KEY = 'tagger.session.v1';

export interface LibraryView {
    filter: string;
    dataset: string | null;
}

interface Session {
    lastLibrary: string | null;
    sortBy?: SortBy;
    views: Record<string, LibraryView>;
}

function read(): Session {
    try {
        const raw = localStorage.getItem(KEY);
        if (raw) {
            const s = JSON.parse(raw);
            if (s && typeof s === 'object') {
                return { lastLibrary: s.lastLibrary ?? null, sortBy: s.sortBy, views: s.views ?? {} };
            }
        }
    } catch { /* storage unavailable or corrupt: start fresh */ }
    return { lastLibrary: null, views: {} };
}

function write(s: Session) {
    try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore */ }
}

export function getLastLibrary(): string | null {
    return read().lastLibrary;
}

export function setLastLibrary(path: string | null) {
    const s = read();
    s.lastLibrary = path;
    write(s);
}

export function getLibraryView(path: string): LibraryView {
    return read().views[path] ?? { filter: '', dataset: null };
}

export function rememberLibraryView(path: string | null | undefined, patch: Partial<LibraryView>) {
    if (!path) return;
    const s = read();
    s.views[path] = { ...(s.views[path] ?? { filter: '', dataset: null }), ...patch };
    write(s);
}

export function forgetLibrary(path: string) {
    const s = read();
    delete s.views[path];
    if (s.lastLibrary === path) s.lastLibrary = null;
    write(s);
}

export function getSortBy(): SortBy | undefined {
    return read().sortBy;
}

export function rememberSortBy(sortBy: SortBy) {
    const s = read();
    s.sortBy = sortBy;
    write(s);
}
