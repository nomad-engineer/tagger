import { create } from 'zustand'

export type SortBy = 'default' | 'name' | 'caption';

export interface StatusMessage {
    text: string;
    type: 'info' | 'success' | 'error';
}

interface TaggerState {
    selectedImages: string[];
    activeImage: string | null;
    currentDataset: string | null;
    thumbnailSize: number;
    sortBy: SortBy;
    status: StatusMessage | null;

    // Actions
    toggleSelection: (hash: string) => void;
    addToSelection: (hashes: string[]) => void;
    clearSelection: () => void;
    selectAll: (hashes: string[]) => void;
    setActiveImage: (hash: string | null) => void;
    setDataset: (datasetName: string | null) => void;
    setThumbnailSize: (n: number) => void;
    setSortBy: (s: SortBy) => void;
    setStatus: (text: string | null, type?: 'info' | 'success' | 'error') => void;
}

export const useTaggerStore = create<TaggerState>((set) => ({
    selectedImages: [],
    activeImage: null,
    currentDataset: null,
    thumbnailSize: 180,
    sortBy: 'default',
    status: null,

    toggleSelection: (hash) => set((state) => {
        const isSelected = state.selectedImages.includes(hash);
        if (isSelected) {
            return { selectedImages: state.selectedImages.filter(h => h !== hash) };
        } else {
            return { selectedImages: [...state.selectedImages, hash] };
        }
    }),

    addToSelection: (hashes) => set((state) => {
        const newSet = new Set([...state.selectedImages, ...hashes]);
        return { selectedImages: Array.from(newSet) };
    }),

    clearSelection: () => set({ selectedImages: [], activeImage: null }),

    selectAll: (hashes) => set({ selectedImages: hashes }),

    setActiveImage: (hash) => set({ activeImage: hash }),

    setDataset: (name) => set({ currentDataset: name }),

    setThumbnailSize: (n) => set({ thumbnailSize: Math.max(80, Math.min(400, n)) }),

    setSortBy: (s) => set({ sortBy: s }),

    setStatus: (text, type = 'info') => set({
        status: text ? { text, type } : null
    }),
}));
