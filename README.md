# Blackjack Game - Network Programming Project

## Team Members
- Hadar Knafo - 206747792
- Lital Kupchick - 318567914

## Description
A client-server implementation of the Blackjack card game using TCP sockets. The server manages the game logic and deals cards, while clients can connect and play multiple rounds.
##  Enhanced Features
- **Visual Interface**: Colorful terminal output using ANSI escape codes for better readability.
- **Smart UI**: Dynamic card emojis (♥️, ♦️, ♣️, ♠️) and suit-based coloring.
- **Network Stability**: 60-second timeouts to prevent zombie connections.
- **Protocol Security**: Strict validation of the **Magic Cookie** (0xabcddcba) on all packets.

##  Project Components
- `blackjack_server.py`: The dealer/host. Handles game logic, deck management, and broadcasting.
- `blackjack_client.py`: The player interface. Handles server discovery and game state display.


##  Game Rules & Flow
### Card Values
* **Number cards (2-10)**: Numeric value[cite: 26].
* **Face cards (J, Q, K)**: 10 points[cite: 27].
* **Ace (A)**: 11 points[cite: 29].
* **Suits**: Heart, Diamond, Club, Spade[cite: 31].

### Round Flow
1.  **Initial Deal**: Player receives 2 cards face-up Dealer receives 2 cards: one face-up and one hidden 
2.  **Player Turn**: Choose "Hit" to draw or "Stand" to stop. Sum > 21 results in an immediate bust and loss.
3.  **Dealer Turn**: If player didn't bust, dealer reveals the hidden card]. Dealer hits if sum < 17 and stands if sum ≥ 17.
4.  **Winner Decision**: 
    * Player bust → Dealer wins.
    * Dealer bust → Player wins.
    * Higher total wins; equal totals result in a tie.
5.  **End of Round**: Server sends result (win/loss/tie), and client updates statistics.