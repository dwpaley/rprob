# RProb

Analyze a repertoire, sort the lines by the expected chance of seeing them, and
identify the positions that are missing. The key concept is a
depth-independent, one-sided probability for any position. In other words,
if you play your repertoire moves, what is the chance that the opponent plays
into the given position?

## Quick start

Clone this repo, install the Python package `python-chess`, then process an example
file:
```
$ git clone https://github.com/dwpaley/rprob
$ pip install python-chess
$ cd rprob/examples
$ python ../rprob.py najdorf_w.pgn w najdorf_w_out.pgn
```
Load the resulting file `najdorf_w_out.pgn` as a Chessbase database. Sort the
games by the White column. Some games look like `z000000` and the line ends in
a comment with a move for White. These are known repertoire positions. Some games
look like `z000005x` and the line ends in a move for Black. These are unknown 
positions. When you decide a move for the given position, add it as a comment and
save the game. On the next run of RProb, the possible followups for Black will be
added as new unknown positions.

When you are comfortable with RProb, then start omitting the output file name; then
the output will overwrite the input. This makes it easy to work efficiently by
iteratively running RProb, reloading the pgn in Chessbase, and adding further moves.

To process a repertoire for Black, change the `w` on the command line to `b`.

## Brief intro

- Think of a repertoire as a list of positions with your side to move. In RProb,
  each position is represented by a whole (pgn) game. You can note your intended 
  repertoire move in the final position as a comment on the last move. If you do
  so, then RProb will find the likely next moves for the other side. These moves
  will generate new unknown positions for your repertoire.

- RProb repertoire games are identified by setting the pgn tag 'Event' to 'RP'. 
  An input file can contain other games, which RProb will ignore and copy to 
  the top of the output file. Keeping one game called Analysis at the top of 
  the file is convenient, and you can include master games as well.

- The pgn inputs and outputs are intended to use with Chessbase, although I'm
  sure other programs work fine. Load the pgn as a database and sort the games
  by White. The repertoire positions will be sorted by likelihood at the end of
  the list, below your analysis and master games. Positions with no repertoire
  move are flagged by an 'x' at the end of the White tag.

- Starting positions for a repertoire: Use a comment 'TTT' to indicate the
  tabiya for the repertoire. The comment should go on your side's last move
  preceding the key position. For a Najdorf repertoire for White, the file could
  contain a game:
```
1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 {TTT} 5... a6 {Be3}
```
  After a run of RProb, the file will be populated with additional games giving
  Black's responses to the English Attack.

- You can put multiple starting positions in one file. A London repertoire for
  Black could start with two games:
```
1. d4 d5 {TTT} 2. Bf4 {c5}
1. d4 d5 2. Nf3 Nf6 {TTT} 3. Bf4 {c5}
```
The positions following these lines will be mixed together and sorted by
likelihood.
- You can omit positions from a repertoire with the word 'skip'. For example,
  the line 1. Nf3 d5 2. c4 e6 belongs in my Reti file, but after 3. d4 then
  it belongs in my QGD file instead. Therefore, I include the following game:
```
{TTT} 1. Nf3 d5 2. c4 e6 3. d4 {skip}
```
  in my Reti file and that position is sorted to the bottom of the file.

- You can upweight positions with the word 'bonus'. For example, someone at the
  club plays the Orthoschnapp Gambit, so I want to see those lines, but without
  making a whole file for them. Therefore, in my 'random French bs' file, I
  include the game:
```
1. e4 e6 {TTT} 2. c4 d5 3. cxd5 exd5 4. Qb3 {dxe4 bonus10}
```
  The final comment gives my repertoire move (4...dxe4) and a multiplier of 10x.
  All the positions following this one will be upweighted by a factor of 10.

- By default, the output file has the same name as the input. For safety, the
  input file is copied with timestamp into a folder called 'rp_backup'.

- RProb takes game statistics from the Lichess master and online databases.
  Caching these database queries is important. Two files are generated, `lc_cache.pkl`
  and `mr_cache.pkl`. Leave those files alone to avoid making too many API requests.

- Transpositions: If a position can be reached by multiple move orders, it only appears
  once in the final repertoire. Its likelihood is the sum of the probabilities for all
  its possible move orders. The position is shown with the most common way to reach it.

- Deactivated lines: If a position becomes unreachable because you've changed one of
  the preceding moves, the unreachable lines are kept but sorted to the bottom. For
  example, if I populate my 1. e4 e5 file with Spanish lines but later remove the move
  3. Bb5, then there is no way of reaching all the following Spanish positions. They will
  remain at the bottom of the file and will reappear if I ever switch back to 3. Bb5.


