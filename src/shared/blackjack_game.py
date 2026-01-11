"""
Blackjack Game Logic - Handles all game rules and state.
Separated from networking concerns.
"""
import random


class BlackjackGame:
    """
    Manages a single round of Blackjack.
    Handles deck, hands, scoring, and game rules.
    """
    
    # Reshuffle when deck gets below this threshold
    RESHUFFLE_THRESHOLD = 5
    
    def __init__(self):
        self.deck = self._create_deck()
        self.player_hand = []
        self.dealer_hand = []
    
    def _create_deck(self):
        """Generates and shuffles a standard 52-card deck."""
        # Cards are tuples: (rank, suit)
        # Ranks: 1-13 (Ace=1, Jack=11, Queen=12, King=13)
        # Suits: 0-3 (Hearts, Diamonds, Clubs, Spades)
        deck = [(rank, suit) for suit in range(4) for rank in range(1, 14)]
        random.shuffle(deck)
        return deck
    
    def _draw_card(self):
        """
        Draws a card from the deck.
        Automatically reshuffles if deck is running low.
        """
        if len(self.deck) < self.RESHUFFLE_THRESHOLD:
            self.deck = self._create_deck()
        return self.deck.pop()
    
    def deal_initial(self):
        """
        Deals initial cards: 2 to player, 2 to dealer.
        Returns: (player_cards, dealer_visible_card)
        """
        self.player_hand = [self._draw_card(), self._draw_card()]
        self.dealer_hand = [self._draw_card(), self._draw_card()]
        return self.player_hand, self.dealer_hand[0]
    
    def player_hit(self):
        """
        Player takes a card.
        Returns: (new_card, is_bust)
        """
        new_card = self._draw_card()
        self.player_hand.append(new_card)
        is_bust = self.calculate_score(self.player_hand) > 21
        return new_card, is_bust
    
    def get_dealer_hidden_card(self):
        """Returns the dealer's second (hidden) card."""
        return self.dealer_hand[1]
    
    def dealer_turn(self):
        """
        Executes dealer's turn (hit until >= 17).
        Yields each new card and whether dealer busted.
        """
        # First yield the hidden card
        yield self.dealer_hand[1], False
        
        # Dealer hits until 17 or higher
        while self.calculate_score(self.dealer_hand) < 17:
            new_card = self._draw_card()
            self.dealer_hand.append(new_card)
            is_bust = self.calculate_score(self.dealer_hand) > 21
            yield new_card, is_bust
            if is_bust:
                return
    
    def calculate_score(self, hand):
        """
        Calculates hand value with flexible Ace handling.
        Aces count as 11 if possible, otherwise 1.
        """
        score = 0
        num_aces = 0
        
        for rank, suit in hand:
            if rank == 1:  # Ace
                score += 11
                num_aces += 1
            elif rank >= 10:  # Face cards (J, Q, K)
                score += 10
            else:
                score += rank
        
        # Adjust Aces from 11 to 1 if needed to avoid bust
        while score > 21 and num_aces > 0:
            score -= 10  # Convert one Ace from 11 to 1
            num_aces -= 1

        return score
    
    def get_player_score(self):
        """Returns current player score."""
        return self.calculate_score(self.player_hand)
    
    def get_dealer_score(self):
        """Returns current dealer score."""
        return self.calculate_score(self.dealer_hand)
    
    def determine_winner(self, player_busted=False):
        """
        Determines the winner after all actions complete.
        Returns: result code (0x1=Tie, 0x2=Loss, 0x3=Win)
        """
        from shared.protocol_constants import RESULT_WIN, RESULT_LOSS, RESULT_TIE
        
        if player_busted:
            return RESULT_LOSS
        
        player_score = self.get_player_score()
        dealer_score = self.get_dealer_score()
        
        if dealer_score > 21:
            return RESULT_WIN  # Dealer busted
        elif player_score > dealer_score:
            return RESULT_WIN
        elif dealer_score > player_score: 
            return RESULT_LOSS
        else:
            return RESULT_TIE
