import { useState, useEffect } from 'react';

// This hook loads multiple scripts sequentially.
export const useDynamicScripts = (urls: string[]) => {
    const [areLoaded, setAreLoaded] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        // Create a stable key from the URLs to check if they've already been loaded.
        const urlsKey = urls.join(',');

        if (!urls || urls.length === 0) {
            setAreLoaded(true);
            return;
        }

        // Use a global flag to prevent re-loading
        if ((window as any)._loadedScripts?.[urlsKey]) {
            setAreLoaded(true);
            return;
        }

        let isMounted = true;
        const loadScript = (index: number) => {
            if (index >= urls.length) {
                if (isMounted) {
                    setAreLoaded(true);
                    if (!(window as any)._loadedScripts) {
                        (window as any)._loadedScripts = {};
                    }
                    (window as any)._loadedScripts[urlsKey] = true;
                }
                return;
            }

            const url = urls[index];
            let script = document.querySelector(`script[src="${url}"]`) as HTMLScriptElement;

            if (script) {
                // If script is already in DOM, assume it's loaded or loading
                // and proceed to the next one.
                loadScript(index + 1);
                return;
            }

            script = document.createElement('script');
            script.src = url;
            // Async is true by default, which is fine as we chain loads with the 'load' event.
            
            const onScriptLoad = () => {
                script.removeEventListener('load', onScriptLoad);
                script.removeEventListener('error', onScriptError);
                if (isMounted) {
                    loadScript(index + 1);
                }
            };

            const onScriptError = (e: Event) => {
                script.removeEventListener('load', onScriptLoad);
                script.removeEventListener('error', onScriptError);
                if (isMounted) {
                    setError(`Nie udało się załadować skryptu: ${url}`);
                }
            };

            script.addEventListener('load', onScriptLoad);
            script.addEventListener('error', onScriptError);

            document.body.appendChild(script);
        };
        
        loadScript(0);
        
        return () => {
            isMounted = false;
        };

    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [JSON.stringify(urls)]); // Use JSON.stringify to depend on the content of the array

    return { areLoaded, error };
};
