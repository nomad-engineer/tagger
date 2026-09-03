import React, { useRef, useState, useEffect, useCallback, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTaggerStore } from './store';

export interface ImageItem {
    hash: string;
    name: string;
    tag_count: number;
    width?: number;
    height?: number;
    has_alpha?: boolean;
}

interface PageResult {
    items: ImageItem[];
    total: number;
    offset: number;
    limit: number;
    has_more: boolean;
}

interface ContextMenuState {
    x: number;
    y: number;
    hashes: string[];
}

interface GalleryProps {
    onSelectImage: (hash: string, index: number, shiftKey: boolean, ctrlKey?: boolean) => void;
    selectedImages: string[];
    currentDataset: string | null;
    focusRef?: React.RefObject<HTMLDivElement | null>;
}

// Justified row layout types
interface JustifiedItem {
    image: ImageItem;
    index: number;
    width: number;
    height: number;
}

interface JustifiedRow {
    items: JustifiedItem[];
    height: number;
}

function computeJustifiedRows(
    images: ImageItem[],
    containerWidth: number,
    targetHeight: number,
    gap: number,
): JustifiedRow[] {
    if (containerWidth <= 0) return [];
    const rows: JustifiedRow[] = [];
    let currentRow: JustifiedItem[] = [];
    let currentWidth = 0;

    for (let i = 0; i < images.length; i++) {
        const img = images[i];
        const ar = (img.width && img.height && img.height > 0)
            ? img.width / img.height
            : 1;
        const scaledWidth = targetHeight * ar;

        currentRow.push({ image: img, index: i, width: scaledWidth, height: targetHeight });
        currentWidth += scaledWidth + (currentRow.length > 1 ? gap : 0);

        if (currentWidth >= containerWidth && currentRow.length > 0) {
            // Scale row to fit exactly
            const totalGap = (currentRow.length - 1) * gap;
            const availableWidth = containerWidth - totalGap;
            const naturalWidth = currentRow.reduce((s, it) => s + it.width, 0);
            const scale = availableWidth / naturalWidth;
            const rowHeight = Math.round(targetHeight * scale);

            const finalItems = currentRow.map(it => ({
                ...it,
                width: Math.round(it.width * scale),
                height: rowHeight,
            }));

            rows.push({ items: finalItems, height: rowHeight });
            currentRow = [];
            currentWidth = 0;
        }
    }

    // Last partial row — keep target height, don't stretch
    if (currentRow.length > 0) {
        rows.push({ items: currentRow, height: targetHeight });
    }

    return rows;
}

// Thumbnail size buckets the backend caches (must match CacheRepository.SIZE_BUCKETS).
const THUMB_BUCKETS = [200, 400, 800];
const THUMB_VERSION = 3;

function pickBucket(px: number): number {
    for (const b of THUMB_BUCKETS) if (px <= b) return b;
    return THUMB_BUCKETS[THUMB_BUCKETS.length - 1];
}

interface ProgressiveThumbProps {
    hash: string;
    name: string;
    width: number;   // rendered CSS pixels (not physical — browser handles DPR scaling)
    height: number;
    className?: string;
}

// Loads a small low-quality preview instantly, then — only when the cell is
// rendered larger than the 200px preview bucket in CSS pixels — fetches the
// next appropriate size tier and fades it in. Small cells never pay for the
// extra request. We deliberately ignore devicePixelRatio here: CSS pixel sizing
// is the right unit for thumbnail quality decisions (browser upscaling 1.2×–1.5×
// is imperceptible), and using physical pixels would push most retina cells to
// the 800px tier unnecessarily.
const ProgressiveThumb = React.memo(function ProgressiveThumb(
    { hash, name, width, height, className }: ProgressiveThumbProps
) {
    const needed = Math.round(Math.max(width, height));
    const bucket = pickBucket(needed);
    const wantHiRes = bucket > THUMB_BUCKETS[0];
    const [hiLoaded, setHiLoaded] = useState(false);

    // Re-run the fade when the image or the target resolution changes.
    useEffect(() => { setHiLoaded(false); }, [hash, bucket]);

    const base = `/api/images/thumbnail/${hash}?v=${THUMB_VERSION}`;
    const imgClass = `${className ?? ''} absolute inset-0`;

    return (
        <>
            <img
                src={`${base}&size=${THUMB_BUCKETS[0]}`}
                alt={name}
                loading="lazy"
                draggable={false}
                className={`${imgClass} ${wantHiRes && !hiLoaded ? 'blur-[1px]' : ''}`}
                style={{ opacity: wantHiRes && hiLoaded ? 0 : 1 }}
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
            {wantHiRes && (
                <img
                    src={`${base}&size=${bucket}`}
                    alt={name}
                    loading="lazy"
                    draggable={false}
                    className={`${imgClass} transition-opacity duration-200`}
                    style={{ opacity: hiLoaded ? 1 : 0 }}
                    onLoad={() => setHiLoaded(true)}
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
            )}
        </>
    );
});

export function ImageGallery({ onSelectImage, selectedImages, currentDataset, focusRef }: GalleryProps) {
    const [containerWidth, setContainerWidth] = useState(0);
    const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
    const { thumbnailSize, sortBy, viewMode, setStatus, activeImage, setActiveImage } = useTaggerStore();
    const qc = useQueryClient();

    // Use callback ref so the observer attaches even when the div mounts late
    const observerRef = useRef<ResizeObserver | null>(null);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const setContainerRef = useCallback((node: HTMLDivElement | null) => {
        if (observerRef.current) {
            observerRef.current.disconnect();
        }
        if (node) {
            const obs = new ResizeObserver(entries => {
                for (const entry of entries) {
                    setContainerWidth(entry.contentRect.width);
                }
            });
            obs.observe(node);
            observerRef.current = obs;
        }
        containerRef.current = node;
        if (focusRef) focusRef.current = node;
    }, [focusRef]);

    useEffect(() => {
        const close = () => setContextMenu(null);
        if (contextMenu) {
            window.addEventListener('click', close);
            return () => window.removeEventListener('click', close);
        }
    }, [contextMenu]);

    const {
        data,
        fetchNextPage,
        hasNextPage,
        isFetchingNextPage,
        isLoading,
    } = useInfiniteQuery<PageResult>({
        queryKey: ['images', sortBy],
        queryFn: async ({ pageParam }) => {
            const offset = pageParam as number;
            const res = await fetch(`/api/datasets/images?offset=${offset}&limit=200&sort=${sortBy}`);
            if (!res.ok) throw new Error('Network response was not ok');
            return res.json();
        },
        getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.offset + lastPage.limit : undefined,
        initialPageParam: 0,
        staleTime: 5000,
    });

    const allImages = data?.pages.flatMap(p => p.items) ?? [];

    const isListMode = viewMode === 'list';

    const gap = 6;
    const targetRowHeight = thumbnailSize;

    const justifiedRows = useMemo(() => {
        if (isListMode) return [];
        return computeJustifiedRows(allImages, containerWidth - 16, targetRowHeight, gap);
    }, [allImages, containerWidth, targetRowHeight, gap, isListMode]);

    const rowCount = isListMode ? allImages.length : justifiedRows.length;
    const listRowHeight = 100;

    const virtualizer = useVirtualizer({
        count: rowCount,
        getScrollElement: () => containerRef.current,
        estimateSize: (index) => {
            if (isListMode) return listRowHeight;
            return (justifiedRows[index]?.height ?? targetRowHeight) + gap;
        },
        overscan: 3,
    });

    // Scroll active image into view
    useEffect(() => {
        if (!activeImage || !containerRef.current) return;
        if (isListMode) {
            const idx = allImages.findIndex(img => img.hash === activeImage);
            if (idx >= 0) virtualizer.scrollToIndex(idx, { align: 'auto' });
        } else {
            const rowIdx = justifiedRows.findIndex(row =>
                row.items.some(it => it.image.hash === activeImage)
            );
            if (rowIdx >= 0) virtualizer.scrollToIndex(rowIdx, { align: 'auto' });
        }
    }, [activeImage]);

    // Arrow key navigation — only when this gallery container is focused
    const handleGalleryKeyDown = useCallback((e: React.KeyboardEvent) => {
        if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;
        if (viewMode === 'single') return;
        e.preventDefault();

        if (isListMode) {
            if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
                const currentIdx = activeImage ? allImages.findIndex(img => img.hash === activeImage) : -1;
                let nextIdx: number;
                if (e.key === 'ArrowUp') {
                    nextIdx = currentIdx > 0 ? currentIdx - 1 : 0;
                } else {
                    nextIdx = currentIdx < allImages.length - 1 ? currentIdx + 1 : allImages.length - 1;
                }
                setActiveImage(allImages[nextIdx].hash);
            }
            return;
        }

        // Gallery grid mode: find current position in justified rows
        let curRow = -1, curCol = -1;
        for (let r = 0; r < justifiedRows.length; r++) {
            const c = justifiedRows[r].items.findIndex(it => it.image.hash === activeImage);
            if (c >= 0) { curRow = r; curCol = c; break; }
        }
        if (curRow < 0) return;

        let nextHash: string | null = null;

        if (e.key === 'ArrowLeft') {
            if (curCol > 0) {
                nextHash = justifiedRows[curRow].items[curCol - 1].image.hash;
            } else if (curRow > 0) {
                const prevRow = justifiedRows[curRow - 1];
                nextHash = prevRow.items[prevRow.items.length - 1].image.hash;
            }
        } else if (e.key === 'ArrowRight') {
            if (curCol < justifiedRows[curRow].items.length - 1) {
                nextHash = justifiedRows[curRow].items[curCol + 1].image.hash;
            } else if (curRow < justifiedRows.length - 1) {
                nextHash = justifiedRows[curRow + 1].items[0].image.hash;
            }
        } else if (e.key === 'ArrowUp') {
            if (curRow > 0) {
                const prevRow = justifiedRows[curRow - 1];
                const col = Math.min(curCol, prevRow.items.length - 1);
                nextHash = prevRow.items[col].image.hash;
            }
        } else if (e.key === 'ArrowDown') {
            if (curRow < justifiedRows.length - 1) {
                const nextRow = justifiedRows[curRow + 1];
                const col = Math.min(curCol, nextRow.items.length - 1);
                nextHash = nextRow.items[col].image.hash;
            }
        }

        if (nextHash) {
            setActiveImage(nextHash);
        }
    }, [activeImage, allImages, justifiedRows, isListMode, viewMode, setActiveImage]);

    // Load more when near the bottom
    const handleScroll = useCallback(() => {
        if (!containerRef.current || !hasNextPage || isFetchingNextPage) return;
        const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
        if (scrollHeight - scrollTop - clientHeight < 600) {
            fetchNextPage();
        }
    }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        el.addEventListener('scroll', handleScroll, { passive: true });
        return () => el.removeEventListener('scroll', handleScroll);
    }, [handleScroll]);

    const handleContextMenu = useCallback((e: React.MouseEvent, hash: string) => {
        e.preventDefault();
        e.stopPropagation();
        const targets = selectedImages.includes(hash) ? selectedImages : [hash];
        setContextMenu({ x: e.clientX, y: e.clientY, hashes: targets });
    }, [selectedImages]);

    const handleDelete = useCallback(async (hashes: string[]) => {
        setContextMenu(null);
        if (!confirm(`Delete ${hashes.length} image(s)? They will be moved to the deleted folder.`)) return;
        try {
            const res = await fetch('/api/images/delete-batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hashes })
            });
            if (res.ok) {
                const d = await res.json();
                setStatus(`Deleted ${d.deleted} image(s)`, 'success');
                qc.invalidateQueries({ queryKey: ['images'] });
            }
        } catch {
            setStatus('Delete failed', 'error');
        }
    }, [qc, setStatus]);

    const { data: datasetsData } = useQuery({
        queryKey: ['datasets-list'],
        queryFn: async () => {
            const res = await fetch('/api/datasets/list');
            return res.json() as Promise<{ datasets: { id: number; name: string; image_count: number }[] }>;
        },
    });
    const datasets = datasetsData?.datasets ?? [];

    const handleAddToDatasetById = useCallback(async (hashes: string[], datasetId: number, datasetName: string) => {
        setContextMenu(null);
        try {
            const res = await fetch('/api/datasets/add-images-to', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dataset_id: datasetId, image_hashes: hashes })
            });
            if (res.ok) {
                const d = await res.json();
                setStatus(`Added ${d.added} image(s) to "${datasetName}"`, 'success');
                qc.invalidateQueries({ queryKey: ['datasets-list'] });
                if (currentDataset === datasetName) qc.invalidateQueries({ queryKey: ['images'] });
            }
        } catch {
            setStatus('Failed to add to dataset', 'error');
        }
    }, [setStatus, qc, currentDataset]);

    const handleRemoveFromDataset = useCallback(async (hashes: string[]) => {
        setContextMenu(null);
        try {
            const res = await fetch('/api/datasets/remove-images', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image_hashes: hashes })
            });
            if (res.ok) {
                const d = await res.json();
                setStatus(`Removed ${d.removed} image(s) from dataset`, 'success');
                qc.invalidateQueries({ queryKey: ['images'] });
            }
        } catch {
            setStatus('Failed to remove from dataset', 'error');
        }
    }, [qc, setStatus]);

    if (isLoading) {
        return (
            <div className="flex w-full h-full items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white" />
            </div>
        );
    }

    if (allImages.length === 0) {
        return (
            <div className="flex w-full h-full items-center justify-center text-gray-500 flex-col gap-2">
                <svg className="w-12 h-12 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <p>No images. Open a library or scan for new files.</p>
            </div>
        );
    }

    return (
        <>
            <div
                ref={setContainerRef}
                className="flex-1 overflow-auto bg-gray-900 p-2 focus:outline-none"
                style={{ height: '100%' }}
                tabIndex={0}
                onKeyDown={handleGalleryKeyDown}
            >
                <div className="relative w-full" style={{ height: `${virtualizer.getTotalSize()}px` }}>
                    {virtualizer.getVirtualItems().map((virtualRow) => {
                        const rowIndex = virtualRow.index;

                        if (isListMode) {
                            const image = allImages[rowIndex];
                            if (!image) return null;
                            const isSelected = selectedImages.includes(image.hash);
                            const isActive = activeImage === image.hash;
                            return (
                                <div
                                    key={image.hash}
                                    className={`absolute top-0 left-0 w-full flex items-center gap-3 px-2 cursor-pointer select-none transition-all duration-100
                                        ${isActive
                                            ? 'bg-gray-700/60 border-l-2 border-white'
                                            : isSelected
                                                ? 'bg-blue-900/40 border-l-2 border-blue-400'
                                                : 'hover:bg-gray-800/60 border-l-2 border-transparent'
                                        }`}
                                    style={{ height: `${listRowHeight}px`, transform: `translateY(${virtualRow.start}px)` }}
                                    onClick={(e) => onSelectImage(image.hash, rowIndex, e.shiftKey, e.ctrlKey || e.metaKey)}
                                    onContextMenu={(e) => handleContextMenu(e, image.hash)}
                                >
                                    <div className={`relative flex-shrink-0 rounded overflow-hidden ${image.has_alpha ? 'checkerboard-bg' : 'bg-gray-900'}`} style={{ width: 120, height: 80 }}>
                                        <ProgressiveThumb
                                            hash={image.hash}
                                            name={image.name}
                                            width={120}
                                            height={80}
                                            className="w-full h-full object-contain"
                                        />
                                        {isSelected && (
                                            <div className="absolute top-1 right-1 w-4 h-4 bg-blue-500 rounded-full flex items-center justify-center">
                                                <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
                                                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                                </svg>
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs text-gray-100 truncate font-medium">{image.name}</p>
                                        <p className="text-[10px] text-gray-500 mt-0.5">{image.tag_count} tags</p>
                                    </div>
                                </div>
                            );
                        }

                        // Justified gallery row
                        const row = justifiedRows[rowIndex];
                        if (!row) return null;

                        return (
                            <div
                                key={virtualRow.index}
                                className="absolute top-0 left-0 w-full flex"
                                style={{
                                    transform: `translateY(${virtualRow.start}px)`,
                                    gap: `${gap}px`,
                                    padding: '0 4px',
                                    height: `${row.height + gap}px`,
                                    alignItems: 'flex-start',
                                }}
                            >
                                {row.items.map((item) => {
                                    const isSelected = selectedImages.includes(item.image.hash);
                                    const isActive = activeImage === item.image.hash;

                                    return (
                                        <div
                                            key={item.image.hash}
                                            style={{ width: `${item.width}px`, height: `${item.height}px` }}
                                            className={`relative rounded cursor-pointer transition-all duration-100 overflow-hidden select-none flex-shrink-0 ${item.image.has_alpha ? 'checkerboard-bg' : 'bg-gray-800'}
                                                ${isActive
                                                    ? 'ring-2 ring-white shadow-lg shadow-white/20'
                                                    : isSelected
                                                        ? 'ring-2 ring-blue-400 shadow-lg shadow-blue-500/30'
                                                        : 'hover:ring-1 hover:ring-gray-500'
                                                }`}
                                            onClick={(e) => onSelectImage(item.image.hash, item.index, e.shiftKey, e.ctrlKey || e.metaKey)}
                                            onContextMenu={(e) => handleContextMenu(e, item.image.hash)}
                                        >
                                            <ProgressiveThumb
                                                hash={item.image.hash}
                                                name={item.image.name}
                                                width={item.width}
                                                height={item.height}
                                                className="w-full h-full object-contain"
                                            />
                                            {isSelected && (
                                                <div className="absolute top-1.5 right-1.5 w-5 h-5 bg-blue-500 rounded-full flex items-center justify-center shadow-md">
                                                    <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                                                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                                    </svg>
                                                </div>
                                            )}
                                            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-1.5 py-0.5">
                                                <p className="text-[10px] text-gray-200 truncate font-medium leading-tight">{item.image.name}</p>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        );
                    })}
                </div>
                {isFetchingNextPage && (
                    <div className="flex justify-center py-4">
                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-400" />
                    </div>
                )}
            </div>

            {contextMenu && (
                <div
                    className="fixed z-50 bg-gray-800 border border-gray-600 rounded-lg shadow-xl py-1 min-w-[160px]"
                    style={{ left: contextMenu.x, top: contextMenu.y }}
                    onClick={e => e.stopPropagation()}
                >
                    <div className="px-3 py-1 text-[10px] text-gray-500 border-b border-gray-700 mb-1">
                        {contextMenu.hashes.length} image(s)
                    </div>
                    {datasets.length > 0 && (
                        <>
                            <div className="px-3 py-1 text-[10px] text-gray-500 uppercase tracking-wider">Add to dataset</div>
                            {datasets.map(ds => (
                                <button
                                    key={ds.id}
                                    className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-700 text-gray-200"
                                    onClick={() => handleAddToDatasetById(contextMenu.hashes, ds.id, ds.name)}
                                >
                                    {ds.name} <span className="text-gray-500">({ds.image_count})</span>
                                </button>
                            ))}
                            {currentDataset && (
                                <button
                                    className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-700 text-red-300"
                                    onClick={() => handleRemoveFromDataset(contextMenu.hashes)}
                                >
                                    Remove from "{currentDataset}"
                                </button>
                            )}
                            <div className="border-t border-gray-700 my-1" />
                        </>
                    )}
                    <button
                        className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-700 text-gray-200"
                        onClick={() => {
                            setContextMenu(null);
                            if (contextMenu.hashes[0]) {
                                navigator.clipboard.writeText(contextMenu.hashes[0]).catch(() => {});
                            }
                        }}
                    >
                        Copy hash
                    </button>
                    <div className="border-t border-gray-700 my-1" />
                    <button
                        className="w-full text-left px-3 py-1.5 text-xs hover:bg-red-900/60 text-red-400"
                        onClick={() => handleDelete(contextMenu.hashes)}
                    >
                        Delete image(s)
                    </button>
                </div>
            )}
        </>
    );
}
