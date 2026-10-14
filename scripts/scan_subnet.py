"""Explicit, local-only diagnostic scanner for configured printer networks."""

import argparse
import concurrent.futures
import ipaddress
import socket


PRINTER_PORTS = (9100, 6101, 80, 515, 631)


def check_ip(ip):
    for port in PRINTER_PORTS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.4)
                if sock.connect_ex((str(ip), port)) == 0:
                    return str(ip), port
        except OSError:
            continue
    return None


def scan_network(cidr, max_workers=32):
    network = ipaddress.ip_network(cidr, strict=False)
    if not network.is_private:
        raise ValueError('To narzędzie pozwala skanować wyłącznie prywatne sieci lokalne.')
    hosts = list(network.hosts())
    if len(hosts) > 1024:
        raise ValueError('Zakres jest zbyt duży; maksymalnie 1024 hosty na jedno uruchomienie.')

    print(f'Skanowanie jawnie wskazanego zakresu {network} w poszukiwaniu portów drukarek...')
    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 64))) as executor:
        for result in executor.map(check_ip, hosts):
            if result:
                found.append(result)
                print(f' [ZNALEZIONO] IP: {result[0]} - port: {result[1]}')
    return found


def main():
    parser = argparse.ArgumentParser(description='Diagnostyczny skan prywatnego subnetu drukarek.')
    parser.add_argument('cidr', help='Jawny prywatny CIDR, np. 10.0.0.0/24')
    parser.add_argument('--workers', type=int, default=32)
    args = parser.parse_args()
    results = scan_network(args.cidr, args.workers)
    if not results:
        print('Nie znaleziono otwartych portów drukarek w podanym zakresie.')


if __name__ == '__main__':
    main()
