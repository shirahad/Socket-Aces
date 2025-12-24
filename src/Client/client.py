import socket
import sys
from BlackjackClientProtocol import BlackjackClientProtocol

class Client:
    # --- Configuration ---
    UDP_PORT = 13122  
    BUFFER_SIZE = 1024
    TEAM_NAME = "TheHighRollers"
    
    # --- Timeout Constants ---
    TCP_CONNECT_TIMEOUT = 5    # Seconds to wait for TCP connection
    TCP_RECV_TIMEOUT = 30      # Seconds to wait for server response

    # --- Visual Constants (ANSI Colors) ---
    RED = "\033[91m"
    RESET = "\033[0m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"

    def __init__(self):
        self.print_welcome_joker()
        print(f"{self.GREEN}Client started, listening for offer requests...{self.RESET}")

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
                print(f"{self.RED}Error in main loop: {e}{self.RESET}")
                print("Restarting listener...")

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
                
                print(f"{self.YELLOW}Received offer from {server_ip} ('{server_name}'){self.RESET}")
                
                udp_socket.close()
                return server_ip, server_tcp_port

            except ValueError:
                continue
            except Exception as e:
                print(f"UDP Error: {e}")
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
            rounds_str = input("How many rounds do you want to play? ")
            while not rounds_str.isdigit():
                rounds_str = input("Please enter a valid positive integer for rounds: ")
            
            rounds = int(rounds_str)

            # Send Request Packet
            req_packet = BlackjackClientProtocol.pack_request(rounds, self.TEAM_NAME)
            tcp_socket.sendall(req_packet)

            # --- Game Loop ---
            for i in range(rounds):
                print(f"\n{self.BLUE}=== Round {i+1} ==={self.RESET}")
                success = self.play_round(tcp_socket)
                if not success:
                    break 
            
            print("Session finished. Disconnecting.")

        except Exception as e:
            print(f"{self.RED}Connection error: {e}{self.RESET}")
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
            print("Waiting for cards...")
            
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
                print(f"{self.CYAN}[💡 Advisor]: Statistically, you should {advice.upper()}{self.RESET}")
                
                decision = self.get_valid_user_decision()
                
                packet = BlackjackClientProtocol.pack_player_decision(decision)
                conn.sendall(packet)

                if decision == "Stand":
                    print("Standing. Watching Dealer...")
                    break
                
                elif decision == "Hit":
                    val = self.receive_and_print_card(conn)
                    if val is False: return True # Bust/Game Over
                    player_hand_val += val # Update sum for next advice

            # --- 3. Dealer Turn ---
            while True:
                if self.receive_and_print_card(conn) is False:
                    break
            return True
            
        except Exception as e:
            print(f"Round Error: {e}")
            return False

    def get_valid_user_decision(self):
        """
        Loops until the user enters exactly 'Hit' or 'Stand'.
        """
        while True:
            user_input = input("Your move (Hit/Stand): ")
            try:
                BlackjackClientProtocol.pack_player_decision(user_input)
                return user_input.strip().title()
                
            except ValueError as e:
                print(f"{self.RED}Error: Please type exactly 'Hit' or 'Stand'.{self.RESET}")

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
        Reads one packet from the server.
        """
        try:
            data = self.recv_exact(conn, 9)
        except TimeoutError as e:
            print(f"{self.RED}Timeout: {e}{self.RESET}")
            raise
        except ConnectionError as e:
            print(f"{self.RED}Connection lost: {e}{self.RESET}")
            raise

        try:
            result, rank, suit = BlackjackClientProtocol.unpack_payload_server(data)
        except ValueError as e:
            print(f"{self.RED}Corrupted message from server: {e}{self.RESET}")
            raise

        if result == 0:
            self.print_card(rank, suit, owner)
            # RETURN THE VALUE OF THE CARD (Ace=11, Face=10)
            if rank == 1: return 11
            elif rank >= 10: return 10
            else: return rank
        else:
            self.print_result(result)
            return False

    # --- Visual / Printing Methods ---

    def print_welcome_joker(self):
        """Prints a cool ASCII Art Joker at startup."""
        joker_art = f"""{self.YELLOW}
           .------.
          |A .   |
          | / \\  |
          |(_,_) |  Welcome to
          |  I   |  Blackjack 2025!
          `------'{self.RESET}
        """
        print(joker_art)

    def print_card(self, rank, suit, owner=""):
        """Prints a card with graphical suits and colors."""
        # Visual Mapping
        suits_symbols = {0: "♥", 1: "♦", 2: "♣", 3: "♠"}
        ranks_map = {1: "A", 11: "J", 12: "Q", 13: "K"}
        
        # Determine Rank String
        rank_str = ranks_map.get(rank, str(rank))
        symbol = suits_symbols.get(suit, "?")
        
        # Color Logic: Hearts/Diamonds are RED, Clubs/Spades are WHITE (or default)
        # Using ANSI colors directly
        color = self.RED if suit in [0, 1] else self.CYAN
        
        # Print owner label
        if owner:
            owner_color = self.GREEN if owner == "Player" else self.YELLOW
            print(f"{owner_color}[{owner}'s Card]{self.RESET}")
        
        # ASCII Card Frame
        card_art = (
            f"{color}"
            f"┌───────┐\n"
            f"| {rank_str:<2}    |\n"
            f"|   {symbol}   |\n"
            f"|    {rank_str:>2} |\n"
            f"└───────┘{self.RESET}"
        )
        print(card_art)

    def print_result(self, result_code):
        """Prints the final game outcome with flair."""
        print("-" * 30)
        if result_code == 0x3:
            print(f"{self.GREEN}🏆  WINNER WINNER CHICKEN DINNER! 🏆{self.RESET}")
        elif result_code == 0x2:
            print(f"{self.RED}💀  YOU BUSTED / LOST! 💀{self.RESET}")
        elif result_code == 0x1:
            print(f"{self.YELLOW}⚖️  IT'S A TIE! ⚖️{self.RESET}")
        else:
            print(f"Unknown result code: {result_code}")
        print("-" * 30)

if __name__ == "__main__":
    client = Client()
    client.start()