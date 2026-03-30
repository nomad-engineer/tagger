import { useState, useEffect, useRef, useCallback } from 'react';
import { useTaggerStore } from './store';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export function TagEditor() {
    const { activeImage, selectedImages, setStatus } = useTaggerStore();
    const queryClient = useQueryClient();
    const [newTagVal, setNewTagVal] = useState('');
    const [captionDraft, setCaptionDraft] = useState('');
    const [captionDirty, setCaptionDirty] = useState(false);
    const [tagSearch, setTagSearch] = useState('');
    const [suggestions, setSuggestions] = useState<string[]>([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [allSuggestions, setAllSuggestions] = useState<string[]>([]);
    const tagValRef = useRef<HTMLInputElement>(null);

    // Fetch autocomplete suggestions
    useEffect(() => {
        fetch('/api/tags/suggestions')
            .then(r => r.json())
            .then(d => setAllSuggestions(d.suggestions || []))
            .catch(() => {});
    }, [activeImage]);

    // Fetch details for the active image
    const { data: activeImageData, isLoading: isLoadingImage } = useQuery({
        queryKey: ['image', activeImage],
        queryFn: async () => {
            if (!activeImage) return null;
            const res = await fetch(`/api/images/data/${activeImage}`);
            if (!res.ok) return null;
            return res.json();
        },
        enabled: !!activeImage
    });

    // Sync caption draft when image changes
    useEffect(() => {
        if (activeImageData) {
            setCaptionDraft(activeImageData.captions?.default || '');
            setCaptionDirty(false);
        }
    }, [activeImageData]);

    // Update suggestions when typing
    useEffect(() => {
        if (newTagVal.length < 1) {
            setShowSuggestions(false);
            return;
        }
        const q = newTagVal.toLowerCase();
        const matches = allSuggestions.filter(s => s.toLowerCase().includes(q)).slice(0, 8);
        setSuggestions(matches);
        setShowSuggestions(matches.length > 0);
    }, [newTagVal, allSuggestions]);

    const saveCaption = useCallback(async () => {
        if (!activeImage) return;
        try {
            const res = await fetch(`/api/images/caption/${activeImage}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: captionDraft, label: 'default' })
            });
            if (res.ok) {
                setCaptionDirty(false);
                setStatus('Caption saved', 'success');
                queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
                queryClient.invalidateQueries({ queryKey: ['images'] });
            }
        } catch {
            setStatus('Failed to save caption', 'error');
        }
    }, [activeImage, captionDraft, queryClient, setStatus]);

    const addTagMutation = useMutation({
        mutationFn: async ({ value, hashes }: { value: string; hashes: string[] }) => {
            const res = await fetch('/api/tags/batch-add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value, hashes })
            });
            return res.json();
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['images'] });
            queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
            setNewTagVal('');
            setShowSuggestions(false);
        }
    });

    const removeTagMutation = useMutation({
        mutationFn: async ({ value, hashes }: { value: string; hashes: string[] }) => {
            const res = await fetch('/api/tags/batch-remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value, hashes })
            });
            return res.json();
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['images'] });
            queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
        }
    });

    const handleAdd = (e: React.FormEvent) => {
        e.preventDefault();
        const val = newTagVal.trim();
        if (!val) return;

        const targetHashes = selectedImages.length > 0 ? selectedImages : (activeImage ? [activeImage] : []);
        if (targetHashes.length === 0) return;

        addTagMutation.mutate({ value: val, hashes: targetHashes });
    };

    const handleRemove = (value: string) => {
        const targetHashes = selectedImages.length > 0 ? selectedImages : (activeImage ? [activeImage] : []);
        if (targetHashes.length === 0) return;
        removeTagMutation.mutate({ value, hashes: targetHashes });
    };

    const tags: string[] = activeImageData?.tags || [];
    const filteredTags = tagSearch
        ? tags.filter(t => t.toLowerCase().includes(tagSearch.toLowerCase()))
        : tags;

    const isMulti = selectedImages.length > 1;
    const hasTarget = selectedImages.length > 0 || !!activeImage;

    return (
        <div className="flex-1 flex flex-col overflow-hidden">
            {/* Image Preview */}
            {activeImage && (
                <div className="flex-shrink-0 border-b border-gray-700">
                    <div className="relative bg-gray-900" style={{ height: '160px' }}>
                        <img
                            src={`/api/images/thumbnail/${activeImage}`}
                            alt="Preview"
                            className="w-full h-full object-contain"
                        />
                    </div>
                    {activeImageData && (
                        <div className="px-3 py-1.5 bg-gray-800/50">
                            <p className="text-xs text-gray-300 truncate font-medium">{activeImageData.name}</p>
                        </div>
                    )}
                </div>
            )}

            {/* No image selected */}
            {!activeImage && selectedImages.length === 0 && (
                <div className="flex-1 flex items-center justify-center">
                    <p className="text-sm text-gray-500 italic text-center px-4">Select an image to view or edit tags</p>
                </div>
            )}

            {hasTarget && (
                <div className="flex-1 flex flex-col overflow-hidden">
                    {/* Header */}
                    <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0">
                        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                            {isMulti ? `Batch Editing (${selectedImages.length})` : 'Tags'}
                        </p>
                    </div>

                    {/* Caption Editor (single image only) */}
                    {!isMulti && activeImage && (
                        <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0">
                            <label className="text-[10px] text-gray-500 uppercase tracking-wider block mb-1">Caption</label>
                            <textarea
                                value={captionDraft}
                                onChange={e => { setCaptionDraft(e.target.value); setCaptionDirty(true); }}
                                onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) saveCaption(); }}
                                rows={3}
                                className="w-full bg-gray-900 border border-gray-600 rounded px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 resize-none"
                                placeholder="Image caption..."
                            />
                            {captionDirty && (
                                <button
                                    onClick={saveCaption}
                                    className="mt-1 w-full bg-blue-700 hover:bg-blue-600 text-white text-xs rounded py-1 transition-colors"
                                >
                                    Save Caption (Ctrl+Enter)
                                </button>
                            )}
                        </div>
                    )}

                    {/* Tags Section */}
                    <div className="flex-1 flex flex-col overflow-hidden px-3 py-2">
                        {/* Tag search */}
                        <div className="flex-shrink-0 mb-2">
                            <input
                                type="text"
                                value={tagSearch}
                                onChange={e => setTagSearch(e.target.value)}
                                placeholder="Search tags..."
                                className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                            />
                        </div>

                        {/* Tag list */}
                        <div className="flex-1 overflow-y-auto min-h-0">
                            {isLoadingImage ? (
                                <div className="flex flex-wrap gap-1.5">
                                    {[...Array(6)].map((_, i) => (
                                        <div key={i} className="h-6 w-20 bg-gray-700 rounded animate-pulse" />
                                    ))}
                                </div>
                            ) : filteredTags.length === 0 ? (
                                <p className="text-xs text-gray-600 italic">
                                    {tagSearch ? 'No matching tags' : 'No tags'}
                                </p>
                            ) : (
                                <div className="flex flex-wrap gap-1.5">
                                    {filteredTags.map((tag: string, idx: number) => (
                                        <div
                                            key={`${tag}-${idx}`}
                                            className="group flex items-center text-xs rounded border overflow-hidden bg-gray-700 hover:bg-gray-600 border-gray-600"
                                        >
                                            <span className="px-1.5 py-0.5 text-gray-200">{tag}</span>
                                            <button
                                                onClick={() => handleRemove(tag)}
                                                className="px-1 py-0.5 text-gray-500 hover:text-red-400 hover:bg-gray-500/30 transition-colors border-l border-gray-600 opacity-0 group-hover:opacity-100"
                                                title="Remove"
                                            >
                                                ✕
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Add Tag Form */}
                        <div className="flex-shrink-0 border-t border-gray-700 pt-2 mt-2">
                            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1.5">Add Tag</p>
                            <form onSubmit={handleAdd} className="flex flex-col gap-1.5">
                                <div className="relative">
                                    <input
                                        ref={tagValRef}
                                        value={newTagVal}
                                        onChange={e => setNewTagVal(e.target.value)}
                                        onFocus={() => newTagVal && setShowSuggestions(suggestions.length > 0)}
                                        onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                                        onKeyDown={e => {
                                            if (e.key === 'Escape') setShowSuggestions(false);
                                        }}
                                        className="w-full bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                                        placeholder="tag value..."
                                    />
                                    {showSuggestions && (
                                        <div className="absolute bottom-full left-0 right-0 mb-1 bg-gray-800 border border-gray-600 rounded shadow-xl z-10 max-h-40 overflow-y-auto">
                                            {suggestions.map(s => (
                                                <button
                                                    key={s}
                                                    type="button"
                                                    onMouseDown={() => {
                                                        setNewTagVal(s);
                                                        setShowSuggestions(false);
                                                        tagValRef.current?.focus();
                                                    }}
                                                    className="w-full text-left px-2 py-1 text-xs text-gray-300 hover:bg-gray-700 truncate"
                                                >
                                                    {s}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                                <button
                                    type="submit"
                                    disabled={addTagMutation.isPending || !newTagVal.trim()}
                                    className="w-full bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded py-1.5 text-xs font-semibold transition-all"
                                >
                                    {addTagMutation.isPending ? 'Adding...' : 'Add Tag'}
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
