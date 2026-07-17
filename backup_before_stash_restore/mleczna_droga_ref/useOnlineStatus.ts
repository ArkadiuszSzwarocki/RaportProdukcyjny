
import React, { useState, useEffect, useCallback } from 'react';
import { logger } from '../utils/logger';

export type ConnectionStatusType = 'good' | 'slow' | 'offline';

export const verifyConnection = async (
  setStatus: React.Dispatch<React.SetStateAction<ConnectionStatusType>>,
  setLatency: React.Dispatch<React.SetStateAction<number | null>>
) => {
  if (!navigator.onLine) {
    setStatus('offline');
    setLatency(null);
    logger.log('warn', 'Wykryto brak połączenia sieciowego (Browser Offline)', 'Sieć');
    return;
  }

  try {
    const startTime = performance.now();
    const response = await fetch('https://www.google.com/favicon.ico?cachebust=' + new Date().getTime(), {
      method: 'GET',
      mode: 'no-cors',
      cache: 'no-store',
      signal: AbortSignal.timeout(8000)
    });
    const endTime = performance.now();
    const currentLatency = Math.round(endTime - startTime);

    if (response.status === 0 || response.ok) {
      setLatency(currentLatency);
      if (currentLatency > 1500) {
        setStatus('slow');
        logger.log('warn', `Wykryto opóźnienie sieciowe: ${currentLatency}ms`, 'Wydajność', undefined, currentLatency);
      } else {
        setStatus('good');
      }
    } else {
      setStatus('offline');
      setLatency(null);
      logger.logError(`Błąd statusu połączenia: ${response.status} (Odbicie od serwera)`, 'Sieć');
    }
  } catch (error: any) {
    setStatus('offline');
    setLatency(null);
    logger.logError(`Niepowodzenie żądania sprawdzającego: ${error.message} (Pusty plik lub brak dostępu)`, 'Sieć', undefined, 'NET_ERROR');
  }
};

export const useOnlineStatus = () => {
    const [status, setStatus] = useState<ConnectionStatusType>(navigator.onLine ? 'good' : 'offline');
    const [latency, setLatency] = useState<number | null>(null);

    const verify = useCallback(() => {
        return verifyConnection(setStatus, setLatency);
    }, []);

    useEffect(() => {
        verify();
        const handleOnline = () => {
            logger.log('info', 'Połączenie przywrócone', 'Sieć');
            verify();
        };
        const handleOffline = () => {
            setStatus('offline');
            setLatency(null);
            logger.log('warn', 'Połączenie utracone', 'Sieć');
        };

        window.addEventListener('online', handleOnline);
        window.addEventListener('offline', handleOffline);
        const interval = setInterval(verify, 60000);

        return () => {
            window.removeEventListener('online', handleOnline);
            window.removeEventListener('offline', handleOffline);
            clearInterval(interval);
        };
    }, [verify]);
    
    return { status, latency, verifyConnection: verify };
};
