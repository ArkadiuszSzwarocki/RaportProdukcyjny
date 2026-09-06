/**
 * Live Password Strength & Policy Validator.
 * Attaches real-time feedback indicator to password input fields.
 */
(function() {
    function evaluatePassword(password) {
        if (!password) {
            return { score: 0, text: 'Wpisz hasło', color: '#94a3b8', valid: false };
        }

        const hasMinLen = password.length >= 8;
        const hasLetter = /[a-zA-Z]/.test(password);
        const hasDigit = /\d/.test(password);
        const hasSpecial = /[^a-zA-Z0-9]/.test(password);

        let passedChecks = 0;
        if (hasMinLen) passedChecks++;
        if (hasLetter) passedChecks++;
        if (hasDigit) passedChecks++;
        if (hasSpecial) passedChecks++;

        if (!hasMinLen || !hasLetter || !hasDigit) {
            return {
                score: Math.min(passedChecks, 2),
                text: 'Słabe (Wymagane: min. 8 znaków, litera i cyfra)',
                color: '#ef4444',
                valid: false
            };
        }

        if (passedChecks >= 4 && password.length >= 10) {
            return { score: 4, text: 'Bardzo silne hasło', color: '#16a34a', valid: true };
        }

        return { score: 3, text: 'Dobre hasło', color: '#2563eb', valid: true };
    }

    window.attachPasswordStrengthIndicator = function(inputElement) {
        if (!inputElement || inputElement._hasPasswordIndicator) return;
        inputElement._hasPasswordIndicator = true;

        const container = document.createElement('div');
        container.className = 'pwd-strength-container';
        container.style.cssText = 'margin-top: 6px; display: flex; flex-direction: column; gap: 4px; font-size: 0.8rem;';

        const barWrapper = document.createElement('div');
        barWrapper.style.cssText = 'height: 4px; width: 100%; background: #e2e8f0; border-radius: 2px; overflow: hidden; display: flex; gap: 2px;';

        const segmentCount = 4;
        const segments = [];
        for (let i = 0; i < segmentCount; i++) {
            const seg = document.createElement('div');
            seg.style.cssText = 'flex: 1; height: 100%; background: #cbd5e1; transition: background 0.2s ease;';
            barWrapper.appendChild(seg);
            segments.push(seg);
        }

        const label = document.createElement('div');
        label.style.cssText = 'color: #64748b; font-size: 0.78rem; font-weight: 600;';
        label.textContent = 'Min. 8 znaków, w tym litera i cyfra';

        container.appendChild(barWrapper);
        container.appendChild(label);
        inputElement.parentNode.insertBefore(container, inputElement.nextSibling);

        inputElement.addEventListener('input', function() {
            const val = inputElement.value;
            const res = evaluatePassword(val);

            segments.forEach((seg, idx) => {
                seg.style.background = (idx < res.score) ? res.color : '#e2e8f0';
            });
            label.textContent = res.text;
            label.style.color = res.color;
        });
    };

    // Auto-attach on DOMContentLoaded for any input with data-password-policy
    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('input[type="password"][data-password-policy]').forEach(el => {
            window.attachPasswordStrengthIndicator(el);
        });
    });
})();
