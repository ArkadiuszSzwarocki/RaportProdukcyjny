import socket
import concurrent.futures

def check_ip(ip):
    # Check common printer ports: 9100, 6101, 80, 515, 631
    for port in [9100, 6101, 80, 515, 631]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.4)
            res = s.connect_ex((ip, port))
            s.close()
            if res == 0:
                return ip, port
        except Exception:
            pass
    return None

def scan_network():
    print("Skanowanie sieci lokalnej 192.168.1.1 - 192.168.1.254 w poszukiwaniu drukarek...")
    found = []
    ips = [f"192.168.1.{i}" for i in range(1, 255)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(check_ip, ips)
        for res in results:
            if res:
                found.append(res)
                print(f" [ZNALAZŁEM] IP: {res[0]} - Otwarty port: {res[1]}")
    if not found:
        print("Nie znaleziono otwartych portów drukarek w sieci 192.168.1.x.")
    return found

if __name__ == '__main__':
    scan_network()
