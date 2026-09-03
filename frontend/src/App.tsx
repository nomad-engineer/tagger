import { useState, useEffect, useCallback, useRef } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient, useQuery } from '@tanstack/react-query';
import { ImageGallery } from './Gallery';
import { TagEditor } from './TagEditor';
import { TaxonomyPanel } from './TaxonomyPanel';
import { FilterPanel } from './FilterPanel';
import { useTaggerStore } from './store';

declare global {
    interface Window {
        electronAPI?: {
            openLibraryDialog: () => Promise<string | null>;
            openFolderDialog: () => Promise<string | null>;
            openNewWindow: (route: string) => void;
        };
    }
}

const queryClient = new QueryClient();

// -----------------------------------------------------------------------
// Status Toast
// -----------------------------------------------------------------------
function StatusToast() {
    const { status, setStatus } = useTaggerStore();

    useEffect(() => {
        if (status) {
            const t = setTimeout(() => setStatus(null), 3000);
            return () => clearTimeout(t);
        }
    }, [status, setStatus]);

    if (!status) return null;

    const colors = {
        info: 'bg-gray-700 text-gray-100 border-gray-600',
        success: 'bg-green-900/80 text-green-100 border-green-700',
        error: 'bg-red-900/80 text-red-100 border-red-700',
    };

    return (
        <div className={`fixed bottom-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg border text-sm shadow-xl ${colors[status.type]}`}>
            {status.text}
        </div>
    );
}

// -----------------------------------------------------------------------
// Reusable Dropdown
// -----------------------------------------------------------------------
function Dropdown({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const close = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', close);
        return () => document.removeEventListener('mousedown', close);
    }, [open]);

    return (
        <div ref={ref} className="relative">
            <button
                onClick={() => setOpen(o => !o)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1
                    ${open ? 'bg-gray-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-200'}`}
            >
                {label}
                <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {open && (
                <div
                    className="absolute top-full left-0 mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-2xl py-1 min-w-[180px] z-30"
                    onClick={() => setOpen(false)}
                >
                    {children}
                </div>
            )}
        </div>
    );
}

function DropdownItem({ onClick, children, variant = 'default' }: {
    onClick: () => void;
    children: React.ReactNode;
    variant?: 'default' | 'danger';
}) {
    return (
        <button
            onClick={onClick}
            className={`w-full text-left px-3 py-1.5 text-xs transition-colors
                ${variant === 'danger' ? 'text-red-400 hover:bg-red-900/40' : 'text-gray-200 hover:bg-gray-700'}`}
        >
            {children}
        </button>
    );
}

function DropdownSeparator() {
    return <div className="border-t border-gray-700 my-1" />;
}

// -----------------------------------------------------------------------
// InputDialog
// -----------------------------------------------------------------------
function InputDialog({
    title,
    fields,
    onConfirm,
    onClose,
}: {
    title: string;
    fields: { label: string; placeholder: string; key: string; defaultValue?: string }[];
    onConfirm: (values: Record<string, string>) => void;
    onClose: () => void;
}) {
    const [values, setValues] = useState<Record<string, string>>(
        Object.fromEntries(fields.map(f => [f.key, f.defaultValue ?? '']))
    );

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onConfirm(values);
        onClose();
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={onClose}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-80 shadow-2xl" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-4">{title}</h2>
                <form onSubmit={handleSubmit} className="space-y-3">
                    {fields.map(f => (
                        <div key={f.key}>
                            <label className="text-[10px] text-gray-400 uppercase tracking-wider block mb-1">{f.label}</label>
                            <input
                                type="text"
                                value={values[f.key]}
                                onChange={e => setValues(v => ({ ...v, [f.key]: e.target.value }))}
                                placeholder={f.placeholder}
                                className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                                autoFocus={fields.indexOf(f) === 0}
                            />
                        </div>
                    ))}
                    <div className="flex gap-2 pt-1">
                        <button type="submit" className="flex-1 bg-blue-700 hover:bg-blue-600 text-white rounded py-2 text-xs font-semibold">OK</button>
                        <button type="button" onClick={onClose} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">Cancel</button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Library Picker Dialog — shows available libraries from root folder
// -----------------------------------------------------------------------
function LibraryPickerDialog({ onClose, onLoad, managed = false }: {
    onClose: () => void;
    onLoad: (path: string) => void;
    managed?: boolean;
}) {
    const [available, setAvailable] = useState<{ name: string; path: string }[]>([]);
    const [customPath, setCustomPath] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch('/api/library/available')
            .then(r => r.json())
            .then(data => { setAvailable(data.libraries || []); setLoading(false); })
            .catch(() => setLoading(false));
    }, []);

    const handlePickFolder = async () => {
        if (window.electronAPI) {
            const p = await window.electronAPI.openFolderDialog();
            if (p) setCustomPath(p);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={onClose}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 w-[420px] shadow-2xl" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-4">Open Library</h2>

                {loading ? (
                    <p className="text-xs text-gray-400 mb-4">Scanning...</p>
                ) : available.length > 0 ? (
                    <div className="mb-4 max-h-64 overflow-y-auto space-y-1">
                        {available.map(lib => (
                            <button
                                key={lib.path}
                                onClick={() => { onLoad(lib.path); onClose(); }}
                                className="w-full text-left px-3 py-2 rounded-lg bg-gray-700/50 hover:bg-gray-700 transition-colors"
                            >
                                <div className="text-xs font-medium text-white">{lib.name}</div>
                                {!managed && (
                                    <div className="text-[10px] text-gray-500 truncate mt-0.5">{lib.path}</div>
                                )}
                            </button>
                        ))}
                    </div>
                ) : (
                    <p className="text-xs text-gray-500 mb-4">No libraries found.</p>
                )}

                {/* Custom path entry — hidden in managed mode (server controls the root) */}
                {!managed && (
                    <div className="border-t border-gray-700 pt-3">
                        <p className="text-[10px] text-gray-500 mb-2 uppercase tracking-wider">Custom path</p>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={customPath}
                                onChange={e => setCustomPath(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter' && customPath.trim()) { onLoad(customPath.trim()); onClose(); } }}
                                placeholder="/path/to/library"
                                className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                            />
                            {window.electronAPI && (
                                <button onClick={handlePickFolder} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-white">Browse</button>
                            )}
                            <button
                                onClick={() => { if (customPath.trim()) { onLoad(customPath.trim()); onClose(); } }}
                                disabled={!customPath.trim()}
                                className="px-3 py-1.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 rounded text-xs text-white"
                            >Open</button>
                        </div>
                    </div>
                )}

                <button onClick={onClose} className={`${managed ? '' : 'mt-3'} w-full py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300`}>Cancel</button>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Create Library Dialog — name only, auto-saves to libraries_root
// -----------------------------------------------------------------------
function CreateLibraryDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
    const [name, setName] = useState('');
    const [loading, setLoading] = useState(false);
    const { setStatus } = useTaggerStore();

    const handleCreate = async () => {
        if (!name.trim()) return;
        setLoading(true);
        try {
            const res = await fetch('/api/library/create-new', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name.trim() })
            });
            if (res.ok) {
                setStatus(`Library "${name}" created`, 'success');
                onDone();
                onClose();
            } else {
                const err = await res.json();
                setStatus('Failed: ' + err.detail, 'error');
            }
        } catch {
            setStatus('Failed to create library', 'error');
        }
        setLoading(false);
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={onClose}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-80 shadow-2xl" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-4">New Library</h2>
                <p className="text-[11px] text-gray-400 mb-3">A new folder will be created in your libraries root directory.</p>
                <input
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleCreate()}
                    placeholder="Library name..."
                    className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 mb-4"
                    autoFocus
                />
                <div className="flex gap-2">
                    <button
                        onClick={handleCreate}
                        disabled={loading || !name.trim()}
                        className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded py-2 text-xs font-semibold"
                    >
                        {loading ? 'Creating...' : 'Create'}
                    </button>
                    <button onClick={onClose} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">Cancel</button>
                </div>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Shared: folder file-picker hook
// -----------------------------------------------------------------------
function useFolderPicker() {
    const inputRef = useRef<HTMLInputElement>(null);

    // Set webkitdirectory after mount (not a standard React prop)
    useEffect(() => {
        const el = inputRef.current;
        if (el) {
            el.setAttribute('webkitdirectory', '');
            el.setAttribute('directory', '');
        }
    }, []);

    const open = () => inputRef.current?.click();

    return { inputRef, open };
}

interface FileSelection {
    files: File[];
    folderName: string;
}

function FolderPickerButton({
    selection,
    onSelect,
    label = 'Select Folder',
}: {
    selection: FileSelection | null;
    onSelect: (sel: FileSelection) => void;
    label?: string;
}) {
    const { inputRef, open } = useFolderPicker();

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files ?? []);
        if (files.length === 0) return;
        const folderName = ((files[0] as any).webkitRelativePath as string || files[0].name).split('/')[0];
        onSelect({ files, folderName });
        // Reset so picking the same folder again fires onChange
        e.target.value = '';
    };

    return (
        <>
            <input ref={inputRef} type="file" multiple onChange={handleChange} className="hidden" />
            <button
                onClick={open}
                className="flex items-center gap-2 px-4 py-2.5 bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-lg text-xs text-gray-200 transition-colors w-full justify-center"
            >
                <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
                </svg>
                {selection ? (
                    <span><span className="text-white font-medium">{selection.folderName}/</span> — {selection.files.length} files</span>
                ) : label}
            </button>
        </>
    );
}

function ImportResultBanner({ result }: { result: { added: number; skipped: number; errors: number } }) {
    const hasErrors = result.errors > 0;
    return (
        <div className={`p-3 rounded text-xs border ${hasErrors ? 'bg-red-900/30 border-red-700 text-red-200' : 'bg-green-900/30 border-green-700 text-green-200'}`}>
            <span className="font-semibold">{result.added}</span> added &nbsp;·&nbsp;
            <span className="font-semibold">{result.skipped}</span> skipped &nbsp;·&nbsp;
            <span className="font-semibold">{result.errors}</span> errors
        </div>
    );
}

// -----------------------------------------------------------------------
// Shared batch-upload helper
// -----------------------------------------------------------------------
const UPLOAD_BATCH = 50;

async function uploadInBatches(
    files: File[],
    endpoint: string,
    onProgress: (batch: number, total: number) => void,
): Promise<{ added: number; skipped: number; errors: number }> {
    const totals = { added: 0, skipped: 0, errors: 0 };
    const batches: File[][] = [];
    for (let i = 0; i < files.length; i += UPLOAD_BATCH) {
        batches.push(files.slice(i, i + UPLOAD_BATCH));
    }

    for (let b = 0; b < batches.length; b++) {
        onProgress(b + 1, batches.length);
        const fd = new FormData();
        for (const file of batches[b]) {
            const rel = (file as any).webkitRelativePath as string || file.name;
            fd.append('files', file, rel);
        }
        const res = await fetch(endpoint, { method: 'POST', body: fd });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail ?? 'Upload failed');
        }
        const data = await res.json();
        totals.added   += data.added   ?? 0;
        totals.skipped += data.skipped ?? 0;
        totals.errors  += data.errors  ?? 0;
    }
    return totals;
}

// -----------------------------------------------------------------------
// Import progress bar (shared by both import dialogs)
// -----------------------------------------------------------------------
function ImportProgressBar({ onCancel }: { onCancel: () => void }) {
    const [status, setStatus] = useState<any>(null);

    useEffect(() => {
        let alive = true;
        let sawRunning = false;
        const poll = async () => {
            while (alive) {
                try {
                    const res = await fetch('/api/library/import-status');
                    const data = await res.json();
                    if (!alive) break;
                    setStatus(data);
                    if (data.running) {
                        sawRunning = true;
                    } else if (sawRunning) {
                        // Only stop once we've seen the backend report "running" at
                        // least once — otherwise we may be racing the request that
                        // kicks off the import thread.
                        break;
                    }
                } catch { /* ignore */ }
                await new Promise(r => setTimeout(r, 250));
            }
        };
        poll();
        return () => { alive = false; };
    }, []);

    // Finished — show final result line
    if (status && !status.running && status.total >= 0 && (status.added !== undefined)) {
        return (
            <div className="mt-3 text-[11px] text-gray-300">
                {status.cancelled && <span className="text-yellow-400 font-medium">Cancelled. </span>}
                {status.added ?? 0} added, {status.skipped ?? 0} skipped, {status.errors ?? 0} errors
            </div>
        );
    }

    // Waiting for the backend to register the import
    if (!status || !status.running) {
        return (
            <div className="mt-3">
                <div className="text-[11px] text-gray-400 mb-1">Starting import…</div>
                <div className="w-full bg-gray-700 rounded-full h-1.5 overflow-hidden">
                    <div className="bg-blue-500 h-1.5 rounded-full animate-pulse w-1/3" />
                </div>
            </div>
        );
    }

    const hasTotal = status.total > 0;
    const pct = hasTotal ? Math.round((status.processed / status.total) * 100) : 0;

    return (
        <div className="mt-3">
            <div className="flex justify-between text-[11px] text-gray-400 mb-1">
                <span>
                    {status.label}
                    {hasTotal ? `: ${status.processed} / ${status.total}` : '…'}
                </span>
                {hasTotal && <span>{pct}%</span>}
            </div>
            <div className="w-full bg-gray-700 rounded-full h-1.5 overflow-hidden">
                {hasTotal ? (
                    <div
                        className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
                        style={{ width: `${pct}%` }}
                    />
                ) : (
                    <div className="bg-blue-500 h-1.5 rounded-full animate-pulse w-1/3" />
                )}
            </div>
            <div className="flex justify-between items-center mt-1">
                <span className="text-[10px] text-gray-500">
                    {status.added} added · {status.skipped} skipped · {status.errors} errors
                </span>
                <button
                    onClick={onCancel}
                    className="text-[10px] text-red-400 hover:text-red-300"
                >
                    Cancel
                </button>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Import Dialog
// -----------------------------------------------------------------------
function ImportDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
    const [folderPath, setFolderPath] = useState('');
    const [importing, setImporting] = useState(false);
    const [result, setResult] = useState<{ added: number; skipped: number; errors: number } | null>(null);
    const { setStatus } = useTaggerStore();

    const handleBrowse = async () => {
        try {
            if (window.electronAPI) {
                const p = await window.electronAPI.openFolderDialog();
                if (p) setFolderPath(p);
            } else {
                const res = await fetch('/api/library/browse-folder');
                const data = await res.json();
                if (data.path) setFolderPath(data.path);
            }
        } catch { /* user cancelled */ }
    };

    const handleCancel = async () => {
        await fetch('/api/library/import-cancel', { method: 'POST' });
    };

    const handleImport = async () => {
        if (!folderPath.trim()) return;
        setResult(null);
        setImporting(true);
        try {
            const res = await fetch('/api/library/import-legacy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: folderPath.trim() }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail ?? 'Import failed');
            setResult(data);
            setStatus(`Imported ${data.added} added, ${data.skipped} skipped`, data.errors ? 'error' : 'success');
            onDone();
        } catch (e: any) {
            setStatus('Import failed: ' + e.message, 'error');
        }
        setImporting(false);
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={!importing ? onClose : undefined}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-[440px] shadow-2xl" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-1">Import Images</h2>
                <p className="text-[11px] text-gray-400 mb-4">
                    Select a library folder. Each image is matched to a sibling
                    <code className="text-blue-300 mx-1">.json</code> metadata file (legacy
                    <code className="text-blue-300 mx-1">{'[{category, value}]'}</code> tags are
                    converted to flat <code className="text-blue-300 ml-1">category:value</code> strings).
                </p>

                <div className="flex gap-2">
                    <input
                        value={folderPath}
                        onChange={e => setFolderPath(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && folderPath.trim() && !importing) handleImport(); }}
                        placeholder="/path/to/library..."
                        className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                        autoFocus
                        disabled={importing}
                    />
                    <button onClick={handleBrowse} disabled={importing} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 rounded text-xs text-white">Browse</button>
                </div>

                {importing && <ImportProgressBar onCancel={handleCancel} />}
                {result && !importing && <div className="mt-3"><ImportResultBanner result={result} /></div>}

                <div className="flex gap-2 mt-4">
                    <button
                        onClick={handleImport}
                        disabled={importing || !folderPath.trim()}
                        className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded py-2 text-xs font-semibold"
                    >
                        {importing ? 'Importing...' : 'Import'}
                    </button>
                    {importing ? (
                        <button onClick={handleCancel} className="px-4 py-2 bg-red-700 hover:bg-red-600 text-white rounded text-xs">Cancel</button>
                    ) : (
                        <button onClick={onClose} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">Close</button>
                    )}
                </div>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Export Dialog
// -----------------------------------------------------------------------
function ExportDialog({
    onClose,
    datasets,
    currentDataset,
    selectedCount,
    selectedHashes,
}: {
    onClose: () => void;
    datasets: Dataset[];
    currentDataset: string | null;
    selectedCount: number;
    selectedHashes: string[];
}) {
    const [outputDir, setOutputDir] = useState('');
    const [scope, setScope] = useState<'library' | 'dataset' | 'selection'>(
        selectedCount > 0 ? 'selection' : currentDataset ? 'dataset' : 'library'
    );
    const [datasetName, setDatasetName] = useState(currentDataset ?? '');
    const [metadataFormat, setMetadataFormat] = useState<'json' | 'txt'>('json');
    const [copyImages, setCopyImages] = useState(true);
    const [useSymlinks, setUseSymlinks] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [progress, setProgress] = useState<{ processed: number; exported: number; errors: number; total: number } | null>(null);
    const [done, setDone] = useState(false);
    const { setStatus } = useTaggerStore();

    const handleBrowse = async () => {
        try {
            if (window.electronAPI) {
                const p = await window.electronAPI.openFolderDialog();
                if (p) setOutputDir(p);
            } else {
                const res = await fetch('/api/library/browse-folder');
                const data = await res.json();
                if (data.path) setOutputDir(data.path);
            }
        } catch { /* user cancelled */ }
    };

    const handleExport = async () => {
        if (!outputDir.trim()) return;
        setExporting(true);
        setDone(false);
        setProgress(null);

        try {
            const body: any = {
                output_dir: outputDir.trim(),
                scope,
                metadata_format: metadataFormat,
                copy_images: copyImages,
                use_symlinks: useSymlinks,
            };
            if (scope === 'dataset') body.dataset_name = datasetName;
            if (scope === 'selection') body.selected_hashes = selectedHashes;

            const res = await fetch('/api/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail ?? 'Export failed');
            }

            // Poll progress
            const poll = setInterval(async () => {
                try {
                    const sr = await fetch('/api/export/status');
                    const st = await sr.json();
                    if (st.running) {
                        setProgress({ processed: st.processed, exported: st.exported, errors: st.errors, total: st.total });
                    } else {
                        clearInterval(poll);
                        setProgress({ processed: st.processed ?? st.total, exported: st.exported ?? 0, errors: st.errors ?? 0, total: st.total ?? 0 });
                        setExporting(false);
                        setDone(true);
                        const exported = st.exported ?? 0;
                        const errors = st.errors ?? 0;
                        setStatus(`Exported ${exported} image(s)${errors ? `, ${errors} error(s)` : ''}`, errors ? 'error' : 'success');
                    }
                } catch {
                    clearInterval(poll);
                    setExporting(false);
                }
            }, 300);
        } catch (e: any) {
            setStatus('Export failed: ' + e.message, 'error');
            setExporting(false);
        }
    };

    const handleCancel = async () => {
        await fetch('/api/export/cancel', { method: 'POST' });
    };

    const canExport = outputDir.trim() && !exporting && (
        scope === 'library' ||
        (scope === 'dataset' && datasetName) ||
        (scope === 'selection' && selectedCount > 0)
    );

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={!exporting ? onClose : undefined}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-[480px] shadow-2xl" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-1">Export</h2>
                <p className="text-[11px] text-gray-400 mb-4">
                    Export images with metadata sidecars. <code className="text-blue-300 mx-1">.json</code>
                    files are re-importable via <strong>Import Images</strong>.
                </p>

                {/* Scope */}
                <label className="text-[10px] text-gray-400 uppercase tracking-wider mb-1 block">Scope</label>
                <div className="flex gap-1 mb-3">
                    <button
                        onClick={() => setScope('library')}
                        className={`flex-1 py-1.5 rounded text-xs transition-colors ${scope === 'library' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                    >Library</button>
                    <button
                        onClick={() => setScope('dataset')}
                        className={`flex-1 py-1.5 rounded text-xs transition-colors ${scope === 'dataset' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                    >Dataset</button>
                    <button
                        onClick={() => setScope('selection')}
                        disabled={selectedCount === 0}
                        className={`flex-1 py-1.5 rounded text-xs transition-colors ${scope === 'selection' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'} disabled:opacity-30`}
                    >Selection ({selectedCount})</button>
                </div>

                {/* Dataset picker (only when scope=dataset) */}
                {scope === 'dataset' && (
                    <div className="mb-3">
                        <select
                            value={datasetName}
                            onChange={e => setDatasetName(e.target.value)}
                            className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                        >
                            <option value="">Select dataset...</option>
                            {datasets.map(d => (
                                <option key={d.id} value={d.name}>{d.name} ({d.image_count})</option>
                            ))}
                        </select>
                    </div>
                )}

                {/* Metadata format */}
                <label className="text-[10px] text-gray-400 uppercase tracking-wider mb-1 block">Metadata format</label>
                <div className="flex gap-1 mb-3">
                    <button
                        onClick={() => setMetadataFormat('json')}
                        className={`flex-1 py-1.5 rounded text-xs transition-colors ${metadataFormat === 'json' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                    >.json (full metadata)</button>
                    <button
                        onClick={() => setMetadataFormat('txt')}
                        className={`flex-1 py-1.5 rounded text-xs transition-colors ${metadataFormat === 'txt' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                    >.txt (tags only)</button>
                </div>

                {/* Options */}
                <div className="flex gap-4 mb-3">
                    <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
                        <input type="checkbox" checked={copyImages} onChange={e => { setCopyImages(e.target.checked); if (e.target.checked) setUseSymlinks(false); }} className="rounded" />
                        Copy images
                    </label>
                    <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
                        <input type="checkbox" checked={useSymlinks} onChange={e => { setUseSymlinks(e.target.checked); if (e.target.checked) setCopyImages(false); }} className="rounded" />
                        Symlinks
                    </label>
                </div>

                {/* Output directory */}
                <label className="text-[10px] text-gray-400 uppercase tracking-wider mb-1 block">Output directory</label>
                <div className="flex gap-2 mb-3">
                    <input
                        value={outputDir}
                        onChange={e => setOutputDir(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && canExport) handleExport(); }}
                        placeholder="/path/to/output..."
                        className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                        autoFocus
                        disabled={exporting}
                    />
                    <button onClick={handleBrowse} disabled={exporting} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 rounded text-xs text-white">Browse</button>
                </div>

                {/* Progress */}
                {exporting && progress && (
                    <div className="mb-3">
                        <div className="w-full bg-gray-700 rounded-full h-1.5 mb-1">
                            <div
                                className="bg-blue-500 h-1.5 rounded-full transition-all"
                                style={{ width: `${progress.total > 0 ? (progress.processed / progress.total) * 100 : 0}%` }}
                            />
                        </div>
                        <div className="flex justify-between text-[10px] text-gray-400">
                            <span>{progress.processed} / {progress.total}</span>
                            <span>{progress.exported} exported{progress.errors > 0 && `, ${progress.errors} errors`}</span>
                        </div>
                    </div>
                )}

                {/* Done banner */}
                {done && progress && !exporting && (
                    <div className="mb-3 bg-green-900/30 border border-green-800 rounded px-3 py-2 text-xs text-green-300">
                        Exported {progress.exported} image(s){progress.errors > 0 && `, ${progress.errors} error(s)`}
                    </div>
                )}

                {/* Actions */}
                <div className="flex gap-2">
                    <button
                        onClick={handleExport}
                        disabled={!canExport}
                        className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded py-2 text-xs font-semibold"
                    >
                        {exporting ? 'Exporting...' : 'Export'}
                    </button>
                    {exporting ? (
                        <button onClick={handleCancel} className="px-4 py-2 bg-red-700 hover:bg-red-600 text-white rounded text-xs">Cancel</button>
                    ) : (
                        <button onClick={onClose} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">Close</button>
                    )}
                </div>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Backfill Indicator — shows background metadata backfill progress
// -----------------------------------------------------------------------
function BackfillIndicator({ libraryPath }: { libraryPath?: string }) {
    const [status, setStatus] = useState<{ running: boolean; processed?: number; total?: number; phase?: string } | null>(null);
    const qc = useQueryClient();

    useEffect(() => {
        let alive = true;
        let lastProcessed = -1;
        const poll = async () => {
            while (alive) {
                try {
                    const res = await fetch('/api/library/backfill-status');
                    const data = await res.json();
                    if (!alive) break;
                    setStatus(data);
                    // When new dimensions land, refresh the gallery so layout
                    // recomputes from squares to actual aspect ratios.
                    if (data.processed && data.processed !== lastProcessed && data.processed - lastProcessed >= 50) {
                        lastProcessed = data.processed;
                        qc.invalidateQueries({ queryKey: ['images'] });
                    }
                    if (!data.running) {
                        if (lastProcessed >= 0) {
                            qc.invalidateQueries({ queryKey: ['images'] });
                        }
                        break;
                    }
                } catch { /* ignore */ }
                await new Promise(r => setTimeout(r, 500));
            }
        };
        poll();
        return () => { alive = false; };
    }, [libraryPath, qc]);

    if (!status || !status.running) return null;
    const pct = status.total && status.total > 0 ? Math.round(((status.processed ?? 0) / status.total) * 100) : 0;

    return (
        <div className="flex items-center gap-1.5 px-2 py-0.5 bg-blue-900/30 border border-blue-800/50 rounded text-[10px] text-blue-300" title="Backfilling image metadata in background">
            <div className="animate-spin rounded-full h-2.5 w-2.5 border border-blue-400 border-t-transparent" />
            <span>Preparing {status.processed}/{status.total} ({pct}%)</span>
        </div>
    );
}

// -----------------------------------------------------------------------
// Find & Replace Dialog
// -----------------------------------------------------------------------
function FindReplaceDialog({
    onClose,
    datasets,
    currentDataset,
    selectedCount,
    selectedHashes,
}: {
    onClose: () => void;
    datasets: Dataset[];
    currentDataset: string | null;
    selectedCount: number;
    selectedHashes: string[];
}) {
    const [search, setSearch] = useState('');
    const [replace, setReplace] = useState('');
    const [inTags, setInTags] = useState(true);
    const [inCaptions, setInCaptions] = useState(false);
    const [scope, setScope] = useState<'library' | 'dataset' | 'selection'>(
        selectedCount > 0 ? 'selection' : currentDataset ? 'dataset' : 'library'
    );
    const [running, setRunning] = useState(false);
    const [preview, setPreview] = useState<{ tag_matches: number; caption_matches: number } | null>(null);
    const [result, setResult] = useState<{ tags_replaced: number; captions_replaced: number } | null>(null);
    const { setStatus } = useTaggerStore();
    const qc = useQueryClient();
    const previewTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Auto-preview on input change
    useEffect(() => {
        if (!search.trim() || (!inTags && !inCaptions)) {
            setPreview(null);
            return;
        }
        if (previewTimer.current) clearTimeout(previewTimer.current);
        previewTimer.current = setTimeout(async () => {
            try {
                const res = await fetch('/api/tags/find-replace/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        search: search,
                        in_tags: inTags,
                        in_captions: inCaptions,
                        scope,
                        selected_hashes: scope === 'selection' ? selectedHashes : undefined,
                    }),
                });
                if (res.ok) {
                    setPreview(await res.json());
                }
            } catch { /* ignore */ }
        }, 300);
        return () => { if (previewTimer.current) clearTimeout(previewTimer.current); };
    }, [search, inTags, inCaptions, scope, selectedHashes]);

    const handleReplace = async () => {
        if (!search.trim() || (!inTags && !inCaptions)) return;
        setRunning(true);
        setResult(null);
        try {
            const res = await fetch('/api/tags/find-replace', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    search,
                    replace,
                    in_tags: inTags,
                    in_captions: inCaptions,
                    scope,
                    selected_hashes: scope === 'selection' ? selectedHashes : undefined,
                }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail ?? 'Find & replace failed');
            }
            const data = await res.json();
            setResult(data);
            const total = data.tags_replaced + data.captions_replaced;
            setStatus(`Replaced ${total} occurrence(s)`, total > 0 ? 'success' : 'info');
            // Invalidate queries so gallery/tag editor refresh
            qc.invalidateQueries({ queryKey: ['images'] });
            qc.invalidateQueries({ queryKey: ['image'] });
            qc.invalidateQueries({ queryKey: ['multi-image-tags'] });
            // Re-run preview
            setPreview(null);
        } catch (e: any) {
            setStatus('Find & replace failed: ' + e.message, 'error');
        }
        setRunning(false);
    };

    const totalPreview = (preview?.tag_matches ?? 0) + (preview?.caption_matches ?? 0);
    const canRun = search.trim() && (inTags || inCaptions) && !running && (
        scope === 'library' ||
        (scope === 'dataset' && currentDataset) ||
        (scope === 'selection' && selectedCount > 0)
    );

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={!running ? onClose : undefined}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-[440px] shadow-2xl" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-4">Find & Replace</h2>

                {/* Search in */}
                <label className="text-[10px] text-gray-400 uppercase tracking-wider mb-1 block">Search in</label>
                <div className="flex gap-4 mb-3">
                    <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
                        <input type="checkbox" checked={inTags} onChange={e => setInTags(e.target.checked)} className="rounded" />
                        Tags
                    </label>
                    <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
                        <input type="checkbox" checked={inCaptions} onChange={e => setInCaptions(e.target.checked)} className="rounded" />
                        Captions
                    </label>
                </div>

                {/* Search / Replace fields */}
                <label className="text-[10px] text-gray-400 uppercase tracking-wider mb-1 block">Find</label>
                <input
                    value={search}
                    onChange={e => { setSearch(e.target.value); setResult(null); }}
                    placeholder="Text to find..."
                    className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 mb-3"
                    autoFocus
                    disabled={running}
                />

                <label className="text-[10px] text-gray-400 uppercase tracking-wider mb-1 block">Replace with</label>
                <input
                    value={replace}
                    onChange={e => { setReplace(e.target.value); setResult(null); }}
                    onKeyDown={e => { if (e.key === 'Enter' && canRun) handleReplace(); }}
                    placeholder="Replacement text (empty to delete)"
                    className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 mb-3"
                    disabled={running}
                />

                {/* Scope */}
                <label className="text-[10px] text-gray-400 uppercase tracking-wider mb-1 block">Scope</label>
                <div className="flex gap-1 mb-3">
                    <button
                        onClick={() => setScope('library')}
                        className={`flex-1 py-1.5 rounded text-xs transition-colors ${scope === 'library' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                    >Library</button>
                    <button
                        onClick={() => setScope('dataset')}
                        disabled={!currentDataset}
                        className={`flex-1 py-1.5 rounded text-xs transition-colors ${scope === 'dataset' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'} disabled:opacity-30`}
                    >Dataset{currentDataset ? `: ${currentDataset}` : ''}</button>
                    <button
                        onClick={() => setScope('selection')}
                        disabled={selectedCount === 0}
                        className={`flex-1 py-1.5 rounded text-xs transition-colors ${scope === 'selection' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'} disabled:opacity-30`}
                    >Selection ({selectedCount})</button>
                </div>

                {/* Preview */}
                {preview && search.trim() && (
                    <div className="mb-3 bg-gray-900/60 border border-gray-700 rounded px-3 py-2 text-xs text-gray-300">
                        {totalPreview === 0 ? (
                            <span className="text-gray-500">No matches found</span>
                        ) : (
                            <>
                                <span className="text-white font-medium">{totalPreview}</span> match{totalPreview !== 1 ? 'es' : ''}
                                {preview.tag_matches > 0 && <span className="ml-1.5">({preview.tag_matches} tag{preview.tag_matches !== 1 ? 's' : ''})</span>}
                                {preview.caption_matches > 0 && <span className="ml-1.5">({preview.caption_matches} caption{preview.caption_matches !== 1 ? 's' : ''})</span>}
                            </>
                        )}
                    </div>
                )}

                {/* Result */}
                {result && (
                    <div className="mb-3 bg-green-900/30 border border-green-800 rounded px-3 py-2 text-xs text-green-300">
                        Replaced: {result.tags_replaced} tag(s), {result.captions_replaced} caption(s)
                    </div>
                )}

                {/* Actions */}
                <div className="flex gap-2">
                    <button
                        onClick={handleReplace}
                        disabled={!canRun}
                        className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded py-2 text-xs font-semibold"
                    >
                        {running ? 'Replacing...' : 'Replace All'}
                    </button>
                    <button onClick={onClose} disabled={running} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-white rounded text-xs">Close</button>
                </div>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Single Image View — full quality large image with navigation
// -----------------------------------------------------------------------
function SingleImageView({ allImages }: {
    allImages: string[];
}) {
    const { activeImage, selectSingle, selectedImages, toggleActiveInSelection } = useTaggerStore();
    const currentIndex = activeImage ? allImages.indexOf(activeImage) : -1;
    const isInSelection = activeImage ? selectedImages.includes(activeImage) : false;

    // Shares the ['image', hash] cache with the tag editor, so this is deduped.
    const { data: activeImageMeta } = useQuery({
        queryKey: ['image', activeImage],
        queryFn: async () => {
            if (!activeImage) return null;
            const res = await fetch(`/api/images/data/${activeImage}`);
            if (!res.ok) return null;
            return res.json();
        },
        enabled: !!activeImage,
    });

    const goPrev = useCallback(() => {
        if (currentIndex > 0) {
            selectSingle(allImages[currentIndex - 1]);
        }
    }, [currentIndex, allImages, selectSingle]);

    const goNext = useCallback(() => {
        if (currentIndex < allImages.length - 1) {
            selectSingle(allImages[currentIndex + 1]);
        }
    }, [currentIndex, allImages, selectSingle]);

    useEffect(() => {
        const handleKey = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
            if (e.key === 'ArrowLeft') { e.preventDefault(); goPrev(); }
            if (e.key === 'ArrowRight') { e.preventDefault(); goNext(); }
            if (e.key === ' ') { e.preventDefault(); toggleActiveInSelection(); }
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [goPrev, goNext, toggleActiveInSelection]);

    if (!activeImage) {
        return (
            <div className="flex-1 flex items-center justify-center text-gray-500">
                <p className="text-sm italic">Select an image to view</p>
            </div>
        );
    }

    return (
        <div className="flex-1 flex flex-col bg-gray-900 overflow-hidden">
            {/* Image */}
            <div className={`flex-1 relative flex items-center justify-center min-h-0 p-4 ${activeImageMeta?.has_alpha ? 'checkerboard-bg' : ''}`}>
                <img
                    src={`/api/images/${activeImage}`}
                    alt="Full resolution"
                    className={`w-full h-full object-contain transition-shadow ${isInSelection ? 'ring-4 ring-blue-500 rounded' : ''}`}
                />

                {/* Selection badge */}
                {isInSelection && (
                    <div className="absolute top-6 right-6 bg-blue-500 text-white text-xs font-bold px-2.5 py-1 rounded-full shadow-lg flex items-center gap-1">
                        <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                        Selected
                    </div>
                )}

                {/* Nav arrows */}
                {currentIndex > 0 && (
                    <button
                        onClick={goPrev}
                        className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/50 hover:bg-black/80 flex items-center justify-center text-white transition-colors"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                    </button>
                )}
                {currentIndex < allImages.length - 1 && (
                    <button
                        onClick={goNext}
                        className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/50 hover:bg-black/80 flex items-center justify-center text-white transition-colors"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                    </button>
                )}
            </div>

            {/* Bottom bar */}
            <div className="flex-shrink-0 bg-gray-800 border-t border-gray-700 px-4 py-2 flex items-center justify-between">
                <span className="text-xs text-gray-400">
                    {currentIndex >= 0 ? `${currentIndex + 1} / ${allImages.length}` : ''}
                </span>
                <div className="flex items-center gap-3">
                    <button
                        onClick={toggleActiveInSelection}
                        className={`px-2 py-0.5 rounded text-xs transition-colors ${isInSelection ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}
                    >
                        {isInSelection ? 'In Selection' : 'Space to Select'}
                    </button>
                    <span className="text-xs text-gray-500">{selectedImages.length} in selection</span>
                    <span className="text-xs text-gray-300 font-mono truncate max-w-[200px]">{activeImage}</span>
                </div>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Dataset type
// -----------------------------------------------------------------------
interface Dataset {
    id: number;
    name: string;
    description: string;
    image_count: number;
}

// -----------------------------------------------------------------------
// Manage Libraries Dialog
// -----------------------------------------------------------------------
function ManageLibrariesDialog({ onClose, onLibraryChanged, currentPath }: { onClose: () => void; onLibraryChanged: () => void; currentPath?: string }) {
    const [libraries, setLibraries] = useState<{ name: string; path: string }[]>([]);
    const [renaming, setRenaming] = useState<string | null>(null); // path being renamed
    const [newName, setNewName] = useState('');
    const [confirmDelete, setConfirmDelete] = useState<string | null>(null); // path to confirm delete
    const [duplicating, setDuplicating] = useState<string | null>(null); // path being duplicated
    const [duplicateName, setDuplicateName] = useState('');
    const [duplicateInProgress, setDuplicateInProgress] = useState(false);
    const { setStatus } = useTaggerStore();

    const loadLibraries = async () => {
        try {
            const res = await fetch('/api/library/available');
            const data = await res.json();
            setLibraries(data.libraries ?? []);
        } catch { /* ignore */ }
    };

    useEffect(() => { loadLibraries(); }, []);

    const handleRename = async (path: string) => {
        if (!newName.trim()) return;
        try {
            const res = await fetch('/api/library/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path, new_name: newName.trim() }),
            });
            if (!res.ok) throw new Error('Rename failed');
            setRenaming(null);
            setNewName('');
            loadLibraries();
            onLibraryChanged();
            setStatus('Library renamed', 'success');
        } catch (e: any) {
            setStatus('Rename failed: ' + e.message, 'error');
        }
    };

    const handleDelete = async (path: string) => {
        try {
            const res = await fetch('/api/library/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path }),
            });
            if (!res.ok) throw new Error('Delete failed');
            setConfirmDelete(null);
            loadLibraries();
            onLibraryChanged();
            setStatus('Library deleted', 'success');
        } catch (e: any) {
            setStatus('Delete failed: ' + e.message, 'error');
        }
    };

    const handleDuplicate = async (path: string) => {
        if (!duplicateName.trim()) return;
        setDuplicateInProgress(true);
        try {
            const res = await fetch('/api/library/duplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path, new_name: duplicateName.trim() }),
            });
            if (!res.ok) throw new Error('Duplicate failed');
            setDuplicating(null);
            setDuplicateName('');
            loadLibraries();
            setStatus(`Library copied as "${duplicateName.trim()}"`, 'success');
        } catch (e: any) {
            setStatus('Duplicate failed: ' + e.message, 'error');
        } finally {
            setDuplicateInProgress(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={onClose}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-[500px] shadow-2xl max-h-[70vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-4">Manage Libraries</h2>

                <div className="flex-1 overflow-y-auto space-y-1 min-h-0">
                    {libraries.length === 0 && (
                        <p className="text-[11px] text-gray-500">No libraries found.</p>
                    )}
                    {libraries.map(lib => {
                        const isCurrent = currentPath === lib.path;
                        return (
                        <div key={lib.path} className={`flex flex-wrap items-center gap-2 p-2 rounded hover:bg-gray-700/50 group ${isCurrent ? 'border border-blue-700/50 bg-blue-900/10' : ''}`}>
                            <div className="flex-1 min-w-0">
                                {renaming === lib.path ? (
                                    <div className="flex gap-1">
                                        <input
                                            autoFocus
                                            value={newName}
                                            onChange={e => setNewName(e.target.value)}
                                            onKeyDown={e => { if (e.key === 'Enter') handleRename(lib.path); if (e.key === 'Escape') setRenaming(null); }}
                                            className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-0.5 text-xs text-white focus:outline-none focus:border-blue-500"
                                        />
                                        <button onClick={() => handleRename(lib.path)} className="px-2 py-0.5 bg-blue-700 hover:bg-blue-600 rounded text-[10px] text-white">Save</button>
                                        <button onClick={() => setRenaming(null)} className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded text-[10px] text-white">Cancel</button>
                                    </div>
                                ) : (
                                    <>
                                        <div className="text-xs text-white font-medium truncate">
                                            {lib.name}
                                            {isCurrent && <span className="ml-1.5 text-[9px] text-blue-400 font-normal">(open)</span>}
                                        </div>
                                        <div className="text-[10px] text-gray-500 truncate">{lib.path}</div>
                                    </>
                                )}
                            </div>

                            {renaming !== lib.path && confirmDelete !== lib.path && duplicating !== lib.path && (
                                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button
                                        onClick={() => { setRenaming(lib.path); setNewName(lib.name); }}
                                        className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded text-[10px] text-gray-300"
                                    >
                                        Rename
                                    </button>
                                    <button
                                        onClick={() => { setDuplicating(lib.path); setDuplicateName(lib.name + ' copy'); }}
                                        className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded text-[10px] text-gray-300"
                                    >
                                        Duplicate
                                    </button>
                                    <button
                                        onClick={() => setConfirmDelete(lib.path)}
                                        className="px-2 py-0.5 bg-red-900/50 hover:bg-red-800 rounded text-[10px] text-red-400"
                                    >
                                        Delete
                                    </button>
                                </div>
                            )}

                            {duplicating === lib.path && (
                                <div className="flex gap-1 w-full mt-1">
                                    <input
                                        autoFocus
                                        value={duplicateName}
                                        onChange={e => setDuplicateName(e.target.value)}
                                        onKeyDown={e => { if (e.key === 'Enter') handleDuplicate(lib.path); if (e.key === 'Escape') setDuplicating(null); }}
                                        disabled={duplicateInProgress}
                                        className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-0.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                                        placeholder="Copy name…"
                                    />
                                    <button
                                        onClick={() => handleDuplicate(lib.path)}
                                        disabled={duplicateInProgress || !duplicateName.trim()}
                                        className="px-2 py-0.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 rounded text-[10px] text-white"
                                    >
                                        {duplicateInProgress ? 'Copying…' : 'Copy'}
                                    </button>
                                    <button
                                        onClick={() => setDuplicating(null)}
                                        disabled={duplicateInProgress}
                                        className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 disabled:opacity-50 rounded text-[10px] text-white"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            )}

                            {confirmDelete === lib.path && (
                                <div className="flex items-center gap-1">
                                    <span className="text-[10px] text-red-400">Delete permanently?</span>
                                    <button
                                        onClick={() => handleDelete(lib.path)}
                                        className="px-2 py-0.5 bg-red-700 hover:bg-red-600 rounded text-[10px] text-white font-medium"
                                    >
                                        Yes
                                    </button>
                                    <button
                                        onClick={() => setConfirmDelete(null)}
                                        className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded text-[10px] text-white"
                                    >
                                        No
                                    </button>
                                </div>
                            )}
                        </div>
                    );
                    })}
                </div>

                <div className="flex justify-end mt-4 pt-3 border-t border-gray-700">
                    <button onClick={onClose} className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">Close</button>
                </div>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Manage Datasets Dialog
// -----------------------------------------------------------------------
function ManageDatasetsDialog({
    onClose,
    onChanged,
    currentDataset,
}: {
    onClose: () => void;
    onChanged: () => void;
    currentDataset: string | null;
}) {
    const [datasets, setDatasets] = useState<Dataset[]>([]);
    const [renaming, setRenaming] = useState<number | null>(null);
    const [newName, setNewName] = useState('');
    const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
    const [duplicating, setDuplicating] = useState<number | null>(null);
    const [duplicateName, setDuplicateName] = useState('');
    const [duplicateInProgress, setDuplicateInProgress] = useState(false);
    const { setStatus } = useTaggerStore();

    const loadDatasets = async () => {
        try {
            const res = await fetch('/api/datasets/list');
            const data = await res.json();
            setDatasets(data.datasets ?? []);
        } catch { /* ignore */ }
    };

    useEffect(() => { loadDatasets(); }, []);

    const handleRename = async (id: number) => {
        if (!newName.trim()) return;
        try {
            const res = await fetch(`/api/datasets/${id}/rename`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_name: newName.trim() }),
            });
            if (!res.ok) throw new Error('Rename failed');
            setRenaming(null);
            setNewName('');
            loadDatasets();
            onChanged();
            setStatus('Dataset renamed', 'success');
        } catch (e: any) {
            setStatus('Rename failed: ' + e.message, 'error');
        }
    };

    const handleDuplicate = async (id: number) => {
        if (!duplicateName.trim()) return;
        setDuplicateInProgress(true);
        try {
            const res = await fetch(`/api/datasets/${id}/duplicate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_name: duplicateName.trim() }),
            });
            if (!res.ok) throw new Error('Duplicate failed');
            setDuplicating(null);
            setDuplicateName('');
            loadDatasets();
            onChanged();
            setStatus(`Dataset copied as "${duplicateName.trim()}"`, 'success');
        } catch (e: any) {
            setStatus('Duplicate failed: ' + e.message, 'error');
        } finally {
            setDuplicateInProgress(false);
        }
    };

    const handleDelete = async (id: number, name: string) => {
        try {
            const res = await fetch(`/api/datasets/${encodeURIComponent(name)}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Delete failed');
            setConfirmDelete(null);
            loadDatasets();
            onChanged();
            setStatus('Dataset deleted', 'success');
        } catch (e: any) {
            setStatus('Delete failed: ' + e.message, 'error');
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={onClose}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-[500px] shadow-2xl max-h-[70vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-4">Manage Datasets</h2>

                <div className="flex-1 overflow-y-auto space-y-1 min-h-0">
                    {datasets.length === 0 && (
                        <p className="text-[11px] text-gray-500">No datasets in this library.</p>
                    )}
                    {datasets.map(ds => {
                        const isCurrent = currentDataset === ds.name;
                        return (
                            <div key={ds.id} className={`flex flex-wrap items-center gap-2 p-2 rounded hover:bg-gray-700/50 group ${isCurrent ? 'border border-blue-700/50 bg-blue-900/10' : ''}`}>
                                <div className="flex-1 min-w-0">
                                    {renaming === ds.id ? (
                                        <div className="flex gap-1">
                                            <input
                                                autoFocus
                                                value={newName}
                                                onChange={e => setNewName(e.target.value)}
                                                onKeyDown={e => { if (e.key === 'Enter') handleRename(ds.id); if (e.key === 'Escape') setRenaming(null); }}
                                                className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-0.5 text-xs text-white focus:outline-none focus:border-blue-500"
                                            />
                                            <button onClick={() => handleRename(ds.id)} className="px-2 py-0.5 bg-blue-700 hover:bg-blue-600 rounded text-[10px] text-white">Save</button>
                                            <button onClick={() => setRenaming(null)} className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded text-[10px] text-white">Cancel</button>
                                        </div>
                                    ) : (
                                        <>
                                            <div className="text-xs text-white font-medium truncate">
                                                {ds.name}
                                                {isCurrent && <span className="ml-1.5 text-[9px] text-blue-400 font-normal">(active)</span>}
                                                <span className="ml-1.5 text-[10px] text-gray-500 font-normal">{ds.image_count} image{ds.image_count !== 1 ? 's' : ''}</span>
                                            </div>
                                            {ds.description && (
                                                <div className="text-[10px] text-gray-500 truncate">{ds.description}</div>
                                            )}
                                        </>
                                    )}
                                </div>

                                {renaming !== ds.id && confirmDelete !== ds.id && duplicating !== ds.id && (
                                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button
                                            onClick={() => { setRenaming(ds.id); setNewName(ds.name); }}
                                            className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded text-[10px] text-gray-300"
                                        >Rename</button>
                                        <button
                                            onClick={() => { setDuplicating(ds.id); setDuplicateName(ds.name + ' copy'); }}
                                            className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded text-[10px] text-gray-300"
                                        >Duplicate</button>
                                        <button
                                            onClick={() => setConfirmDelete(ds.id)}
                                            className="px-2 py-0.5 bg-red-900/50 hover:bg-red-800 rounded text-[10px] text-red-400"
                                        >Delete</button>
                                    </div>
                                )}

                                {duplicating === ds.id && (
                                    <div className="flex gap-1 w-full mt-1">
                                        <input
                                            autoFocus
                                            value={duplicateName}
                                            onChange={e => setDuplicateName(e.target.value)}
                                            onKeyDown={e => { if (e.key === 'Enter') handleDuplicate(ds.id); if (e.key === 'Escape') setDuplicating(null); }}
                                            disabled={duplicateInProgress}
                                            className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-0.5 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                                            placeholder="Copy name…"
                                        />
                                        <button
                                            onClick={() => handleDuplicate(ds.id)}
                                            disabled={duplicateInProgress || !duplicateName.trim()}
                                            className="px-2 py-0.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 rounded text-[10px] text-white"
                                        >{duplicateInProgress ? 'Copying…' : 'Copy'}</button>
                                        <button
                                            onClick={() => setDuplicating(null)}
                                            disabled={duplicateInProgress}
                                            className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 disabled:opacity-50 rounded text-[10px] text-white"
                                        >Cancel</button>
                                    </div>
                                )}

                                {confirmDelete === ds.id && (
                                    <div className="flex items-center gap-1">
                                        <span className="text-[10px] text-red-400">Delete permanently?</span>
                                        <button
                                            onClick={() => handleDelete(ds.id, ds.name)}
                                            className="px-2 py-0.5 bg-red-700 hover:bg-red-600 rounded text-[10px] text-white font-medium"
                                        >Yes</button>
                                        <button
                                            onClick={() => setConfirmDelete(null)}
                                            className="px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded text-[10px] text-white"
                                        >No</button>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>

                <div className="flex justify-end mt-4 pt-3 border-t border-gray-700">
                    <button onClick={onClose} className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">Close</button>
                </div>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Restore Deleted Dialog
// -----------------------------------------------------------------------
type DeletedItem = {
    filename: string;
    hash: string;
    name: string;
    tag_count: number;
    deleted_at: number;
    media_type: string;
};

const PAGE_SIZE = 100;

function RestoreDeletedDialog({
    onClose,
    onRestored,
    datasets,
}: {
    onClose: () => void;
    onRestored: () => void;
    datasets: Dataset[];
}) {
    const [items, setItems] = useState<DeletedItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [targetDataset, setTargetDataset] = useState<number | null>(null);
    const [restoring, setRestoring] = useState(false);
    const [search, setSearch] = useState('');
    const [sortKey, setSortKey] = useState<'date_desc' | 'date_asc' | 'name_asc' | 'name_desc'>('date_desc');
    const [page, setPage] = useState(1);
    const { setStatus } = useTaggerStore();

    useEffect(() => {
        fetch('/api/library/deleted')
            .then(r => r.json())
            .then(d => { setItems(d.items ?? []); setLoading(false); })
            .catch(() => setLoading(false));
    }, []);

    const filtered = (() => {
        let list = search.trim()
            ? items.filter(i => i.name.toLowerCase().includes(search.toLowerCase()) || i.filename.toLowerCase().includes(search.toLowerCase()))
            : items;
        if (sortKey === 'date_desc') list = [...list].sort((a, b) => b.deleted_at - a.deleted_at);
        else if (sortKey === 'date_asc') list = [...list].sort((a, b) => a.deleted_at - b.deleted_at);
        else if (sortKey === 'name_asc') list = [...list].sort((a, b) => a.name.localeCompare(b.name));
        else if (sortKey === 'name_desc') list = [...list].sort((a, b) => b.name.localeCompare(a.name));
        return list;
    })();

    const visible = filtered.slice(0, page * PAGE_SIZE);
    const hasMore = visible.length < filtered.length;

    // Reset page when search or sort changes
    useEffect(() => { setPage(1); }, [search, sortKey]);

    const toggleSelect = (filename: string) => {
        setSelected(prev => {
            const next = new Set(prev);
            if (next.has(filename)) next.delete(filename);
            else next.add(filename);
            return next;
        });
    };

    const selectAllFiltered = () => setSelected(new Set(filtered.map(i => i.filename)));
    const clearAll = () => setSelected(new Set());

    const handleRestore = async () => {
        if (selected.size === 0) return;
        setRestoring(true);
        try {
            const res = await fetch('/api/library/restore-deleted', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filenames: [...selected],
                    dataset_id: targetDataset ?? null,
                }),
            });
            if (!res.ok) throw new Error('Restore failed');
            const data = await res.json();
            setStatus(`Restored ${data.restored} image(s)${data.skipped ? `, ${data.skipped} skipped` : ''}`, 'success');
            onRestored();
            setItems(prev => prev.filter(i => !selected.has(i.filename)));
            setSelected(new Set());
        } catch (e: any) {
            setStatus('Restore failed: ' + e.message, 'error');
        } finally {
            setRestoring(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={onClose}>
            <div
                className="bg-gray-800 border border-gray-700 rounded-xl p-5 w-[760px] max-h-[85vh] flex flex-col shadow-2xl"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex items-center justify-between mb-3">
                    <h2 className="text-sm font-bold text-white">Restore Deleted Images</h2>
                    <span className="text-[11px] text-gray-400">
                        {filtered.length !== items.length ? `${filtered.length} / ${items.length}` : `${items.length}`} deleted
                    </span>
                </div>

                {/* Search + sort controls */}
                <div className="flex gap-2 mb-2">
                    <input
                        type="text"
                        placeholder="Search by name…"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                    />
                    <select
                        value={sortKey}
                        onChange={e => setSortKey(e.target.value as typeof sortKey)}
                        className="bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
                    >
                        <option value="date_desc">Newest deleted first</option>
                        <option value="date_asc">Oldest deleted first</option>
                        <option value="name_asc">Name A→Z</option>
                        <option value="name_desc">Name Z→A</option>
                    </select>
                </div>

                {loading ? (
                    <div className="flex-1 flex items-center justify-center text-gray-500 text-xs">Loading...</div>
                ) : filtered.length === 0 ? (
                    <div className="flex-1 flex items-center justify-center text-gray-500 text-xs">
                        {items.length === 0 ? 'No deleted images found.' : 'No matches.'}
                    </div>
                ) : (
                    <>
                        {/* Selection controls */}
                        <div className="flex items-center gap-2 mb-2">
                            <button onClick={selectAllFiltered} className="px-2 py-0.5 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300">
                                Select All{search ? ' Filtered' : ''}
                            </button>
                            <button onClick={clearAll} className="px-2 py-0.5 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300">Clear</button>
                            <span className="text-[10px] text-gray-500 ml-1">{selected.size} selected</span>
                        </div>

                        {/* Thumbnail grid — paginated to avoid loading thousands of images at once */}
                        <div className="flex-1 overflow-y-auto min-h-0">
                            <div className="grid gap-1.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))' }}>
                                {visible.map(item => {
                                const isSelected = selected.has(item.filename);
                                return (
                                    <div
                                        key={item.filename}
                                        onClick={() => toggleSelect(item.filename)}
                                        className={`relative rounded overflow-hidden cursor-pointer border-2 transition-colors
                                            ${isSelected ? 'border-blue-500' : 'border-transparent hover:border-gray-500'}`}
                                    >
                                        <img
                                            src={`/api/library/deleted-thumbnail/${encodeURIComponent(item.filename)}?size=200`}
                                            alt={item.name}
                                            className="w-full aspect-square object-cover bg-gray-900"
                                        />
                                        {isSelected && (
                                            <div className="absolute top-1 right-1 w-4 h-4 bg-blue-500 rounded-full flex items-center justify-center">
                                                <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
                                                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                                </svg>
                                            </div>
                                        )}
                                        <div className="absolute bottom-0 inset-x-0 bg-black/60 px-1 py-0.5">
                                            <p className="text-[9px] text-gray-200 truncate">{item.name}</p>
                                            <p className="text-[8px] text-gray-400">{item.tag_count} tag{item.tag_count !== 1 ? 's' : ''}</p>
                                        </div>
                                    </div>
                                );
                                })}
                            </div>
                            {hasMore && (
                                <div className="flex justify-center py-3">
                                    <button
                                        onClick={() => setPage(p => p + 1)}
                                        className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs"
                                    >
                                        Load more ({filtered.length - visible.length} remaining)
                                    </button>
                                </div>
                            )}
                        </div>
                    </>
                )}

                {/* Footer */}
                <div className="flex items-center gap-3 mt-4 pt-3 border-t border-gray-700">
                    {/* Dataset picker */}
                    <div className="flex items-center gap-1.5 flex-1">
                        <label className="text-[10px] text-gray-400 whitespace-nowrap">Add to dataset:</label>
                        <select
                            value={targetDataset ?? ''}
                            onChange={e => setTargetDataset(e.target.value ? parseInt(e.target.value) : null)}
                            className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-0.5 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
                        >
                            <option value="">None</option>
                            {datasets.map(d => (
                                <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                        </select>
                    </div>
                    <button
                        onClick={handleRestore}
                        disabled={selected.size === 0 || restoring}
                        className="px-4 py-1.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white rounded text-xs font-medium"
                    >
                        {restoring ? 'Restoring…' : `Restore${selected.size > 0 ? ` (${selected.size})` : ''}`}
                    </button>
                    <button onClick={onClose} className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">Close</button>
                </div>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Main App Content
// -----------------------------------------------------------------------
function AppContent() {
    const [libraryInfo, setLibraryInfo] = useState<{ name: string; path: string; count: number } | null>(null);
    const [datasets, setDatasets] = useState<Dataset[]>([]);
    const [showImport, setShowImport] = useState(false);
    const [showCreateLibrary, setShowCreateLibrary] = useState(false);
    const [showLibraryPicker, setShowLibraryPicker] = useState(false);
    const [showManageLibraries, setShowManageLibraries] = useState(false);
    const [managedMode, setManagedMode] = useState(false);
    const [showTaxonomy, setShowTaxonomy] = useState(false);
    const [showCreateDatasetDialog, setShowCreateDatasetDialog] = useState(false);
    const [showManageDatasets, setShowManageDatasets] = useState(false);
    const [showRestoreDeleted, setShowRestoreDeleted] = useState(false);
    const [showHFPullDialog, setShowHFPullDialog] = useState(false);
    const [showHFPushDialog, setShowHFPushDialog] = useState(false);
    const [showExport, setShowExport] = useState(false);
    const [showFindReplace, setShowFindReplace] = useState(false);
    const [showDuplicateTags, setShowDuplicateTags] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [showFilterPanel, setShowFilterPanel] = useState(false);
    const [filteredTotal, setFilteredTotal] = useState<number | null>(null);
    const [deleteDialog, setDeleteDialog] = useState<{ hashes: string[]; nextHash: string | null } | null>(null);
    const filterPanelRef = useRef<HTMLDivElement>(null);
    const galleryFocusRef = useRef<HTMLDivElement | null>(null);

    const focusGallery = useCallback(() => {
        setTimeout(() => galleryFocusRef.current?.focus(), 0);
    }, []);

    const {
        selectedImages, selectSingle, ctrlSelect, addToSelection, setActiveImage,
        activeImage, currentDataset, setDataset, clearSelection, selectAll,
        toggleActiveInSelection,
        thumbnailSize, setThumbnailSize, sortBy, setSortBy,
        viewMode, setViewMode, tagEditorWidth, setTagEditorWidth, setStatus
    } = useTaggerStore();
    const qc = useQueryClient();
    const lastClickedIdx = useRef<number | null>(null);

    const refreshLibrary = useCallback(() => {
        fetch('/api/library/current')
            .then(res => res.json())
            .then(data => setLibraryInfo(data || null))
            .catch(console.error);
    }, []);

    const refreshDatasets = useCallback(() => {
        fetch('/api/datasets/list')
            .then(res => res.json())
            .then(data => { if (data?.datasets) setDatasets(data.datasets); })
            .catch(console.error);
    }, []);

    useEffect(() => {
        if (currentDataset === null) {
            fetch('/api/datasets/close', { method: 'POST' }).catch(console.error);
        }
        refreshLibrary();
        refreshDatasets();

        // Fetch server config to know if we're in managed mode (--libraries-root set).
        // In managed mode the UI shows only the libraries from the configured root,
        // no raw path entry.
        fetch('/api/library/config')
            .then(r => r.json())
            .then(cfg => {
                if (cfg?.managed) setManagedMode(true);
            })
            .catch(() => {});
    }, []);

    // Close filter panel on outside click
    useEffect(() => {
        if (!showFilterPanel) return;
        const handler = (e: MouseEvent) => {
            if (filterPanelRef.current && !filterPanelRef.current.contains(e.target as Node)) {
                setShowFilterPanel(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [showFilterPanel]);

    const getAllLoadedHashes = useCallback((): string[] => {
        const data = qc.getQueryData<{ pages: { items: { hash: string }[] }[] }>(['images', sortBy]);
        return data?.pages.flatMap(p => p.items.map(img => img.hash)) ?? [];
    }, [qc, sortBy]);

    const selectAllFiltered = useCallback(async () => {
        try {
            const res = await fetch(`/api/images/all-hashes?sort=${encodeURIComponent(sortBy)}`);
            const data = await res.json();
            if (data?.hashes?.length > 0) selectAll(data.hashes);
        } catch {
            // Fallback to loaded pages if request fails
            const loaded = getAllLoadedHashes();
            if (loaded.length > 0) selectAll(loaded);
        }
    }, [sortBy, selectAll, getAllLoadedHashes]);

    // Keep filteredTotal in sync with the first page of the image query
    useEffect(() => {
        const update = () => {
            const d = qc.getQueryData<{ pages: { total: number }[] }>(['images', sortBy]);
            setFilteredTotal(d?.pages?.[0]?.total ?? null);
        };
        update();
        const unsub = qc.getQueryCache().subscribe(update);
        return unsub;
    }, [qc, sortBy]);

    // Auto-select first image when library loads or images change with no active image
    useEffect(() => {
        const unsub = qc.getQueryCache().subscribe(() => {
            const current = useTaggerStore.getState().activeImage;
            if (!current) {
                const data = qc.getQueryData<{ pages: { items: { hash: string }[] }[] }>(['images', sortBy]);
                const first = data?.pages?.[0]?.items?.[0]?.hash;
                if (first) {
                    selectSingle(first);
                }
            }
        });
        return unsub;
    }, [qc, sortBy]);

    // Navigate active image with arrow keys, space toggles selection
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
            // Don't intercept keys when tag editor list is focused — it handles its own
            const tagList = document.querySelector('[data-tag-list]');
            const inTagEditor = tagList?.contains(document.activeElement) || document.activeElement === tagList;

            if (e.key === 'z' && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
                e.preventDefault(); handleUndo();
            } else if ((e.key === 'y' && (e.ctrlKey || e.metaKey)) || (e.key === 'z' && e.shiftKey && e.ctrlKey)) {
                e.preventDefault(); handleRedo();
            } else if (inTagEditor) {
                return; // let tag editor handle everything else
            } else if (e.key === 'Escape') {
                if (deleteDialog) { setDeleteDialog(null); return; }
                clearSelection();
            } else if (e.key === 'a' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                selectAllFiltered();
            } else if (e.key === 'Delete') {
                e.preventDefault();
                const hashes = selectedImages.length > 0 ? selectedImages : (activeImage ? [activeImage] : []);
                if (hashes.length > 0) {
                    const loaded = getAllLoadedHashes();
                    const deleteSet = new Set(hashes);
                    const anchorIdx = activeImage ? loaded.indexOf(activeImage) : -1;
                    let nextHash: string | null = null;
                    for (let i = anchorIdx + 1; i < loaded.length; i++) {
                        if (!deleteSet.has(loaded[i])) { nextHash = loaded[i]; break; }
                    }
                    if (!nextHash) {
                        for (let i = anchorIdx - 1; i >= 0; i--) {
                            if (!deleteSet.has(loaded[i])) { nextHash = loaded[i]; break; }
                        }
                    }
                    setDeleteDialog({ hashes, nextHash });
                }
            } else if (e.key === ' ' && viewMode !== 'single') {
                e.preventDefault();
                toggleActiveInSelection();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedImages, sortBy, activeImage, viewMode, selectAllFiltered, deleteDialog]);

    // Click handler: plain click = single select, ctrl = toggle multi, shift = range
    // Once in multi mode (selection exists), plain click adds to selection
    const handleSelectImage = (hash: string, index: number, shiftKey: boolean, ctrlKey?: boolean) => {
        if (shiftKey && lastClickedIdx.current !== null) {
            // Shift+click: range select
            const allHashes = getAllLoadedHashes();
            const start = Math.min(lastClickedIdx.current, index);
            const end = Math.max(lastClickedIdx.current, index);
            addToSelection(allHashes.slice(start, end + 1));
            setActiveImage(hash);
        } else if (ctrlKey || selectedImages.length > 0) {
            // Ctrl+click or already in multi mode: toggle in/out of selection
            ctrlSelect(hash);
            lastClickedIdx.current = index;
        } else {
            // Plain click with no selection: single select
            selectSingle(hash);
            lastClickedIdx.current = index;
        }
    };

    const loadLibraryPath = async (filePath: string) => {
        try {
            const res = await fetch('/api/library/load', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: filePath }),
            });
            if (!res.ok) {
                const err = await res.json();
                setStatus('Failed to load library: ' + err.detail, 'error');
                return;
            }
            refreshLibrary();
            refreshDatasets();
            clearSelection();
            setActiveImage(null);
            qc.invalidateQueries({ queryKey: ['images'] });
            setStatus('Library loaded', 'success');
        } catch {
            setStatus('Error loading library', 'error');
        }
    };

    const handleOpenLibrary = () => {
        setShowLibraryPicker(true);
    };

    const handleScan = async () => {
        const res = await fetch('/api/library/scan', { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            refreshLibrary();
            qc.invalidateQueries({ queryKey: ['images'] });
            setStatus(`Scan complete: ${data.added} new file(s)`, 'info');
        }
    };

    const handleUndo = async () => {
        const res = await fetch('/api/tags/undo', { method: 'POST' });
        if (res.ok) {
            qc.invalidateQueries({ queryKey: ['images'] });
            if (activeImage) qc.invalidateQueries({ queryKey: ['image', activeImage] });
            setStatus('Undone', 'info');
        }
    };

    const handleRedo = async () => {
        const res = await fetch('/api/tags/redo', { method: 'POST' });
        if (res.ok) {
            qc.invalidateQueries({ queryKey: ['images'] });
            if (activeImage) qc.invalidateQueries({ queryKey: ['image', activeImage] });
            setStatus('Redone', 'info');
        }
    };

    const performDelete = async (mode: 'library' | 'dataset') => {
        if (!deleteDialog) return;
        const { hashes, nextHash } = deleteDialog;
        const deleteSet = new Set(hashes);
        setDeleteDialog(null);

        try {
            if (mode === 'dataset') {
                const res = await fetch('/api/datasets/remove-images', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_hashes: hashes }),
                });
                if (res.ok) {
                    const data = await res.json();
                    setStatus(`Removed ${data.removed} image(s) from dataset`, 'success');
                } else {
                    setStatus('Remove from dataset failed', 'error');
                    return;
                }
            } else {
                const res = await fetch('/api/images/delete-batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ hashes }),
                });
                if (res.ok) {
                    const data = await res.json();
                    setStatus(`Deleted ${data.deleted} image(s)`, 'success');
                    refreshLibrary();
                } else {
                    setStatus('Delete failed', 'error');
                    return;
                }
            }
            // Update selection: keep images that weren't deleted
            const remaining = selectedImages.filter(h => !deleteSet.has(h));
            selectAll(remaining);
            // Advance active image to next valid one
            if (nextHash) {
                setActiveImage(nextHash);
            } else if (remaining.length > 0) {
                setActiveImage(remaining[0]);
            } else {
                setActiveImage(null);
            }
            qc.invalidateQueries({ queryKey: ['images'] });
        } catch {
            setStatus('Operation failed', 'error');
        }
    };

    const handleDeleteSelected = () => {
        const hashes = selectedImages.length > 0 ? selectedImages : (activeImage ? [activeImage] : []);
        if (hashes.length === 0) return;
        const loaded = getAllLoadedHashes();
        const deleteSet = new Set(hashes);
        const anchorIdx = activeImage ? loaded.indexOf(activeImage) : -1;
        let nextHash: string | null = null;
        for (let i = anchorIdx + 1; i < loaded.length; i++) {
            if (!deleteSet.has(loaded[i])) { nextHash = loaded[i]; break; }
        }
        if (!nextHash) {
            for (let i = anchorIdx - 1; i >= 0; i--) {
                if (!deleteSet.has(loaded[i])) { nextHash = loaded[i]; break; }
            }
        }
        setDeleteDialog({ hashes, nextHash });
    };

    const handleSearch = async (query: string) => {
        setSearchQuery(query);
        await fetch('/api/library/filter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ expression: query }),
        });
        qc.invalidateQueries({ queryKey: ['images'] });
    };

    const handleSwitchDataset = async (name: string | null) => {
        if (name === null) {
            await fetch('/api/datasets/close', { method: 'POST' });
            setDataset(null);
        } else {
            const res = await fetch('/api/datasets/load', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name }),
            });
            if (res.ok) setDataset(name);
        }
        qc.invalidateQueries({ queryKey: ['images'] });
    };

    const handleCreateDataset = async (name: string) => {
        if (!name.trim()) return;
        const res = await fetch('/api/datasets/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name.trim() }),
        });
        if (res.ok) {
            setDataset(name.trim());
            refreshDatasets();
            qc.invalidateQueries({ queryKey: ['images'] });
        } else {
            const err = await res.json();
            setStatus('Failed: ' + err.detail, 'error');
        }
    };

    const handleAddSelectionToDataset = async () => {
        if (!currentDataset || selectedImages.length === 0) return;
        const res = await fetch('/api/datasets/add-images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_hashes: selectedImages })
        });
        if (res.ok) {
            const data = await res.json();
            setStatus(`Added ${data.added} image(s) to dataset`, 'success');
        }
    };

    const handleRemoveSelectionFromDataset = async () => {
        if (!currentDataset || selectedImages.length === 0) return;
        const res = await fetch('/api/datasets/remove-images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_hashes: selectedImages })
        });
        if (res.ok) {
            const data = await res.json();
            setStatus(`Removed ${data.removed} image(s) from dataset`, 'success');
            qc.invalidateQueries({ queryKey: ['images'] });
        }
    };

    const handlePullHF = async (values: Record<string, string>) => {
        const { repo_id, dataset_name } = values;
        if (!repo_id.trim()) return;
        const res = await fetch('/api/hf/pull', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_id: repo_id.trim(), dataset_name: dataset_name.trim() || undefined }),
        });
        if (res.ok) {
            setStatus('HF pull started. Refresh in a few moments.', 'info');
            setTimeout(() => { refreshLibrary(); refreshDatasets(); qc.invalidateQueries({ queryKey: ['images'] }); }, 5000);
        } else {
            const err = await res.json();
            setStatus('Pull failed: ' + err.detail, 'error');
        }
    };

    const handlePushHF = async (values: Record<string, string>) => {
        const { repo_id } = values;
        if (!repo_id.trim()) return;
        const res = await fetch('/api/hf/push', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_id: repo_id.trim(), private: true }),
        });
        if (res.ok) {
            setStatus('HF push started.', 'info');
        } else {
            const err = await res.json();
            setStatus('Push failed: ' + err.detail, 'error');
        }
    };

    return (
        <div className="flex flex-col h-screen w-full bg-gray-900 text-gray-100 overflow-hidden font-sans">
            {/* Top Bar */}
            <div className="flex-shrink-0 h-11 border-b border-gray-700 bg-gray-800/90 flex items-center px-3 gap-2">

                {/* App title + library name */}
                <span className="text-xs font-bold text-white tracking-tight whitespace-nowrap mr-1">Tagger</span>
                {libraryInfo && (
                    <span className="text-[10px] text-blue-400 truncate max-w-[160px]" title={libraryInfo.path}>
                        {libraryInfo.name}{' '}
                        {searchQuery && filteredTotal !== null
                            ? <span>(<span className="text-yellow-300">{filteredTotal}</span>/{libraryInfo.count})</span>
                            : `(${libraryInfo.count})`
                        }
                    </span>
                )}

                <BackfillIndicator libraryPath={libraryInfo?.path} />

                <div className="w-px h-5 bg-gray-700 mx-1" />

                {/* Library dropdown */}
                <Dropdown label="Library">
                    <DropdownItem onClick={handleOpenLibrary}>Open Library...</DropdownItem>
                    <DropdownItem onClick={() => setShowCreateLibrary(true)}>New Library...</DropdownItem>
                    <DropdownItem onClick={() => setShowManageLibraries(true)}>Manage Libraries...</DropdownItem>
                    <DropdownSeparator />
                    <DropdownItem onClick={() => setShowImport(true)}>Import Images...</DropdownItem>
                    <DropdownItem onClick={handleScan}>Scan for New Files</DropdownItem>
                    <DropdownSeparator />
                    <DropdownItem onClick={() => setShowExport(true)}>Export...</DropdownItem>
                </Dropdown>

                {/* Dataset dropdown */}
                <Dropdown label={currentDataset ? `Dataset: ${currentDataset}` : 'Dataset'}>
                    <DropdownItem onClick={() => handleSwitchDataset(null)}>
                        <span className={!currentDataset ? 'text-blue-400' : ''}>All Images (Library)</span>
                    </DropdownItem>
                    {datasets.length > 0 && <DropdownSeparator />}
                    {datasets.map(d => (
                        <DropdownItem key={d.id} onClick={() => handleSwitchDataset(d.name)}>
                            <span className={currentDataset === d.name ? 'text-blue-400' : ''}>
                                {d.name}
                                <span className="text-gray-500 ml-1.5">({d.image_count})</span>
                            </span>
                        </DropdownItem>
                    ))}
                    <DropdownSeparator />
                    <DropdownItem onClick={() => setShowCreateDatasetDialog(true)}>+ New Dataset...</DropdownItem>
                    <DropdownItem onClick={() => setShowManageDatasets(true)}>Manage Datasets...</DropdownItem>
                </Dropdown>

                {/* Tools dropdown */}
                <Dropdown label="Tools">
                    <DropdownItem onClick={() => setShowTaxonomy(true)}>Tag Taxonomy</DropdownItem>
                    <DropdownItem onClick={() => setShowFindReplace(true)}>Find & Replace...</DropdownItem>
                    <DropdownItem onClick={() => setShowDuplicateTags(true)}>Find Duplicate Tags...</DropdownItem>
                    <DropdownSeparator />
                    <DropdownItem onClick={() => setShowRestoreDeleted(true)}>Restore Deleted...</DropdownItem>
                    <DropdownSeparator />
                    <DropdownItem onClick={handleUndo}>Undo (Ctrl+Z)</DropdownItem>
                    <DropdownItem onClick={handleRedo}>Redo (Ctrl+Y)</DropdownItem>
                    <DropdownSeparator />
                    <DropdownItem onClick={() => setShowHFPullDialog(true)}>Pull from HF Hub...</DropdownItem>
                    <DropdownItem onClick={() => setShowHFPushDialog(true)}>Push to HF Hub...</DropdownItem>
                </Dropdown>

                <div className="w-px h-5 bg-gray-700 mx-1" />

                {/* Filter */}
                <div className="relative flex-1 max-w-md" ref={filterPanelRef}>
                    <button
                        onClick={() => setShowFilterPanel(p => !p)}
                        className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors w-full
                            ${searchQuery
                                ? 'bg-blue-900/40 border border-blue-600 text-blue-300'
                                : showFilterPanel
                                    ? 'bg-gray-600 text-white'
                                    : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                    >
                        <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                        </svg>
                        {searchQuery ? (
                            <span className="truncate font-mono text-[10px]">{searchQuery}</span>
                        ) : (
                            <span>Filter</span>
                        )}
                        {searchQuery && (
                            <button
                                onClick={e => { e.stopPropagation(); handleSearch(''); setShowFilterPanel(false); }}
                                className="ml-auto text-gray-400 hover:text-white flex-shrink-0"
                                title="Clear filter"
                            >
                                ✕
                            </button>
                        )}
                    </button>
                    {showFilterPanel && (
                        <div className="absolute top-full left-0 right-0 mt-1 z-30 min-w-[400px]">
                            <FilterPanel
                                expression={searchQuery}
                                onApply={(expr) => {
                                    handleSearch(expr);
                                    setShowFilterPanel(false);
                                    focusGallery();
                                }}
                            />
                        </div>
                    )}
                </div>

                {/* Sort */}
                <select
                    value={sortBy}
                    onChange={e => { setSortBy(e.target.value as any); qc.invalidateQueries({ queryKey: ['images'] }); focusGallery(); }}
                    className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none"
                >
                    <option value="default">Default</option>
                    <option value="name">Name</option>
                    <option value="caption">Caption</option>
                </select>

                {/* Thumbnail size — only useful in gallery mode */}
                {viewMode === 'gallery' && (
                    <div className="flex items-center gap-1.5">
                        <svg className="w-3 h-3 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                        </svg>
                        <input
                            type="range"
                            min="80"
                            max="320"
                            step="20"
                            value={thumbnailSize}
                            onChange={e => setThumbnailSize(Number(e.target.value))}
                            className="w-18 h-1 accent-blue-500"
                        />
                    </div>
                )}

                {/* View mode toggle */}
                <div className="flex border border-gray-600 rounded overflow-hidden">
                    <button
                        onClick={() => { setViewMode('gallery'); focusGallery(); }}
                        title="Gallery view"
                        className={`px-2 py-1 text-xs transition-colors ${viewMode === 'gallery' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                    >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                        </svg>
                    </button>
                    <button
                        onClick={() => { setViewMode('list'); focusGallery(); }}
                        title="List view"
                        className={`px-2 py-1 text-xs transition-colors ${viewMode === 'list' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                    >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                        </svg>
                    </button>
                    <button
                        onClick={() => setViewMode('single')}
                        title="Single image view"
                        className={`px-2 py-1 text-xs transition-colors ${viewMode === 'single' ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                    >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4h16v16H4z" />
                        </svg>
                    </button>
                </div>

                <div className="w-px h-5 bg-gray-700" />

                {/* Selection info + actions */}
                <span className="text-[10px] text-gray-500 whitespace-nowrap">{selectedImages.length} sel</span>

                {selectedImages.length > 0 ? (
                    <>
                        <button onClick={clearSelection} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300" title="Deselect (Esc)">✕</button>
                        <button onClick={() => selectAllFiltered()} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300" title="Select all (Ctrl+A)">All</button>
                        {datasets.length > 0 && (
                            <select
                                value=""
                                onChange={async e => {
                                    const dsId = Number(e.target.value);
                                    if (!dsId) return;
                                    const ds = datasets.find(d => d.id === dsId);
                                    try {
                                        const res = await fetch('/api/datasets/add-images-to', {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ dataset_id: dsId, image_hashes: selectedImages }),
                                        });
                                        if (res.ok) {
                                            const data = await res.json();
                                            setStatus(`Added ${data.added} image(s) to "${ds?.name}"`, 'success');
                                            refreshDatasets();
                                            if (currentDataset === ds?.name) qc.invalidateQueries({ queryKey: ['images'] });
                                        }
                                    } catch {
                                        setStatus('Failed to add to dataset', 'error');
                                    }
                                }}
                                className="bg-gray-700 border border-gray-600 rounded px-1 py-0.5 text-[10px] text-gray-300 focus:outline-none"
                                title="Add selection to dataset"
                            >
                                <option value="">+ Dataset</option>
                                {datasets.map(d => (
                                    <option key={d.id} value={d.id}>{d.name} ({d.image_count})</option>
                                ))}
                            </select>
                        )}
                        {currentDataset && (
                            <button onClick={handleRemoveSelectionFromDataset} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px]" title="Remove from current dataset">-DS</button>
                        )}
                        <button onClick={handleDeleteSelected} className="px-2 py-1 bg-red-900/60 hover:bg-red-800/60 rounded text-[10px] text-red-300" title="Delete (Del)">Del</button>
                    </>
                ) : (
                    <button onClick={() => selectAllFiltered()} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300" title="Select all (Ctrl+A)">Select All</button>
                )}
            </div>

            {/* Gallery + TagEditor row */}
            <div className="flex-1 flex min-h-0">
                {viewMode === 'single' ? (
                    <SingleImageView
                        allImages={getAllLoadedHashes()}
                    />
                ) : (
                    <ImageGallery
                        onSelectImage={handleSelectImage}
                        selectedImages={selectedImages}
                        currentDataset={currentDataset}
                        focusRef={galleryFocusRef}
                    />
                )}

                {/* Resizable Splitter */}
                <div
                    className="w-1.5 flex-shrink-0 bg-gray-700 hover:bg-blue-500 cursor-col-resize transition-colors"
                    onMouseDown={(e) => {
                        e.preventDefault();
                        const startX = e.clientX;
                        const startWidth = tagEditorWidth;
                        const onMove = (ev: MouseEvent) => {
                            const delta = startX - ev.clientX;
                            setTagEditorWidth(startWidth + delta);
                        };
                        const onUp = () => {
                            document.removeEventListener('mousemove', onMove);
                            document.removeEventListener('mouseup', onUp);
                            document.body.style.cursor = '';
                            document.body.style.userSelect = '';
                        };
                        document.body.style.cursor = 'col-resize';
                        document.body.style.userSelect = 'none';
                        document.addEventListener('mousemove', onMove);
                        document.addEventListener('mouseup', onUp);
                    }}
                />

                {/* Tag Editor Panel */}
                <div
                    className="flex-shrink-0 bg-gray-800 border-l border-gray-700 flex flex-col overflow-hidden"
                    style={{ width: `${tagEditorWidth}px` }}
                >
                    <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0">
                        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Tag Editor</h2>
                    </div>
                    <TagEditor />
                </div>
            </div>

            {/* Modals */}
            {showLibraryPicker && (
                <LibraryPickerDialog
                    onClose={() => setShowLibraryPicker(false)}
                    onLoad={loadLibraryPath}
                    managed={managedMode}
                />
            )}
            {showImport && (
                <ImportDialog
                    onClose={() => setShowImport(false)}
                    onDone={() => { refreshLibrary(); qc.invalidateQueries({ queryKey: ['images'] }); }}
                />
            )}
            {showCreateLibrary && (
                <CreateLibraryDialog
                    onClose={() => setShowCreateLibrary(false)}
                    onDone={() => { refreshLibrary(); refreshDatasets(); qc.invalidateQueries({ queryKey: ['images'] }); }}
                />
            )}
            {showManageLibraries && (
                <ManageLibrariesDialog
                    onClose={() => setShowManageLibraries(false)}
                    onLibraryChanged={() => { refreshLibrary(); refreshDatasets(); qc.invalidateQueries({ queryKey: ['images'] }); }}
                    currentPath={libraryInfo?.path}
                />
            )}
            {showExport && (
                <ExportDialog
                    onClose={() => setShowExport(false)}
                    datasets={datasets}
                    currentDataset={currentDataset}
                    selectedCount={selectedImages.length}
                    selectedHashes={selectedImages}
                />
            )}
            {showTaxonomy && <TaxonomyPanel onClose={() => setShowTaxonomy(false)} />}
            {showFindReplace && (
                <FindReplaceDialog
                    onClose={() => setShowFindReplace(false)}
                    datasets={datasets}
                    currentDataset={currentDataset}
                    selectedCount={selectedImages.length}
                    selectedHashes={selectedImages}
                />
            )}
            {showCreateDatasetDialog && (
                <InputDialog
                    title="New Dataset"
                    fields={[{ label: 'Dataset name', placeholder: 'my-dataset', key: 'name' }]}
                    onConfirm={v => v.name && handleCreateDataset(v.name)}
                    onClose={() => setShowCreateDatasetDialog(false)}
                />
            )}
            {showManageDatasets && (
                <ManageDatasetsDialog
                    onClose={() => setShowManageDatasets(false)}
                    onChanged={() => { refreshDatasets(); }}
                    currentDataset={currentDataset}
                />
            )}
            {showHFPullDialog && (
                <InputDialog
                    title="Pull from HF Hub"
                    fields={[
                        { label: 'Repository ID', placeholder: 'user/dataset-name', key: 'repo_id' },
                        { label: 'Local dataset name (optional)', placeholder: '', key: 'dataset_name' },
                    ]}
                    onConfirm={handlePullHF}
                    onClose={() => setShowHFPullDialog(false)}
                />
            )}
            {showHFPushDialog && (
                <InputDialog
                    title="Push to HF Hub"
                    fields={[{ label: 'Target repository ID', placeholder: 'user/my-dataset', key: 'repo_id' }]}
                    onConfirm={handlePushHF}
                    onClose={() => setShowHFPushDialog(false)}
                />
            )}

            {showDuplicateTags && <DuplicateTagsDialog onClose={() => setShowDuplicateTags(false)} />}

            {showRestoreDeleted && (
                <RestoreDeletedDialog
                    onClose={() => setShowRestoreDeleted(false)}
                    onRestored={() => { qc.invalidateQueries({ queryKey: ['images'] }); refreshLibrary(); }}
                    datasets={datasets}
                />
            )}

            {/* Delete / Remove confirm dialog */}
            {deleteDialog && (
                <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" onClick={() => setDeleteDialog(null)}>
                    <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 w-80 shadow-2xl" onClick={e => e.stopPropagation()}>
                        <p className="text-sm text-white font-semibold mb-1">
                            {deleteDialog.hashes.length === 1 ? 'Remove image?' : `Remove ${deleteDialog.hashes.length} images?`}
                        </p>
                        <p className="text-[11px] text-gray-400 mb-4">Choose how to remove {deleteDialog.hashes.length === 1 ? 'this image' : 'these images'}.</p>
                        <div className="flex flex-col gap-2">
                            {currentDataset && (
                                <button
                                    autoFocus
                                    onClick={() => performDelete('dataset')}
                                    className="w-full px-3 py-2 bg-blue-700 hover:bg-blue-600 text-white rounded text-xs font-medium text-left"
                                >
                                    Remove from <span className="font-bold">"{currentDataset}"</span>
                                    <span className="block text-[10px] text-blue-300 font-normal">Stays in library</span>
                                </button>
                            )}
                            <button
                                autoFocus={!currentDataset}
                                onClick={() => performDelete('library')}
                                className="w-full px-3 py-2 bg-red-800/70 hover:bg-red-700/80 text-red-200 rounded text-xs font-medium text-left"
                            >
                                Delete from Library
                                <span className="block text-[10px] text-red-400 font-normal">Permanent — cannot be undone</span>
                            </button>
                            <button
                                onClick={() => setDeleteDialog(null)}
                                className="w-full px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <StatusToast />
        </div>
    );
}

function DuplicateTagsDialog({ onClose }: { onClose: () => void }) {
    const { setStatus } = useTaggerStore();
    const qc = useQueryClient();

    const [scanResult, setScanResult] = useState<{
        images: { hash: string; name: string; duplicates: { tag: string; count: number }[] }[];
        total_images: number;
        total_duplicates: number;
    } | null>(null);
    const [scanning, setScanning] = useState(true);
    const [fixing, setFixing] = useState(false);

    // Auto-scan on open
    useEffect(() => {
        setScanning(true);
        fetch('/api/tags/find-duplicates')
            .then(r => r.json())
            .then(data => {
                setScanResult(data);
                setScanning(false);
            })
            .catch(() => {
                setScanning(false);
                setStatus('Failed to scan for duplicates', 'error');
            });
    }, [setStatus]);

    const handleFixAll = async () => {
        if (!scanResult || scanResult.total_images === 0) return;
        setFixing(true);
        try {
            const res = await fetch('/api/tags/deduplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hashes: null }),
            });
            const data = await res.json();
            if (data.status === 'success') {
                setStatus(`Removed ${data.duplicates_removed} duplicate tags from ${data.images_fixed} images (Ctrl+Z to undo)`, 'success');
                qc.invalidateQueries({ queryKey: ['images'] });
                qc.invalidateQueries({ queryKey: ['image'] });
                qc.invalidateQueries({ queryKey: ['tag-counts'] });
                onClose();
            } else {
                setStatus('No duplicates to fix', 'info');
            }
        } catch {
            setStatus('Failed to deduplicate', 'error');
        }
        setFixing(false);
    };

    const handleFixOne = async (hash: string) => {
        setFixing(true);
        try {
            const res = await fetch('/api/tags/deduplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hashes: [hash] }),
            });
            const data = await res.json();
            if (data.status === 'success') {
                setStatus(`Removed ${data.duplicates_removed} duplicates (Ctrl+Z to undo)`, 'success');
                qc.invalidateQueries({ queryKey: ['images'] });
                qc.invalidateQueries({ queryKey: ['image', hash] });
                // Re-scan
                const scan = await fetch('/api/tags/find-duplicates').then(r => r.json());
                setScanResult(scan);
            }
        } catch {
            setStatus('Failed to deduplicate', 'error');
        }
        setFixing(false);
    };

    return (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center" onClick={onClose}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-[550px] shadow-2xl max-h-[70vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-sm font-bold text-white">Find Duplicate Tags</h2>
                    <button onClick={onClose} className="text-gray-400 hover:text-white text-lg leading-none">✕</button>
                </div>

                {scanning ? (
                    <div className="flex items-center justify-center py-8">
                        <div className="text-sm text-gray-400">Scanning for duplicate tags...</div>
                    </div>
                ) : scanResult && scanResult.total_images === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 gap-2">
                        <p className="text-sm text-green-400">No duplicate tags found.</p>
                        <p className="text-xs text-gray-500">All images have unique tag lists.</p>
                    </div>
                ) : scanResult ? (
                    <>
                        <div className="flex items-center justify-between mb-3">
                            <p className="text-xs text-gray-400">
                                Found <span className="text-yellow-400 font-semibold">{scanResult.total_duplicates}</span> duplicate tag{scanResult.total_duplicates !== 1 ? 's' : ''} across <span className="text-yellow-400 font-semibold">{scanResult.total_images}</span> image{scanResult.total_images !== 1 ? 's' : ''}
                            </p>
                            <button
                                onClick={handleFixAll}
                                disabled={fixing}
                                className="px-3 py-1.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white text-xs rounded font-semibold"
                            >
                                {fixing ? 'Fixing...' : 'Fix All'}
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto space-y-2 min-h-0">
                            {scanResult.images.map(img => (
                                <div key={img.hash} className="bg-gray-900 rounded p-3 border border-gray-700">
                                    <div className="flex items-center justify-between mb-2">
                                        <div className="flex items-center gap-2 min-w-0">
                                            <img
                                                src={`/api/images/thumbnail/${img.hash}`}
                                                alt=""
                                                className="w-8 h-8 rounded object-cover flex-shrink-0"
                                            />
                                            <span className="text-xs text-gray-300 truncate">{img.name}</span>
                                        </div>
                                        <button
                                            onClick={() => handleFixOne(img.hash)}
                                            disabled={fixing}
                                            className="text-[10px] text-blue-400 hover:text-blue-300 disabled:opacity-40 flex-shrink-0"
                                        >
                                            Fix
                                        </button>
                                    </div>
                                    <div className="flex flex-wrap gap-1">
                                        {img.duplicates.map(d => (
                                            <span
                                                key={d.tag}
                                                className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-yellow-900/30 border border-yellow-700/40 rounded text-[10px] text-yellow-300"
                                            >
                                                {d.tag}
                                                <span className="text-yellow-500">x{d.count}</span>
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>

                        <p className="text-[10px] text-gray-600 mt-3">Duplicates are removed keeping the first occurrence. Use Ctrl+Z to undo.</p>
                    </>
                ) : null}
            </div>
        </div>
    );
}

function App() {
    return (
        <QueryClientProvider client={queryClient}>
            <AppContent />
        </QueryClientProvider>
    );
}

export default App;
