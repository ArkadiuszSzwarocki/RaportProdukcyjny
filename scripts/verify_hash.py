from werkzeug.security import check_password_hash

adm_hash = "scrypt:32768:8:1$9wKC1e5XyYlX17v1$d2638669b770610d83b0698cf1d8d14209e30c30dfa2d05b119fd1c200887b40692d0864737b29d7e15e38043ddb244790804da8938d456276aabf8ebb11cd01"
print('Admin matches masterkey?', check_password_hash(adm_hash, 'masterkey'))
print('Admin matches wrong?', check_password_hash(adm_hash, 'wrong'))
