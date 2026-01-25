// Shared toast helper
function showToast(message, type){
  try{
    var container = document.getElementById('toastContainer');
    if(!container){
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.setAttribute('aria-live','polite');
      container.setAttribute('aria-atomic','true');
      document.body.appendChild(container);
    }
    var d = document.createElement('div'); d.className = 'toast ' + (type||'info'); d.textContent = message;
    container.appendChild(d);
    setTimeout(function(){ d.style.transition='opacity 0.25s'; d.style.opacity='0'; setTimeout(function(){ d.remove(); },250); }, 4000);
  }catch(e){ if(window && window.console) console.error('showToast error', e); }
}
