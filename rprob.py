import chess.pgn
import pickle
import sys
import requests
import copy
import os
import datetime
import shutil


color_enum = {
    'w': True,
    'b': False
}

def raw_pgn(rgame, comments=False):
  exporter = chess.pgn.StringExporter(
      headers=False, variations=False, comments=comments
  )
  return rgame.game.accept(exporter)

def fix_lichess_uci(response):
  translator = {
      'e1h1': 'e1g1',
      'e1a1': 'e1c1',
      'e8h8': 'e8g8',
      'e8a8': 'e8c8'
  }
  db_moves = response['moves']
  for m in response['moves']:
    if \
        m['san'] in ['O-O', 'O-O-O'] and \
        m['uci'] in ['e1h1', 'e1a1', 'e8h8', 'e8a8']:
      m['uci'] = translator[m['uci']]

def fen_simple(fen):
  return ' '.join(fen.split()[:4])

class Repertoire:
  """
  Data structures in the Repertoire:
  - A dictionary where the key is an fen position (user to move) and the value
      is the corresponding Rpt_position.
  - A set of positions that result from moves in the repertoire. A given move 
      order is reachable if every position is in this set.
  """

  def __init__(self, color):
    self.next_positions = set()
    self.data = dict()
    self.color = color

  def add(self, game, augmented=False):
    pos = Rpt_game(game, self.color, augmented=augmented)
    if pos.terminated: 
      self.next_positions.add(pos.next_pos_fen)
    fen_final = fen_simple(pos.b_final.fen())
    if fen_final in self.data.keys():
      self.data[fen_final].add(pos)
    else:
      self.data[fen_final] = Rpt_position(pos)

  def flattened_games(self):
    result = []
    for k in self.data:
      result.extend(self.data[k].games)
    return result

  def augment_positions(self, lookups):
    for game in self.flattened_games():
      if not game.terminated: continue
      new_games = game.augment(lookups)
      #import pdb;pdb.set_trace()
      for new_game in new_games:
        self.add(new_game, augmented=True)

  def get_filter_fens(self, label):
    result = []
    for pos in self.data.values():
      f = pos.get_filter_fen(label)
      if f:
        result.append(f)
    return result

  def compute_scores(self, lookups, filter_fens=None):
    for pos in self.data.values():
      pos.compute_scores(lookups, self.next_positions, filter_fens)

  def write(self, ofile):
    rpositions = sorted(self.data.values(), key=lambda x:x.score, reverse=True)
    score_scalar = rpositions[0].score
    for i, rpos in enumerate(rpositions):
      score = rpos.score / score_scalar
      rgame = rpos.games[0] # this is a Rpt_game
      header = 'z{:06d}'.format(i)
      if not rgame.terminated: header += 'x'
      game = rgame.game
      game.headers['White'] = header
      game.headers['Black'] = '{:.6f}'.format(score)
      print(game, file=ofile, flush=True)
      print(file=ofile, flush=True)


class Rpt_position:
  """
  A position with the user to move. Holds one or more Rpt_games that define the
  possible move orders to reach the position.
  """


  def __init__(self, rgame):
    self.games = []
    self.add(rgame)
    self.score = 0

  def add(self, rgame):
    """
    The tricky part is a situation where we have loaded the same move order
    twice, once labeled 'skip' and once not. This can happen if two files
    have been aggregated together. If so, we replace the skipped one with the
    non-skipped.
    """
    m_next_str = rgame.m_next_str
    raw = raw_pgn(rgame)
    seen = False
    for i, g2 in enumerate(self.games):
      g2.reconcile_terminations(rgame)
      if raw == raw_pgn(g2):
        if (
            'skip' in raw_pgn(g2, comments=True)
            and not 'skip' in raw_pgn(rgame, comments=True)
            and not rgame.augmented
        ) or (
            rgame.terminated
            and not g2.terminated
        ):
          self.games[i] = rgame
          return
        else:
          seen = True
    if not seen:
      self.games.append(rgame)


  def get_filter_fen(self, label):
    """
    A variation may be marked 'filter'. If so, return the fen for the final
    position.
    """
    for g in self.games:
      ml = list(g.game.mainline())
      if not ml: continue
      last_move = ml[-1]
      if label in last_move.comment: 
        result = last_move.board().fen()
        return result
    return None

  def compute_scores(self, lookups, next_positions, filter_fens=None):

    for g in self.games:
      g.compute_score(lookups, next_positions, filter_fens=filter_fens)
    self.games.sort(key=lambda x:x.score, reverse=True)
    self.score = sum(g.score for g in self.games)


class Rpt_game:
  """
  A Rpt_game is a game with the user to move in the final position. It comes
  in two types, terminated or not. Terminated positions have the user's next
  move indicated as a comment on the final position.
  """

  def __init__(self, game, color, augmented=False):
    assert color in ['w', 'b']
    mainline = game.mainline()
    if list(mainline):
      m_final = list(game.mainline())[-1]
      assert m_final.turn() == color_enum[color]
    else:
      m_final = game
    b_final = m_final.board()
    final_comment = m_final.comment
    if final_comment and 'skip' not in final_comment:
      m_next_str = final_comment.split()[0]
      m_next = b_final.parse_san(m_next_str)
      b_temp = copy.deepcopy(b_final)
      b_temp.push(m_next)
      self.terminated = True
      self.next_pos_fen = b_temp.fen()
    else:
      m_next_str = None
      m_next = None
      self.terminated = False
      self.next_pos_fen = None
    if not game.mainline(): #special case for White's first move
      self.terminated = True
    self.b_final = b_final
    self.m_next = m_next
    self.m_next_str = m_next_str
    self.final_comment = final_comment
    self.color = color
    self.game = game
    self.score = 0
    self.augmented = augmented

  def reconcile_terminations(self, other):
    if 'skip' in raw_pgn(self, comments=True) or \
        'skip' in raw_pgn(other, comments=True):
      return
    if other.terminated and not self.terminated:
      self.add_termination(other.final_comment)
    elif self.terminated and not other.terminated:
      other.add_termination(self.final_comment)

  def add_termination(self, final_comment):
    m_next_str = final_comment.split()[0]
    b_final = self.b_final
    m_next = b_final.parse_san(m_next_str)
    b_temp = copy.deepcopy(b_final)
    b_temp.push(m_next)
    self.terminated = True
    self.next_pos_fen = b_temp.fen()
    self.m_next = m_next
    self.m_next_str = m_next_str

    game = self.game
    m_final = list(game.mainline())[-1]
    m_final.comment = m_next_str



  def compute_score(self, lookups, rpt, filter_fens=None):
    if not self.reachable(rpt):
      self.score = 0
      return
    scores = [1] * len(lookups)
    if filter_fens is None: filter_fens = []
    keep = not filter_fens
    for m in self.game.mainline():
      if m.board().fen() in filter_fens: keep = True
      if 'skip' in m.comment:
        self.score = 0
        return
      b = m.board()
      move = b.pop()
      if b.turn == color_enum[self.color]:
        if '': pass
        continue
      if 'bonus' in m.comment:
        bonus = None
        words = m.comment.split()
        for w in words:
          if w.startswith('bonus'):
            bonus = float(w[5:])
            break
        assert bonus is not None, 'something is wrong with the bonus'
      else:
        bonus = 1
      for i, l in enumerate(lookups):
        hit = l.get(b.fen())
        fix_lichess_uci(hit)
        db_moves = hit['moves']
        total_hits = 0
        selected_hits = 0
        for db_m in db_moves:
          total_hits += db_m['white']
          total_hits += db_m['black']
          total_hits += db_m['draws']
          if db_m['uci'] == move.uci():
            selected_hits += db_m['white']
            selected_hits += db_m['black']
            selected_hits += db_m['draws']
        if total_hits:
          single_score = selected_hits/total_hits * bonus
        else:
          single_score = 0
        scores[i] *= single_score
    if keep:
      self.score = sum(scores)/len(scores)
    else:
      self.score = 0

  def augment(self, lookups):
    result = []
    gc = copy.deepcopy(self.game)
    #gc.end().comment = ' '.join(gc.end().comment.split()[1:])
    gc.end().comment = ''
    if self.m_next:
      gc.end().add_main_variation(self.m_next)
    next_moves = set()
    fen = gc.end().board().fen()
    for i, l in enumerate(lookups):
      verbose = i==0
      hit = l.get(fen, verbose=verbose)
      for m in hit['moves']:
        next_moves.add(m['uci'])
    for m in next_moves:
      gc2 = copy.deepcopy(gc)
      gc2.end().add_main_variation(chess.Move.from_uci(m))
      result.append(gc2)
    return result

  def reachable(self, next_positions):
    # The position is reachable if every preceding move is also a repertoire
    # move.
    if not self.game.mainline():
      return True
    for m in reversed(self.game.mainline()):
      b = m.board()
      if b.turn == color_enum[self.color]:
        continue
      if 'TTT' in m.comment:
        return True
      if not b.fen() in next_positions:
        return False
    return True


class lookup_adapter:
  def __init__(self, endpoint, params):
    self.cache = {}
    self.endpoint = endpoint
    self.params = params

  def get(self, key, verbose=False):
    if key not in self.cache:
      if verbose: print('fetching: ', key)
      rp = {'fen': key}
      rp.update(self.params)
      r = requests.get(self.endpoint, rp)
      self.cache[key] = r.json()
    return self.cache[key]


if __name__ == '__main__':
  # configure lookups
  lc_cache_name = 'lc_cache.pkl'
  mr_cache_name = 'mr_cache.pkl'
  try:
    lc_cache = pickle.load(open(lc_cache_name, 'rb'))
  except FileNotFoundError:
    lc_cache = lookup_adapter(
      endpoint='https://explorer.lichess.ovh/lichess',
      params={
        'speeds': 'blitz,rapid,classical',
        'ratings': '2000,2200,2500'
      }
    )
  try:
    mr_cache = pickle.load(open(mr_cache_name, 'rb'))
  except FileNotFoundError:
    mr_cache = lookup_adapter(
      endpoint='https://explorer.lichess.ovh/masters',
      params={}
    )
  lc_cache.verbose = False
  mr_cache.verbose = True
  lookups = [lc_cache, mr_cache]

  #backup the current pgn
  try:
    os.mkdir('rp_backup')
  except FileExistsError:
    pass
  timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
  bk_path = os.path.join('rp_backup', timestamp+sys.argv[1])
  shutil.copy2(sys.argv[1], bk_path)

  # load games from current pgn
  infile = open(sys.argv[1])
  g = chess.pgn.read_game(infile)
  non_rpt_games = []
  loaded_games = []
  run_color = sys.argv[2]
  while g:
    if g.headers['Event'] != 'RP':
      non_rpt_games.append(g)
    else:
      loaded_games.append(g)
    g = chess.pgn.read_game(infile)
  infile.close()

  # compute
  positions = Repertoire(color=sys.argv[2])
  for g in loaded_games:
    positions.add(g)
  #import pdb;pdb.set_trace()
  if len(sys.argv) >= 4:
    filter_fens = []
    for word in sys.argv[3:]:
      filter_fens.extend(positions.get_filter_fens(word))
  else:
    filter_fens = None
  positions.augment_positions(lookups)
  positions.compute_scores(lookups, filter_fens=filter_fens)

  # Sort the non-repertoire games
  match_games = []
  nonmatch_games = []
  if filter_fens is not None:
    for g in non_rpt_games:
      match = False
      for m in g.mainline():
        fen = m.board().fen()
        if fen in filter_fens:
          match = True
          break
      if match:
        match_games.append(g)
      else:
        nonmatch_games.append(g)


  else:
    nonmatch_games = non_rpt_games






  # Write out the results
  if len(sys.argv)>3 and False:
    of_name = sys.argv[3]
  else:
    of_name = sys.argv[1]
  with open(of_name, 'w') as ofile:
    for g in match_games:
      print(g, file=ofile, flush=True)
      print(file=ofile, flush=True)
    positions.write(ofile)
    for g in nonmatch_games:
      print(g, file=ofile, flush=True)
      print(file=ofile, flush=True)

  # Cache the db lookups
  pickle.dump(lc_cache, open(lc_cache_name, 'wb'))
  pickle.dump(mr_cache, open(mr_cache_name, 'wb'))
