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

class Repertoire:
  def __init__(self):
    self.all_positions = set()
  def add(self, fen):
    self.all_positions.add(fen)
  def has(self, fen):
    return fen in self.all_positions


class Rpt_position:
  def __init__(self, game, color, final_positions=None, seen_positions=None):
    # final_positions have the OTHER side to move. They are used to determine
    # if a positions is reachable given the current repertoire.
    # seen_positions have the PLAYER side to move. They are used to avoid 
    # duplicating positions.
    assert color in ['w', 'b']
    if game.mainline():
      m_final = list(game.mainline())[-1]
    else:
      m_final = game
    # In the final position, the repertoire color is the side to move.
    assert m_final.turn() == color_enum[color]
    b_final = m_final.board()
    if seen_positions is not None:
      seen_positions.add(b_final.fen())
    final_comment = m_final.comment
    if final_comment and 'skip' not in final_comment:
      m_next_str = final_comment.split()[0]
      m_next = b_final.parse_san(m_next_str)
      b_temp = copy.deepcopy(b_final)
      b_temp.push(m_next)
      if final_positions is not None:
        final_positions.add(b_temp.fen())
      self.terminated = True
    else:
      m_next = None
      self.terminated = False
    self.b_final = b_final
    self.m_next = m_next
    self.color = color
    self.game = game
    self.score = 0

  def fix_lichess_uci(self, hit):
    translator = {
        'e1h1': 'e1g1',
        'e1a1': 'e1c1',
        'e8h8': 'e8g8',
        'e8a8': 'e8c8'
    }
    db_moves = hit['moves']
    for m in hit['moves']:
      if \
          m['san'] in ['O-O', 'O-O-O'] and \
          m['uci'] in ['e1h1', 'e1a1', 'e8h8', 'e8a8']:
        m['uci'] = translator[m['uci']]

  def compute_score(self, lookups, rpt=None):
    if not self.reachable(rpt):
      self.score = 0
      return
    scores = [1] * len(lookups)
    for m in self.game.mainline():
      if m.comment == 'skip':
        self.score = 0
        return
      b = m.board()
      move = b.pop()
      if b.turn == color_enum[self.color]:
        continue
      for i, l in enumerate(lookups):
        hit = l.get(b.fen())
        self.fix_lichess_uci(hit)
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
          single_score = selected_hits/total_hits
        else:
          single_score = 0
        scores[i] *= single_score
    self.score = sum(scores)/len(scores)

  def augment(self, lookups, seen_positions=None):
    result = []
    gc = copy.deepcopy(self.game)
    gc.end().comment = ''
    gc.end().add_main_variation(self.m_next)
    next_moves = set()
    for l in lookups:
      hit = l.get(gc.end().board().fen())
      for m in hit['moves']:
        next_moves.add(m['uci'])
    for m in next_moves:
      gc2 = copy.deepcopy(gc)
      gc2.end().add_main_variation(chess.Move.from_uci(m))
      new_pos = Rpt_position(gc2, self.color)
      if seen_positions is not None and \
          seen_positions.has(new_pos.game.end().board().fen()): continue
      result.append(new_pos)
    #import pdb;pdb.set_trace()
    return result

  def reachable(self, all_rpt_positions):
    if not self.game.mainline():
      return True
    for m in reversed(self.game.mainline()):
      b = m.board()
      if b.turn == color_enum[self.color]:
        continue
      if 'TTT' in m.comment:
        return True
      if not all_rpt_positions.has(b.fen()):
        return False
    return True


class lookup_adapter:
  def __init__(self, endpoint, params):
    self.cache = {}
    self.endpoint = endpoint
    self.params = params

  def get(self, key):
    if key not in self.cache:
      rp = {'fen': key}
      rp.update(self.params)
      r = requests.get(self.endpoint, rp)
      self.cache[key] = r.json()
    return self.cache[key]


if __name__ == '__main__':
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
  caches = [lc_cache, mr_cache]


  final_positions = Repertoire()
  seen_positions = Repertoire()
  
  try:
    os.mkdir('rp_backup')
  except FileExistsError:
    pass
  timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
  bk_path = os.path.join('rp_backup', timestamp+sys.argv[1])
  shutil.copy2(sys.argv[1], bk_path)

  infile = open(sys.argv[1])
  g = chess.pgn.read_game(infile)
  ignore_games = []
  loaded_games = []
  run_color = sys.argv[2]
  while g:
    if g.headers['Event'] != 'RP':
      ignore_games.append(g)
    else:
      loaded_games.append(g)
    g = chess.pgn.read_game(infile)
  infile.close()

  positions = []
  for g in loaded_games:
    pos = Rpt_position(g, run_color, final_positions, seen_positions)
    positions.append(pos)

  all_new_positions = []
  for pos in positions:
    if pos.reachable(final_positions) and pos.terminated:
      new_positions = pos.augment(caches, seen_positions)
      all_new_positions.extend(new_positions)
  all_positions = positions + all_new_positions
  for pos in all_positions:
    pos.compute_score(caches, final_positions)
  all_positions.sort(key=lambda x:x.score, reverse=True)
  score_scalar = all_positions[0].score
  for p in all_positions:
    p.score /= score_scalar
  if len(sys.argv)>3:
    of_name = sys.argv[3]
  else:
    of_name = sys.argv[1]
  with open(of_name, 'w') as ofile:
    for g in ignore_games:
      print(g, file=ofile)
      print(file=ofile)
    for i, pos in enumerate(all_positions):
      header = f'z{i:06d}'
      if not pos.terminated: header += 'x'
      pos.game.headers['White'] = header
      pos.game.headers['Black'] = f'{pos.score:.6f}'
      print(pos.game, file=ofile)
      print(file=ofile)

  lc_cache, mr_cache = caches
  pickle.dump(lc_cache, open(lc_cache_name, 'wb'))
  pickle.dump(mr_cache, open(mr_cache_name, 'wb'))








