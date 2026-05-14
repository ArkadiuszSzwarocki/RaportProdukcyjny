import React, { useState, useEffect } from 'react';
import { logger } from '../utils/logger';

// A custom hook to manage state that persists in localStorage.
export const usePersistedState = <T,>(key: string, defaultValue: T): [T, React.Dispatch<React.SetStateAction<T>>] => {
    const [state, setState] = useState<T>(() => {
        let valueToReturn: T;
        try {
            const item = localStorage.getItem(key);
            // If item is null, undefined, or the literal string 'undefined', use the default value.
            if (item == null || item === 'undefined') {
                valueToReturn = defaultValue;
            } else {
                const parsed = JSON.parse(item);
                // If the parsed value is null or undefined, use default.
                valueToReturn = parsed == null ? defaultValue : parsed as T;
            }
        } catch (error) {
            console.warn(`Error reading localStorage key “${key}”:`, error);
            logger.logError(error as Error, 'usePersistedState:read');
            // Fallback to default value on any parsing error.
            valueToReturn = defaultValue;
        }

        // Final sanity check to prevent undefined from ever being returned from the initializer.
        if (valueToReturn === undefined) {
            return defaultValue;
        }
        return valueToReturn;
    });

    useEffect(() => {
        try {
            // Prevent storing `undefined` which becomes a string "undefined" and causes parse errors.
            if (state === undefined) {
                localStorage.removeItem(key);
            } else {
                localStorage.setItem(key, JSON.stringify(state));
            }
        } catch (error) {
            console.error(`Error writing to localStorage for key “${key}”:`, error);
            logger.logError(error as Error, 'usePersistedState:write');
        }
    }, [key, state]);

    return [state, setState];
};