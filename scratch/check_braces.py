import sys

def check_braces(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    stack = []
    line_num = 1
    col_num = 1
    
    for i, char in enumerate(content):
        if char == '\n':
            line_num += 1
            col_num = 1
        else:
            col_num += 1
            
        if char == '{':
            stack.append(('{', line_num, col_num))
        elif char == '}':
            if not stack:
                print(f"Extra closing brace at line {line_num}, col {col_num}")
                return False
            stack.pop()
            
    if stack:
        for brace, line, col in stack:
            print(f"Unclosed brace '{brace}' at line {line}, col {col}")
        return False
    
    print("Braces are balanced!")
    return True

if __name__ == "__main__":
    check_braces(r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny\static\scripts.js')
