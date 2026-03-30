import { useState, useEffect, useCallback, useRef } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { ImageGallery } from './Gallery';
import { TagEditor } from './TagEditor';
import { TaxonomyPanel } from './TaxonomyPanel';
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
// Simple text-input dialog (replaces prompt())
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
                        <button
                            type="submit"
                            className="flex-1 bg-blue-700 hover:bg-blue-600 text-white rounded py-2 text-xs font-semibold"
                        >
                            OK
                        </button>
                        <button type="button" onClick={onClose} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">
                            Cancel
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Import Dialog
// -----------------------------------------------------------------------
function ImportDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
    const [folderPath, setFolderPath] = useState('');
    const [recursive, setRecursive] = useState(true);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ added: number; skipped: number; errors: number } | null>(null);
    const { setStatus } = useTaggerStore();

    const handlePickFolder = async () => {
        if (window.electronAPI) {
            const p = await window.electronAPI.openFolderDialog();
            if (p) setFolderPath(p);
        }
    };

    const handleImport = async () => {
        if (!folderPath.trim()) return;
        setLoading(true);
        try {
            const res = await fetch('/api/library/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: folderPath, recursive })
            });
            if (res.ok) {
                const data = await res.json();
                setResult(data);
                setStatus(`Imported ${data.added} images`, 'success');
                onDone();
            } else {
                const err = await res.json();
                setStatus('Import failed: ' + err.detail, 'error');
            }
        } catch {
            setStatus('Import failed', 'error');
        }
        setLoading(false);
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center" onClick={onClose}>
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-96 shadow-2xl" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-4">Import Images</h2>

                <div className="flex gap-2 mb-3">
                    <input
                        type="text"
                        value={folderPath}
                        onChange={e => setFolderPath(e.target.value)}
                        placeholder="Folder path..."
                        className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                        autoFocus
                    />
                    {window.electronAPI && (
                        <button
                            onClick={handlePickFolder}
                            className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-xs text-white"
                        >
                            Browse
                        </button>
                    )}
                </div>

                <label className="flex items-center gap-2 text-xs text-gray-300 mb-4">
                    <input type="checkbox" checked={recursive} onChange={e => setRecursive(e.target.checked)} />
                    Scan subdirectories
                </label>

                {result && (
                    <div className="mb-4 p-2 bg-gray-900 rounded text-xs text-gray-300">
                        Added: {result.added} | Skipped (duplicates): {result.skipped} | Errors: {result.errors}
                    </div>
                )}

                <div className="flex gap-2">
                    <button
                        onClick={handleImport}
                        disabled={loading || !folderPath.trim()}
                        className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded py-2 text-xs font-semibold"
                    >
                        {loading ? 'Importing...' : 'Import'}
                    </button>
                    <button onClick={onClose} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}

// -----------------------------------------------------------------------
// Create Library Dialog
// -----------------------------------------------------------------------
function CreateLibraryDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
    const [name, setName] = useState('');
    const [folderPath, setFolderPath] = useState('');
    const [loading, setLoading] = useState(false);
    const { setStatus } = useTaggerStore();

    const handlePickFolder = async () => {
        if (window.electronAPI) {
            const p = await window.electronAPI.openFolderDialog();
            if (p) setFolderPath(p);
        }
    };

    const handleCreate = async () => {
        if (!name.trim() || !folderPath.trim()) return;
        setLoading(true);
        try {
            const res = await fetch('/api/library/create-new', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name.trim(), path: folderPath })
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
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-96 shadow-2xl" onClick={e => e.stopPropagation()}>
                <h2 className="text-sm font-bold text-white mb-4">New Library</h2>

                <input
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="Library name..."
                    className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 mb-3"
                    autoFocus
                />

                <div className="flex gap-2 mb-4">
                    <input
                        type="text"
                        value={folderPath}
                        onChange={e => setFolderPath(e.target.value)}
                        placeholder="Folder path..."
                        className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                    />
                    {window.electronAPI && (
                        <button onClick={handlePickFolder} className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-xs text-white">
                            Browse
                        </button>
                    )}
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={handleCreate}
                        disabled={loading || !name.trim() || !folderPath.trim()}
                        className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded py-2 text-xs font-semibold"
                    >
                        {loading ? 'Creating...' : 'Create Library'}
                    </button>
                    <button onClick={onClose} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs">
                        Cancel
                    </button>
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
// Main App Content
// -----------------------------------------------------------------------
function AppContent() {
    const [libraryInfo, setLibraryInfo] = useState<{ name: string; path: string; count: number } | null>(null);
    const [datasets, setDatasets] = useState<Dataset[]>([]);
    const [showImport, setShowImport] = useState(false);
    const [showCreateLibrary, setShowCreateLibrary] = useState(false);
    const [showTaxonomy, setShowTaxonomy] = useState(false);
    const [showOpenLibraryDialog, setShowOpenLibraryDialog] = useState(false);
    const [showCreateDatasetDialog, setShowCreateDatasetDialog] = useState(false);
    const [showHFPullDialog, setShowHFPullDialog] = useState(false);
    const [showHFPushDialog, setShowHFPushDialog] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');

    const {
        selectedImages, toggleSelection, addToSelection, setActiveImage,
        activeImage, currentDataset, setDataset, clearSelection, selectAll,
        thumbnailSize, setThumbnailSize, sortBy, setSortBy, setStatus
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
    }, []);

    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

            if (e.key === 'Escape') {
                clearSelection();
            } else if (e.key === 'a' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                const allHashes = getAllLoadedHashes();
                if (allHashes.length > 0) selectAll(allHashes);
            } else if (e.key === 'Delete') {
                if (selectedImages.length > 0) {
                    e.preventDefault();
                    handleDeleteSelected();
                }
            } else if (e.key === 'z' && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
                e.preventDefault();
                handleUndo();
            } else if ((e.key === 'y' && (e.ctrlKey || e.metaKey)) || (e.key === 'z' && e.shiftKey && e.ctrlKey)) {
                e.preventDefault();
                handleRedo();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedImages, sortBy]);

    const getAllLoadedHashes = (): string[] => {
        const data = qc.getQueryData<{ pages: { items: { hash: string }[] }[] }>(['images', sortBy]);
        return data?.pages.flatMap(p => p.items.map(img => img.hash)) ?? [];
    };

    const handleSelectImage = (hash: string, index: number, shiftKey: boolean) => {
        if (shiftKey && lastClickedIdx.current !== null) {
            const allHashes = getAllLoadedHashes();
            const start = Math.min(lastClickedIdx.current, index);
            const end = Math.max(lastClickedIdx.current, index);
            const rangeHashes = allHashes.slice(start, end + 1);
            addToSelection(rangeHashes);
        } else {
            toggleSelection(hash);
            lastClickedIdx.current = index;
        }
        setActiveImage(hash);
    };

    const handleOpenLibrary = async () => {
        if (!window.electronAPI) {
            setShowOpenLibraryDialog(true);
            return;
        }
        const filePath = await window.electronAPI.openLibraryDialog();
        if (filePath) await loadLibraryPath(filePath);
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
            qc.invalidateQueries({ queryKey: ['images'] });
            setStatus('Library loaded', 'success');
        } catch {
            setStatus('Error loading library', 'error');
        }
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

    const handleDeleteSelected = async () => {
        if (selectedImages.length === 0) return;
        if (!confirm(`Delete ${selectedImages.length} image(s)?`)) return;
        try {
            const res = await fetch('/api/images/delete-batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hashes: selectedImages })
            });
            if (res.ok) {
                const data = await res.json();
                clearSelection();
                qc.invalidateQueries({ queryKey: ['images'] });
                refreshLibrary();
                setStatus(`Deleted ${data.deleted} image(s)`, 'success');
            }
        } catch {
            setStatus('Delete failed', 'error');
        }
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
        <div className="flex h-screen w-full bg-gray-900 text-gray-100 overflow-hidden font-sans">
            {/* Sidebar */}
            <div className="w-52 flex-shrink-0 bg-gray-800 border-r border-gray-700 flex flex-col">
                <div className="p-3 border-b border-gray-700">
                    <h1 className="text-sm font-bold text-white tracking-tight">Image Tagger</h1>
                    {libraryInfo ? (
                        <p className="text-[11px] text-blue-400 mt-0.5 truncate" title={libraryInfo.path}>
                            {libraryInfo.name} ({libraryInfo.count})
                        </p>
                    ) : (
                        <p className="text-[11px] text-yellow-500 mt-0.5">No Library</p>
                    )}
                </div>

                <div className="p-2 space-y-1.5 border-b border-gray-700">
                    <button onClick={handleOpenLibrary} className="w-full px-2 py-1.5 bg-blue-700 hover:bg-blue-600 rounded text-xs font-medium transition-colors">
                        Open Library
                    </button>
                    <button onClick={() => setShowCreateLibrary(true)} className="w-full px-2 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs font-medium transition-colors">
                        New Library
                    </button>
                    <button onClick={handleScan} className="w-full px-2 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs font-medium transition-colors">
                        Scan for New Files
                    </button>
                    <button onClick={() => setShowImport(true)} className="w-full px-2 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs font-medium transition-colors">
                        Import Images...
                    </button>
                    <button onClick={() => setShowTaxonomy(true)} className="w-full px-2 py-1.5 bg-purple-800 hover:bg-purple-700 rounded text-xs font-medium transition-colors">
                        Tag Taxonomy
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-2">
                    <div className="flex justify-between items-center mb-1.5">
                        <h2 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Datasets</h2>
                        <button
                            onClick={() => setShowCreateDatasetDialog(true)}
                            className="text-blue-400 hover:text-blue-300 w-5 h-5 text-lg font-bold flex items-center justify-center"
                            title="New Dataset"
                        >+</button>
                    </div>
                    <ul className="space-y-0.5">
                        <li
                            onClick={() => handleSwitchDataset(null)}
                            className={`px-2 py-1 rounded text-[11px] cursor-pointer border transition-colors ${!currentDataset ? 'bg-blue-900/60 text-blue-100 border-blue-700/50' : 'text-gray-400 border-transparent hover:bg-gray-700/50'}`}
                        >
                            Library (All Images)
                        </li>
                        {datasets.map(d => (
                            <li
                                key={d.id}
                                onClick={() => handleSwitchDataset(d.name)}
                                className={`px-2 py-1 rounded text-[11px] cursor-pointer border transition-colors ${currentDataset === d.name ? 'bg-blue-900/60 text-blue-100 border-blue-700/50' : 'text-gray-400 border-transparent hover:bg-gray-700/50'}`}
                            >
                                <div className="truncate">{d.name}</div>
                                <div className="text-[9px] text-gray-600">{d.image_count} images</div>
                            </li>
                        ))}
                    </ul>

                    <div className="mt-4">
                        <h2 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Integrations</h2>
                        <button
                            onClick={() => setShowHFPullDialog(true)}
                            className="w-full px-2 py-1.5 bg-orange-700 hover:bg-orange-600 rounded text-xs font-medium transition-colors flex items-center justify-center gap-1.5"
                        >
                            <span>🤗</span><span>Pull from HF Hub</span>
                        </button>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0">
                {/* Toolbar */}
                <div className="flex-shrink-0 h-11 border-b border-gray-700 bg-gray-800/90 flex items-center px-3 gap-2">
                    {/* Search */}
                    <div className="relative flex-1 max-w-xs">
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleSearch(searchQuery)}
                            onBlur={() => handleSearch(searchQuery)}
                            placeholder="Filter tags (tag AND NOT other)..."
                            className="w-full bg-gray-900 border border-gray-600 rounded-full px-3 py-1 text-xs text-white focus:outline-none focus:border-blue-500 pl-7"
                        />
                        <svg className="w-3.5 h-3.5 absolute left-2.5 top-1.5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                    </div>

                    {/* Sort */}
                    <select
                        value={sortBy}
                        onChange={e => { setSortBy(e.target.value as any); qc.invalidateQueries({ queryKey: ['images'] }); }}
                        className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none"
                    >
                        <option value="default">Order: Default</option>
                        <option value="name">Order: Name</option>
                        <option value="caption">Order: Caption</option>
                    </select>

                    {/* Thumbnail size */}
                    <div className="flex items-center gap-1.5">
                        <svg className="w-3.5 h-3.5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                        </svg>
                        <input
                            type="range"
                            min="80"
                            max="320"
                            step="20"
                            value={thumbnailSize}
                            onChange={e => setThumbnailSize(Number(e.target.value))}
                            className="w-20 h-1 accent-blue-500"
                        />
                    </div>

                    <div className="w-px h-5 bg-gray-600" />

                    {/* Selection info + actions */}
                    <span className="text-[10px] text-gray-500 whitespace-nowrap">{selectedImages.length} selected</span>

                    {selectedImages.length > 0 ? (
                        <>
                            <button onClick={clearSelection} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300" title="Deselect all (Esc)">
                                Deselect
                            </button>
                            <button
                                onClick={() => selectAll(getAllLoadedHashes())}
                                className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300"
                                title="Select all (Ctrl+A)"
                            >
                                All
                            </button>
                            {currentDataset && (
                                <>
                                    <button onClick={handleAddSelectionToDataset} className="px-2 py-1 bg-blue-800 hover:bg-blue-700 rounded text-[10px]" title="Add to dataset">
                                        + Dataset
                                    </button>
                                    <button onClick={handleRemoveSelectionFromDataset} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px]" title="Remove from dataset">
                                        - Dataset
                                    </button>
                                </>
                            )}
                            <button onClick={handleDeleteSelected} className="px-2 py-1 bg-red-900/60 hover:bg-red-800/60 rounded text-[10px] text-red-300" title="Delete (Del)">
                                Delete
                            </button>
                        </>
                    ) : (
                        <button
                            onClick={() => selectAll(getAllLoadedHashes())}
                            className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-[10px] text-gray-300"
                            title="Select all (Ctrl+A)"
                        >
                            Select All
                        </button>
                    )}

                    <div className="w-px h-5 bg-gray-600" />

                    {/* Undo/Redo */}
                    <button onClick={handleUndo} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs" title="Undo (Ctrl+Z)">↩</button>
                    <button onClick={handleRedo} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs" title="Redo (Ctrl+Y)">↪</button>

                    <div className="ml-auto">
                        <button onClick={() => setShowHFPushDialog(true)} className="px-2 py-1 bg-green-700 hover:bg-green-600 rounded text-xs font-medium">
                            Push to HF
                        </button>
                    </div>
                </div>

                {/* Gallery + TagEditor row */}
                <div className="flex-1 flex min-h-0">
                    <ImageGallery
                        onSelectImage={handleSelectImage}
                        selectedImages={selectedImages}
                        currentDataset={currentDataset}
                    />

                    {/* Tag Editor Panel */}
                    <div className="w-64 flex-shrink-0 bg-gray-800 border-l border-gray-700 flex flex-col overflow-hidden">
                        <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0">
                            <h2 className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Tag Editor</h2>
                        </div>
                        <TagEditor />
                    </div>
                </div>
            </div>

            {/* Modals */}
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
            {showTaxonomy && <TaxonomyPanel onClose={() => setShowTaxonomy(false)} />}

            {showOpenLibraryDialog && (
                <InputDialog
                    title="Open Library"
                    fields={[{ label: 'Path', placeholder: '/path/to/library', key: 'path' }]}
                    onConfirm={v => v.path && loadLibraryPath(v.path)}
                    onClose={() => setShowOpenLibraryDialog(false)}
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
                    fields={[
                        { label: 'Target repository ID', placeholder: 'user/my-dataset', key: 'repo_id' },
                    ]}
                    onConfirm={handlePushHF}
                    onClose={() => setShowHFPushDialog(false)}
                />
            )}

            <StatusToast />
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
