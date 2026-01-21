(async ()=>{
  try{
    const res = await fetch('http://localhost:8089/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'password' })
    });
    const txt = await res.text();
    console.log('HTTP', res.status);
    console.log(txt);
  }catch(e){
    console.error('ERROR', e.message);
    process.exit(2);
  }
})();
