import socket
import sys
import os

# Add parent directory to path to import shared module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from BlackjackClientProtocol import BlackjackClientProtocol
from blackjack_ui import BlackjackUI
from shared.protocol_constants import (
    RESULT_WIN, RESULT_LOSS, RESULT_TIE, RESULT_CONTINUE,
    SERVER_PAYLOAD_SIZE
)


class Client:
    # --- Configuration ---
    UDP_PORT = 13122  
    BUFFER_SIZE = 1024
    TEAM_NAME = "TheHighRollers"
    
    # --- Timeout Constants ---
    TCP_CONNECT_TIMEOUT = 5    # Seconds to wait for TCP connection
    TCP_RECV_TIMEOUT = 30      # Seconds to wait for server response

    def __init__(self):
        self.ui = BlackjackUI()
        
        self.stats = {
            "rounds_played": 0,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "player_busts": 0,
            "dealer_busts": 0,
            "hits": 0,
            "stands": 0
        }

    def start(self):
        """
        Main application loop.
        """
        while True:
            try:
                # Step 1: Find a server via UDP broadcast
                server_ip, server_port = self.find_server()
                
                # Step 2: Connect and play
                self.connect_and_play(server_ip, server_port)

            except Exception as e:
                self.ui.print_error(f"Error in main loop: {e}")
                self.ui.print_info("Restarting listener...")

    def find_server(self):
        """
        Listens on UDP port 13122 for an Offer packet.
        """
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
        udp_socket.bind(('', self.UDP_PORT))

        while True:
            try:
                data, addr = udp_socket.recvfrom(self.BUFFER_SIZE)
                server_ip = addr[0]

                server_tcp_port, server_name = BlackjackClientProtocol.unpack_offer(data)
                
                self.ui.print_offer_received(server_ip, server_name)
                
                udp_socket.close()
                return server_ip, server_tcp_port

            except ValueError:
                continue
            except Exception as e:
                self.ui.print_error(f"UDP Error: {e}")
                udp_socket.close()
                raise

    def connect_and_play(self, ip, port):
        """
        Establishes TCP connection and manages the game session.
        """
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        try:
            # Set connection timeout
            tcp_socket.settimeout(self.TCP_CONNECT_TIMEOUT)
            tcp_socket.connect((ip, port))
            # Set recv timeout for game communication
            tcp_socket.settimeout(self.TCP_RECV_TIMEOUT)
            
            # --- Handshake ---
            rounds = self.ui.get_rounds_input()

            # Send Request Packet
            req_packet = BlackjackClientProtocol.pack_request(rounds, self.TEAM_NAME)
            tcp_socket.sendall(req_packet)

            # --- Game Loop ---
            for i in range(rounds):
                self.ui.print_round_header(i + 1)
                success = self.play_round(tcp_socket)
                if not success:
                    break 
            
            self.ui.print_info("Session finished. Disconnecting.")

        except Exception as e:
            self.ui.print_error(f"Connection error: {e}")
        finally:
            tcp_socket.close()

    def get_strategy_advice(self, player_sum, dealer_card_rank):
        """
        Returns 'Hit' or 'Stand' based on Basic Blackjack Strategy.
        """
        # Normalize face cards (J,Q,K=10) for strategy math
        d_val = 10 if dealer_card_rank >= 10 else (11 if dealer_card_rank == 1 else dealer_card_rank)
        
        # 1. Always Stand on 17 or higher (Hard total)
        if player_sum >= 17:
            return "Stand"
        
        # 2. Always Hit on 11 or less
        if player_sum <= 11:
            return "Hit"
            
        # 3. Tricky Middle Ground (12-16) ("Stiff Hands")
        # Strategy: Stand if dealer is weak (2-6), Hit if dealer is strong (7-Ace)
        if 12 <= player_sum <= 16:
            if 2 <= d_val <= 6:
                return "Stand" # Dealer likely to bust
            else:
                return "Hit"   # Dealer likely to beat you, take a risk
        
        return "Hit" # Fallback

    def play_round(self, conn):
        """
        Logic for a single round.
        """
        try:
            # --- 1. Initial Deal ---
            self.ui.print_waiting_for_cards()
            
            player_hand_val = 0
            dealer_up_card = 0

            # Receive 2 player cards + 1 dealer card (face-up)
            for i in range(2):
                val = self.receive_and_print_card(conn, "Player")
                if not val:
                    return False
                player_hand_val += val
            dealer_up_card = self.receive_and_print_card(conn, "Dealer")
            if not dealer_up_card:
                return False

            # --- 2. Player Turn ---
            while True:
                # Get Advice
                advice = self.get_strategy_advice(player_hand_val, dealer_up_card)
                self.ui.print_advice(advice)
                
                decision = self.get_valid_user_decision()
                
                packet = BlackjackClientProtocol.pack_player_decision(decision)
                conn.sendall(packet)

                if decision == "Stand":
                    self.ui.print_standing()
                    self.stats["stands"] += 1
                    break
                
                elif decision == "Hit":
                    self.stats["hits"] += 1
                    val = self.receive_and_print_card(conn)
                    if val is False: return True # Bust/Game Over
                    player_hand_val += val # Update sum for next advice

            # --- 3. Dealer Turn ---
            while True:
                if self.receive_and_print_card(conn) is False:
                    break
            return True
            
        except Exception as e:
            self.ui.print_error(f"Round Error: {e}")
            return False

    def get_valid_user_decision(self):
        """
        Loops until the user enters exactly 'Hit' or 'Stand'.
        """
        while True:
            user_input = self.ui.get_decision_input()
            try:
                BlackjackClientProtocol.pack_player_decision(user_input)
                return user_input.strip().title()
                
            except ValueError as e:
                self.ui.print_invalid_decision()

    def recv_exact(self, conn, num_bytes):
        """
        Receives exactly num_bytes from the socket.
        Handles partial reads and ensures complete data.
        """
        data = b''
        while len(data) < num_bytes:
            try:
                chunk = conn.recv(num_bytes - len(data))
                if not chunk:
                    raise ConnectionError("Server disconnected.")
                data += chunk
            except socket.timeout:
                raise TimeoutError("Server response timed out.")
        return data

    def receive_and_print_card(self, conn, owner=""):
        """
        Reads one packet. 
        Prints card if present. 
        Prints result if present.
        Returns: card value if game continues, False if game over.
        """
        try:
            data = self.recv_exact(conn, SERVER_PAYLOAD_SIZE)
        except TimeoutError as e:
            self.ui.print_error(f"Timeout: {e}")
            raise
        except ConnectionError as e:
            self.ui.print_error(f"Connection lost: {e}")
            raise

        try:
            result, rank, suit = BlackjackClientProtocol.unpack_payload_server(data)
        except ValueError as e:
            self.ui.print_error(f"Corrupted message from server: {e}")
            raise

        # 1. Check if card is valid and print it
        is_valid_card = (1 <= rank <= 13) and (0 <= suit <= 3)
        if is_valid_card:
            self.ui.print_card(rank, suit, owner)

        # 2. Check result and handle logic
        if result == RESULT_CONTINUE:
            # Game is still going - return card value
            if not is_valid_card:
                raise ValueError(f"Invalid card received: rank={rank}, suit={suit}")
            # Return card value: Ace=11, Face cards=10, others=face value
            if rank == 1:
                return 11
            elif rank >= 10:
                return 10
            else:
                return rank
        else:
            # Game Over (Win/Loss/Tie)
            self._update_stats(result)
            self.ui.print_result(result)
            self.ui.print_statistics(self.stats)
            return False

    def _update_stats(self, result_code):
        """Updates statistics based on result code."""
        self.stats["rounds_played"] += 1
        if result_code == RESULT_WIN:
            self.stats["wins"] += 1
        elif result_code == RESULT_LOSS:
            self.stats["losses"] += 1
        elif result_code == RESULT_TIE:
            self.stats["ties"] += 1


if __name__ == "__main__":
    client = Client()
    client.start()