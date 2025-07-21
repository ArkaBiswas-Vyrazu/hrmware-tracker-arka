#!./venv/bin/python3

import psutil
import socket


def get_domain(ip):
    try:
        domain = socket.gethostbyaddr(ip)
        return domain[0]
    except socket.herror:
        return None


def monitor_packets():
    while True:
        connections = psutil.net_connections(kind='inet')
        for connection in connections:
            if connection.status != 'ESTABLISHED':
                continue
            
            ip = connection.raddr.ip
            domain = get_domain(ip)
            if domain is not None:
                print(f"Connection found to {domain} ({ip})")


def main(): 
    try:
        print("Listening for packets.....")
        monitor_packets()
    except KeyboardInterrupt:
        print("Program Terminated\n")


if __name__ == "__main__":
    main()
