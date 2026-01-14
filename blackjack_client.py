import socket, struct

# Protocol constants - these are shared values between client and server to ensure they speak the same protocol
MAGIC_COOKIE = 0xabcddcba  # Unique identifier to verify server legitimacy and prevent protocol mismatches
UDP_PORT = 13122
TCP_TIMEOUT = 60
TEAM_NAME_LENGTH = 32

# Message types
MSG_TYPE_OFFER = 0x02
MSG_TYPE_REQUEST = 0x03
MSG_TYPE_PAYLOAD = 0x04

# Game status codes
STATUS_CARD = 0
STATUS_TIE = 1
STATUS_LOSS = 2
STATUS_WIN = 3

# Decision strings
DECISION_HIT = b"Hittt"
DECISION_STAND = b"Stand"

class BlackjackClient:
    """BlackJack client for connecting to game servers and playing multiple rounds.
    
    The client listens for UDP broadcasts from servers and initiates TCP connections
    to play BlackJack games with colored console output and win rate tracking.
    """
    
    def __init__(self, team_name="Joker"):
        """Initialize the BlackJack client.
        
        Args:
            team_name (str): The client's team name (max 32 characters).
        """
        self.magic_cookie = MAGIC_COOKIE
        # Pad team name to 32 bytes with null bytes (per protocol specification)
        self.team_name = (team_name.ljust(TEAM_NAME_LENGTH, '\x00')[:TEAM_NAME_LENGTH]).encode('utf-8')
        self.wins = 0
        self.losses = 0
        self.ties = 0
        # Card suit emojis
        self.suit_symbols = {0: '♥️', 1: '♦️', 2: '♣️', 3: '♠️'}
        self.suit_names = {0: 'Hearts', 1: 'Diamonds', 2: 'Clubs', 3: 'Spades'}
        # ANSI color codes
        self.RED = '\033[91m'
        self.GREEN = '\033[92m'
        self.YELLOW = '\033[93m'
        self.BLUE = '\033[94m'
        self.MAGENTA = '\033[95m'
        self.CYAN = '\033[96m'
        self.RESET = '\033[0m'
        self.BOLD = '\033[1m'

    def start_game(self, ip, port, rounds):
        """Connects to the server via TCP and manages the game loop for the specified number of rounds.
        Handles protocol parsing, user input validation, and game state management.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
                tcp.settimeout(TCP_TIMEOUT)  # Prevent hanging if server stops responding
                tcp.connect((ip, port))
                # Send game request with magic cookie (verification), message type, number of rounds, and team name
                tcp.sendall(struct.pack('!IbB32s', self.magic_cookie, MSG_TYPE_REQUEST, rounds, self.team_name))
                
                for r in range(1, rounds + 1):
                    print(f"\n{self.BOLD}{self.CYAN}{'='*40}")
                    print(f"🎰 ROUND {r} 🎰")
                    print(f"{'='*40}{self.RESET}")
                    
                    # Reset game state for each new round
                    # We track card counts to know when dealer's turn starts
                    player_cards_received = 0  # Count of player cards (first 2 are initial deal)
                    dealer_cards_received = 0  # Count of dealer cards (first is visible, rest are revealed later)
                    dealer_turn = False  # Flags when we switch from player turn to dealer turn
                    current_player_sum = 0  # Running total of player's hand value
                    
                    while True:
                        # Receive card data from server (9 bytes: magic cookie, message type, status, rank, suit)
                        data = tcp.recv(9)
                        if not data:
                            print(f"{self.RED}Server disconnected. Returning to listening mode.{self.RESET}")
                            return
                        
                        if len(data) < 9:
                            print(f"{self.RED}Invalid packet received. Connection error.{self.RESET}")
                            return
                        
                        # Unpack the binary data according to the protocol format
                        magic, m_type, status, rank, suit = struct.unpack('!IbBHB', data)
                        
                        # Validate message
                        if magic != self.magic_cookie or m_type != MSG_TYPE_PAYLOAD:
                            print(f"{self.RED}Protocol error: Invalid message received.{self.RESET}")
                            return
                        
                        if status == STATUS_CARD:
                            # Convert numeric rank to card names (A=Ace, J=Jack, Q=Queen, K=King)
                            r_name = {1:'A', 11:'J', 12:'Q', 13:'K'}.get(rank, str(rank))
                            suit_emoji = self.suit_symbols.get(suit, '')  # Get visual symbol for suit
                            suit_name = self.suit_names.get(suit, 'Unknown')
                            card_info = f"{r_name}{suit_emoji} of {suit_name}"
                            
                            # Color cards by suit for better visual distinction
                            # Red cards (hearts, diamonds) and blue cards (clubs, spades) are easier to read
                            if suit in [0, 1]:  # Hearts (0), Diamonds (1) - Red
                                card_color = self.RED
                            else:  # Clubs (2), Spades (3) - Blue
                                card_color = self.BLUE

                            # Identify which card this is based on the order received
                            # First 2 cards = player's initial hand
                            # 3rd card = dealer's visible card
                            # Remaining cards before dealer_turn = player hits
                            # After dealer_turn = dealer reveals hidden card and draws
                            if not dealer_turn:
                                if player_cards_received < 2:
                                    # First 2 cards belong to the player's initial hand
                                    print(f"{self.GREEN}🃏 Your card: {card_color}{card_info}{self.RESET}")
                                    # Calculate card value: Ace=11, Face cards=10, others=pip value
                                    val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                                    current_player_sum += val
                                    player_cards_received += 1
                                elif dealer_cards_received == 0:
                                    # Third card is the dealer's visible/up card (dealer shows this card at start)
                                    print(f"{self.YELLOW}🎴 Dealer's visible card: {card_color}{card_info}{self.RESET}")
                                    dealer_cards_received += 1
                                else:
                                    # Additional cards after dealer's visible card = player requested a Hit
                                    print(f"{self.GREEN}📥 Hit! Received: {card_color}{card_info}{self.RESET}")
                                    val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                                    current_player_sum += val
                                    player_cards_received += 1
                            else:
                                # After player stands, dealer reveals their hidden card and draws more if needed
                                print(f"{self.YELLOW}🎴 Dealer reveals/draws: {card_color}{card_info}{self.RESET}")
                                dealer_cards_received += 1

                            # Ask player for their decision after dealer's visible card is revealed
                            # Only ask if: we haven't transitioned to dealer's turn yet AND dealer showed a card AND player hasn't busted
                            if not dealer_turn and dealer_cards_received > 0 and current_player_sum < 21:
                                print(f"{self.MAGENTA}💰 Your current sum: {current_player_sum}{self.RESET}")
                                
                                # Get and validate player input (Hit or Stand)
                                # Repeat until valid input is received
                                while True:
                                    choice = input(f"{self.BOLD}Hit(H) or Stand(S)? {self.RESET}").lower().strip()
                                    if choice in ['h', 's']:
                                        break
                                    print(f"{self.RED}❌ Invalid input. Please enter 'H' for Hit or 'S' for Stand.{self.RESET}")
                                
                                if choice == 's':
                                    # Player stands - tell server to move to dealer's turn
                                    dealer_turn = True
                                    tcp.sendall(struct.pack('!Ib5s', self.magic_cookie, MSG_TYPE_PAYLOAD, DECISION_STAND))
                                else:
                                    # Player hits - send request for another card to the server
                                    tcp.sendall(struct.pack('!Ib5s', self.magic_cookie, MSG_TYPE_PAYLOAD, DECISION_HIT))
                            
                            elif current_player_sum >= 21:
                                # If player reached or exceeded 21, automatically move to dealer's turn
                                # (they either have 21 or busted - either way, no more decisions)
                                dealer_turn = True
                        
                        else:
                            # Status is not STATUS_CARD, so this is the final result message
                            # Display result and update statistics
                            if status == STATUS_TIE:
                                print(f"\n{self.YELLOW}{self.BOLD}🤝 Result: TIE!{self.RESET}")
                                self.ties += 1
                            elif status == STATUS_LOSS:
                                print(f"\n{self.RED}{self.BOLD}😞 Result: LOSS!{self.RESET}")
                                self.losses += 1
                            elif status == STATUS_WIN:
                                print(f"\n{self.GREEN}{self.BOLD}🎉 Result: WIN!{self.RESET}")
                                self.wins += 1
                            # Exit the inner loop to move to the next round
                            break
        
        except socket.timeout:
            print(f"{self.RED}Connection timeout. Server not responding.{self.RESET}")
        except ConnectionResetError:
            print(f"{self.RED}Connection reset by server.{self.RESET}")
        except Exception as e:
            print(f"{self.RED}Game error: {e}{self.RESET}")

    def run(self):
        """Main client loop: listens for server offers via UDP broadcast and initiates games.
        Handles multiple game sessions and displays final statistics.
        """
        while True:
            try:
                # Ask user how many rounds they want to play
                user_input = input("\nHow many rounds would you like to play? (or type 'exit' to quit): ").strip()
                if user_input.lower() == 'exit':
                    break
                num_rounds = int(user_input)
            except ValueError:
                print("Please enter a valid number.")
                continue

            # Listen for UDP broadcast offers from servers
            print("Client started, listening for offer requests...")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                # Allow reusing the port if it was recently used
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    # Try to enable SO_REUSEPORT for more flexible port binding
                    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except:
                    pass  # Not all systems support SO_REUSEPORT, that's okay
                
                # Bind to the broadcast port to receive server offers
                udp.bind(('', UDP_PORT))
                # Wait for a broadcast offer from a server
                data, addr = udp.recvfrom(1024)
                
                if len(data) < 39:
                    print(f"{self.RED}Invalid offer packet received.{self.RESET}")
                    continue
                
                # Parse the offer packet: magic cookie, message type, TCP port, server name
                magic, m_type, port, name_raw = struct.unpack('!IbH32s', data[:39])
                
                # Verify the offer is valid and from a legitimate server
                if magic == self.magic_cookie and m_type == MSG_TYPE_OFFER:
                    # Extract and clean up the server's team name
                    name = name_raw.decode('utf-8', errors='ignore').strip('\x00').strip()
                    print(f"{self.CYAN}✨ Received offer from {self.BOLD}{name}{self.RESET}{self.CYAN} at {addr[0]}{self.RESET}")
                    
                    # Reset game statistics for this new game session
                    self.wins = 0
                    self.losses = 0
                    self.ties = 0
                    
                    # Connect to the server and play the requested number of rounds
                    self.start_game(addr[0], port, num_rounds)
                    
                    # Calculate and display game statistics after all rounds are complete
                    total = self.wins + self.losses + self.ties
                    if total > 0:
                        # Calculate win/loss/tie rates as percentages
                        win_rate = (self.wins / total) * 100
                        loss_rate = (self.losses / total) * 100
                        tie_rate = (self.ties / total) * 100
                        
                        print(f"\n{self.BOLD}{self.CYAN}{'='*50}")
                        print(f"📊 GAME STATISTICS")
                        print(f"{'='*50}{self.RESET}")
                        print(f"{self.GREEN}Wins: {self.wins} ({win_rate:.1f}%){self.RESET}")
                        print(f"{self.RED}Losses: {self.losses} ({loss_rate:.1f}%){self.RESET}")
                        print(f"{self.YELLOW}Ties: {self.ties} ({tie_rate:.1f}%){self.RESET}")
                        print(f"{self.CYAN}Total rounds: {total}{self.RESET}")
                    else:
                        print(f"{self.YELLOW}No rounds completed.{self.RESET}")

if __name__ == "__main__":
    BlackjackClient().run()