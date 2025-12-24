import socket
import threading
import time
import sys
import os

# Add parent directory to path to import shared module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from BlackjackServerProtocol import BlackjackServerProtocol
from shared.blackjack_game import BlackjackGame
from shared.protocol_constants import (
    RESULT_WIN, RESULT_LOSS, RESULT_CONTINUE,
    CLIENT_PAYLOAD_SIZE
)

class Server:
    # --- Network Constants ---
    UDP_DEST_PORT = 13122 
    
    SERVER_NAME = "CasinoRoyaleServer"
    
    # --- Timeout Constants ---
    CLIENT_TIMEOUT = 120  # Seconds to wait for client response
    
    def __init__(self):
        self.server_ip = self.get_local_ip()
        self.tcp_port = 0 # 0 lets the OS pick a free random port
        
        # Setup the TCP Socket for game connections
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.bind(('', self.tcp_port))
        
        # Update port to the actual one assigned by OS
        self.tcp_port = self.tcp_socket.getsockname()[1]
        
        print(f"Server started, listening on IP address {self.server_ip}")

    def get_local_ip(self):
        """Attempts to find the local IP address visible to the network."""
        try:
            # Connect to a dummy external IP to get the interface IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self):
        """Main entry point: starts UDP broadcast and TCP listener."""
        self.tcp_socket.listen()
        
        # Start UDP Broadcast in a separate thread (Daemon dies when main dies)
        udp_thread = threading.Thread(target=self.broadcast_offer, daemon=True)
        udp_thread.start()

        # Main loop to accept TCP clients
        while True:
            try:
                client_sock, client_addr = self.tcp_socket.accept()
                print(f"New connection from {client_addr}")
                
                # Handle each client in a separate thread
                client_thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_sock,)
                )
                client_thread.start()
            except Exception as e:
                print(f"Error accepting connection: {e}")

    def broadcast_offer(self):
        """Sends UDP Offer packets every 1 second."""
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Use the protocol class to pack the offer message
        packet = BlackjackServerProtocol.pack_offer(self.tcp_port, self.SERVER_NAME)

        while True:
            try:
                udp_sock.sendto(packet, ('<broadcast>', self.UDP_DEST_PORT))
                time.sleep(1) # Broadcast once every second
            except Exception as e:
                print(f"UDP Broadcast error: {e}")
                time.sleep(1)

    def recv_exact(self, conn, num_bytes):
        """
        Receives exactly num_bytes from the socket.
        Handles partial reads and ensures complete data.
        """
        data = b''
        while len(data) < num_bytes:
            chunk = conn.recv(num_bytes - len(data))
            if not chunk:
                raise ConnectionError("Client disconnected.")
            data += chunk
        return data

    def handle_client(self, conn):
        """Manages the full game session with a single client."""
        try:
            # Set timeout for client responses
            conn.settimeout(self.CLIENT_TIMEOUT)
            
            # --- 1. Receive Request ---
            try:
                data = self.recv_exact(conn, 38)  # Request packet is 38 bytes
            except (socket.timeout, ConnectionError) as e:
                print(f"Failed to receive handshake: {e}")
                return

            # Parse handshake using Protocol class
            try:
                rounds, team_name = BlackjackServerProtocol.unpack_request(data)
                print(f"Game started with team: {team_name} for {rounds} rounds")
            except ValueError as e:
                print(f"Handshake failed (corrupted data): {e}")
                return

            # --- 2. Game Loop ---
            for i in range(rounds):
                # If play_round returns False, a fatal error occurred (disconnect)
                if not self.play_round(conn, i + 1):
                    print(f"Terminating session with {team_name} due to error.")
                    break
            
            print(f"Finished session with {team_name}") 

        except Exception as e:
            print(f"Error with client: {e}")
        finally:
            conn.close()

    def play_round(self, conn, round_num):
        """
        Executes one round of Blackjack. 
        Returns True if successful, False if connection/protocol failed.
        """
        game = BlackjackGame()
        
        # Initial Deal: 2 cards for player, 1 visible for dealer
        player_cards, dealer_visible = game.deal_initial()
        
        # Send initial cards to client
        try:
            self.send_card(conn, player_cards[0])
            self.send_card(conn, player_cards[1])
            self.send_card(conn, dealer_visible)
        except Exception as e:
            print(f"Error sending initial cards: {e}")
            return False

        # --- Player Turn ---
        player_busted = False
        while True:
            try:
                # Wait for player decision packet
                data = self.recv_exact(conn, CLIENT_PAYLOAD_SIZE)
                decision = BlackjackServerProtocol.unpack_player_decision(data)
                
                if decision == "Hit":
                    new_card, is_bust = game.player_hit()
                    
                    if is_bust:
                        # BUST! Send Card AND Result in one packet
                        packet = BlackjackServerProtocol.pack_payload_server(
                            RESULT_LOSS, new_card[0], new_card[1]
                        )
                        conn.sendall(packet)
                        return True
                    else:
                        self.send_card(conn, new_card)
                        
                elif decision == "Stand":
                    break
                    
            except ValueError as e:
                print(f"Protocol violation by client: {e}. Terminating connection.")
                return False
            except socket.timeout:
                print("Client response timed out. Terminating connection.")
                return False
            except ConnectionError as e:
                print(f"Client disconnected: {e}")
                return False

        # --- Dealer Turn ---
        try:
            for card, is_bust in game.dealer_turn():
                if is_bust:
                    # Dealer busted - player wins
                    packet = BlackjackServerProtocol.pack_payload_server(
                        RESULT_WIN, card[0], card[1]
                    )
                    conn.sendall(packet)
                    return True
                else:
                    self.send_card(conn, card)
        except Exception:
            return False

        # --- Determine Winner and Send Result ---
        result_code = game.determine_winner(player_busted)
        
        try:
            packet = BlackjackServerProtocol.pack_payload_server(result_code)
            conn.sendall(packet)
            return True
        except Exception:
            return False

    def send_card(self, conn, card):
        """Helper to send a card using the Protocol class."""
        rank, suit = card
        packet = BlackjackServerProtocol.pack_payload_server(RESULT_CONTINUE, rank, suit)
        conn.sendall(packet)


if __name__ == "__main__":
    server = Server()
    server.start()