# Blackjack Game - Network Programming Project

## Team Members
- [Add team member names here]

## Description
A client-server implementation of the Blackjack card game using TCP sockets. The server manages the game logic and deals cards, while clients can connect and play multiple rounds.

## Features
- TCP-based network communication
- Multi-round gameplay
- Standard Blackjack rules (dealer hits until 17)
- Binary protocol for efficient data transmission

## How to Run

### Running the Server
```bash
python blackjack_server.py
```
The server will start and display its IP address and port number.

### Running the Client
```bash
python blackjack_client.py
```
When prompted:
1. Enter the server's IP address
2. Enter the server's port number
3. Enter the number of rounds you want to play

## Requirements
- Python 3.x
- No additional packages required (uses standard library only)

## Protocol
The game uses a custom binary protocol with the following message types:
- **Offer (0x02)**: Server broadcasts game availability via UDP
- **Request (0x03)**: Client requests to join a game
- **Payload (0x04)**: Server sends card information

## Game Rules
- Player receives 2 cards, dealer receives 2 cards (one hidden)
- Player can hit (take another card) or stand
- Player automatically stands if sum >= 17
- Dealer reveals hidden card and hits until sum >= 17
- Closest to 21 without busting wins
