import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useTaggerStore } from './store';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const THUMB_VERSION = 3;

function gcd(a: number, b: number): number { return b === 0 ? a : gcd(b, a % b); }
function aspectRatio(w: number, h: number): string {
    const d = gcd(Math.round(w), Math.round(h));
    const rw = Math.round(w) / d;
    const rh = Math.round(h) / d;
    // If the ratio numbers are large, fall back to decimal
    if (rw > 32 || rh > 32) return (w / h).toFixed(2) + ':1';
    return `${rw}:${rh}`;
}

export function TagEditor() {
    const { activeImage, selectedImages, setStatus, setActiveImage, sortBy, viewMode } = useTaggerStore();
    const queryClient = useQueryClient();

    // Get all loaded image hashes for left/right navigation
    const getAllLoadedHashes = useCallback((): string[] => {
        const data = queryClient.getQueryData<{ pages: { items: { hash: string }[] }[] }>(['images', sortBy]);
        return data?.pages.flatMap(p => p.items.map(img => img.hash)) ?? [];
    }, [queryClient, sortBy]);

    const navigateImage = useCallback((direction: 'prev' | 'next') => {
        const hashes = getAllLoadedHashes();
        if (hashes.length === 0) return;
        const currentIdx = activeImage ? hashes.indexOf(activeImage) : -1;
        let nextIdx: number;
        if (direction === 'prev') {
            nextIdx = currentIdx > 0 ? currentIdx - 1 : hashes.length - 1;
        } else {
            nextIdx = currentIdx < hashes.length - 1 ? currentIdx + 1 : 0;
        }
        setActiveImage(hashes[nextIdx]);
    }, [getAllLoadedHashes, activeImage, setActiveImage]);

    // Caption list state
    const [editingCaptionLabel, setEditingCaptionLabel] = useState<string | null>(null);
    const [captionDraft, setCaptionDraft] = useState('');
    const [captionDirty, setCaptionDirty] = useState(false);
    const [addingCaption, setAddingCaption] = useState(false);
    const [newCaptionLabel, setNewCaptionLabel] = useState('');
    const captionTextareaRef = useRef<HTMLTextAreaElement>(null);
    const newCaptionInputRef = useRef<HTMLInputElement>(null);

    const [tagSearch, setTagSearch] = useState('');
    const [allSuggestions, setAllSuggestions] = useState<string[]>([]);

    // Tag list interaction state
    const [focusedIndex, setFocusedIndex] = useState<number>(-1);
    const [selectedTags, setSelectedTags] = useState<Set<number>>(new Set());
    const [lastSelectedIndex, setLastSelectedIndex] = useState<number>(-1);
    const [editingIndex, setEditingIndex] = useState<number>(-1);
    const [editingValue, setEditingValue] = useState('');
    const [suggestionIndex, setSuggestionIndex] = useState<number>(-1);
    const [dragIndex, setDragIndex] = useState<number>(-1);
    const [dragOverIndex, setDragOverIndex] = useState<number>(-1);
    const tagListRef = useRef<HTMLDivElement>(null);
    const editInputRef = useRef<HTMLInputElement>(null);
    const suggestionsRef = useRef<HTMLDivElement>(null);
    const pendingFocusTag = useRef<string | null>(null);
    const editSelectAll = useRef(false);
    const commitHandled = useRef(false);
    const liveEditValue = useRef('');

    const isMulti = selectedImages.length > 1;
    const hasTarget = selectedImages.length > 0 || !!activeImage;

    // Fetch autocomplete suggestions
    useEffect(() => {
        fetch('/api/tags/suggestions')
            .then(r => r.json())
            .then(d => setAllSuggestions(d.suggestions || []))
            .catch(() => {});
    }, [activeImage]);

    // Fetch details for the active image (single mode)
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

    // Fetch tags for all selected images (multi mode)
    const { data: multiImageData } = useQuery({
        queryKey: ['multi-image-tags', ...selectedImages],
        queryFn: async () => {
            if (selectedImages.length <= 1) return null;
            const results = await Promise.all(
                selectedImages.map(async (hash) => {
                    const res = await fetch(`/api/images/data/${hash}`);
                    if (!res.ok) return { hash, tags: [] };
                    const data = await res.json();
                    return { hash, tags: data.tags || [] };
                })
            );
            return results;
        },
        enabled: isMulti,
        staleTime: 2000,
    });

    // Compute merged tags for multi-select with counts
    const mergedTags: { tag: string; count: number }[] = (() => {
        if (!isMulti || !multiImageData) return [];
        const tagCounts = new Map<string, number>();
        for (const img of multiImageData) {
            for (const tag of img.tags) {
                tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);
            }
        }
        return Array.from(tagCounts.entries())
            .map(([tag, count]) => ({ tag, count }))
            .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
    })();

    // Tags to display — defined early so callbacks can reference them
    const singleTags: string[] = activeImageData?.tags || [];
    const displayTags = isMulti ? mergedTags : singleTags.map(t => ({ tag: t, count: 1 }));
    const filteredDisplayTags = tagSearch
        ? displayTags.filter(t => t.tag.toLowerCase().includes(tagSearch.toLowerCase()))
        : displayTags;
    const showBlankEntry = !tagSearch && hasTarget;
    const listItems = showBlankEntry
        ? [...filteredDisplayTags, { tag: '', count: 0, isBlank: true }]
        : filteredDisplayTags.map(t => ({ ...t, isBlank: false }));

    // Sync caption state when image changes
    useEffect(() => {
        if (activeImageData) {
            setCaptionDirty(false);
            setEditingCaptionLabel(null);
            setAddingCaption(false);
        }
    }, [activeImageData]);

    // Captions as sorted list of {label, content}
    const captionEntries: { label: string; content: string }[] = useMemo(() => {
        const caps = activeImageData?.captions ?? {};
        return Object.entries(caps)
            .map(([label, content]) => ({ label, content: content as string }))
            .sort((a, b) => {
                if (a.label === 'default') return -1;
                if (b.label === 'default') return 1;
                return a.label.localeCompare(b.label);
            });
    }, [activeImageData]);

    // Reset tag selection state when image changes
    useEffect(() => {
        setFocusedIndex(-1);
        setSelectedTags(new Set());
        setLastSelectedIndex(-1);
        setEditingIndex(-1);
    }, [activeImage]);

    // After a tag is added, focus it once the data refreshes
    useEffect(() => {
        if (pendingFocusTag.current) {
            const idx = displayTags.findIndex(t => t.tag === pendingFocusTag.current);
            if (idx >= 0) {
                setFocusedIndex(idx);
                setSelectedTags(new Set([idx]));
                setLastSelectedIndex(idx);
                pendingFocusTag.current = null;
                // Re-focus the tag list so arrow keys work immediately
                tagListRef.current?.focus();
                scrollTagIntoView(idx);
            }
        }
    }, [displayTags]);

    // Focus edit input when editing starts
    useEffect(() => {
        if (editingIndex >= 0 && editInputRef.current) {
            editInputRef.current.focus();
            if (editSelectAll.current) {
                editInputRef.current.select();
            } else {
                // Place cursor at end (typed character start)
                const len = editInputRef.current.value.length;
                editInputRef.current.setSelectionRange(len, len);
            }
            editSelectAll.current = false;
        }
    }, [editingIndex]);

    // Filtered suggestions for the current edit value
    const editSuggestions = useMemo(() => {
        if (editingIndex < 0 || editingValue.length < 1) return [];
        const q = editingValue.toLowerCase();
        return allSuggestions.filter(s => s.toLowerCase().includes(q) && s !== editingValue).slice(0, 8);
    }, [editingValue, allSuggestions, editingIndex]);

    // Scroll to keep the suggestions dropdown visible within the tag list container
    useEffect(() => {
        if (editSuggestions.length > 0 && suggestionsRef.current && tagListRef.current) {
            const container = tagListRef.current;
            const dropdown = suggestionsRef.current;
            const dropdownRect = dropdown.getBoundingClientRect();
            const containerRect = container.getBoundingClientRect();
            // If dropdown bottom is below container bottom, scroll down
            const overflow = dropdownRect.bottom - containerRect.bottom;
            if (overflow > 0) {
                container.scrollTop += overflow + 8;
            }
        }
    }, [editSuggestions.length, editingIndex]);

    const saveCaption = useCallback(async (label?: string) => {
        const saveLabel = label ?? editingCaptionLabel;
        if (!activeImage || !saveLabel) return;
        try {
            const res = await fetch(`/api/images/caption/${activeImage}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: captionDraft, label: saveLabel })
            });
            if (res.ok) {
                setCaptionDirty(false);
                setEditingCaptionLabel(null);
                setStatus('Caption saved', 'success');
                queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
                queryClient.invalidateQueries({ queryKey: ['images'] });
            }
        } catch {
            setStatus('Failed to save caption', 'error');
        }
    }, [activeImage, captionDraft, editingCaptionLabel, queryClient, setStatus]);

    const deleteCaption = useCallback(async (label: string) => {
        if (!activeImage) return;
        try {
            const res = await fetch(`/api/images/caption/${activeImage}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: '', label })
            });
            if (res.ok) {
                setStatus('Caption deleted', 'success');
                setEditingCaptionLabel(null);
                queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
                queryClient.invalidateQueries({ queryKey: ['images'] });
            }
        } catch {
            setStatus('Failed to delete caption', 'error');
        }
    }, [activeImage, queryClient, setStatus]);

    const startEditingCaption = useCallback((label: string, content: string) => {
        setEditingCaptionLabel(label);
        setCaptionDraft(content);
        setCaptionDirty(false);
        setTimeout(() => captionTextareaRef.current?.focus(), 0);
    }, []);

    const startAddingCaption = useCallback(() => {
        setAddingCaption(true);
        setNewCaptionLabel('');
        setTimeout(() => newCaptionInputRef.current?.focus(), 0);
    }, []);

    const pendingEditLabel = useRef<string | null>(null);

    const confirmAddCaption = useCallback(async () => {
        const label = newCaptionLabel.trim().toLowerCase();
        if (!label || !activeImage) return;
        if (captionEntries.some(c => c.label === label)) {
            setStatus(`Caption "${label}" already exists`, 'error');
            return;
        }
        setAddingCaption(false);
        setNewCaptionLabel('');
        // Save empty caption so it appears in the list, then open editor
        try {
            const res = await fetch(`/api/images/caption/${activeImage}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: ' ', label }),
            });
            if (res.ok) {
                pendingEditLabel.current = label;
                await queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
            }
        } catch {
            setStatus('Failed to create caption', 'error');
        }
    }, [newCaptionLabel, activeImage, captionEntries, setStatus, queryClient]);

    // After a new caption is created, open editor for it
    useEffect(() => {
        if (pendingEditLabel.current) {
            const entry = captionEntries.find(c => c.label === pendingEditLabel.current);
            if (entry) {
                const label = pendingEditLabel.current;
                pendingEditLabel.current = null;
                startEditingCaption(label, entry.content);
            }
        }
    }, [captionEntries, startEditingCaption]);

    // Focus textarea when editing caption starts
    useEffect(() => {
        if (editingCaptionLabel && captionTextareaRef.current) {
            captionTextareaRef.current.focus();
        }
    }, [editingCaptionLabel]);

    const addTagMutation = useMutation({
        mutationFn: async ({ value, hashes }: { value: string; hashes: string[] }) => {
            const res = await fetch('/api/tags/batch-add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value, hashes })
            });
            return res.json();
        },
        onMutate: ({ value }) => {
            pendingFocusTag.current = value;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['images'] });
            queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
            queryClient.invalidateQueries({ queryKey: ['multi-image-tags'] });
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
            queryClient.invalidateQueries({ queryKey: ['multi-image-tags'] });
        }
    });

    const renameTagMutation = useMutation({
        mutationFn: async ({ oldValue, newValue, hashes }: { oldValue: string; newValue: string; hashes: string[] }) => {
            const res = await fetch('/api/tags/batch-rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ old_value: oldValue, new_value: newValue, hashes })
            });
            return res.json();
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['images'] });
            queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
            queryClient.invalidateQueries({ queryKey: ['multi-image-tags'] });
        }
    });

    const reorderMutation = useMutation({
        mutationFn: async ({ hash, tags }: { hash: string; tags: string[] }) => {
            const res = await fetch('/api/tags/reorder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hash, tags })
            });
            return res.json();
        },
        onMutate: async ({ hash, tags }) => {
            await queryClient.cancelQueries({ queryKey: ['image', hash] });
            const prev = queryClient.getQueryData(['image', hash]);
            queryClient.setQueryData(['image', hash], (old: any) =>
                old ? { ...old, tags } : old
            );
            return { prev, hash };
        },
        onError: (_err, _vars, context) => {
            if (context?.prev) {
                queryClient.setQueryData(['image', context.hash], context.prev);
            }
        },
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
            queryClient.invalidateQueries({ queryKey: ['images'] });
        }
    });

    const handleRemove = (value: string) => {
        const targetHashes = selectedImages.length > 0 ? selectedImages : (activeImage ? [activeImage] : []);
        if (targetHashes.length === 0) return;
        removeTagMutation.mutate({ value, hashes: targetHashes });
    };

    const handleRemoveSelected = () => {
        if (selectedTags.size === 0) return;
        const targetHashes = selectedImages.length > 0 ? selectedImages : (activeImage ? [activeImage] : []);
        if (targetHashes.length === 0) return;
        // selectedTags indices correspond to filteredDisplayTags (what's visually rendered)
        const indices = Array.from(selectedTags).filter(i => i < filteredDisplayTags.length).sort((a, b) => a - b);
        const tagsToRemove = indices
            .map(i => filteredDisplayTags[i]?.tag)
            .filter(Boolean);
        if (tagsToRemove.length === 0) return;
        // Focus the next tag after the lowest removed index
        const remaining = filteredDisplayTags.length - tagsToRemove.length;
        const nextFocus = indices.length > 0
            ? Math.min(indices[0], remaining - 1)
            : -1;
        // Single batch request to remove all selected tags at once
        fetch('/api/tags/batch-remove-multi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ values: tagsToRemove, hashes: targetHashes }),
        }).then(() => {
            queryClient.invalidateQueries({ queryKey: ['images'] });
            queryClient.invalidateQueries({ queryKey: ['image', activeImage] });
            queryClient.invalidateQueries({ queryKey: ['multi-image-tags'] });
        });
        if (nextFocus >= 0) {
            setFocusedIndex(nextFocus);
            setSelectedTags(new Set([nextFocus]));
            setLastSelectedIndex(nextFocus);
        } else {
            setFocusedIndex(-1);
            setSelectedTags(new Set());
        }
    };

    // Commit an inline edit — handles both editing existing tags and adding new ones
    // Single image: edit/add/delete only for that image
    // Multi image: add to all, edit only on images that have the old tag, delete from all
    // Using a ref so blur/keydown handlers always call the latest version
    const commitEditRef = useRef<() => void>(() => {});
    commitEditRef.current = () => {
        if (commitHandled.current || editingIndex < 0 || !activeImage) return;
        commitHandled.current = true;
        // Use the ref value which is always current, avoiding stale closure issues
        const newVal = liveEditValue.current.trim();
        const isNewEntry = !isMulti
            ? editingIndex >= singleTags.length
            : editingIndex >= mergedTags.length;

        const targetHashes = selectedImages.length > 0 ? selectedImages : [activeImage];

        if (isNewEntry) {
            // Adding a new tag — applies to all target images
            if (newVal) {
                addTagMutation.mutate({ value: newVal, hashes: targetHashes });
            }
        } else if (isMulti) {
            // Editing an existing tag in multi mode — rename only on images that have it
            const oldVal = mergedTags[editingIndex]?.tag;
            if (newVal && oldVal && newVal !== oldVal) {
                renameTagMutation.mutate({ oldValue: oldVal, newValue: newVal, hashes: targetHashes });
            }
        } else {
            // Editing an existing tag in single mode — update the full tag list
            const oldVal = singleTags[editingIndex];
            if (newVal && newVal !== oldVal) {
                const newTags = [...singleTags];
                newTags[editingIndex] = newVal;
                reorderMutation.mutate({ hash: activeImage, tags: newTags });
            }
        }
        liveEditValue.current = '';
        setEditingIndex(-1);
        setEditingValue('');
        setSuggestionIndex(-1);
        // Re-focus the tag list so arrow key navigation works immediately
        setTimeout(() => tagListRef.current?.focus(), 0);
    };
    const commitEdit = () => commitEditRef.current();

    const cancelEdit = () => {
        liveEditValue.current = '';
        setEditingIndex(-1);
        setEditingValue('');
        setSuggestionIndex(-1);
        // Re-focus the tag list so arrow key navigation works immediately
        setTimeout(() => tagListRef.current?.focus(), 0);
    };

    // Move tags by drag or keyboard
    const moveTags = (fromIndex: number, toIndex: number) => {
        if (!activeImage || isMulti) return;
        const newTags = [...singleTags];
        const [moved] = newTags.splice(fromIndex, 1);
        newTags.splice(toIndex, 0, moved);
        reorderMutation.mutate({ hash: activeImage, tags: newTags });
    };

    // Tag click handler with multi/range select
    const handleTagClick = (index: number, e: React.MouseEvent) => {
        if (editingIndex >= 0) return;

        if (e.shiftKey && lastSelectedIndex >= 0) {
            const start = Math.min(lastSelectedIndex, index);
            const end = Math.max(lastSelectedIndex, index);
            const newSelection = new Set(selectedTags);
            for (let i = start; i <= end; i++) {
                newSelection.add(i);
            }
            setSelectedTags(newSelection);
        } else if (e.ctrlKey || e.metaKey) {
            const newSelection = new Set(selectedTags);
            if (newSelection.has(index)) {
                newSelection.delete(index);
            } else {
                newSelection.add(index);
            }
            setSelectedTags(newSelection);
            setLastSelectedIndex(index);
        } else {
            setSelectedTags(new Set([index]));
            setLastSelectedIndex(index);
        }
        setFocusedIndex(index);
    };

    // Start editing a tag at index (Tab/F2/double-click: pre-fill existing value, select all)
    const startEditing = (idx: number) => {
        editSelectAll.current = true;
        commitHandled.current = false;
        const val = idx < displayTags.length ? displayTags[idx].tag : '';
        liveEditValue.current = val;
        setEditingIndex(idx);
        setEditingValue(val);
        setSuggestionIndex(-1);
    };

    // Handle keyboard in edit input (shared by all edit fields including blank entry)
    const handleEditKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'ArrowDown' && editSuggestions.length > 0) {
            e.preventDefault();
            setSuggestionIndex(prev => Math.min(prev + 1, editSuggestions.length - 1));
        } else if (e.key === 'ArrowUp' && editSuggestions.length > 0) {
            e.preventDefault();
            setSuggestionIndex(prev => Math.max(prev - 1, -1));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (suggestionIndex >= 0 && editSuggestions[suggestionIndex]) {
                liveEditValue.current = editSuggestions[suggestionIndex];
                setEditingValue(editSuggestions[suggestionIndex]);
                setSuggestionIndex(-1);
            } else {
                commitEdit();
            }
        } else if (e.key === 'Tab') {
            e.preventDefault();
            // Accept suggestion if highlighted
            if (suggestionIndex >= 0 && editSuggestions[suggestionIndex]) {
                liveEditValue.current = editSuggestions[suggestionIndex];
                setEditingValue(editSuggestions[suggestionIndex]);
                setSuggestionIndex(-1);
                return;
            }
            commitEdit();
            // Move to next/prev tag for editing
            const dir = e.shiftKey ? -1 : 1;
            const nextIdx = focusedIndex + dir;
            if (nextIdx >= 0 && nextIdx <= listItems.length - 1) {
                setFocusedIndex(nextIdx);
                setSelectedTags(new Set([nextIdx]));
                startEditing(nextIdx);
                scrollTagIntoView(nextIdx);
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancelEdit();
        }
        e.stopPropagation();
    };

    // Keyboard navigation for the tag list
    const handleTagListKeyDown = (e: React.KeyboardEvent) => {
        if (editingIndex >= 0) return;
        const itemCount = listItems.length;
        const tagCount = filteredDisplayTags.length;

        // Left/Right: navigate active image
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            e.stopPropagation();
            navigateImage('prev');
            return;
        }
        if (e.key === 'ArrowRight') {
            e.preventDefault();
            e.stopPropagation();
            navigateImage('next');
            return;
        }

        if (itemCount === 0) return;

        // Alt+Arrow: reorder tag position (only for real tags, not blank entry)
        if (e.altKey && focusedIndex >= 0 && focusedIndex < tagCount && !isMulti && selectedTags.size <= 1) {
            if (e.key === 'ArrowUp' && focusedIndex > 0) {
                e.preventDefault();
                e.stopPropagation();
                moveTags(focusedIndex, focusedIndex - 1);
                setFocusedIndex(focusedIndex - 1);
                setSelectedTags(new Set([focusedIndex - 1]));
                return;
            } else if (e.key === 'ArrowDown' && focusedIndex < tagCount - 1) {
                e.preventDefault();
                e.stopPropagation();
                moveTags(focusedIndex, focusedIndex + 1);
                setFocusedIndex(focusedIndex + 1);
                setSelectedTags(new Set([focusedIndex + 1]));
                return;
            }
        }

        // All keys below should stop propagation to prevent page scroll
        e.preventDefault();
        e.stopPropagation();

        switch (e.key) {
            case 'ArrowUp': {
                const next = focusedIndex <= 0 ? itemCount - 1 : focusedIndex - 1;
                setFocusedIndex(next);
                if (e.shiftKey) {
                    const newSel = new Set(selectedTags);
                    newSel.add(next);
                    setSelectedTags(newSel);
                } else {
                    setSelectedTags(new Set([next]));
                    setLastSelectedIndex(next);
                }
                scrollTagIntoView(next);
                break;
            }
            case 'ArrowDown': {
                const next = focusedIndex >= itemCount - 1 ? 0 : focusedIndex + 1;
                setFocusedIndex(next);
                if (e.shiftKey) {
                    const newSel = new Set(selectedTags);
                    newSel.add(next);
                    setSelectedTags(newSel);
                } else {
                    setSelectedTags(new Set([next]));
                    setLastSelectedIndex(next);
                }
                scrollTagIntoView(next);
                break;
            }
            case 'Delete':
            case 'Backspace':
                handleRemoveSelected();
                break;
            case 'Tab':
            case 'F2':
                if (focusedIndex >= 0) {
                    startEditing(focusedIndex);
                }
                break;
            case ' ':
                if (focusedIndex >= 0 && focusedIndex < tagCount) {
                    const newSel = new Set(selectedTags);
                    if (newSel.has(focusedIndex)) {
                        newSel.delete(focusedIndex);
                    } else {
                        newSel.add(focusedIndex);
                    }
                    setSelectedTags(newSel);
                    setLastSelectedIndex(focusedIndex);
                }
                break;
            case 'a':
                if (e.ctrlKey || e.metaKey) {
                    // Select all real tags (not the blank entry)
                    setSelectedTags(new Set(filteredDisplayTags.map((_, i) => i)));
                }
                break;
            case 'Escape':
                setSelectedTags(new Set());
                setFocusedIndex(-1);
                break;
            default:
                // Printable character: start editing with that character (replaces old value)
                if (focusedIndex >= 0 && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
                    commitHandled.current = false;
                    liveEditValue.current = e.key;
                    setEditingIndex(focusedIndex);
                    setEditingValue(e.key);
                    setSuggestionIndex(-1);
                }
                break;
        }
    };

    const scrollTagIntoView = (index: number) => {
        const scrollContainer = tagListRef.current;
        const itemsContainer = scrollContainer?.querySelector('[data-tag-items]');
        const el = itemsContainer?.children[index] as HTMLElement | undefined;
        if (!el || !scrollContainer) return;
        // Scroll within the tag list only — never trigger page scroll
        const elRect = el.getBoundingClientRect();
        const containerRect = scrollContainer.getBoundingClientRect();
        if (elRect.top < containerRect.top) {
            scrollContainer.scrollTop -= containerRect.top - elRect.top;
        } else if (elRect.bottom > containerRect.bottom) {
            scrollContainer.scrollTop += elRect.bottom - containerRect.bottom;
        }
    };

    // Drag handlers
    const handleDragStart = (index: number, e: React.DragEvent) => {
        if (isMulti || index >= singleTags.length) return;
        setDragIndex(index);
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(index));
    };

    const handleDragOver = (index: number, e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        setDragOverIndex(index);
    };

    const handleDrop = (index: number, e: React.DragEvent) => {
        e.preventDefault();
        if (dragIndex >= 0 && dragIndex !== index && index < singleTags.length) {
            moveTags(dragIndex, index);
            setFocusedIndex(index);
            setSelectedTags(new Set([index]));
        }
        setDragIndex(-1);
        setDragOverIndex(-1);
    };

    const handleDragEnd = () => {
        setDragIndex(-1);
        setDragOverIndex(-1);
    };

    return (
        <div className="flex-1 flex flex-col overflow-hidden">
            {/* Image Preview - Single */}
            {!isMulti && activeImage && (
                <div className="flex-shrink-0 border-b border-gray-700">
                    {viewMode !== 'single' && (
                        <div className={`relative ${activeImageData?.has_alpha ? 'checkerboard-bg' : 'bg-gray-900'}`} style={{ height: '160px' }}>
                            <img
                                src={`/api/images/thumbnail/${activeImage}?v=${THUMB_VERSION}&size=400`}
                                alt="Preview"
                                className="w-full h-full object-contain"
                            />
                        </div>
                    )}
                    {activeImageData && (
                        <div className="px-3 py-1.5 bg-gray-800/50 space-y-0.5">
                            <p className="text-xs text-gray-300 truncate font-medium">{activeImageData.name}</p>
                            {activeImageData.width && activeImageData.height && (
                                <p className="text-[10px] text-gray-500">
                                    {activeImageData.width} × {activeImageData.height}
                                    <span className="ml-2">{aspectRatio(activeImageData.width, activeImageData.height)}</span>
                                </p>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Image Preview - Multi-select collage */}
            {isMulti && (
                <div className="flex-shrink-0 border-b border-gray-700">
                    <div className="relative bg-gray-900 p-2" style={{ height: '160px' }}>
                        <div className="w-full h-full grid gap-1" style={{
                            gridTemplateColumns: `repeat(${Math.min(selectedImages.length, selectedImages.length <= 4 ? 2 : 3)}, 1fr)`,
                            gridTemplateRows: `repeat(${Math.min(Math.ceil(selectedImages.length / (selectedImages.length <= 4 ? 2 : 3)), 3)}, 1fr)`,
                        }}>
                            {selectedImages.slice(0, 9).map((hash) => (
                                <div key={hash} className="relative overflow-hidden rounded bg-gray-800">
                                    <img
                                        src={`/api/images/thumbnail/${hash}?v=${THUMB_VERSION}&size=200`}
                                        alt=""
                                        className="w-full h-full object-cover"
                                    />
                                </div>
                            ))}
                        </div>
                        {selectedImages.length > 9 && (
                            <div className="absolute bottom-2 right-2 bg-black/70 text-white text-[10px] px-1.5 py-0.5 rounded">
                                +{selectedImages.length - 9} more
                            </div>
                        )}
                    </div>
                    <div className="px-3 py-1.5 bg-gray-800/50">
                        <p className="text-xs text-blue-400 font-medium">{selectedImages.length} images selected</p>
                    </div>
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
                    {/* Header — batch editing only */}
                    {isMulti && (
                        <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0 flex items-center justify-between">
                            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                                Batch Editing ({selectedImages.length})
                            </p>
                        </div>
                    )}

                    {/* Caption List (single image only) */}
                    {!isMulti && activeImage && (
                        <div className="border-b border-gray-700 flex-shrink-0">
                            <div className="px-3 py-1.5 flex items-center justify-between">
                                <label className="text-[10px] text-gray-500 uppercase tracking-wider">Captions</label>
                                {!addingCaption && (
                                    <button
                                        onClick={startAddingCaption}
                                        className="text-[10px] text-gray-500 hover:text-blue-400 transition-colors"
                                        title="Add caption"
                                    >+ Add</button>
                                )}
                            </div>

                            {/* Add new caption label */}
                            {addingCaption && (
                                <div className="px-3 pb-2 flex items-center gap-1.5">
                                    <input
                                        ref={newCaptionInputRef}
                                        value={newCaptionLabel}
                                        onChange={e => setNewCaptionLabel(e.target.value)}
                                        onKeyDown={e => {
                                            e.stopPropagation();
                                            if (e.key === 'Enter') confirmAddCaption();
                                            if (e.key === 'Escape') { setAddingCaption(false); setNewCaptionLabel(''); }
                                        }}
                                        placeholder="Label name (e.g. long, short)..."
                                        className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                                        list="caption-label-suggestions"
                                    />
                                    <datalist id="caption-label-suggestions">
                                        {['long', 'short', 'detailed', 'brief'].filter(l => !captionEntries.some(c => c.label === l)).map(l => (
                                            <option key={l} value={l} />
                                        ))}
                                    </datalist>
                                    <button
                                        onClick={confirmAddCaption}
                                        disabled={!newCaptionLabel.trim()}
                                        className="px-2 py-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white text-xs rounded"
                                    >Add</button>
                                    <button
                                        onClick={() => { setAddingCaption(false); setNewCaptionLabel(''); }}
                                        className="px-1.5 py-1 text-gray-400 hover:text-white text-xs"
                                    >✕</button>
                                </div>
                            )}

                            {/* Caption entries */}
                            {captionEntries.length === 0 && !addingCaption && (
                                <div className="px-3 pb-2">
                                    <p className="text-xs text-gray-600 italic">No captions</p>
                                </div>
                            )}
                            <div className="space-y-px">
                                {captionEntries.map(cap => {
                                    const isEditing = editingCaptionLabel === cap.label;
                                    return (
                                        <div key={cap.label} className="group">
                                            {isEditing ? (
                                                <div className="px-3 py-2 bg-gray-800/50">
                                                    <div className="flex items-center gap-1.5 mb-1">
                                                        <span className="text-[10px] font-semibold text-blue-400 uppercase tracking-wider">{cap.label}</span>
                                                        <span className="text-[10px] text-gray-600">editing</span>
                                                    </div>
                                                    <textarea
                                                        ref={captionTextareaRef}
                                                        value={captionDraft}
                                                        onChange={e => { setCaptionDraft(e.target.value); setCaptionDirty(true); }}
                                                        onKeyDown={e => {
                                                            e.stopPropagation();
                                                            if (e.key === 'Enter' && e.ctrlKey) saveCaption();
                                                            if (e.key === 'Escape') { setEditingCaptionLabel(null); setCaptionDirty(false); }
                                                        }}
                                                        rows={3}
                                                        className="w-full bg-gray-900 border border-blue-500 rounded px-2 py-1.5 text-xs text-white focus:outline-none resize-y"
                                                        placeholder="Caption text..."
                                                    />
                                                    <div className="flex items-center gap-1.5 mt-1">
                                                        <button
                                                            onClick={() => saveCaption()}
                                                            disabled={!captionDirty}
                                                            className="px-2 py-0.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white text-xs rounded transition-colors"
                                                        >
                                                            Save (Ctrl+Enter)
                                                        </button>
                                                        <button
                                                            onClick={() => { setEditingCaptionLabel(null); setCaptionDirty(false); }}
                                                            className="px-2 py-0.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs rounded"
                                                        >Cancel</button>
                                                    </div>
                                                </div>
                                            ) : (
                                                <div
                                                    className="px-3 py-1.5 flex items-start gap-2 cursor-pointer hover:bg-gray-800/50 transition-colors"
                                                    onClick={() => startEditingCaption(cap.label, cap.content)}
                                                >
                                                    <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider flex-shrink-0 mt-0.5 min-w-[48px]">{cap.label}</span>
                                                    <p className="text-xs text-gray-300 flex-1 line-clamp-2 leading-relaxed min-w-0">
                                                        {cap.content || <span className="italic text-gray-600">empty</span>}
                                                    </p>
                                                    <div className="flex items-center gap-1 flex-shrink-0 opacity-0 group-hover:opacity-100">
                                                        <button
                                                            onClick={e => { e.stopPropagation(); startEditingCaption(cap.label, cap.content); }}
                                                            className="text-[10px] text-gray-500 hover:text-blue-400 px-0.5"
                                                            title="Edit"
                                                        >✎</button>
                                                        {cap.label !== 'default' && (
                                                            <button
                                                                onClick={e => {
                                                                    e.stopPropagation();
                                                                    if (confirm(`Delete "${cap.label}" caption?`)) deleteCaption(cap.label);
                                                                }}
                                                                className="text-[10px] text-gray-500 hover:text-red-400 px-0.5"
                                                                title="Delete caption"
                                                            >✕</button>
                                                        )}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Tags Section */}
                    <div className="flex-1 flex flex-col overflow-hidden px-3 py-2">
                        {/* Tag search + selection actions */}
                        <div className="flex-shrink-0 mb-2 flex items-center gap-2">
                            <input
                                type="text"
                                value={tagSearch}
                                onChange={e => setTagSearch(e.target.value)}
                                placeholder="Filter tags..."
                                className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                            />
                            {selectedTags.size > 0 && (
                                <>
                                    <span className="text-[10px] text-gray-500 flex-shrink-0">{selectedTags.size} sel</span>
                                    <button
                                        onClick={handleRemoveSelected}
                                        className="text-[10px] text-red-400 hover:text-red-300 transition-colors flex-shrink-0"
                                        title="Delete selected tags (Delete)"
                                    >✕</button>
                                </>
                            )}
                        </div>

                        {/* Tag list */}
                        <div
                            ref={tagListRef}
                            data-tag-list
                            className="flex-1 overflow-y-auto min-h-0 focus:outline-none"
                            tabIndex={0}
                            onKeyDown={handleTagListKeyDown}
                        >
                            {isLoadingImage && !isMulti ? (
                                <div className="space-y-1">
                                    {[...Array(6)].map((_, i) => (
                                        <div key={i} className="h-7 bg-gray-700 rounded animate-pulse" />
                                    ))}
                                </div>
                            ) : listItems.length === 0 ? (
                                <p className="text-xs text-gray-600 italic">
                                    {tagSearch ? 'No matching tags' : 'No tags'}
                                </p>
                            ) : (
                                <div className="space-y-px" data-tag-items>
                                    {listItems.map((item, idx) => {
                                        const isFocused = focusedIndex === idx;
                                        const isSelected = selectedTags.has(idx);
                                        const isDragOver = dragOverIndex === idx;
                                        const isDragging = dragIndex === idx;
                                        const isBlank = item.isBlank;
                                        const isEditing = editingIndex === idx;

                                        return (
                                            <div
                                                key={isBlank ? '__blank__' : `${item.tag}-${idx}`}
                                                draggable={!isMulti && !isBlank && !isEditing}
                                                onDragStart={e => handleDragStart(idx, e)}
                                                onDragOver={e => handleDragOver(idx, e)}
                                                onDrop={e => handleDrop(idx, e)}
                                                onDragEnd={handleDragEnd}
                                                onClick={e => {
                                                    // Keep focus on the tag list container for keyboard events
                                                    tagListRef.current?.focus();
                                                    if (isBlank && !isEditing) {
                                                        setFocusedIndex(idx);
                                                        startEditing(idx);
                                                    } else {
                                                        handleTagClick(idx, e);
                                                    }
                                                }}
                                                onDoubleClick={() => {
                                                    if (!isBlank) startEditing(idx);
                                                }}
                                                className={[
                                                    'group flex items-center text-xs rounded px-2 py-1 cursor-pointer transition-colors select-none relative',
                                                    isDragging ? 'opacity-40' : '',
                                                    isDragOver && !isBlank ? 'border-t-2 border-blue-500' : 'border-t-2 border-transparent',
                                                    isBlank && !isEditing
                                                        ? isFocused
                                                            ? 'bg-gray-700/50 text-gray-400'
                                                            : 'text-gray-600 hover:bg-gray-700/30'
                                                        : isSelected
                                                            ? 'bg-blue-600/30 text-white'
                                                            : isFocused
                                                                ? 'bg-gray-700 text-white'
                                                                : 'text-gray-300 hover:bg-gray-700/50',
                                                ].join(' ')}
                                            >
                                                {/* Drag handle */}
                                                {!isMulti && !isBlank && (
                                                    <span className="mr-1.5 text-gray-600 group-hover:text-gray-400 cursor-grab flex-shrink-0" title="Drag to reorder">
                                                        ⠿
                                                    </span>
                                                )}
                                                {!isMulti && isBlank && !isEditing && (
                                                    <span className="mr-1.5 text-gray-700 flex-shrink-0">+</span>
                                                )}

                                                {/* Index number */}
                                                {!isBlank && (
                                                    <span className="text-[10px] text-gray-600 mr-2 w-4 text-right flex-shrink-0">
                                                        {idx + 1}
                                                    </span>
                                                )}

                                                {/* Tag value or edit input */}
                                                {isEditing ? (
                                                    <div className="flex-1 relative min-w-0">
                                                        <input
                                                            ref={editInputRef}
                                                            value={editingValue}
                                                            onChange={e => {
                                                                liveEditValue.current = e.target.value;
                                                                setEditingValue(e.target.value);
                                                                setSuggestionIndex(-1);
                                                            }}
                                                            onKeyDown={handleEditKeyDown}
                                                            onBlur={() => {
                                                                // Delay to allow suggestion clicks to register
                                                                setTimeout(commitEdit, 150);
                                                            }}
                                                            onClick={e => e.stopPropagation()}
                                                            className="w-full bg-gray-900 border border-blue-500 rounded px-1 py-0 text-xs text-white focus:outline-none"
                                                            placeholder={isBlank ? 'add new tag...' : ''}
                                                            autoComplete="off"
                                                        />
                                                        {editSuggestions.length > 0 && (
                                                            <div ref={suggestionsRef} className="absolute left-0 right-0 top-full mt-1 bg-gray-800 border border-gray-600 rounded shadow-xl z-20 max-h-40 overflow-y-auto">
                                                                {editSuggestions.map((s, si) => (
                                                                    <button
                                                                        key={s}
                                                                        type="button"
                                                                        onMouseDown={(e) => {
                                                                            e.preventDefault();
                                                                            liveEditValue.current = s;
                                                                            setEditingValue(s);
                                                                            setSuggestionIndex(-1);
                                                                            editInputRef.current?.focus();
                                                                        }}
                                                                        className={[
                                                                            'w-full text-left px-2 py-1 text-xs truncate',
                                                                            si === suggestionIndex
                                                                                ? 'bg-blue-600 text-white'
                                                                                : 'text-gray-300 hover:bg-gray-700',
                                                                        ].join(' ')}
                                                                    >
                                                                        {s}
                                                                    </button>
                                                                ))}
                                                            </div>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <span className={`flex-1 truncate ${isBlank ? 'italic' : ''}`}>
                                                        {isBlank ? 'add tag...' : item.tag}
                                                    </span>
                                                )}

                                                {/* Multi-select count badge */}
                                                {isMulti && !isBlank && item.count < selectedImages.length && (
                                                    <span className="ml-1 text-[9px] text-yellow-400 flex-shrink-0">
                                                        {item.count}/{selectedImages.length}
                                                    </span>
                                                )}

                                                {/* Remove button */}
                                                {!isEditing && !isBlank && (
                                                    <button
                                                        onClick={e => { e.stopPropagation(); handleRemove(item.tag); }}
                                                        className="ml-1 px-1 text-gray-600 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0"
                                                        title="Remove"
                                                    >
                                                        ✕
                                                    </button>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>

                        {/* Keyboard hints */}
                        {focusedIndex >= 0 && (
                            <div className="flex-shrink-0 pt-1 text-[9px] text-gray-600 leading-tight">
                                ↑↓ Navigate · ←→ Prev/Next Image · Tab Edit · Space Toggle · Shift+↑↓ Range · Del Remove{!isMulti && ' · Alt+↑↓ Reorder'}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
