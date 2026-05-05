import { useState, useEffect, useCallback, useRef } from 'react';

interface VoiceCommand {
  command: string | string[];
  callback: (command: string, ...args: any[]) => void;
  matchInterim?: boolean;
}

interface SpeechRecognition {
  new (): SpeechRecognition;
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onresult: (event: any) => void;
  onerror: (event: any) => void;
  onend: () => void;
}

declare global {
  interface Window {
    SpeechRecognition: SpeechRecognition;
    webkitSpeechRecognition: SpeechRecognition;
  }
}

const getSpeechRecognition = (): SpeechRecognition | null => {
  if (typeof window !== 'undefined') {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }
  return null;
};

export const useVoiceCommands = (commands: VoiceCommand[]) => {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [recognitionError, setRecognitionError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const isListeningRef = useRef(isListening); // Use a ref to track listening state in onend

  useEffect(() => {
    isListeningRef.current = isListening;
  }, [isListening]);

  useEffect(() => {
    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      console.warn('Speech Recognition API not supported in this browser.');
      setRecognitionError('Rozpoznawanie mowy nie jest wspierane w tej przeglądarce.');
      return;
    }
    
    if (!recognitionRef.current) {
        recognitionRef.current = new SpeechRecognition();
        recognitionRef.current.continuous = true;
        recognitionRef.current.interimResults = true;
        recognitionRef.current.lang = 'pl-PL';

        recognitionRef.current.onresult = (event: any) => {
            let finalTranscript = '';
            let interimTranscript = '';
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                } else {
                    interimTranscript += event.results[i][0].transcript;
                }
            }
            
            setTranscript(interimTranscript);
            
            if (finalTranscript) {
                const finalCommand = finalTranscript.trim().toLowerCase();
                console.log("Final command:", finalCommand);
                setTranscript(finalCommand);
                
                for (const { command, callback } of commands) {
                    const commandList = Array.isArray(command) ? command : [command];
                    for (const cmd of commandList) {
                        if (finalCommand.startsWith(cmd.toLowerCase())) {
                            callback(finalCommand);
                            return; // Execute first match
                        }
                    }
                }
            }
        };

        recognitionRef.current.onerror = (event: any) => {
            console.error('Speech recognition error:', event.error, event.message);
             if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                setRecognitionError('Dostęp do mikrofonu został zablokowany lub mikrofon jest niedostępny. Funkcja komend głosowych nie będzie działać.');
            } else if (event.error === 'no-speech') {
                 setRecognitionError('Nie wykryto mowy. Spróbuj ponownie.');
            } else {
                setRecognitionError(`Błąd rozpoznawania mowy: ${event.error}.`);
            }
            setIsListening(false);
        };

        recognitionRef.current.onend = () => {
            // Check ref instead of state because state might be stale in this closure
            if (isListeningRef.current) {
              // If it ended unexpectedly while it should be listening, try to restart it.
              // This can happen if the browser kills the service after a period of silence.
              try {
                  recognitionRef.current?.start();
              } catch (e) {
                  console.error("Error restarting recognition:", e);
                  setIsListening(false); // Update state if restart fails
              }
            } else {
                // If it ended because we called stop(), ensure the state is synchronised.
                setIsListening(false);
            }
        };
    }
  }, [commands]);

  const startListening = useCallback(() => {
    setRecognitionError(null); // Clear previous errors on a new attempt
    if (recognitionRef.current && !isListening) {
      try {
        recognitionRef.current.start();
        setIsListening(true);
        setTranscript('');
      } catch (e: any) {
        console.error("Could not start recognition:", e);
        setRecognitionError(`Nie można uruchomić rozpoznawania mowy: ${e.message}`);
        setIsListening(false);
      }
    }
  }, [isListening]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current && isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
      setTranscript('');
    }
  }, [isListening]);
  
  const toggleListening = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

  return { isListening, transcript, startListening, stopListening, toggleListening, recognitionError };
};
