import socket
import sys

zpl_test = """^XA
^FO50,30^A0N,40,40^FDTEST DRUKARKI OSIP^FS
^FO50,80^A0N,30,30^FDIP: 192.168.1.47^FS
^FO50,120^A0N,25,25^FDRaportProdukcyjny - Test ZPL^FS
^FO50,160^BQN,2,4^FDMM,A-TEST-OSIP-192.168.1.47^FS
^XZ"""

def send_test_label(ip="192.168.1.47", port=9100):
    print(f"Proba bezposredniego wyslania etykiety testowej do {ip}:{port}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((ip, port))
        s.sendall(zpl_test.encode('utf-8'))
        s.close()
        print(f"[OK] SUKCES: Etykieta testowa zostala pomyslnie wyslana bezposrednio do drukarki {ip}:{port}!")
        return True
    except Exception as e:
        print(f"[ERROR] BRAK BEZPOŚREDNIEGO DOSTĘPU TCP z serwera do {ip}:{port}: {e}")
        print("Komputer serwera nie ma bezposredniego polaczenia TCP z prywatnym IP w OSIP.")
        print("Wyslanie etykiety w OSIP odbywa sie przez Serwer Druku (mostek) uruchomiony na komputerze w OSIP na porcie 3001.")
        return False

if __name__ == '__main__':
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.47"
    send_test_label(ip)
