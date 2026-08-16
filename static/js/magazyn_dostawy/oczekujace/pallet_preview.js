function startPalletPreviewTimer(palletsHtml, event) {
    cancelPalletPreviewTimer(); // ensure previous is cleared

    if (!palletsHtml) return;

    // Create a floating indicator
    hoverIndicator = document.createElement('div');
    hoverIndicator.style.position = 'absolute';
    hoverIndicator.style.left = (event.pageX + 15) + 'px';
    hoverIndicator.style.top = (event.pageY + 15) + 'px';
    hoverIndicator.style.background = 'rgba(15, 23, 42, 0.85)';
    hoverIndicator.style.color = '#fff';
    hoverIndicator.style.padding = '4px 8px';
    hoverIndicator.style.borderRadius = '6px';
    hoverIndicator.style.fontSize = '12px';
    hoverIndicator.style.fontWeight = '600';
    hoverIndicator.style.zIndex = '9999';
    hoverIndicator.style.pointerEvents = 'none';
    hoverIndicator.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
    hoverIndicator.innerHTML = 'Podgląd za 2.0s...';
    document.body.appendChild(hoverIndicator);

    let timeLeft = 2.0;
    countdownInterval = setInterval(() => {
        timeLeft -= 0.1;
        if (timeLeft <= 0) {
            clearInterval(countdownInterval);
            if (hoverIndicator) hoverIndicator.innerHTML = 'Ładowanie...';
        } else {
            if (hoverIndicator) hoverIndicator.innerHTML = 'Podgląd za ' + Math.max(0, timeLeft).toFixed(1) + 's...';
        }
    }, 100);

    // Update position on mousemove
    document.addEventListener('mousemove', updateHoverIndicatorPos);

    palletPreviewTimer = setTimeout(function () {
        cancelPalletPreviewTimer();
        AppDialog.alert('<div style="text-align: left; margin-top: 10px;">' + palletsHtml + '</div>', 'Oczekujące palety w zleceniu');
    }, 2000);
}

function updateHoverIndicatorPos(e) {
    if (hoverIndicator) {
        hoverIndicator.style.left = (e.pageX + 15) + 'px';
        hoverIndicator.style.top = (e.pageY + 15) + 'px';
    }
}

function removeHoverIndicator() {
    if (hoverIndicator && hoverIndicator.parentNode) {
        hoverIndicator.parentNode.removeChild(hoverIndicator);
    }
    hoverIndicator = null;
    document.removeEventListener('mousemove', updateHoverIndicatorPos);
}

function cancelPalletPreviewTimer() {
    if (palletPreviewTimer) {
        clearTimeout(palletPreviewTimer);
        palletPreviewTimer = null;
    }
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
    removeHoverIndicator();
}

