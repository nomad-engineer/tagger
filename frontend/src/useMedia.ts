import { useEffect, useState } from 'react';

/** Tracks a CSS media query; updates on change (rotation, resize). */
export function useMediaQuery(query: string): boolean {
    const get = () => typeof window !== 'undefined' && window.matchMedia(query).matches;
    const [matches, setMatches] = useState(get);
    useEffect(() => {
        const mq = window.matchMedia(query);
        const onChange = () => setMatches(mq.matches);
        onChange();
        mq.addEventListener('change', onChange);
        return () => mq.removeEventListener('change', onChange);
    }, [query]);
    return matches;
}

/** Phone-sized viewport: separate full-screen views, tag editor as a drawer. */
export const useIsMobile = () => useMediaQuery('(max-width: 767px)');
