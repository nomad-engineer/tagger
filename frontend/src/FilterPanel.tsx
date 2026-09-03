import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';

interface SavedFilter {
    id: number;
    name: string;
    expression: string;
    created_at: string;
    modified_at: string;
}

interface FilterPanelProps {
    expression: string;
    onApply: (expression: string) => void;
}

// Quick-insert filter chips
const QUICK_FILTERS = [
    { label: 'Images', expr: 'type:image', group: 'type' },
    { label: 'Videos', expr: 'type:video', group: 'type' },
    { label: 'Has Alpha', expr: 'has:alpha', group: 'property' },
    { label: 'Has Caption', expr: 'has:caption', group: 'property' },
    { label: 'Untagged', expr: 'untagged', group: 'property' },
    { label: 'Has Tags', expr: 'has:tags', group: 'property' },
] as const;

export function FilterPanel({ expression, onApply }: FilterPanelProps) {
    const [localExpr, setLocalExpr] = useState(expression);
    const [showSaveDialog, setShowSaveDialog] = useState(false);
    const [saveName, setSaveName] = useState('');
    const [showHelp, setShowHelp] = useState(false);
    const [editingFilterId, setEditingFilterId] = useState<number | null>(null);
    const [editingName, setEditingName] = useState('');
    const [suggestionIndex, setSuggestionIndex] = useState(-1);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);
    const suggestionsRef = useRef<HTMLDivElement>(null);
    const qc = useQueryClient();

    // Fetch all tag suggestions for autocomplete
    const { data: allTags } = useQuery<string[]>({
        queryKey: ['tag-suggestions-all'],
        queryFn: async () => {
            const res = await fetch('/api/tags/suggestions');
            if (!res.ok) return [];
            const data = await res.json();
            return data.suggestions || [];
        },
        staleTime: 30000,
    });

    // Sync with parent expression
    useEffect(() => {
        setLocalExpr(expression);
    }, [expression]);

    // Extract the current token being typed (the partial tag after operators/parens)
    const getCurrentToken = useCallback((): { token: string; start: number; end: number } | null => {
        const input = inputRef.current;
        if (!input) return null;
        const cursor = input.selectionStart ?? localExpr.length;
        const textBeforeCursor = localExpr.slice(0, cursor);

        // Find the start of the current token: split on whitespace, parens, quotes
        const match = textBeforeCursor.match(/([^\s()]+)$/);
        if (!match) return null;
        const token = match[1];
        const start = cursor - token.length;

        // Don't suggest for operators/keywords or special predicates
        const upper = token.toUpperCase();
        if (['AND', 'OR', 'NOT'].includes(upper)) return null;
        if (/^(type:|has:|untagged|tag_count)/i.test(token)) return null;

        // Need at least 1 character
        if (token.length < 1) return null;

        return { token, start, end: cursor };
    }, [localExpr]);

    // Fuzzy match: characters must appear in order (not necessarily contiguous)
    const fuzzyMatch = useCallback((needle: string, haystack: string): { match: boolean; score: number } => {
        const lower = haystack.toLowerCase();
        const search = needle.toLowerCase();
        let si = 0;
        let score = 0;
        let prevMatchIdx = -2;

        for (let hi = 0; hi < lower.length && si < search.length; hi++) {
            if (lower[hi] === search[si]) {
                score += 1;
                // Bonus for consecutive matches
                if (hi === prevMatchIdx + 1) score += 2;
                // Bonus for matching at start or after separator
                if (hi === 0 || lower[hi - 1] === ':' || lower[hi - 1] === '_' || lower[hi - 1] === '-') score += 3;
                prevMatchIdx = hi;
                si++;
            }
        }

        return { match: si === search.length, score };
    }, []);

    const suggestions = useMemo(() => {
        if (!allTags?.length) return [];
        const tokenInfo = getCurrentToken();
        if (!tokenInfo) return [];
        const { token } = tokenInfo;

        const scored: { tag: string; score: number }[] = [];
        for (const tag of allTags) {
            // Exact prefix gets highest priority
            if (tag.toLowerCase().startsWith(token.toLowerCase())) {
                scored.push({ tag, score: 1000 + tag.length });
            } else if (tag.toLowerCase().includes(token.toLowerCase())) {
                scored.push({ tag, score: 500 });
            } else {
                const { match, score } = fuzzyMatch(token, tag);
                if (match) scored.push({ tag, score });
            }
        }

        scored.sort((a, b) => b.score - a.score);
        return scored.slice(0, 10).map(s => s.tag);
    }, [allTags, localExpr, getCurrentToken, fuzzyMatch]);

    // Show/hide suggestions based on whether we have matches
    useEffect(() => {
        setShowSuggestions(suggestions.length > 0);
        setSuggestionIndex(-1);
    }, [suggestions]);

    // Scroll active suggestion into view
    useEffect(() => {
        if (suggestionIndex >= 0 && suggestionsRef.current) {
            const items = suggestionsRef.current.children;
            if (items[suggestionIndex]) {
                (items[suggestionIndex] as HTMLElement).scrollIntoView({ block: 'nearest' });
            }
        }
    }, [suggestionIndex]);

    const acceptSuggestion = useCallback((tag: string) => {
        const tokenInfo = getCurrentToken();
        if (!tokenInfo) return;
        const before = localExpr.slice(0, tokenInfo.start);
        const after = localExpr.slice(tokenInfo.end);
        const formatted = tag.includes(' ') ? `"${tag}"` : tag;
        const newExpr = before + formatted + after;
        setLocalExpr(newExpr);
        setShowSuggestions(false);
        setSuggestionIndex(-1);
        setTimeout(() => {
            if (inputRef.current) {
                inputRef.current.focus();
                const pos = tokenInfo.start + formatted.length;
                inputRef.current.setSelectionRange(pos, pos);
            }
        }, 0);
    }, [localExpr, getCurrentToken]);

    // Saved filters query
    const { data: savedFilters } = useQuery<SavedFilter[]>({
        queryKey: ['saved-filters'],
        queryFn: async () => {
            const res = await fetch('/api/library/filters/saved');
            if (!res.ok) return [];
            const data = await res.json();
            return data.filters || [];
        },
        staleTime: 10000,
    });

    // Save filter mutation
    const saveMutation = useMutation({
        mutationFn: async ({ name, expr }: { name: string; expr: string }) => {
            const res = await fetch('/api/library/filters/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, expression: expr }),
            });
            if (!res.ok) throw new Error('Failed to save');
            return res.json();
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['saved-filters'] });
            setShowSaveDialog(false);
            setSaveName('');
        },
    });

    // Delete filter mutation
    const deleteMutation = useMutation({
        mutationFn: async (id: number) => {
            const res = await fetch(`/api/library/filters/${id}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Failed to delete');
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['saved-filters'] }),
    });

    // Rename filter mutation
    const renameMutation = useMutation({
        mutationFn: async ({ id, name }: { id: number; name: string }) => {
            const res = await fetch(`/api/library/filters/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name }),
            });
            if (!res.ok) throw new Error('Failed to rename');
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['saved-filters'] });
            setEditingFilterId(null);
        },
    });

    const handleApply = useCallback(() => {
        onApply(localExpr);
    }, [localExpr, onApply]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (showSuggestions && suggestions.length > 0) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setSuggestionIndex(i => Math.min(i + 1, suggestions.length - 1));
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                setSuggestionIndex(i => Math.max(i - 1, -1));
                return;
            }
            if (e.key === 'Tab' || (e.key === 'Enter' && suggestionIndex >= 0)) {
                e.preventDefault();
                const idx = suggestionIndex >= 0 ? suggestionIndex : 0;
                acceptSuggestion(suggestions[idx]);
                return;
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                setShowSuggestions(false);
                return;
            }
        }
        if (e.key === 'Enter') {
            handleApply();
        }
    };

    const handleClear = () => {
        setLocalExpr('');
        onApply('');
        inputRef.current?.focus();
    };

    const insertExpression = (expr: string) => {
        const current = localExpr.trim();
        if (!current) {
            setLocalExpr(expr);
        } else {
            // Smart append: add AND if needed
            setLocalExpr(`${current} AND ${expr}`);
        }
    };

    const toggleQuickFilter = (expr: string) => {
        const current = localExpr.trim();
        // Check if this exact expression is already in the filter
        const parts = current.split(/\s+AND\s+|\s+OR\s+/i).map(p => p.trim().replace(/^\(|\)$/g, '').trim());
        if (parts.some(p => p.toLowerCase() === expr.toLowerCase())) {
            // Remove it
            const regex = new RegExp(
                `(\\s+AND\\s+${expr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}|${expr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+AND\\s+|${expr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`,
                'gi'
            );
            const newExpr = current.replace(regex, '').trim();
            setLocalExpr(newExpr);
            onApply(newExpr);
        } else {
            const newExpr = current ? `${current} AND ${expr}` : expr;
            setLocalExpr(newExpr);
            onApply(newExpr);
        }
    };

    const isQuickFilterActive = (expr: string) => {
        const current = localExpr.toLowerCase();
        return current.includes(expr.toLowerCase());
    };

    const handleSave = () => {
        if (saveName.trim() && localExpr.trim()) {
            saveMutation.mutate({ name: saveName.trim(), expr: localExpr.trim() });
        }
    };

    const loadSavedFilter = (filter: SavedFilter) => {
        setLocalExpr(filter.expression);
        onApply(filter.expression);
    };

    const handleRenameSubmit = (id: number) => {
        if (editingName.trim()) {
            renameMutation.mutate({ id, name: editingName.trim() });
        } else {
            setEditingFilterId(null);
        }
    };

    return (
        <div className="bg-gray-800 border border-gray-700 rounded-lg shadow-2xl overflow-hidden">
            {/* Expression input */}
            <div className="p-3 space-y-2">
                <div className="flex gap-2">
                    <div className="relative flex-1">
                        <input
                            ref={inputRef}
                            type="text"
                            value={localExpr}
                            onChange={e => setLocalExpr(e.target.value)}
                            onKeyDown={handleKeyDown}
                            onBlur={() => { setTimeout(() => setShowSuggestions(false), 150); }}
                            onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
                            placeholder="Filter expression... (e.g. class:* AND NOT untagged)"
                            className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 pr-16 font-mono"
                            autoFocus
                        />
                        {localExpr && (
                            <button
                                onClick={handleClear}
                                className="absolute right-8 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs px-1"
                                title="Clear filter"
                            >
                                ✕
                            </button>
                        )}
                        <button
                            onClick={() => setShowHelp(h => !h)}
                            className={`absolute right-1.5 top-1/2 -translate-y-1/2 text-xs px-1.5 py-0.5 rounded ${showHelp ? 'text-blue-400 bg-blue-900/30' : 'text-gray-500 hover:text-gray-300'}`}
                            title="Filter syntax help"
                        >
                            ?
                        </button>
                        {/* Tag suggestions dropdown */}
                        {showSuggestions && suggestions.length > 0 && (
                            <div
                                ref={suggestionsRef}
                                className="absolute left-0 right-0 top-full mt-1 bg-gray-900 border border-gray-600 rounded shadow-xl z-50 max-h-48 overflow-y-auto"
                            >
                                {suggestions.map((tag, i) => {
                                    const tokenInfo = getCurrentToken();
                                    const needle = tokenInfo?.token.toLowerCase() || '';
                                    // Highlight matching characters
                                    const parts: { text: string; highlight: boolean }[] = [];
                                    let ni = 0;
                                    for (let ci = 0; ci < tag.length; ci++) {
                                        if (ni < needle.length && tag[ci].toLowerCase() === needle[ni]) {
                                            parts.push({ text: tag[ci], highlight: true });
                                            ni++;
                                        } else {
                                            parts.push({ text: tag[ci], highlight: false });
                                        }
                                    }
                                    return (
                                        <div
                                            key={tag}
                                            onMouseDown={e => { e.preventDefault(); acceptSuggestion(tag); }}
                                            onMouseEnter={() => setSuggestionIndex(i)}
                                            className={`px-3 py-1 text-xs font-mono cursor-pointer ${
                                                i === suggestionIndex
                                                    ? 'bg-blue-700/60 text-white'
                                                    : 'text-gray-300 hover:bg-gray-800'
                                            }`}
                                        >
                                            {parts.map((p, j) =>
                                                p.highlight
                                                    ? <span key={j} className="text-blue-400 font-semibold">{p.text}</span>
                                                    : <span key={j}>{p.text}</span>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                    <button
                        onClick={handleApply}
                        className="px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white rounded text-xs font-medium flex-shrink-0"
                    >
                        Apply
                    </button>
                </div>

                {/* Quick filter chips */}
                <div className="flex flex-wrap gap-1.5">
                    {QUICK_FILTERS.map(qf => (
                        <button
                            key={qf.expr}
                            onClick={() => toggleQuickFilter(qf.expr)}
                            className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors border
                                ${isQuickFilterActive(qf.expr)
                                    ? 'bg-blue-700/60 border-blue-500 text-blue-200'
                                    : 'bg-gray-800 border-gray-600 text-gray-400 hover:border-gray-500 hover:text-gray-300'}`}
                        >
                            {qf.label}
                        </button>
                    ))}
                    <span className="text-gray-600 text-[10px] leading-5 px-1">|</span>
                    <button
                        onClick={() => insertExpression('tag_count>5')}
                        className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-800 border border-gray-600 text-gray-400 hover:border-gray-500 hover:text-gray-300"
                    >
                        Tags &gt; 5
                    </button>
                    <button
                        onClick={() => insertExpression('tag_count<3')}
                        className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-800 border border-gray-600 text-gray-400 hover:border-gray-500 hover:text-gray-300"
                    >
                        Tags &lt; 3
                    </button>
                </div>

                {/* Logical operator insert buttons */}
                <div className="flex gap-1.5 items-center">
                    <span className="text-[9px] text-gray-500 uppercase tracking-wider">Insert:</span>
                    {['AND', 'OR', 'NOT', '(', ')'].map(op => (
                        <button
                            key={op}
                            onClick={() => {
                                const cur = localExpr.trim();
                                if (op === '(' || op === 'NOT') {
                                    setLocalExpr(cur ? `${cur} ${op} ` : `${op} `);
                                } else if (op === ')') {
                                    setLocalExpr(`${cur})`);
                                } else {
                                    setLocalExpr(cur ? `${cur} ${op} ` : '');
                                }
                                inputRef.current?.focus();
                            }}
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-gray-700 text-gray-400 hover:bg-gray-600 hover:text-gray-200"
                        >
                            {op}
                        </button>
                    ))}
                </div>
            </div>

            {/* Saved filters */}
            {(savedFilters && savedFilters.length > 0) && (
                <div className="border-t border-gray-700 px-3 py-2">
                    <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[9px] text-gray-500 uppercase tracking-wider font-semibold">Saved Filters</span>
                    </div>
                    <div className="space-y-0.5 max-h-32 overflow-y-auto">
                        {savedFilters.map(sf => (
                            <div
                                key={sf.id}
                                className="flex items-center gap-1.5 group rounded px-1.5 py-1 hover:bg-gray-700/50 -mx-1.5"
                            >
                                {editingFilterId === sf.id ? (
                                    <input
                                        type="text"
                                        value={editingName}
                                        onChange={e => setEditingName(e.target.value)}
                                        onKeyDown={e => {
                                            if (e.key === 'Enter') handleRenameSubmit(sf.id);
                                            if (e.key === 'Escape') setEditingFilterId(null);
                                        }}
                                        onBlur={() => handleRenameSubmit(sf.id)}
                                        className="flex-1 bg-gray-900 border border-blue-500 rounded px-1.5 py-0.5 text-[10px] text-white focus:outline-none"
                                        autoFocus
                                    />
                                ) : (
                                    <button
                                        onClick={() => loadSavedFilter(sf)}
                                        className="flex-1 text-left text-[11px] text-gray-300 hover:text-white truncate"
                                        title={sf.expression}
                                    >
                                        <span className="font-medium">{sf.name}</span>
                                        <span className="text-gray-600 ml-1.5 font-mono text-[9px]">{sf.expression}</span>
                                    </button>
                                )}
                                <button
                                    onClick={() => { setEditingFilterId(sf.id); setEditingName(sf.name); }}
                                    className="text-gray-600 hover:text-gray-300 text-[10px] opacity-0 group-hover:opacity-100 transition-opacity px-0.5"
                                    title="Rename"
                                >
                                    ✎
                                </button>
                                <button
                                    onClick={() => deleteMutation.mutate(sf.id)}
                                    className="text-gray-600 hover:text-red-400 text-[10px] opacity-0 group-hover:opacity-100 transition-opacity px-0.5"
                                    title="Delete"
                                >
                                    ✕
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Save current filter */}
            <div className="border-t border-gray-700 px-3 py-2">
                {showSaveDialog ? (
                    <div className="flex gap-1.5">
                        <input
                            type="text"
                            value={saveName}
                            onChange={e => setSaveName(e.target.value)}
                            onKeyDown={e => {
                                if (e.key === 'Enter') handleSave();
                                if (e.key === 'Escape') setShowSaveDialog(false);
                            }}
                            placeholder="Filter name..."
                            className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-1 text-[10px] text-white focus:outline-none focus:border-blue-500"
                            autoFocus
                        />
                        <button
                            onClick={handleSave}
                            disabled={!saveName.trim() || !localExpr.trim()}
                            className="px-2 py-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded text-[10px] font-medium"
                        >
                            Save
                        </button>
                        <button
                            onClick={() => setShowSaveDialog(false)}
                            className="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-[10px]"
                        >
                            Cancel
                        </button>
                    </div>
                ) : (
                    <button
                        onClick={() => setShowSaveDialog(true)}
                        disabled={!localExpr.trim()}
                        className="text-[10px] text-gray-500 hover:text-gray-300 disabled:opacity-30 disabled:cursor-default"
                    >
                        + Save current filter
                    </button>
                )}
            </div>

            {/* Syntax help */}
            {showHelp && (
                <div className="border-t border-gray-700 px-3 py-2 bg-gray-900/50">
                    <div className="text-[10px] text-gray-400 space-y-1.5">
                        <p className="font-semibold text-gray-300 text-[11px] mb-2">Filter Syntax</p>
                        <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                            <code className="text-blue-400 font-mono">class:lake</code>
                            <span>Exact tag match</span>

                            <code className="text-blue-400 font-mono">class:*</code>
                            <span>Wildcard — all tags starting with "class:"</span>

                            <code className="text-blue-400 font-mono">*mountain*</code>
                            <span>Contains "mountain" anywhere in tag</span>

                            <code className="text-blue-400 font-mono">"tag with spaces"</code>
                            <span>Use quotes for tags containing spaces</span>

                            <code className="text-blue-400 font-mono">A AND B</code>
                            <span>Both conditions must match</span>

                            <code className="text-blue-400 font-mono">A OR B</code>
                            <span>Either condition matches</span>

                            <code className="text-blue-400 font-mono">NOT A</code>
                            <span>Negation — exclude matches</span>

                            <code className="text-blue-400 font-mono">(A OR B) AND C</code>
                            <span>Group with parentheses</span>

                            <code className="text-blue-400 font-mono">type:image</code>
                            <span>Filter by media type (image/video)</span>

                            <code className="text-blue-400 font-mono">has:alpha</code>
                            <span>Images with variable transparency</span>

                            <code className="text-blue-400 font-mono">has:caption</code>
                            <span>Images that have a caption</span>

                            <code className="text-blue-400 font-mono">untagged</code>
                            <span>Images with no tags</span>

                            <code className="text-blue-400 font-mono">tag_count&gt;5</code>
                            <span>Tag count comparison (&gt;, &lt;, =, &gt;=, &lt;=)</span>
                        </div>
                        <p className="text-gray-500 mt-2 italic">Operators: NOT binds tightest, then AND, then OR</p>
                    </div>
                </div>
            )}
        </div>
    );
}
