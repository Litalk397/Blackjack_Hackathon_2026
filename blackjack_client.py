import socket, struct

class BlackjackClient:
    def __init__(self, team_name="Joker"):
        self.magic_cookie = 0xabcddcba
        # Pad team name to 32 bytes with null bytes (per protocol specification)
        self.team_name = (team_name.ljust(32, '\x00')[:32]).encode('utf-8')
        self.wins = 0
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
        """
        Connects to the server via TCP and manages the game loop for the specified number of rounds.
        Handles protocol parsing, user input validation, and game state management.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
                tcp.settimeout(60)
                tcp.connect((ip, port))
                # Step 6: Send game request
                tcp.sendall(struct.pack('!IbB32s', self.magic_cookie, 0x03, rounds, self.team_name) + b'\n')
                
                for r in range(1, rounds + 1):
                    print(f"\n{self.BOLD}{self.CYAN}{'='*40}")
                    print(f"🎰 ROUND {r} 🎰")
                    print(f"{'='*40}{self.RESET}")
                    cards_in_round = 0
                    current_player_sum = 0
                    is_my_turn = True
                    
                    while True:
                        data = tcp.recv(9) # Server format: Magic(4), Type(1), Status(1), Rank(2), Suit(1)
                        if not data or len(data) < 9: break
                        
                        _, _, status, rank, suit = struct.unpack('!IbBHB', data)
                        
                        if status == 0: # Card message (Regular Payload)
                            cards_in_round += 1
                            r_name = {1:'A', 11:'J', 12:'Q', 13:'K'}.get(rank, str(rank))
                            suit_emoji = self.suit_symbols.get(suit, '')
                            suit_name = self.suit_names.get(suit, 'Unknown')
                            card_info = f"{r_name}{suit_emoji} of {suit_name}"
                            
                            # Color cards by suit
                            if suit in [0, 1]:  # Hearts, Diamonds - Red
                                card_color = self.RED
                            else:  # Clubs, Spades - Blue
                                card_color = self.BLUE

                            if cards_in_round <= 2:
                                print(f"{self.GREEN}🃏 Your card: {card_color}{card_info}{self.RESET}")
                                val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                                current_player_sum += val
                            elif cards_in_round == 3:
                                print(f"{self.YELLOW}🎴 Dealer's visible card: {card_color}{card_info}{self.RESET}")
                            else:
                                # Important print: Is this our Hit or dealer's turn?
                                if is_my_turn:
                                    print(f"{self.GREEN}📥 Hit! Received: {card_color}{card_info}{self.RESET}")
                                    val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                                    current_player_sum += val
                                else:
                                    # Print dealer cards (reveal hidden card and draw cards until 17)
                                    print(f"{self.YELLOW}🎴 Dealer reveals/draws: {card_color}{card_info}{self.RESET}")

                            # Decision logic
                            if is_my_turn and cards_in_round >= 3 and current_player_sum < 21:
                                print(f"{self.MAGENTA}💰 Your current sum: {current_player_sum}{self.RESET}")
                                # Validate user input - only accept 'h' or 's'
                                while True:
                                    choice = input(f"{self.BOLD}Hit(H) or Stand(S)? {self.RESET}").lower().strip()
                                    if choice in ['h', 's']:
                                        break
                                    print(f"{self.RED}❌ Invalid input. Please enter 'H' for Hit or 'S' for Stand.{self.RESET}")
                                
                                if choice == 's': 
                                    is_my_turn = False
                                    decision = "Stand"
                                else: 
                                    decision = "Hittt"
                                # Send decision (10 bytes)
                                tcp.sendall(struct.pack('!Ib5s', self.magic_cookie, 0x04, decision.encode()))
                            elif current_player_sum >= 21:
                                is_my_turn = False # Automatic transition to dealer's turn or result
                        
                        else: # Result message (Win/Loss/Tie)
                            if status == 1:
                                print(f"\n{self.YELLOW}{self.BOLD}🤝 Result: TIE!{self.RESET}")
                            elif status == 2:
                                print(f"\n{self.RED}{self.BOLD}😞 Result: LOSS!{self.RESET}")
                            elif status == 3:
                                print(f"\n{self.GREEN}{self.BOLD}🎉 Result: WIN!{self.RESET}")
                                self.wins += 1
                            break # Round ended
        except Exception as e:
            print(f"Game error: {e}")

    def run(self):
        """
        Main client loop: listens for server offers via UDP broadcast and initiates games.
        Handles multiple game sessions and displays final statistics.
        """
        while True:
            try:
                user_input = input("\nHow many rounds would you like to play? (or type 'exit' to quit): ").strip()
                if user_input.lower() == 'exit': break
                num_rounds = int(user_input)
            except ValueError:
                print("Please enter a valid number.")
                continue

            print("Client started, listening for offer requests...")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try: udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except: pass
                
                udp.bind(('', 13122))
                data, addr = udp.recvfrom(1024)
                magic, m_type, port, name_raw = struct.unpack('!IbH32s', data[:39])
                
                if magic == self.magic_cookie and m_type == 0x02:
                    name = name_raw.decode('utf-8', errors='ignore').strip('\x00').strip()
                    print(f"{self.CYAN}✨ Received offer from {self.BOLD}{name}{self.RESET}{self.CYAN} at {addr[0]}{self.RESET}")
                    self.wins = 0
                    self.start_game(addr[0], port, num_rounds)
                    
                    win_rate = (self.wins / num_rounds) * 100 if num_rounds > 0 else 0
                    print(f"Finished playing {num_rounds} rounds, win rate: {win_rate:.1f}%")

if __name__ == "__main__":
    BlackjackClient().run()