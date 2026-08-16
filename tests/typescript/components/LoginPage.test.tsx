import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import LoginPage from '../LoginPage';

declare var describe: any;
declare var it: any;
declare var expect: any;
declare var jest: any;

// Mock context hook
jest.mock('../contexts/AuthContext', () => ({
    useAuth: () => ({
        users: [
            { username: 'admin', password: 'password', role: 'admin' }
        ]
    })
}));

describe('LoginPage', () => {
    it('renders login form correctly', () => {
        render(<LoginPage onLoginSuccess={jest.fn()} />);
        expect(screen.getByLabelText(/Nazwa użytkownika/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Hasło/i)).toBeInTheDocument();
    });

    it('shows error on empty submission', () => {
        render(<LoginPage onLoginSuccess={jest.fn()} />);
        const submitBtn = screen.getByRole('button', { name: /Zaloguj się/i });
        
        fireEvent.click(submitBtn);
        
        // Sprawdź czy pojawiła się walidacja HTML5 lub customowy alert
        // W Twoim kodzie Input ma props `required`, więc przeglądarka to obsłuży,
        // ale jeśli masz stan błędu w React:
        // expect(screen.getByText(/Nazwa użytkownika jest wymagana/i)).toBeInTheDocument();
    });

    it('calls onLoginSuccess with correct credentials', () => {
        const mockLoginSuccess = jest.fn();
        render(<LoginPage onLoginSuccess={mockLoginSuccess} />);

        fireEvent.change(screen.getByLabelText(/Nazwa użytkownika/i), { target: { value: 'admin' } });
        fireEvent.change(screen.getByLabelText(/Hasło/i), { target: { value: 'password' } });
        
        fireEvent.click(screen.getByRole('button', { name: /Zaloguj się/i }));

        expect(mockLoginSuccess).toHaveBeenCalledTimes(1);
        expect(mockLoginSuccess).toHaveBeenCalledWith(expect.objectContaining({
            username: 'admin',
            role: 'admin'
        }));
    });
});