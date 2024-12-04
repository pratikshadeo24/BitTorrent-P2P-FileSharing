import os
import sys
import socket
import threading
import random
import time
from datetime import datetime
from bitfield_manager import BitfieldManager
from message_handler import MessageHandler
from utils import recv_all, log_event
class PeerProcess:
    def __init__(self, peer_id, peer_info, config):
        self.peer_id = peer_id
        self.peer_info = peer_info
        self.config = config
        self.host = self.get_host_for_peer(peer_id)
        self.port = self.get_port_for_peer(peer_id)
        self.connections = {}  # Key: peer_id, Value: PeerConnection instance
        self.peer_sockets = {}  # Key: peer_id, Value: socket object
        self.num_pieces = self.calculate_num_pieces(config['file_size'], config['piece_size'])
        self.bitfield_manager = BitfieldManager(self.num_pieces)
        self.has_file = self.get_has_file_for_peer(peer_id)
        if self.has_file:
            self.bitfield_manager.set_all()
            self.split_file_into_pieces()
        self.lock = threading.Lock()
        self.is_terminated = False
        self.preferred_neighbors = []
        self.optimistic_unchoke_neighbor = None
        # Initialize logging

    def split_file_into_pieces(self):
        # Only split if the peer has the complete file
        file_path = f"peer_{self.peer_id}/{self.config['file_name']}"
        if not os.path.exists(file_path):
            print(f"File {self.config['file_name']} not found in peer_{self.peer_id}/")
            return
        # Read the complete file
        with open(file_path, 'rb') as f:
            data = f.read()
        # Split into pieces
        piece_size = self.config['piece_size']
        num_pieces = self.num_pieces
        dir_path = f"peer_{self.peer_id}/pieces"
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        for i in range(num_pieces):
            start = i * piece_size
            end = min(start + piece_size, len(data))
            piece_data = data[start:end]
            piece_path = os.path.join(dir_path, f"{i}.dat")
            with open(piece_path, 'wb') as piece_file:
                piece_file.write(piece_data)
        print(f"Split file into {num_pieces} pieces in {dir_path}")

    def assemble_file_from_pieces(self):
        dir_path = f"peer_{self.peer_id}/pieces"
        file_path = f"peer_{self.peer_id}/{self.config['file_name']}"
        with open(file_path, 'wb') as outfile:
            for i in range(self.num_pieces):
                piece_path = os.path.join(dir_path, f"{i}.dat")
                with open(piece_path, 'rb') as infile:
                    outfile.write(infile.read())
        print(f"Reconstructed file saved at {file_path}")
        log_event(self.peer_id, f"Peer {self.peer_id} has downloaded the complete file.")

    def calculate_num_pieces(self, file_size, piece_size):
        """
        Calculate the number of pieces based on the file size and piece size.
        """
        return (file_size + piece_size - 1) // piece_size

    def get_host_for_peer(self, peer_id):
        for peer in self.peer_info:
            if peer['peer_id'] == peer_id:
                return peer['host']
        return None

    def get_port_for_peer(self, peer_id):
        for peer in self.peer_info:
            if peer['peer_id'] == peer_id:
                return peer['port']
        return None

    def get_has_file_for_peer(self, peer_id):
        for peer in self.peer_info:
            if peer['peer_id'] == peer_id:
                return peer['has_file']
        return None

    def start(self):
        # Start listening for incoming connections
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Peer {self.peer_id} listening on port {self.port}")

        # Start a thread to accept incoming connections
        threading.Thread(target=self.accept_incoming_connections, daemon=True).start()

        # Connect to peers that started earlier
        self.connect_to_peers()

        threading.Thread(target=self.unchoking_task, daemon=True).start()
        threading.Thread(target=self.optimistic_unchoking_task, daemon=True).start()
        # Start the completion check task
        threading.Thread(target=self.completion_check_task, daemon=True).start()
        # Main loop
        while True:
            time.sleep(1)  # Prevents busy waiting

    def unchoking_task(self):
        while True:
            try:
                time.sleep(self.config['unchoking_interval'])
                self.select_preferred_neighbors()
            except Exception as e:
                print(f"Error in unchoking_task: {e}")

    def select_preferred_neighbors(self):
        with self.lock:
            interested_peers = [conn for conn in self.connections.values() if conn.is_interested]
            k = self.config['num_preferred_neighbors']

            if self.has_file:
                # Peer has the complete file, select randomly
                preferred_neighbors = random.sample(interested_peers, min(k, len(interested_peers)))
            else:
                # Peer does not have the complete file, select based on download rates
                # Sort interested peers by download rate in descending order
                sorted_peers = sorted(interested_peers, key=lambda x: x.download_rate, reverse=True)
                preferred_neighbors = sorted_peers[:k]

            # Store the preferred neighbors
            self.preferred_neighbors = preferred_neighbors

            # Update choked status
            for conn in self.connections.values():
                if conn in self.preferred_neighbors or (self.optimistic_unchoke_neighbor == conn.peer_id):
                    if conn.is_choked:
                        conn.send_unchoke()
                else:
                    if not conn.is_choked:
                        conn.send_choke()

            # Log the preferred neighbors
            neighbor_ids = [conn.peer_id for conn in self.preferred_neighbors]
            log_event(self.peer_id, f"Peer {self.peer_id} has the preferred neighbors {neighbor_ids}")

            # Reset download rates for the next interval
            for conn in self.connections.values():
                conn.download_rate = conn.downloaded_bytes / self.config['unchoking_interval']
                conn.downloaded_bytes = 0

    def accept_incoming_connections(self):
        while True:
            client_socket, addr = self.server_socket.accept()
            print(f"Accepted connection from {addr}")
            threading.Thread(target=self.handle_incoming_connection, args=(client_socket,), daemon=True).start()

    def handle_incoming_connection(self, client_socket):
        from peer_connection import PeerConnection
        # Receive handshake
        peer_id = MessageHandler.receive_handshake(client_socket)
        if peer_id is None:
            print("Invalid handshake received. Closing connection.")
            client_socket.close()
            return
        print(f"Received handshake from Peer {peer_id}")
        log_event(self.peer_id, f"Peer {self.peer_id} is connected from Peer {peer_id}")

        # Send handshake back
        MessageHandler.send_handshake(client_socket, self.peer_id)
        print(f"Sent handshake to Peer {peer_id}")

        # Create a PeerConnection instance
        peer_connection = PeerConnection(peer_id, client_socket, self)
        self.connections[peer_id] = peer_connection

    def connect_to_peers(self):
        for peer in self.peer_info:
            if peer['peer_id'] < self.peer_id:
                threading.Thread(target=self.establish_connection, args=(peer,), daemon=True).start()

    def establish_connection(self, peer):
        from peer_connection import PeerConnection
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((peer['host'], peer['port']))
            print(f"Peer {self.peer_id} connected to Peer {peer['peer_id']}")
            log_event(self.peer_id, f"Peer {self.peer_id} makes a connection to Peer {peer['peer_id']}")

            # Send handshake
            MessageHandler.send_handshake(s, self.peer_id)
            print(f"Sent handshake to Peer {peer['peer_id']}")

            # Receive handshake
            received_peer_id = MessageHandler.receive_handshake(s)
            if received_peer_id != peer['peer_id']:
                print(f"Invalid peer ID received in handshake from Peer {peer['peer_id']}. Closing connection.")
                s.close()
                return
            print(f"Received handshake from Peer {received_peer_id}")

            # Create a PeerConnection instance
            peer_connection = PeerConnection(peer['peer_id'], s, self)
            self.connections[peer['peer_id']] = peer_connection
        except Exception as e:
            print(f"Error connecting to Peer {peer['peer_id']}: {e}")

    # Additional methods for unchoking intervals, optimistic unchoking, etc.
    def optimistic_unchoking_task(self):
        while True:
            try:
                time.sleep(self.config['optimistic_unchoking_interval'])
                self.select_optimistic_unchoke_neighbor()
            except Exception as e:
                print(f"Error in optimistic_unchoking_task: {e}")

    def select_optimistic_unchoke_neighbor(self):
        with self.lock:
            # Find choked and interested peers not in preferred neighbors
            choked_interested_peers = [
                conn for conn in self.connections.values()
                if conn.is_interested and conn.is_choked and conn not in self.preferred_neighbors
            ]

            if choked_interested_peers:
                # Randomly select one peer to unchoke
                optimistic_peer = random.choice(choked_interested_peers)
                optimistic_peer.send_unchoke()
                self.optimistic_unchoke_neighbor = optimistic_peer.peer_id
                log_event(self.peer_id,
                          f"Peer {self.peer_id} has the optimistically unchoked neighbor {optimistic_peer.peer_id}")
            else:
                self.optimistic_unchoke_neighbor = None

    def completion_check_task(self):
        while not self.is_terminated:
            time.sleep(5)  # Check every 5 seconds
            with self.lock:
                if self.bitfield_manager.is_complete():
                    all_peers_completed = all(
                        conn.has_complete_file for conn in self.connections.values()
                    )
                    if all_peers_completed:
                        self.terminate()

    def terminate(self):
        with self.lock:
            if self.is_terminated:
                return
            self.is_terminated = True
            # Log the completion event
            log_event(self.peer_id, f"Peer {self.peer_id} has downloaded the complete file.")
            print(f"Peer {self.peer_id} has downloaded the complete file and is terminating.")
            # Close all connections
            for conn in self.connections.values():
                conn.close()
            # Close the server socket
            self.server_socket.close()
            # Exit the program
            os._exit(0)


def read_config_files():
    # Reading Common.cfg
    config = {}
    with open('Common.cfg', 'r') as file:
        for line in file:
            if line.strip():  # Ignore empty lines
                key, value = line.strip().split(' ', 1)  # Split by the first space only
                config[key] = value
    return {
        'num_preferred_neighbors': int(config['NumberOfPreferredNeighbors']),
        'unchoking_interval': int(config['UnchokingInterval']),
        'optimistic_unchoking_interval': int(config['OptimisticUnchokingInterval']),
        'file_name': config['FileName'],
        'file_size': int(config['FileSize']),
        'piece_size': int(config['PieceSize'])
    }

def read_peer_info():
    peer_info = []
    with open('PeerInfo.cfg', 'r') as file:
        for line in file:
            peer_id, host, port, has_file = line.strip().split()
            peer_info.append({
                'peer_id': int(peer_id),
                'host': host,
                'port': int(port),
                'has_file': int(has_file)
            })
    return peer_info


# Main execution
if __name__ == "__main__":
    peer_id = int(sys.argv[1])
    config = read_config_files()
    peer_info = read_peer_info()

    peer = PeerProcess(peer_id, peer_info, config)
    peer.start()
