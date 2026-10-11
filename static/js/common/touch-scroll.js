/** Block page pull-to-refresh without blocking independently scrollable panels. */
(function () {
    var touchStartY = 0;
    document.addEventListener('touchstart', function (event) {
        if (event.touches && event.touches.length === 1) touchStartY = event.touches[0].clientY;
    }, { passive: true });
    document.addEventListener('touchmove', function (event) {
        if (!event.touches || event.touches.length !== 1) return;
        var element = event.target;
        while (element && element !== document.body && element !== document.documentElement) {
            var overflow = getComputedStyle(element).overflowY;
            if ((overflow === 'auto' || overflow === 'scroll') && element.scrollHeight > element.clientHeight) return;
            element = element.parentElement;
        }
        var pageTop = window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
        if (pageTop <= 0 && event.touches[0].clientY > touchStartY && event.cancelable) event.preventDefault();
    }, { passive: false });
})();
