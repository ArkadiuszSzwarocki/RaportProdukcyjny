import bcrypt from 'bcrypt';
(async()=>{
  const hash = '$2b$10$5VxFmNezTfXYnQJw8dIo8.x7VmY49goZ148E5gEqrpTkYmPJnWo9i';
  const ok = await bcrypt.compare('password', hash);
  console.log('COMPARE_RESULT:', ok);
})();
