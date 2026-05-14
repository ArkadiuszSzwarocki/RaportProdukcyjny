import { useState, useCallback, useLayoutEffect, useRef } from 'react';

export const useScrollArrows = (orientation: 'horizontal' | 'vertical' = 'vertical') => {
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [showStartArrow, setShowStartArrow] = useState(false);
    const [showEndArrow, setShowEndArrow] = useState(false);

    const checkScroll = useCallback(() => {
        const el = scrollContainerRef.current;
        if (!el) return;

        if (orientation === 'vertical') {
            const hasOverflow = el.scrollHeight > el.clientHeight;
            // Use a small buffer (1px) to avoid floating point inaccuracies
            setShowStartArrow(hasOverflow && el.scrollTop > 1);
            setShowEndArrow(hasOverflow && el.scrollTop < el.scrollHeight - el.clientHeight - 1);
        } else { // horizontal
            const hasOverflow = el.scrollWidth > el.clientWidth;
            setShowStartArrow(hasOverflow && el.scrollLeft > 1);
            setShowEndArrow(hasOverflow && el.scrollLeft < el.scrollWidth - el.clientWidth - 1);
        }
    }, [orientation]);

    useLayoutEffect(() => {
        const el = scrollContainerRef.current;
        if (el) {
            checkScroll();
            const resizeObserver = new ResizeObserver(checkScroll);
            resizeObserver.observe(el);
            el.addEventListener('scroll', checkScroll, { passive: true });

            // Also observe the direct child to detect content changes that affect scrollHeight/Width
            if (el.children[0]) {
                resizeObserver.observe(el.children[0]);
            }

            return () => {
                resizeObserver.disconnect();
                el.removeEventListener('scroll', checkScroll);
            };
        }
    }, [checkScroll]);

    const handleScroll = (direction: 'start' | 'end') => {
        const el = scrollContainerRef.current;
        if (el) {
            if (orientation === 'vertical') {
                const scrollAmount = el.clientHeight * 0.8;
                el.scrollBy({ top: direction === 'start' ? -scrollAmount : scrollAmount, behavior: 'smooth' });
            } else { // horizontal
                const scrollAmount = el.clientWidth * 0.8;
                el.scrollBy({ left: direction === 'start' ? -scrollAmount : scrollAmount, behavior: 'smooth' });
            }
        }
    };

    return {
        scrollContainerRef,
        showStartArrow,
        showEndArrow,
        handleScroll,
    };
};
