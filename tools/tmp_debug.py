import os, sys, importlib
print('CWD=' + os.getcwd())
print('sys.path[:5]=', sys.path[:5])
print('find_spec app=', importlib.util.find_spec('app'))
print('ls=', os.listdir('.')[:20])
