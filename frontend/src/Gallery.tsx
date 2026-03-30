import React, { useRef, useState, useEffect, useCallback } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { useTaggerStore } from './store';

export interface ImageItem {
    hash: string;
    name: string;
    tag_count: number;
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
    onSelectImage: (hash: string, index: number, shiftKey: boolean) => void;
    selectedImages: string[];
    currentDataset: string | null;
}

export function ImageGallery({ onSelectImage, selectedImages, currentDataset }: GalleryProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [containerWidth, setContainerWidth] = useState(800);
    const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
    const { thumbnailSize, sortBy, setStatus } = useTaggerStore();
    const qc = useQueryClient();

    useEffect(() => {
        const observer = new ResizeObserver(entries => {
            for (const entry of entries) {
                setContainerWidth(entry.contentRect.width);
            }
        });
        if (containerRef.current) observer.observe(containerRef.current);
        return () => observer.disconnect();
    }, []);

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

    const gap = 8;
    const itemWidth = thumbnailSize + gap;
    const columnCount = Math.max(1, Math.floor((containerWidth - 16) / itemWidth));
    const rowCount = Math.ceil(allImages.length / columnCount);
    const rowHeight = thumbnailSize + 52;

    const virtualizer = useVirtualizer({
        count: rowCount,
        getScrollElement: () => containerRef.current,
        estimateSize: () => rowHeight,
        overscan: 3,
    });

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

    const handleAddToDataset = useCallback(async (hashes: string[]) => {
        setContextMenu(null);
        try {
            const res = await fetch('/api/datasets/add-images', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image_hashes: hashes })
            });
            if (res.ok) {
                const d = await res.json();
                setStatus(`Added ${d.added} image(s) to dataset`, 'success');
            }
        } catch {
            setStatus('Failed to add to dataset', 'error');
        }
    }, [setStatus]);

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
                ref={containerRef}
                className="flex-1 overflow-auto bg-gray-900 p-2"
                style={{ height: '100%' }}
                tabIndex={0}
            >
                <div className="relative w-full" style={{ height: `${virtualizer.getTotalSize()}px` }}>
                    {virtualizer.getVirtualItems().map((virtualRow) => {
                        const rowIndex = virtualRow.index;
                        return (
                            <div
                                key={virtualRow.index}
                                className="absolute top-0 left-0 w-full flex"
                                style={{
                                    height: `${rowHeight}px`,
                                    transform: `translateY(${virtualRow.start}px)`,
                                    gap: `${gap}px`,
                                    padding: '0 4px',
                                }}
                            >
                                {[...Array(columnCount)].map((_, colIndex) => {
                                    const itemIndex = rowIndex * columnCount + colIndex;
                                    const image = allImages[itemIndex];

                                    if (!image) return <div key={colIndex} style={{ flex: 1 }} />;

                                    const isSelected = selectedImages.includes(image.hash);

                                    return (
                                        <div
                                            key={image.hash}
                                            style={{ flex: 1, maxWidth: `${thumbnailSize + 4}px` }}
                                            className={`flex flex-col rounded-lg cursor-pointer transition-all duration-100 overflow-hidden select-none
                                                ${isSelected
                                                    ? 'ring-2 ring-blue-400 shadow-lg shadow-blue-500/30 bg-gray-700'
                                                    : 'hover:ring-1 hover:ring-gray-500 bg-gray-800'
                                                }`}
                                            onClick={(e) => onSelectImage(image.hash, itemIndex, e.shiftKey)}
                                            onContextMenu={(e) => handleContextMenu(e, image.hash)}
                                        >
                                            <div
                                                className="relative overflow-hidden bg-gray-900"
                                                style={{ height: `${thumbnailSize}px` }}
                                            >
                                                <img
                                                    src={`/api/images/thumbnail/${image.hash}`}
                                                    alt={image.name}
                                                    loading="lazy"
                                                    className="w-full h-full object-cover"
                                                    onError={(e) => {
                                                        (e.target as HTMLImageElement).style.display = 'none';
                                                    }}
                                                />
                                                {isSelected && (
                                                    <div className="absolute top-1.5 right-1.5 w-5 h-5 bg-blue-500 rounded-full flex items-center justify-center shadow-md">
                                                        <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                                                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                                        </svg>
                                                    </div>
                                                )}
                                            </div>
                                            <div className="px-1.5 py-1">
                                                <p className="text-[10px] text-gray-200 truncate font-medium leading-tight">{image.name}</p>
                                                <p className="text-[9px] text-gray-500 leading-tight mt-0.5">{image.tag_count} tags</p>
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
                    {currentDataset && (
                        <>
                            <button
                                className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-700 text-gray-200"
                                onClick={() => handleAddToDataset(contextMenu.hashes)}
                            >
                                + Add to "{currentDataset}"
                            </button>
                            <button
                                className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-700 text-gray-200"
                                onClick={() => handleRemoveFromDataset(contextMenu.hashes)}
                            >
                                - Remove from dataset
                            </button>
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
