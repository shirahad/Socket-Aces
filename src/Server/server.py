import socket
import threading
import time
import random

import BlackjackServerProtocol 

class Server:
    # --- Network Constants ---
    UDP_DEST_PORT = 13122 
    
    SERVER_NAME = "CasinoRoyaleServer"
    
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

    def handle_client(self, conn):
        """Manages the full game session with a single client."""
        try:
            # --- 1. Receive Request ---
            data = conn.recv(1024)
            if not data:
                return 

            # Parse handshake using Protocol class
            try:
                rounds, team_name = BlackjackServerProtocol.unpack_request(data)
                print(f"Game started with team: {team_name} for {rounds} rounds")
            except ValueError as e:
                print(f"Handshake failed: {e}")
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
        deck = self.create_deck()
        
        # Initial Deal: 2 cards for player, 2 for dealer
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]
        
        # Send initial cards to client (Server sends Payload)
        try:
            self.send_card(conn, player_hand[0]) # Card 1
            self.send_card(conn, player_hand[1]) # Card 2
        except Exception as e:
            print(f"Error sending initial cards: {e}")
            return False

        # --- Player Turn ---
        player_busted = False
        while True:
            try:
                # Wait for player decision packet
                data = conn.recv(1024)
                if not data: 
                    print("Client disconnected unexpectedly.")
                    return False
                
                # Use Protocol to unpack and VALIDATE (Strict check)
                decision = BlackjackServerProtocol.unpack_player_decision(data)
                
                if decision == "Hit":
                    new_card = deck.pop()
                    player_hand.append(new_card)
                    self.send_card(conn, new_card) # Send new card to client
                    
                    if self.calculate_score(player_hand) > 21: # Check Bust
                        player_busted = True
                        break 
                        
                elif decision == "Stand":
                    break
                    
            except ValueError as e:
                # STRICT ERROR HANDLING: Disconnect immediately on protocol violation
                print(f"Protocol violation by client: {e}. Terminating connection.")
                return False
            except Exception as e:
                print(f"Unexpected error during player turn: {e}")
                return False

        # --- Dealer Turn ---
        dealer_busted = False
        if not player_busted:
            try:
                # FIRST: Reveal the hidden second card to the client 
                self.send_card(conn, dealer_hand[1])

                # Dealer logic: Draw until sum >= 17 
                while self.calculate_score(dealer_hand) < 17:
                    new_card = deck.pop()
                    dealer_hand.append(new_card)
                    
                    # Reveal each new card to the client 
                    self.send_card(conn, new_card)
                
                if self.calculate_score(dealer_hand) > 21: # Check Dealer Bust
                    dealer_busted = True
            except Exception:
                return False

        # --- 4. Determine Winner and Send Result ---
        player_score = self.calculate_score(player_hand)
        dealer_score = self.calculate_score(dealer_hand)
        
        # Result codes: Win=0x3, Loss=0x2, Tie=0x1
        result_code = 0
        if player_busted:
            result_code = 0x2 # Loss (Player busted) 
        elif dealer_busted:
            result_code = 0x3 # Win (Dealer busted) 
        elif player_score > dealer_score:
            result_code = 0x3 # Win 
        elif dealer_score > player_score:
            result_code = 0x2 # Loss 
        else:
            result_code = 0x1 # Tie 

        # Send final result packet 
        try:
            # Result packet uses dummy card (0,0) as placeholder
            packet = BlackjackServerProtocol.pack_payload_server(result_code)
            conn.sendall(packet)
            return True
        except Exception:
            return False

    def send_card(self, conn, card):
        """Helper to send a card using the Protocol class."""
        rank, suit = card
        # Result Code 0x0 means 'Round Not Over'
        packet = BlackjackServerProtocol.pack_payload_server(0x0, rank, suit)
        conn.sendall(packet)

    def create_deck(self):
        """Generates a standard 52-card deck."""
        # Suits: 0-3 (Heart, Diamond, Club, Spade)
        # Ranks: 1-13
        deck = [(rank, suit) for suit in range(4) for rank in range(1, 14)]
        random.shuffle(deck) #
        return deck

    def calculate_score(self, cards):
        """Calculates hand value (Ace = 1 or 11 : An added feature)."""
        score = 0
        aces = 0
        for rank, suit in cards:
            if rank == 1: # Ace
                score += 11
                aces += 1
            elif rank >= 10: # Face cards (J,Q,K) are 10
                score += 10
            else:
                score += rank # Number cards
        
        # Adjust for Aces if bust (Standard Blackjack rule)
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
            
        return score

if __name__ == "__main__":
    server = Server()
    server.start()