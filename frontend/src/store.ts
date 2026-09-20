import { create } from 'zustand'

export type SortBy = 'default' | 'name' | 'caption';
export type ViewMode = 'gallery' | 'list' | 'single';

export interface StatusMessage {
    text: string;
    type: 'info' | 'success' | 'error';
}

interface TaggerState {
    // activeImage: the currently highlighted/focused image (shown in single view, tags displayed)
    // selectedImages: the batch selection for multi-edit (independent of activeImage)
    selectedImages: string[];
    activeImage: string | null;
    currentDataset: string | null;
    thumbnailSize: number;
    sortBy: SortBy;
    viewMode: ViewMode;
    tagEditorWidth: number;
    // Last non-single view, so the mobile single-image view can go "back" to it.
    lastGridView: 'gallery' | 'list';
    // Touch multi-select: while on, a tap toggles selection instead of opening the image.
    selectMode: boolean;
    // Mobile: whether the tag editor drawer is slid out.
    editorOpen: boolean;
    status: StatusMessage | null;

    // Actions
    setActiveImage: (hash: string | null) => void;
    // Single click: set active, clear selection
    selectSingle: (hash: string) => void;
    // Ctrl+click: toggle hash in/out of selection, set active
    ctrlSelect: (hash: string) => void;
    // Shift+click: add range to selection
    addToSelection: (hashes: string[]) => void;
    // Toggle a hash in/out of the selection and make it active (touch select mode)
    toggleSelect: (hash: string) => void;
    // Space: toggle active image in/out of selection without changing active
    toggleActiveInSelection: () => void;
    clearSelection: () => void;
    selectAll: (hashes: string[]) => void;
    setDataset: (datasetName: string | null) => void;
    setThumbnailSize: (n: number) => void;
    setSortBy: (s: SortBy) => void;
    setViewMode: (m: ViewMode) => void;
    setTagEditorWidth: (n: number) => void;
    setSelectMode: (on: boolean) => void;
    setEditorOpen: (open: boolean) => void;
    setStatus: (text: string | null, type?: 'info' | 'success' | 'error') => void;
}

export const useTaggerStore = create<TaggerState>((set) => ({
    selectedImages: [],
    activeImage: null,
    currentDataset: null,
    thumbnailSize: 180,
    sortBy: 'default',
    viewMode: 'gallery',
    // Scale the default with the screen so large monitors get a roomier editor.
    tagEditorWidth: typeof window === 'undefined' ? 320 : Math.round(Math.max(320, Math.min(560, window.innerWidth * 0.22))),
    lastGridView: 'gallery',
    selectMode: false,
    editorOpen: false,
    status: null,

    setActiveImage: (hash) => set({ activeImage: hash }),

    selectSingle: (hash) => set({ activeImage: hash, selectedImages: [] }),

    ctrlSelect: (hash) => set((state) => {
        // If entering multi-select from single mode, include the previously active image
        let base = state.selectedImages;
        if (base.length === 0 && state.activeImage && state.activeImage !== hash) {
            base = [state.activeImage];
        }
        const isSelected = base.includes(hash);
        const newSelection = isSelected
            ? base.filter(h => h !== hash)
            : [...base, hash];
        return { activeImage: hash, selectedImages: newSelection };
    }),

    toggleSelect: (hash) => set((state) => ({
        activeImage: hash,
        selectedImages: state.selectedImages.includes(hash)
            ? state.selectedImages.filter(h => h !== hash)
            : [...state.selectedImages, hash],
    })),

    addToSelection: (hashes) => set((state) => {
        const newSet = new Set([...state.selectedImages, ...hashes]);
        return { selectedImages: Array.from(newSet) };
    }),

    toggleActiveInSelection: () => set((state) => {
        if (!state.activeImage) return {};
        const hash = state.activeImage;
        const isSelected = state.selectedImages.includes(hash);
        if (isSelected) {
            return { selectedImages: state.selectedImages.filter(h => h !== hash) };
        } else {
            return { selectedImages: [...state.selectedImages, hash] };
        }
    }),

    clearSelection: () => set({ selectedImages: [], selectMode: false }),

    selectAll: (hashes) => set({ selectedImages: hashes }),

    setDataset: (name) => set({ currentDataset: name }),

    setThumbnailSize: (n) => set({ thumbnailSize: Math.max(80, Math.min(480, n)) }),

    setSortBy: (s) => set({ sortBy: s }),

    setViewMode: (m) => set((state) => ({
        viewMode: m,
        lastGridView: m === 'single' ? state.lastGridView : m,
    })),

    setTagEditorWidth: (n) => set({ tagEditorWidth: Math.max(200, Math.min(800, n)) }),

    setSelectMode: (on) => set(on ? { selectMode: true } : { selectMode: false, selectedImages: [] }),

    setEditorOpen: (open) => set({ editorOpen: open }),

    setStatus: (text, type = 'info') => set({
        status: text ? { text, type } : null
    }),
}));
