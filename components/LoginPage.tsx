
import React, { useState, useEffect } from 'react';
import { useAuth } from './contexts/AuthContext';
import Input from './Input';
import Button from './Button';
import Alert from './Alert';
import PadlockIcon from './icons/PadlockIcon';
import UserIcon from './icons/UserIcon';
import EyeIcon from './icons/EyeIcon';
import EyeSlashIcon from './icons/EyeSlashIcon';
import QrCodeIcon from './icons/QrCodeIcon';
import { User } from '../types';
import MLogoIcon from './icons/MLogoIcon';
import AnimatedBackground from './AnimatedBackground';

interface LoginPageProps {
  onLoginSuccess: (user: User) => void;
}

const LoginPage: React.FC<LoginPageProps> = ({ onLoginSuccess }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [errors, setErrors] = useState<{ username?: string, password?: string, form?: string }>({});
    const [showPassword, setShowPassword] = useState(false);
    const { handleLogin, currentUser } = useAuth();
    const [loginInProgress, setLoginInProgress] = useState(false);

    // Kiedy currentUser zmieni się (po successfullym logowaniu), wyślij to do AppContent
    useEffect(() => {
        if (currentUser && loginInProgress) {
            console.log('🔐 LoginPage: currentUser zmienił się na:', currentUser);
            console.log('🔐 LoginPage: username =', currentUser.username);
            console.log('🔐 LoginPage: permissions =', currentUser.permissions);
            setLoginInProgress(false);
            // Wyślij poprawne dane z AuthContext
            onLoginSuccess(currentUser);
        }
    }, [currentUser, loginInProgress, onLoginSuccess]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setErrors({}); // Clear previous errors
        let validationErrors: { username?: string, password?: string, form?: string } = {};

        if (!username.trim()) {
            validationErrors.username = 'Nazwa użytkownika jest wymagana.';
        }
    
        if (!password.trim()) {
            validationErrors.password = 'Hasło jest wymagane.';
        }
    
        if (Object.keys(validationErrors).length > 0) {
            setErrors(validationErrors);
            return;
        }

        // Uruchom handleLogin - ustawi currentUser w AuthContext
        setLoginInProgress(true);
        const result = await handleLogin(username, password);
        
        if (!result.success) {
            setLoginInProgress(false);
            setErrors({ form: result.message });
        }
        // Jeśli success, czekamy na zmianę currentUser w useEffect wyżej
    };
    
    const handleQrLogin = () => {
        alert("Logowanie kodem QR jest w trakcie implementacji.");
    };

    return (
        <>
            <AnimatedBackground />
            <div className="min-h-screen bg-secondary-900/80 backdrop-blur-sm flex flex-col justify-center items-center p-4 animate-fadeIn">
                <div className="w-full max-w-md bg-secondary-800 rounded-2xl shadow-xl p-8 space-y-6">
                    
                    <div className="mx-auto h-16 w-16">
                        <MLogoIcon />
                    </div>
                    
                    <div className="text-center">
                        <h2 className="text-3xl font-bold text-white">Logowanie do Systemu</h2>
                        <p className="mt-2 text-sm text-slate-400">Wprowadź swoje dane, aby uzyskać dostęp.</p>
                    </div>
                    
                    {errors.form && <Alert type="error" message={errors.form} />}

                    <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                        <Input
                            label="Nazwa użytkownika"
                            id="username"
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            required
                            autoFocus
                            autoComplete="username"
                            icon={<UserIcon className="h-5 w-5 text-slate-400" />}
                            error={errors.username}
                        />
                        <Input
                            label="Hasło"
                            id="password"
                            type={showPassword ? 'text' : 'password'}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            autoComplete="current-password"
                            icon={<PadlockIcon className="h-5 w-5 text-slate-400" />}
                            rightIcon={showPassword ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
                            onRightIconClick={() => setShowPassword(!showPassword)}
                            error={errors.password}
                        />
                        <Button type="submit" className="w-full justify-center !py-3 !text-base">
                            Zaloguj się
                        </Button>
                    </form>

                    <div className="relative">
                        <div className="absolute inset-0 flex items-center" aria-hidden="true">
                            <div className="w-full border-t border-secondary-600" />
                        </div>
                        <div className="relative flex justify-center">
                            <span className="bg-secondary-800 px-2 text-sm text-slate-400">
                                Lub
                            </span>
                        </div>
                    </div>
                    
                    <Button variant="secondary" onClick={handleQrLogin} className="w-full justify-center !py-3 !text-base">
                        <QrCodeIcon className="h-5 w-5 mr-2" />
                        Zaloguj kodem QR
                    </Button>
                </div>
                {/* Version badge */}
                <div className="fixed right-3 bottom-3 text-xs text-slate-400 bg-secondary-800/60 px-2 py-1 rounded-md pointer-events-none select-none">
                    <VersionBadge />
                </div>
            </div>
        </>
    );
};

const VersionBadge: React.FC = () => {
    const [v, setV] = useState<string>('');
    useEffect(() => {
        let mounted = true;
        fetch('/version.txt').then(r => r.text()).then(t => { if (mounted) setV(t.trim()); }).catch(() => {});
        return () => { mounted = false; };
    }, []);
    return <span>{v || 'ver: unknown'}</span>;
};

export default LoginPage;
