import { useState, useCallback } from 'react';
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
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
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
        onSuccess: (data) => {
            qc.invalidateQueries({ queryKey: ['taxonomy-tags'] });
            setSelectedTags(new Set());
            setStatus(`Assigned ${data.assigned} tags`, 'success');
        },
    });

    const filteredTags = allTags.filter(t => {
        if (tagSearch && !t.value.toLowerCase().includes(tagSearch.toLowerCase())) return false;
        if (showUnassigned && t.category_id !== null) return false;
        if (filterCatId !== 'all' && filterCatId !== null && t.category_id !== filterCatId) return false;
        if (filterCatId === null && t.category_id !== null) return false;
        return true;
    });

    const toggleTag = useCallback((value: string) => {
        setSelectedTags(prev => {
            const next = new Set(prev);
            if (next.has(value)) next.delete(value);
            else next.add(value);
            return next;
        });
    }, []);

    const handleCreateCategory = (e: React.FormEvent) => {
        e.preventDefault();
        if (!newCatName.trim()) return;
        createCategoryMutation.mutate(newCatName.trim());
    };

    return (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-stretch justify-end" onClick={onClose}>
            <div
                className="w-full max-w-4xl bg-gray-900 flex flex-col shadow-2xl"
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-gray-800 flex-shrink-0">
                    <h2 className="text-sm font-bold text-white">Tag Taxonomy</h2>
                    <button onClick={onClose} className="text-gray-400 hover:text-white text-lg leading-none">✕</button>
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
                        <div className="px-3 py-2 border-b border-gray-700 flex items-center gap-2 flex-shrink-0 bg-gray-800/50">
                            <input
                                type="text"
                                value={tagSearch}
                                onChange={e => setTagSearch(e.target.value)}
                                placeholder="Search tags..."
                                className="flex-1 max-w-xs bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                            />

                            {selectedTags.size > 0 && (
                                <>
                                    <span className="text-xs text-gray-400">{selectedTags.size} selected</span>
                                    <span className="text-xs text-gray-600">→ Assign to:</span>
                                    {categories.map(cat => (
                                        <button
                                            key={cat.id}
                                            onClick={() => bulkAssignMutation.mutate({ tag_values: Array.from(selectedTags), category_id: cat.id })}
                                            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-white hover:opacity-80 transition-opacity"
                                            style={{ backgroundColor: cat.color ?? '#6b7280' }}
                                        >
                                            {cat.name}
                                        </button>
                                    ))}
                                    <button
                                        onClick={() => bulkAssignMutation.mutate({ tag_values: Array.from(selectedTags), category_id: null })}
                                        className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300"
                                    >
                                        Unassign
                                    </button>
                                    <button
                                        onClick={() => setSelectedTags(new Set())}
                                        className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-400"
                                    >
                                        Clear
                                    </button>
                                </>
                            )}

                            <span className="ml-auto text-[10px] text-gray-500">{filteredTags.length} tags</span>
                        </div>

                        {/* Tag list */}
                        <div className="flex-1 overflow-y-auto p-3">
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
                                <div className="grid grid-cols-1 gap-1">
                                    {filteredTags.map(tag => {
                                        const isSelected = selectedTags.has(tag.value);
                                        return (
                                            <div
                                                key={tag.value}
                                                className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors group ${isSelected ? 'bg-blue-900/50 border border-blue-700/50' : 'hover:bg-gray-800 border border-transparent'}`}
                                                onClick={() => toggleTag(tag.value)}
                                            >
                                                {/* Selection checkbox */}
                                                <div className={`w-3.5 h-3.5 flex-shrink-0 rounded border ${isSelected ? 'bg-blue-500 border-blue-400' : 'border-gray-600'} flex items-center justify-center`}>
                                                    {isSelected && <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>}
                                                </div>

                                                {/* Tag value + count */}
                                                <span className="flex-1 text-xs text-gray-200 truncate">{tag.value}</span>
                                                <span className="text-[10px] text-gray-500 flex-shrink-0">{tag.count}</span>

                                                {/* Category dot */}
                                                {tag.category_id && (
                                                    <div
                                                        className="w-2 h-2 rounded-full flex-shrink-0"
                                                        style={{ backgroundColor: tag.color ?? '#6b7280' }}
                                                        title={tag.category_name ?? ''}
                                                    />
                                                )}

                                                {/* Assign dropdown — shown on hover */}
                                                <div
                                                    className="opacity-0 group-hover:opacity-100 flex items-center gap-1 flex-shrink-0"
                                                    onClick={e => e.stopPropagation()}
                                                >
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
                                                        <option value="">— unassigned —</option>
                                                        {categories.map(cat => (
                                                            <option key={cat.id} value={cat.id}>{cat.name}</option>
                                                        ))}
                                                    </select>
                                                </div>
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
