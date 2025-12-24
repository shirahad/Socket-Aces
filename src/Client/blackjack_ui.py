"""
Blackjack UI - Handles all display and user interaction.
Separated from networking and game logic.
"""


class BlackjackUI:
    """
    Handles all console output and user input for Blackjack.
    Uses ANSI colors for visual appeal.
    """
    
    # ANSI Color Codes
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    
    # Card Display Mappings
    SUIT_SYMBOLS = {0: "♥", 1: "♦", 2: "♣", 3: "♠"}
    RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}
    
    def __init__(self):
        self.print_welcome()
    
    def print_welcome(self):
        """Prints ASCII Art welcome message."""
        joker_art = f"""{self.YELLOW}
           .------.
          |A .   |
          | / \\  |
          |(_,_) |  Welcome to
          |  I   |  Blackjack 2025!
          `------'{self.RESET}
        """
        print(joker_art)
        print(f"{self.GREEN}Client started, listening for offer requests...{self.RESET}")
    
    def print_offer_received(self, server_ip, server_name):
        """Displays server offer notification."""
        print(f"{self.YELLOW}Received offer from {server_ip} ('{server_name}'){self.RESET}")
    
    def print_round_header(self, round_num):
        """Displays round header."""
        print(f"\n{self.BLUE}=== Round {round_num} ==={self.RESET}")
    
    def print_waiting_for_cards(self):
        """Displays waiting message."""
        print("Waiting for cards...")
    
    def print_card(self, rank, suit, owner=""):
        """Prints a card with graphical suits and colors."""
        # Determine rank string
        rank_str = self.RANK_NAMES.get(rank, str(rank))
        symbol = self.SUIT_SYMBOLS.get(suit, "?")
        
        # Hearts/Diamonds are RED, Clubs/Spades are CYAN
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
    
    def print_advice(self, advice):
        """Displays strategy advice."""
        print(f"{self.CYAN}[💡 Advisor]: Statistically, you should {advice.upper()}{self.RESET}")
    
    def print_standing(self):
        """Displays standing message."""
        print("Standing. Watching Dealer...")
    
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
    
    def print_statistics(self, stats):
        """Prints game statistics."""
        print("\n" + "=" * 40)
        print(f"{self.CYAN}📊 Game Statistics 📊{self.RESET}")
        print(f"Rounds played : {stats['rounds_played']}")
        print(f"Wins          : {stats['wins']}")
        print(f"Losses        : {stats['losses']}")
        print(f"Ties          : {stats['ties']}")
        
        if stats["rounds_played"] > 0:
            win_rate = stats["wins"] / stats["rounds_played"]
            print(f"Win rate      : {win_rate:.2%}")
        
        print(f"Hits          : {stats['hits']}")
        print(f"Stands        : {stats['stands']}")
        print("=" * 40)
    
    def print_error(self, message):
        """Prints error message."""
        print(f"{self.RED}{message}{self.RESET}")
    
    def print_info(self, message):
        """Prints info message."""
        print(message)
    
    def get_rounds_input(self):
        """Gets number of rounds from user."""
        rounds_str = input("How many rounds do you want to play? ")
        while not rounds_str.isdigit() or int(rounds_str) <= 0:
            rounds_str = input("Please enter a valid positive integer for rounds: ")
        return int(rounds_str)
    
    def get_decision_input(self):
        """Gets Hit/Stand decision from user."""
        return input("Your move (Hit/Stand): ")
    
    def print_invalid_decision(self):
        """Prints invalid decision error."""
        print(f"{self.RED}Error: Please type exactly 'Hit' or 'Stand'.{self.RESET}")
