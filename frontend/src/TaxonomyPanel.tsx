import { useState, useCallback, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTaggerStore } from './store';

interface Category {
    id: number;
    name: string;
    sort_order: number;
    color: string | null;
}

interface TaxonomyTag {
    value: string;
    count: number;
    category_id: number | null;
    category_name: string | null;
    color: string | null;
}

interface TaxonomyPanelProps {
    onClose: () => void;
}

const DEFAULT_COLORS = [
    '#ef4444', '#f97316', '#eab308', '#22c55e',
    '#06b6d4', '#3b82f6', '#8b5cf6', '#ec4899',
    '#6b7280',
];

export function TaxonomyPanel({ onClose }: TaxonomyPanelProps) {
    const { setStatus } = useTaggerStore();
    const qc = useQueryClient();

    const [filterCatId, setFilterCatId] = useState<number | null | 'all'>('all');
    const [showUnassigned, setShowUnassigned] = useState(false);
    const [tagSearch, setTagSearch] = useState('');
    const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
    const [newCatName, setNewCatName] = useState('');
    const [newCatColor, setNewCatColor] = useState(DEFAULT_COLORS[5]);
    const [editingCat, setEditingCat] = useState<Category | null>(null);

    // Create-new-tag form
    const [newTagValue, setNewTagValue] = useState('');

    // Tag editing state
    const [editingTagValue, setEditingTagValue] = useState<string | null>(null);
    const [editingTagDraft, setEditingTagDraft] = useState('');
    const editInputRef = useRef<HTMLInputElement>(null);

    // Keyboard focus for tag list
    const [focusedIndex, setFocusedIndex] = useState(-1);
    const [lastClickedIndex, setLastClickedIndex] = useState(-1);
    const tagListRef = useRef<HTMLDivElement>(null);

    // Find & replace
    const [showFindReplace, setShowFindReplace] = useState(false);
    const [findText, setFindText] = useState('');
    const [replaceText, setReplaceText] = useState('');
    const [findCaseSensitive, setFindCaseSensitive] = useState(false);
    const findInputRef = useRef<HTMLInputElement>(null);

    const { data: categoriesData, isLoading: loadingCats } = useQuery({
        queryKey: ['taxonomy-categories'],
        queryFn: async () => {
            const res = await fetch('/api/taxonomy/categories');
            return res.json() as Promise<{ categories: Category[] }>;
        },
    });

    const { data: tagsData, isLoading: loadingTags } = useQuery({
        queryKey: ['taxonomy-tags'],
        queryFn: async () => {
            const res = await fetch('/api/taxonomy/tags');
            return res.json() as Promise<{ tags: TaxonomyTag[] }>;
        },
    });

    const categories = categoriesData?.categories ?? [];
    const allTags = tagsData?.tags ?? [];

    const createCategoryMutation = useMutation({
        mutationFn: async (name: string) => {
            const res = await fetch('/api/taxonomy/categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, sort_order: categories.length, color: newCatColor }),
            });
            return res.json();
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['taxonomy-categories'] });
            setNewCatName('');
            setStatus('Category created', 'success');
        },
    });

    const updateCategoryMutation = useMutation({
        mutationFn: async (cat: Category) => {
            const res = await fetch(`/api/taxonomy/categories/${cat.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: cat.name, sort_order: cat.sort_order, color: cat.color }),
            });
            return res.json();
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['taxonomy-categories'] });
            qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
            setEditingCat(null);
            setStatus('Category updated', 'success');
        },
    });

    const deleteCategoryMutation = useMutation({
        mutationFn: async (catId: number) => {
            const res = await fetch(`/api/taxonomy/categories/${catId}`, { method: 'DELETE' });
            return res.json();
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['taxonomy-categories'] });
            qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
            setStatus('Category deleted', 'success');
        },
    });

    const assignTagMutation = useMutation({
        mutationFn: async ({ tag_value, category_id }: { tag_value: string; category_id: number | null }) => {
            const res = await fetch('/api/taxonomy/assign', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag_value, category_id }),
            });
            return res.json();
        },
        onSuccess: async () => {
            await qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
        },
    });

    const bulkAssignMutation = useMutation({
        mutationFn: async ({ tag_values, category_id }: { tag_values: string[]; category_id: number | null }) => {
            const res = await fetch('/api/taxonomy/assign-bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag_values, category_id }),
            });
            return res.json();
        },
        onSuccess: async (data) => {
            await qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
            setSelectedTags(new Set());
            setStatus(`Assigned ${data.assigned} tags`, 'success');
        },
    });

    const globalRenameMutation = useMutation({
        mutationFn: async ({ old_value, new_value }: { old_value: string; new_value: string }) => {
            const res = await fetch('/api/tags/global-rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ old_value, new_value }),
            });
            return res.json();
        },
        onSuccess: (data) => {
            qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
            qc.invalidateQueries({ queryKey: ['tag-counts'] });
            setEditingTagValue(null);
            setEditingTagDraft('');
            if (data.status === 'noop') {
                setStatus('Rename skipped (empty or unchanged)', 'info');
            } else if (data.renamed > 0) {
                setStatus(`Renamed on ${data.renamed} image${data.renamed === 1 ? '' : 's'}`, 'success');
            } else if (data.taxonomy_updated) {
                setStatus('Tag renamed in taxonomy', 'success');
            } else {
                setStatus('Tag renamed', 'success');
            }
        },
    });

    const globalDeleteMutation = useMutation({
        mutationFn: async (values: string[]) => {
            const res = await fetch('/api/tags/global-delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ values }),
            });
            return res.json();
        },
        onSuccess: (data) => {
            qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
            qc.invalidateQueries({ queryKey: ['tag-counts'] });
            setSelectedTags(new Set());
            setStatus(`Deleted from ${data.removed} images`, 'success');
        },
    });

    const filteredTags = allTags.filter(t => {
        if (tagSearch && !t.value.toLowerCase().includes(tagSearch.toLowerCase())) return false;
        if (showUnassigned && t.category_id !== null) return false;
        if (filterCatId !== 'all' && filterCatId !== null && t.category_id !== filterCatId) return false;
        if (filterCatId === null && t.category_id !== null) return false;
        return true;
    });

    const toggleTag = useCallback((value: string, index: number, e: React.MouseEvent, fromCheckbox = false) => {
        if (e.shiftKey && lastClickedIndex >= 0) {
            // Shift+Click: range select (with Ctrl held, add to existing; otherwise replace)
            const start = Math.min(lastClickedIndex, index);
            const end = Math.max(lastClickedIndex, index);
            setSelectedTags(prev => {
                const next = (e.ctrlKey || e.metaKey) ? new Set(prev) : new Set<string>();
                for (let i = start; i <= end; i++) {
                    next.add(filteredTags[i].value);
                }
                return next;
            });
        } else if (e.ctrlKey || e.metaKey || fromCheckbox) {
            // Ctrl+Click or checkbox click: toggle single without clearing
            setSelectedTags(prev => {
                const next = new Set(prev);
                if (next.has(value)) next.delete(value);
                else next.add(value);
                return next;
            });
        } else {
            // Plain click on row: if in multi-select mode (2+), toggle; otherwise exclusive select
            setSelectedTags(prev => {
                if (prev.size > 1) {
                    // Multi-select mode: toggle like gallery
                    const next = new Set(prev);
                    if (next.has(value)) next.delete(value);
                    else next.add(value);
                    return next;
                }
                // Single/no selection: exclusive select (click again to deselect)
                if (prev.size === 1 && prev.has(value)) return new Set();
                return new Set([value]);
            });
        }
        setLastClickedIndex(index);
        setFocusedIndex(index);
    }, [lastClickedIndex, filteredTags]);

    const selectAll = useCallback(() => {
        setSelectedTags(new Set(filteredTags.map(t => t.value)));
    }, [filteredTags]);

    const clearSelection = useCallback(() => {
        setSelectedTags(new Set());
        setFocusedIndex(-1);
    }, []);

    const startEditingTag = useCallback((value: string) => {
        setEditingTagValue(value);
        setEditingTagDraft(value);
    }, []);

    const commitTagEdit = useCallback(() => {
        if (!editingTagValue) return;
        const trimmed = editingTagDraft.trim();
        if (!trimmed || trimmed === editingTagValue) {
            setEditingTagValue(null);
            setEditingTagDraft('');
            return;
        }
        globalRenameMutation.mutate({ old_value: editingTagValue, new_value: trimmed });
    }, [editingTagValue, editingTagDraft, globalRenameMutation]);

    const cancelEdit = useCallback(() => {
        setEditingTagValue(null);
        setEditingTagDraft('');
    }, []);

    const computeReplacePairs = useCallback(() => {
        if (!findText) return [];
        const scope = selectedTags.size > 0
            ? filteredTags.filter(t => selectedTags.has(t.value))
            : filteredTags;
        const flags = findCaseSensitive ? 'g' : 'gi';
        const escaped = findText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const pairs: { old_value: string; new_value: string }[] = [];
        for (const t of scope) {
            // Fresh regex per iteration — avoids shared-lastIndex bugs with /g.
            let re: RegExp;
            try {
                re = new RegExp(escaped, flags);
            } catch {
                return [];
            }
            const next = t.value.replace(re, replaceText);
            if (next === t.value) continue;       // no match → skip
            if (next.trim() === '') continue;     // refuse to create empty tag
            pairs.push({ old_value: t.value, new_value: next });
        }
        return pairs;
    }, [findText, replaceText, findCaseSensitive, filteredTags, selectedTags]);

    const findMatchCount = computeReplacePairs().length;

    const runReplaceAll = useCallback(async () => {
        const pairs = computeReplacePairs();
        if (pairs.length === 0) {
            setStatus('No matches', 'info');
            return;
        }
        if (!confirm(`Rename ${pairs.length} tag${pairs.length > 1 ? 's' : ''} on all images?`)) return;
        let total = 0;
        for (const p of pairs) {
            try {
                const res = await fetch('/api/tags/global-rename', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(p),
                });
                const data = await res.json();
                total += data.renamed ?? 0;
            } catch { /* ignore */ }
        }
        await qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
        await qc.invalidateQueries({ queryKey: ['tag-counts'] });
        setStatus(`Replaced ${pairs.length} tags (${total} image updates)`, 'success');
    }, [computeReplacePairs, qc, setStatus]);

    const handleDeleteSelected = useCallback(() => {
        if (selectedTags.size === 0) return;
        const count = selectedTags.size;
        if (confirm(`Delete ${count} tag${count > 1 ? 's' : ''} from ALL images?`)) {
            globalDeleteMutation.mutate(Array.from(selectedTags));
        }
    }, [selectedTags, globalDeleteMutation]);

    // Focus edit input when editing starts
    useEffect(() => {
        if (editingTagValue && editInputRef.current) {
            editInputRef.current.focus();
            editInputRef.current.select();
        }
    }, [editingTagValue]);

    // Keyboard handler for tag list
    const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
        // Don't handle if we're editing a tag or in an input
        if (editingTagValue) {
            if (e.key === 'Escape') cancelEdit();
            if (e.key === 'Enter') commitTagEdit();
            return;
        }

        // Ctrl+F works even when inside inputs
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault();
            setShowFindReplace(true);
            setTimeout(() => findInputRef.current?.focus(), 0);
            return;
        }

        if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'SELECT') return;

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                setFocusedIndex(prev => {
                    const next = Math.min(prev + 1, filteredTags.length - 1);
                    if (e.shiftKey) {
                        setSelectedTags(s => {
                            const ns = new Set(s);
                            ns.add(filteredTags[next].value);
                            return ns;
                        });
                    }
                    return next;
                });
                break;
            case 'ArrowUp':
                e.preventDefault();
                setFocusedIndex(prev => {
                    const next = Math.max(prev - 1, 0);
                    if (e.shiftKey) {
                        setSelectedTags(s => {
                            const ns = new Set(s);
                            ns.add(filteredTags[next].value);
                            return ns;
                        });
                    }
                    return next;
                });
                break;
            case ' ':
                e.preventDefault();
                if (focusedIndex >= 0 && focusedIndex < filteredTags.length) {
                    const val = filteredTags[focusedIndex].value;
                    setSelectedTags(prev => {
                        const next = new Set(prev);
                        if (next.has(val)) next.delete(val);
                        else next.add(val);
                        return next;
                    });
                }
                break;
            case 'a':
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    selectAll();
                }
                break;
            case 'Delete':
            case 'Backspace':
                if (selectedTags.size > 0) {
                    e.preventDefault();
                    handleDeleteSelected();
                }
                break;
            case 'F2':
                if (focusedIndex >= 0 && focusedIndex < filteredTags.length) {
                    e.preventDefault();
                    startEditingTag(filteredTags[focusedIndex].value);
                }
                break;
            case 'Escape':
                e.preventDefault();
                clearSelection();
                break;
        }
    }, [editingTagValue, filteredTags, focusedIndex, selectedTags, selectAll, clearSelection, handleDeleteSelected, startEditingTag, cancelEdit, commitTagEdit]);

    // Scroll focused tag into view
    useEffect(() => {
        if (focusedIndex < 0 || !tagListRef.current) return;
        const el = tagListRef.current.querySelector(`[data-tag-index="${focusedIndex}"]`);
        el?.scrollIntoView({ block: 'nearest' });
    }, [focusedIndex]);

    const handleCreateCategory = (e: React.FormEvent) => {
        e.preventDefault();
        if (!newCatName.trim()) return;
        createCategoryMutation.mutate(newCatName.trim());
    };

    const createTagMutation = useMutation({
        mutationFn: async ({ tag_value, category_id }: { tag_value: string; category_id: number | null }) => {
            const res = await fetch('/api/taxonomy/assign', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag_value, category_id }),
            });
            return res.json();
        },
        onSuccess: async (_d, vars) => {
            await qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
            setStatus(`Added "${vars.tag_value}"`, 'success');
            setNewTagValue('');
        },
    });

    const handleCreateTag = (e: React.FormEvent) => {
        e.preventDefault();
        const trimmed = newTagValue.trim();
        if (!trimmed) return;
        // Target category: the currently filtered one if it's a real category,
        // otherwise null (unassigned).
        const targetCat = typeof filterCatId === 'number' ? filterCatId : null;
        if (allTags.some(t => t.value === trimmed)) {
            // Tag already exists — just (re)assign it so the user gets the
            // expected behavior of "this tag now lives in this category".
            createTagMutation.mutate({ tag_value: trimmed, category_id: targetCat });
        } else {
            createTagMutation.mutate({ tag_value: trimmed, category_id: targetCat });
        }
    };

    return (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-stretch justify-end" onClick={onClose}>
            <div
                className="w-full max-w-4xl bg-gray-900 flex flex-col shadow-2xl"
                onClick={e => e.stopPropagation()}
                onKeyDown={handleKeyDown}
                tabIndex={-1}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-gray-800 flex-shrink-0">
                    <h2 className="text-sm font-bold text-white">Tag Taxonomy</h2>
                    <div className="flex items-center gap-2">
                        <span className="text-[10px] text-gray-500">
                            Space=toggle  Shift+Click=range  Ctrl+A=all  F2=edit  Del=delete
                        </span>
                        <button onClick={onClose} className="text-gray-400 hover:text-white text-lg leading-none">✕</button>
                    </div>
                </div>

                <div className="flex-1 flex min-h-0">
                    {/* Categories panel */}
                    <div className="w-64 flex-shrink-0 border-r border-gray-700 flex flex-col bg-gray-850">
                        <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0">
                            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Categories</p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-2 space-y-1">
                            {/* All / Unassigned filters */}
                            <button
                                onClick={() => { setFilterCatId('all'); setShowUnassigned(false); }}
                                className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${filterCatId === 'all' && !showUnassigned ? 'bg-blue-700 text-white' : 'text-gray-300 hover:bg-gray-700'}`}
                            >
                                All tags ({allTags.length})
                            </button>
                            <button
                                onClick={() => { setShowUnassigned(true); setFilterCatId('all'); }}
                                className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${showUnassigned ? 'bg-yellow-800 text-yellow-100' : 'text-gray-400 hover:bg-gray-700'}`}
                            >
                                Unassigned ({allTags.filter(t => t.category_id === null).length})
                            </button>

                            <div className="border-t border-gray-700 my-1" />

                            {loadingCats ? (
                                <div className="space-y-1">
                                    {[...Array(3)].map((_, i) => <div key={i} className="h-7 bg-gray-700 rounded animate-pulse" />)}
                                </div>
                            ) : (
                                categories.map(cat => (
                                    editingCat?.id === cat.id ? (
                                        <div key={cat.id} className="p-2 bg-gray-700 rounded space-y-1.5">
                                            <input
                                                value={editingCat.name}
                                                onChange={e => setEditingCat({ ...editingCat, name: e.target.value })}
                                                className="w-full bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none"
                                                autoFocus
                                            />
                                            <div className="flex flex-wrap gap-1">
                                                {DEFAULT_COLORS.map(c => (
                                                    <button
                                                        key={c}
                                                        onClick={() => setEditingCat({ ...editingCat, color: c })}
                                                        className={`w-4 h-4 rounded-full border-2 ${editingCat.color === c ? 'border-white' : 'border-transparent'}`}
                                                        style={{ backgroundColor: c }}
                                                    />
                                                ))}
                                            </div>
                                            <div className="flex gap-1">
                                                <button
                                                    onClick={() => updateCategoryMutation.mutate(editingCat)}
                                                    className="flex-1 text-xs bg-blue-700 hover:bg-blue-600 rounded py-1 text-white"
                                                >Save</button>
                                                <button
                                                    onClick={() => setEditingCat(null)}
                                                    className="text-xs bg-gray-600 hover:bg-gray-500 rounded py-1 px-2 text-white"
                                                >✕</button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div
                                            key={cat.id}
                                            className={`group flex items-center justify-between px-2 py-1.5 rounded cursor-pointer transition-colors ${filterCatId === cat.id && !showUnassigned ? 'bg-gray-600' : 'hover:bg-gray-700/60'}`}
                                            onClick={() => { setFilterCatId(cat.id); setShowUnassigned(false); }}
                                        >
                                            <div className="flex items-center gap-2 min-w-0">
                                                <div
                                                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                                                    style={{ backgroundColor: cat.color ?? '#6b7280' }}
                                                />
                                                <span className="text-xs text-gray-200 truncate">{cat.name}</span>
                                                <span className="text-[10px] text-gray-500">
                                                    ({allTags.filter(t => t.category_id === cat.id).length})
                                                </span>
                                            </div>
                                            <div className="flex gap-1 opacity-0 group-hover:opacity-100">
                                                <button
                                                    onClick={e => { e.stopPropagation(); setEditingCat(cat); }}
                                                    className="text-[10px] text-gray-400 hover:text-blue-400"
                                                    title="Edit"
                                                >✎</button>
                                                <button
                                                    onClick={e => { e.stopPropagation(); if (confirm(`Delete category "${cat.name}"?`)) deleteCategoryMutation.mutate(cat.id); }}
                                                    className="text-[10px] text-gray-400 hover:text-red-400"
                                                    title="Delete"
                                                >✕</button>
                                            </div>
                                        </div>
                                    )
                                ))
                            )}
                        </div>

                        {/* New category form */}
                        <div className="p-2 border-t border-gray-700 flex-shrink-0">
                            <form onSubmit={handleCreateCategory} className="space-y-1.5">
                                <input
                                    value={newCatName}
                                    onChange={e => setNewCatName(e.target.value)}
                                    placeholder="New category name..."
                                    className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                                />
                                <div className="flex flex-wrap gap-1">
                                    {DEFAULT_COLORS.map(c => (
                                        <button
                                            key={c}
                                            type="button"
                                            onClick={() => setNewCatColor(c)}
                                            className={`w-4 h-4 rounded-full border-2 ${newCatColor === c ? 'border-white' : 'border-transparent'}`}
                                            style={{ backgroundColor: c }}
                                        />
                                    ))}
                                </div>
                                <button
                                    type="submit"
                                    disabled={!newCatName.trim() || createCategoryMutation.isPending}
                                    className="w-full bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded py-1 text-xs font-semibold"
                                >
                                    Add Category
                                </button>
                            </form>
                        </div>
                    </div>

                    {/* Tags panel */}
                    <div className="flex-1 flex flex-col min-w-0">
                        {/* Tags toolbar */}
                        <div className="px-3 py-2 border-b border-gray-700 flex items-center gap-2 flex-shrink-0 bg-gray-800/50 flex-wrap">
                            <div className="relative flex-1 max-w-xs">
                                <input
                                    type="text"
                                    value={tagSearch}
                                    onChange={e => setTagSearch(e.target.value)}
                                    placeholder="Search tags..."
                                    className="w-full bg-gray-900 border border-gray-700 rounded pl-2 pr-6 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                                />
                                {tagSearch && (
                                    <button
                                        type="button"
                                        onClick={() => setTagSearch('')}
                                        className="absolute right-1 top-1/2 -translate-y-1/2 w-4 h-4 flex items-center justify-center text-gray-500 hover:text-gray-200 text-xs leading-none"
                                        title="Clear search"
                                    >
                                        ✕
                                    </button>
                                )}
                            </div>

                            {/* Find & replace toggle */}
                            <button
                                onClick={() => {
                                    setShowFindReplace(v => !v);
                                    if (!showFindReplace) setTimeout(() => findInputRef.current?.focus(), 0);
                                }}
                                className={`px-2 py-1 rounded text-xs ${showFindReplace ? 'bg-blue-700 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}
                                title="Find & replace (Ctrl+F)"
                            >
                                🔎
                            </button>

                            {/* Selection actions */}
                            <button
                                onClick={selectAll}
                                className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300"
                                title="Ctrl+A"
                            >
                                Select All
                            </button>

                            {selectedTags.size > 0 && (
                                <>
                                    <span className="text-xs text-gray-400">{selectedTags.size} selected</span>

                                    <button
                                        onClick={handleDeleteSelected}
                                        className="px-2 py-1 bg-red-900 hover:bg-red-800 rounded text-xs text-red-200"
                                        title="Delete selected tags from all images"
                                    >
                                        Delete
                                    </button>

                                    <span className="text-xs text-gray-600">|</span>
                                    <select
                                        value=""
                                        onChange={e => {
                                            const v = e.target.value;
                                            if (v === '') return;
                                            const catId = v === 'none' ? null : Number(v);
                                            bulkAssignMutation.mutate({ tag_values: Array.from(selectedTags), category_id: catId });
                                        }}
                                        className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                                        title="Classify selected tags"
                                    >
                                        <option value="">Classify as…</option>
                                        {categories.map(cat => (
                                            <option key={cat.id} value={cat.id}>{cat.name}</option>
                                        ))}
                                        <option value="none">— Unassign —</option>
                                    </select>

                                    <span className="text-xs text-gray-600">|</span>
                                    <button
                                        onClick={clearSelection}
                                        className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-400"
                                    >
                                        Clear
                                    </button>
                                </>
                            )}

                            <span className="ml-auto text-[10px] text-gray-500">{filteredTags.length} tags</span>
                        </div>

                        {/* Find & replace bar */}
                        {showFindReplace && (
                            <div className="px-3 py-2 border-b border-gray-700 flex items-center gap-2 flex-shrink-0 bg-gray-800/80 flex-wrap">
                                <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Find/Replace</span>
                                <input
                                    ref={findInputRef}
                                    type="text"
                                    value={findText}
                                    onChange={e => setFindText(e.target.value)}
                                    onKeyDown={e => {
                                        e.stopPropagation();
                                        if (e.key === 'Escape') setShowFindReplace(false);
                                        if (e.key === 'Enter') runReplaceAll();
                                    }}
                                    placeholder="Find..."
                                    className="flex-1 max-w-[180px] bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                                />
                                <span className="text-gray-500 text-xs">→</span>
                                <input
                                    type="text"
                                    value={replaceText}
                                    onChange={e => setReplaceText(e.target.value)}
                                    onKeyDown={e => {
                                        e.stopPropagation();
                                        if (e.key === 'Escape') setShowFindReplace(false);
                                        if (e.key === 'Enter') runReplaceAll();
                                    }}
                                    placeholder="Replace with..."
                                    className="flex-1 max-w-[180px] bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                                />
                                <label className="flex items-center gap-1 text-[10px] text-gray-400 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={findCaseSensitive}
                                        onChange={e => setFindCaseSensitive(e.target.checked)}
                                        className="accent-blue-500"
                                    />
                                    Aa
                                </label>
                                <span className="text-[10px] text-gray-500">
                                    {findText ? `${findMatchCount} match${findMatchCount === 1 ? '' : 'es'}` : ''}
                                    {selectedTags.size > 0 ? ' (in selection)' : ''}
                                </span>
                                <button
                                    onClick={runReplaceAll}
                                    disabled={!findText || findMatchCount === 0}
                                    className="px-2 py-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 rounded text-xs text-white font-semibold"
                                >
                                    Replace All
                                </button>
                                <button
                                    onClick={() => setShowFindReplace(false)}
                                    className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300"
                                    title="Close (Esc)"
                                >
                                    ✕
                                </button>
                            </div>
                        )}

                        {/* Add new tag form */}
                        <form
                            onSubmit={handleCreateTag}
                            className="px-3 py-2 border-b border-gray-700 flex items-center gap-2 flex-shrink-0 bg-gray-800/30"
                        >
                            <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">New tag</span>
                            <input
                                type="text"
                                value={newTagValue}
                                onChange={e => setNewTagValue(e.target.value)}
                                onKeyDown={e => e.stopPropagation()}
                                placeholder={
                                    typeof filterCatId === 'number'
                                        ? `Add tag to "${categories.find(c => c.id === filterCatId)?.name ?? '...'}"`
                                        : 'Add tag (unassigned)'
                                }
                                className="flex-1 max-w-sm bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                            />
                            <button
                                type="submit"
                                disabled={!newTagValue.trim() || createTagMutation.isPending}
                                className="px-2 py-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 rounded text-xs text-white font-semibold"
                            >
                                Add
                            </button>
                            {typeof filterCatId !== 'number' && (
                                <span className="text-[10px] text-gray-500">
                                    Select a category on the left to add directly into it
                                </span>
                            )}
                        </form>

                        {/* Tag list */}
                        <div className="flex-1 overflow-y-auto p-3" ref={tagListRef}>
                            {loadingTags ? (
                                <div className="grid grid-cols-2 gap-2">
                                    {[...Array(12)].map((_, i) => (
                                        <div key={i} className="h-8 bg-gray-700 rounded animate-pulse" />
                                    ))}
                                </div>
                            ) : filteredTags.length === 0 ? (
                                <div className="flex items-center justify-center h-32 text-gray-500 text-sm">
                                    No tags found
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 gap-0.5">
                                    {filteredTags.map((tag, index) => {
                                        const isSelected = selectedTags.has(tag.value);
                                        const isFocused = focusedIndex === index;
                                        const isEditing = editingTagValue === tag.value;

                                        return (
                                            <div
                                                key={tag.value}
                                                data-tag-index={index}
                                                className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors group
                                                    ${isSelected ? 'bg-blue-900/50 border border-blue-700/50' : 'border border-transparent'}
                                                    ${isFocused && !isSelected ? 'bg-gray-700/50 border-gray-600' : ''}
                                                    ${!isSelected && !isFocused ? 'hover:bg-gray-800' : ''}
                                                `}
                                                onClick={e => {
                                                    if (isEditing) return;
                                                    toggleTag(tag.value, index, e);
                                                }}
                                                onDoubleClick={() => startEditingTag(tag.value)}
                                            >
                                                {/* Selection checkbox */}
                                                <div
                                                    className={`w-3.5 h-3.5 flex-shrink-0 rounded border ${isSelected ? 'bg-blue-500 border-blue-400' : 'border-gray-600'} flex items-center justify-center`}
                                                    onClick={e => {
                                                        e.stopPropagation();
                                                        if (!isEditing) toggleTag(tag.value, index, e, true);
                                                    }}
                                                >
                                                    {isSelected && <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>}
                                                </div>

                                                {/* Tag value — editable or display */}
                                                {isEditing ? (
                                                    <input
                                                        ref={editInputRef}
                                                        value={editingTagDraft}
                                                        onChange={e => setEditingTagDraft(e.target.value)}
                                                        onKeyDown={e => {
                                                            e.stopPropagation();
                                                            if (e.key === 'Enter') commitTagEdit();
                                                            if (e.key === 'Escape') cancelEdit();
                                                            if (e.key === 'Tab') {
                                                                e.preventDefault();
                                                                commitTagEdit();
                                                            }
                                                        }}
                                                        onBlur={() => {
                                                            setTimeout(commitTagEdit, 100);
                                                        }}
                                                        className="flex-1 bg-gray-900 border border-blue-500 rounded px-1.5 py-0.5 text-xs text-white focus:outline-none min-w-0"
                                                        onClick={e => e.stopPropagation()}
                                                    />
                                                ) : (
                                                    <span className="flex-1 text-xs text-gray-200 truncate">{tag.value}</span>
                                                )}

                                                <span className="text-[10px] text-gray-500 flex-shrink-0">{tag.count}</span>

                                                {/* Category dot */}
                                                {tag.category_id && (
                                                    <div
                                                        className="w-2 h-2 rounded-full flex-shrink-0"
                                                        style={{ backgroundColor: tag.color ?? '#6b7280' }}
                                                        title={tag.category_name ?? ''}
                                                    />
                                                )}

                                                {/* Action buttons on hover */}
                                                {!isEditing && (
                                                    <div
                                                        className="opacity-0 group-hover:opacity-100 flex items-center gap-1 flex-shrink-0"
                                                        onClick={e => e.stopPropagation()}
                                                    >
                                                        <button
                                                            onClick={() => startEditingTag(tag.value)}
                                                            className="text-[10px] text-gray-400 hover:text-blue-400 px-0.5"
                                                            title="Rename (F2)"
                                                        >✎</button>
                                                        <button
                                                            onClick={() => {
                                                                if (confirm(`Delete tag "${tag.value}" from all ${tag.count} images?`)) {
                                                                    globalDeleteMutation.mutate([tag.value]);
                                                                }
                                                            }}
                                                            className="text-[10px] text-gray-400 hover:text-red-400 px-0.5"
                                                            title="Delete from all images"
                                                        >✕</button>
                                                        <select
                                                            value={tag.category_id ?? ''}
                                                            onChange={e => {
                                                                const val = e.target.value;
                                                                assignTagMutation.mutate({
                                                                    tag_value: tag.value,
                                                                    category_id: val ? Number(val) : null,
                                                                });
                                                            }}
                                                            className="bg-gray-700 border border-gray-600 rounded px-1 py-0.5 text-[10px] text-white focus:outline-none"
                                                        >
                                                            <option value="">--</option>
                                                            {categories.map(cat => (
                                                                <option key={cat.id} value={cat.id}>{cat.name}</option>
                                                            ))}
                                                        </select>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
