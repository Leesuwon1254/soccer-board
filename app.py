from __future__ import annotations
import csv
import json
import os
from datetime import datetime, date
from typing import Dict, List, Tuple
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from markupsafe import Markup
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, UniqueConstraint

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'soccer_secret_key_2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///soccer.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ===== 등급 브랜드 로고 필터 =====
SKILL_LOGOS = {
    'A': Markup('<span class="skill-logo skill-nike" title="나이키">NIKE</span>'),
    'B': Markup('<span class="skill-logo skill-adidas" title="아디다스">adidas</span>'),
    'C': Markup('<span class="skill-logo skill-mizuno" title="미즈노">Mizuno</span>'),
}

@app.template_filter('skill_logo')
def skill_logo_filter(skill):
    return SKILL_LOGOS.get(skill, Markup(f'<span class="skill-badge">{skill}</span>'))

# ===== 관리자 비밀번호 (config.json) =====
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

def get_password() -> str:
    try:
        with open(_CONFIG_PATH, encoding='utf-8') as f:
            return json.load(f).get('admin_password', '1234')
    except Exception:
        # config.json 없으면 기본값 1234로 자동 생성
        with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump({'admin_password': '1234'}, f, ensure_ascii=False)
        return '1234'

def set_password(new_pw: str):
    with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump({'admin_password': new_pw}, f, ensure_ascii=False)

# ===== 기본 상수 =====
POSITION_CODES = ['GK','DF','MF','FW']
SKILL_RANK = {'A':3,'B':2,'C':1}
REQUIRED_BY_POS = {'GK':1,'DF':4,'MF':4,'FW':2}  # 기본(4-4-2)

# ===== 모델 =====
class Player(db.Model):
    __tablename__ = 'players'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    birth_date = db.Column(db.Date, nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    skill_grade = db.Column(db.String(1), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class PlayerPosition(db.Model):
    __tablename__ = 'player_positions'
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), primary_key=True)
    priority = db.Column(db.Integer, primary_key=True)  # 1,2
    position_code = db.Column(db.String(10), nullable=False)

class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    session_date = db.Column(db.Date, nullable=False)
    venue = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    __table_args__ = (UniqueConstraint('session_date','venue',name='uq_session_date_venue'),)

class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    checkin_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('session_id','player_id',name='uq_attendance_once'),)

class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    game_no = db.Column(db.Integer, nullable=False)
    match_type = db.Column(db.String(20), nullable=False, default='INTERNAL')  # INTERNAL|EVENT|SCRIMMAGE
    event_flavor = db.Column(db.String(30), nullable=True)  # FORM:4-3-3 등 메모용
    opponent_name = db.Column(db.String(120), nullable=True)
    kickoff_time = db.Column(db.Time, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('session_id','game_no',name='uq_session_game'),)

class Team(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
    team_label = db.Column(db.String(30), nullable=False)  # BLUE/WHITE/WORLD/KLEAGUE
    side = db.Column(db.String(1), nullable=True)  # A/B

class TeamAssignment(db.Model):
    __tablename__ = 'team_assignments'
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    assigned_position = db.Column(db.String(10), nullable=False)
    is_starter = db.Column(db.Boolean, nullable=False, default=True)

# ===== 유틸 =====
def get_or_create_today_session(venue='메인운동장'):
    today = date.today()
    s = Session.query.filter_by(session_date=today, venue=venue).first()
    if not s:
        s = Session(session_date=today, venue=venue)
        db.session.add(s); db.session.commit()
    return s

def get_today_attendance_map(session_id:int)->Dict[int,Attendance]:
    rows = Attendance.query.filter_by(session_id=session_id).all()
    return {r.player_id:r for r in rows}

def get_appearances_today_map(session_id:int)->Dict[int,int]:
    q = db.session.query(TeamAssignment.player_id, func.count(TeamAssignment.id))\
        .join(Match, Match.id==TeamAssignment.match_id)\
        .filter(Match.session_id==session_id).group_by(TeamAssignment.player_id)
    return {pid:cnt for pid,cnt in q}

def get_player_positions(player_id:int):
    pmap = {pp.priority:pp.position_code for pp in PlayerPosition.query.filter_by(player_id=player_id).all()}
    return pmap.get(1), pmap.get(2), pmap.get(3), pmap.get(4)

def get_player_pos12(player_id:int):
    p1, p2, _, _ = get_player_positions(player_id)
    return p1, p2

def calc_age(bd:date|None)->int|None:
    if not bd: return None
    t = date.today()
    return t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))

def in_age_group(bd:date|None, group:str)->bool:
    age = calc_age(bd)
    if age is None: return False
    if group=='young': return 10<=age<=30
    if group=='middle': return 40<=age<=50
    if group=='senior': return 60<=age<=80
    return False

# ===== 전법(formation) 자동 선택 =====
FORMATIONS = [
    (4,4,2), (4,3,3), (4,5,1),
    (3,5,2), (3,4,3),
    (5,3,2), (5,4,1)
]

def choose_formation(available: dict[str,int]) -> tuple[int,int,int]:
    if available.get('GK',0) < 1:
        return (4,4,2)
    def score(df,mf,fw):
        need = {'DF':df,'MF':mf,'FW':fw}
        s = 0
        for k in ('DF','MF','FW'):
            diff = available.get(k,0) - need[k]
            s += (diff >= 0) * diff * 1 + (diff < 0) * (-diff) * 3
        if available.get('FW',0) < fw: s += (fw - available.get('FW',0))
        return s
    best_s, best = None, (4,4,2)
    for df,mf,fw in FORMATIONS:
        if df+mf+fw != 10:  # GK 1 포함해 11
            continue
        sc = score(df,mf,fw)
        if best_s is None or sc < best_s:
            best_s, best = sc, (df,mf,fw)
    return best

def counts_from_candidates(cands) -> dict[str,int]:
    cnt = {'GK':0,'DF':0,'MF':0,'FW':0}
    for c in cands:
        if c.pos1 in cnt: cnt[c.pos1] += 1
        if c.pos2 in cnt: cnt[c.pos2] += 1
    for k in cnt: cnt[k] //= 2
    return cnt

# ===== 후보/선정 =====
class Candidate:
    def __init__(self, player, checkin_time, games_played):
        self.player = player
        self.checkin_time = checkin_time
        self.games_played = games_played
        self.pos1, self.pos2, self.pos3, self.pos4 = get_player_positions(player.id)
        self.grade_rank = SKILL_RANK.get(player.skill_grade,1)

    def all_positions(self):
        return [p for p in (self.pos1, self.pos2, self.pos3, self.pos4) if p]

def order_candidates(session_id:int, player_ids:List[int])->List[Candidate]:
    att = get_today_attendance_map(session_id); apps = get_appearances_today_map(session_id)
    c: List[Candidate] = []
    for pid in player_ids:
        if pid not in att: continue
        p = db.session.get(Player, pid)
        c.append(Candidate(p, att[pid].checkin_time, apps.get(pid,0)))
    c.sort(key=lambda x:(x.games_played, x.checkin_time))
    return c

def pick_candidates(session_id:int, need:int)->List[Candidate]:
    return order_candidates(session_id, list(get_today_attendance_map(session_id).keys()))[:need]

# ===== 배정(전법 반영) =====
def _pos_priority(cand:Candidate, pos:str) -> int:
    """선수가 해당 포지션을 몇 순위로 할 수 있는지 (낮을수록 우선, 없으면 99)"""
    for priority, p in enumerate((cand.pos1, cand.pos2, cand.pos3, cand.pos4), start=0):
        if p == pos:
            return priority
    return 99

# ===== 방식 B: 직전 경기 배제 로테이션 선발 =====
def _assign_positions_to_cands(candidates:List[Candidate]) -> List[tuple]:
    """4-4-2 포지션 배정. GK 반드시 포함."""
    needed = [('GK',1),('DF',4),('MF',4),('FW',2)]
    result:list[tuple] = []
    unplaced = list(candidates)
    for pos, cnt in needed:
        placed = []
        for c in list(unplaced):
            if len(placed) >= cnt: break
            if pos in c.all_positions():
                placed.append((c, pos)); unplaced.remove(c)
        for c in list(unplaced):
            if len(placed) >= cnt: break
            placed.append((c, pos)); unplaced.remove(c)
        result.extend(placed)
    # GK 없으면 첫 번째 선수에 강제 배정
    if result and 'GK' not in [pos for _,pos in result]:
        c, _ = result[0]; result[0] = (c, 'GK')
    return result[:11]

def select_11_players_final(cands:List[Candidate], prev_player_ids:set) -> List[tuple]:
    """
    방식 B 로테이션 선발:
      1. 직전 경기 11명 배제
      2. 나머지로 11명 채우기
      3. 부족하면 배제 선수 중 출전횟수↑ → 등급↑(A>B>C) → 나이↓ 순으로 보충
    """
    def sort_key(c:Candidate):
        skill_order = {'A':0,'B':1,'C':2}.get(c.player.skill_grade, 3)
        age = calc_age(c.player.birth_date) or 99
        return (c.games_played, skill_order, age)

    field = sorted([c for c in cands if c.player.id not in prev_player_ids], key=sort_key)
    bench = sorted([c for c in cands if c.player.id in prev_player_ids], key=sort_key)

    candidates = list(field)
    if len(candidates) < 11:
        candidates += bench[:11 - len(candidates)]
    # 그래도 부족(전체 출석 < 11)이면 중복 허용
    all_sorted = sorted(cands, key=sort_key)
    while len(candidates) < 11:
        for c in all_sorted:
            if len(candidates) >= 11: break
            candidates.append(c)

    return _assign_positions_to_cands(candidates[:11])

def assign_one_team(cands:List[Candidate], required_by_pos:dict[str,int]|None=None):
    if required_by_pos is None: required_by_pos = REQUIRED_BY_POS
    team: list[tuple] = []
    count = {k:0 for k in required_by_pos}
    used: set[int] = set()

    for pos in ['GK','DF','MF','FW']:
        need = required_by_pos.get(pos, 0)
        if need <= 0: continue
        # 우선순위: (포지션순위, 출전횟수 오름차순, 등급 내림차순)
        # → 적게 뛴 선수가 등급보다 먼저 선발됨
        pool = sorted(
            [(i,c) for i,c in enumerate(cands) if i not in used],
            key=lambda ic: (_pos_priority(ic[1], pos), ic[1].games_played, -ic[1].grade_rank)
        )
        for i, c in pool:
            if count[pos] >= need: break
            team.append((c, pos)); used.add(i); count[pos] += 1

    # 남은 슬롯(포지션 부족 시) — 미사용 선수로 채움
    for i, c in enumerate(cands):
        if len(team) >= 11: break
        if i not in used:
            pos = c.pos1 or c.pos2 or 'MF'
            team.append((c, pos)); used.add(i)

    # 11명 미달 시 — 중복 허용, 출전횟수 적은 순으로 채움
    fair_sorted = sorted(cands, key=lambda c: (c.games_played, -c.grade_rank))
    while len(team) < 11:
        for c in fair_sorted:
            if len(team) >= 11: break
            team.append((c, c.pos1 or 'MF'))

    return team[:11]

def assign_two_teams(cands:List[Candidate], reqA:dict[str,int]|None=None, reqB:dict[str,int]|None=None):
    if reqA is None: reqA = REQUIRED_BY_POS.copy()
    if reqB is None: reqB = REQUIRED_BY_POS.copy()
    teamA: list[tuple] = []; teamB: list[tuple] = []
    countA = {k:0 for k in reqA}; countB = {k:0 for k in reqB}
    unassigned = set(range(len(cands)))

    def add(team, cnt, pos, idx):
        team.append((cands[idx], pos))
        cnt[pos] = cnt.get(pos, 0) + 1
        unassigned.discard(idx)

    for pos in ['GK','DF','MF','FW']:
        pool = sorted(
            [(i, cands[i]) for i in list(unassigned)],
            key=lambda ic: (_pos_priority(ic[1], pos), ic[1].games_played, -ic[1].grade_rank)
        )
        needA = reqA.get(pos, 0)
        pool_copy = list(pool)
        for i, _ in pool_copy:
            if countA.get(pos,0) >= needA: break
            if i in unassigned: add(teamA, countA, pos, i)
        needB = reqB.get(pos, 0)
        pool = [(i,c) for i,c in pool if i in unassigned]
        for i, _ in pool:
            if countB.get(pos,0) >= needB: break
            if i in unassigned: add(teamB, countB, pos, i)

    # 미사용 선수 배분 — 출전횟수 적은 순 우선
    rest = sorted(list(unassigned), key=lambda i: (cands[i].games_played, -cands[i].grade_rank))
    for idx in rest:
        if len(teamA) >= 11 and len(teamB) >= 11: break
        pos = cands[idx].pos1 or cands[idx].pos2 or 'MF'
        if len(teamA) <= len(teamB) and len(teamA) < 11:
            add(teamA, countA, pos, idx)
        elif len(teamB) < 11:
            add(teamB, countB, pos, idx)
        elif len(teamA) < 11:
            add(teamA, countA, pos, idx)

    # 중복 허용으로 11명 강제 충원
    fair_sorted = sorted(cands, key=lambda c: (c.games_played, -c.grade_rank))
    for team, cnt in [(teamA, countA), (teamB, countB)]:
        while len(team) < 11:
            for c in fair_sorted:
                if len(team) >= 11: break
                team.append((c, c.pos1 or 'MF'))

    return teamA[:11], teamB[:11]

# ====== 필드 슬롯(동적 생성) ======
FIELD_W = 1000
Y_TOP, Y_BOTTOM = 120, 480
X_COL = { 'GK': 70, 'DF': 200, 'MF': 330, 'FW': 450 }  # 반쪽필드(좌측) 기준 열 (% = x/10)

def _distribute_y(n: int, top=Y_TOP, bottom=Y_BOTTOM) -> list[int]:
    if n <= 0: return []
    if n == 1: return [int((top + bottom) / 2)]
    step = (bottom - top) / (n - 1)
    return [int(round(top + i * step)) for i in range(n)]

def _make_slots_for_counts(counts: dict[str, int], side: str = 'left') -> dict[str, list[tuple[int, int]]]:
    slots: dict[str, list[tuple[int, int]]] = {}
    for pos in ('GK','DF','MF','FW'):
        n = max(0, int(counts.get(pos, 0)))
        x = X_COL.get(pos, X_COL['MF']) if side=='left' else FIELD_W - X_COL.get(pos, X_COL['MF'])
        if pos == 'GK':
            ys = [int((Y_TOP + Y_BOTTOM) / 2)] if n > 0 else []
        else:
            n = min(n, 5)
            ys = _distribute_y(n)
        slots[pos] = [(x,y) for y in ys]
    return slots

def _counts_from_assignments(assignments: list[tuple]) -> dict[str, int]:
    cnt = {'GK':0,'DF':0,'MF':0,'FW':0}
    for item in assignments:
        pos = item[1] if item[1] in cnt else 'MF'
        cnt[pos] += 1
    return cnt

def _counts_from_flavor(event_flavor: str | None) -> dict[str, int] | None:
    if not event_flavor or not event_flavor.startswith('FORM:'):
        return None
    try:
        body = event_flavor.split(':', 1)[1]
        df, mf, fw = [int(x) for x in body.split('-')]
        return {'GK':1,'DF':df,'MF':mf,'FW':fw}
    except Exception:
        return None

def layout_positions(assignments: list[tuple], side: str = 'left', counts: dict[str, int] | None = None):
    if counts is None:
        counts = _counts_from_assignments(assignments)
    slots = _make_slots_for_counts(counts, side=side)
    pos_counters = {k:0 for k in slots}
    dots=[]
    for item in assignments:
        name, pos, pid = item[0], item[1], item[2]
        skill = item[3] if len(item) > 3 else ''
        p = pos if pos in slots else 'MF'
        idx = pos_counters[p]
        if idx >= len(slots[p]) and slots[p]:
            x,y = slots[p][-1]; y = y + (idx - len(slots[p]) + 1) * 26
        elif slots[p]:
            x,y = slots[p][idx]
        else:
            backup='MF'
            bi = pos_counters.get(backup,0)
            if bi >= len(slots[backup]) and slots[backup]:
                x,y = slots[backup][-1]; y = y + (bi - len(slots[backup]) + 1) * 26
            elif slots[backup]:
                x,y = slots[backup][bi]
            else:
                x,y = (X_COL['MF'] if side=='left' else FIELD_W - X_COL['MF'], int((Y_TOP + Y_BOTTOM)/2))
            pos_counters[backup] = bi + 1
            dots.append(dict(x=x,y=y,name=name,pos=backup,id=pid,skill=skill))
            continue
        pos_counters[p] = idx + 1
        dots.append(dict(x=x,y=y,name=name,pos=p,id=pid,skill=skill))
    return dots

# ===== API: 드래그로 포지션 변경 =====
@app.post('/api/reassign')
def api_reassign():
    """
    JSON: {match_id, player_id, new_pos}  new_pos in {'GK','DF','MF','FW'}
    """
    data = request.get_json(force=True, silent=True) or {}
    match_id = int(data.get('match_id', 0))
    player_id = int(data.get('player_id', 0))
    new_pos = (data.get('new_pos') or '').upper()

    if match_id <= 0 or player_id <= 0 or new_pos not in ('GK','DF','MF','FW'):
        return jsonify({'ok': False, 'msg': 'invalid parameters'}), 400

    ta = TeamAssignment.query.filter_by(match_id=match_id, player_id=player_id).first()
    if not ta:
        return jsonify({'ok': False, 'msg': 'assignment not found'}), 404

    ta.assigned_position = new_pos
    db.session.commit()
    return jsonify({'ok': True})

# ===== API: 새로운경기 생성(JSON) — 방식 B 로테이션 =====
def _get_prev_player_ids(sess_id:int, match_type:str='INTERNAL') -> set:
    """직전 경기(해당 타입) 출전 선수 ID 집합"""
    last = Match.query.filter_by(session_id=sess_id, match_type=match_type)\
               .order_by(Match.game_no.desc()).first()
    if not last:
        return set()
    return {ta.player_id for ta in TeamAssignment.query.filter_by(match_id=last.id).all()}

def _create_internal_match(sess, team:List[tuple]) -> int:
    """INTERNAL 경기를 DB에 저장하고 game_no 반환"""
    pos_cnt = {'GK':0,'DF':0,'MF':0,'FW':0}
    for _, pos in team:
        pos_cnt[pos] = pos_cnt.get(pos,0)+1
    df = pos_cnt.get('DF',4); mf = pos_cnt.get('MF',4); fw = pos_cnt.get('FW',2)
    last = Match.query.filter_by(session_id=sess.id).order_by(Match.game_no.desc()).first()
    next_no = 1 if not last else last.game_no + 1
    match = Match(session_id=sess.id, game_no=next_no, match_type='INTERNAL',
                  event_flavor=f'FORM:{df}-{mf}-{fw}')
    db.session.add(match); db.session.flush()
    tA = Team(match_id=match.id, team_label='BLUE', side='A')
    db.session.add(tA); db.session.flush()
    for cand, pos in team:
        db.session.add(TeamAssignment(match_id=match.id, team_id=tA.id,
                                      player_id=cand.player.id, assigned_position=pos))
    db.session.commit()
    return next_no

@app.post('/api/new_game')
def api_new_game():
    sess = get_or_create_today_session()
    att_count = Attendance.query.filter_by(session_id=sess.id).count()
    if att_count < 11:
        return jsonify({'ok': False, 'msg': '출석 인원이 11명 미만입니다.'}), 400
    cands = pick_candidates(sess.id, att_count)
    prev_ids = _get_prev_player_ids(sess.id, 'INTERNAL')
    team = select_11_players_final(cands, prev_ids)
    next_no = _create_internal_match(sess, team)
    return jsonify({'ok': True, 'game_no': next_no})

# ===== [신규] API: 출석 토글(JSON) =====
@app.post('/api/attendance/toggle')
def api_toggle_attendance():
    """
    JSON: {player_id}
    응답: {ok:True, state:'in'|'out', count:int, time:'HH:MM:SS'|None}
    """
    data = request.get_json(force=True, silent=True) or {}
    try:
        player_id = int(data.get('player_id', 0))
    except Exception:
        return jsonify({'ok': False, 'msg': 'invalid player_id'}), 400

    if player_id <= 0:
        return jsonify({'ok': False, 'msg': 'invalid player_id'}), 400

    sess = get_or_create_today_session()
    att = Attendance.query.filter_by(session_id=sess.id, player_id=player_id).first()
    if att:
        db.session.delete(att)
        db.session.commit()
        state = 'out'
        tm = None
    else:
        rec = Attendance(session_id=sess.id, player_id=player_id)
        db.session.add(rec)
        db.session.commit()
        state = 'in'
        tm = rec.checkin_time.strftime('%H:%M:%S')

    count_now = Attendance.query.filter_by(session_id=sess.id).count()
    return jsonify({'ok': True, 'state': state, 'count': count_now, 'time': tm})

# ===== 라우트 =====
@app.route('/')
def home():
    get_or_create_today_session()
    return redirect(url_for('attendance_page'))

@app.route('/initdb')
def initdb():
    db.drop_all(); db.create_all()
    flash('DB 초기화 완료','success')
    return redirect(url_for('attendance_page'))

@app.route('/import', methods=['GET','POST'])
def import_csv():
    if request.method=='POST':
        f = request.files.get('file')
        if not f:
            flash('파일이 업로드되지 않았습니다.','warning')
            return redirect(url_for('players_list'))
        filename = f.filename.lower()
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            n = _import_players_from_xlsx(f)
        else:
            rows = csv.DictReader(f.stream.read().decode('utf-8-sig').splitlines())
            n = _import_players_from_rows(rows)
        flash(f'업로드 완료: {n}명 추가','success')
        return redirect(url_for('players_list'))
    return render_template('import.html', active_tab='players')

# 세부 포지션 → GK/DF/MF/FW 매핑
_XLSX_POS_MAP = {
    'GK': 'GK',
    'CB': 'DF', 'LB': 'DF', 'RB': 'DF', 'WB': 'DF',
    'CM': 'MF', 'CAM': 'MF', 'CDM': 'MF', 'LM': 'MF', 'RM': 'MF',
    'RW': 'FW', 'LW': 'FW', 'ST': 'FW', 'CF': 'FW', 'SS': 'FW',
}

def _import_players_from_xlsx(f) -> int:
    try:
        import openpyxl
    except ImportError:
        flash('openpyxl 패키지가 필요합니다: pip install openpyxl', 'danger')
        return 0
    wb = openpyxl.load_workbook(f)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return 0
    # 헤더 행 감지: No/이름 포함 여부로 판단
    header = [str(c).strip() if c else '' for c in rows[0]]
    col = {h: i for i, h in enumerate(header)}
    # 컬럼 인덱스 (헤더 없을 경우 고정 순서: No,이름,나이,능력대,소속,성별,포지션1,포지션2,등급)
    i_name  = col.get('이름',  1)
    i_pos1  = col.get('포지션1', 6)
    i_pos2  = col.get('포지션2', 7)
    i_grade = col.get('등급',  8)
    i_phone = col.get('연락처', None)
    cnt = 0
    for row in rows[1:]:
        if not row or not row[i_name]: continue
        name  = str(row[i_name]).strip()
        grade = str(row[i_grade] or 'C').strip().upper()
        if grade not in ('A','B','C'): grade = 'C'
        phone = str(row[i_phone]).strip() if i_phone and i_phone < len(row) and row[i_phone] else None
        p = Player(name=name, skill_grade=grade, phone=phone)
        db.session.add(p); db.session.flush()
        pos1_raw = str(row[i_pos1] or '').strip().upper()
        pos2_raw = str(row[i_pos2] or '').strip().upper()
        pos1 = _XLSX_POS_MAP.get(pos1_raw) or (pos1_raw if pos1_raw in POSITION_CODES else None)
        pos2 = _XLSX_POS_MAP.get(pos2_raw) or (pos2_raw if pos2_raw in POSITION_CODES else None)
        if pos1: db.session.add(PlayerPosition(player_id=p.id, priority=1, position_code=pos1))
        if pos2 and pos2 != pos1: db.session.add(PlayerPosition(player_id=p.id, priority=2, position_code=pos2))
        cnt += 1
    db.session.commit()
    return cnt

def _import_players_from_rows(rows)->int:
    cnt=0
    for r in rows:
        name=(r.get('name') or '').strip()
        if not name: continue
        bd_s=(r.get('birth_date') or '').strip(); bd=None
        if bd_s:
            try: bd=datetime.strptime(bd_s,'%Y-%m-%d').date()
            except: bd=None
        skill=(r.get('skill_grade') or 'C').strip().upper()
        if skill not in SKILL_RANK: skill='C'
        p=Player(name=name, birth_date=bd, phone=(r.get('phone') or None), skill_grade=skill)
        db.session.add(p); db.session.flush()
        pos1=(r.get('position1') or '').strip().upper()
        pos2=(r.get('position2') or '').strip().upper()
        if pos1 in POSITION_CODES: db.session.add(PlayerPosition(player_id=p.id, priority=1, position_code=pos1))
        if pos2 in POSITION_CODES: db.session.add(PlayerPosition(player_id=p.id, priority=2, position_code=pos2))
        cnt+=1
    db.session.commit(); return cnt

# ----- 출석 -----
@app.route('/attendance')
def attendance_page():
    sess = get_or_create_today_session()
    players = Player.query.order_by(Player.name).all()
    att_map = get_today_attendance_map(sess.id)
    apps_map = get_appearances_today_map(sess.id)  # {player_id: 출전횟수}
    return render_template('attendance.html', players=players, att_map=att_map,
                           apps_map=apps_map, sess=sess, active_tab='attendance')

@app.route('/attendance/toggle/<int:player_id>', methods=['POST'])
def toggle_attendance(player_id):
    # 기존 동작(새로고침 기반) — 그대로 유지
    sess = get_or_create_today_session()
    att = Attendance.query.filter_by(session_id=sess.id, player_id=player_id).first()
    if att: db.session.delete(att); db.session.commit(); flash('출석 해제','info')
    else: db.session.add(Attendance(session_id=sess.id, player_id=player_id)); db.session.commit(); flash('출석 완료','success')
    return redirect(url_for('attendance_page'))

# ----- 생성: 기본(11명, 한 팀) — 전법 자동 적용 -----
@app.route('/scheduler/generate_next', methods=['POST'])
def scheduler_generate_next():
    sess = get_or_create_today_session()
    att_count = Attendance.query.filter_by(session_id=sess.id).count()
    if att_count < 11:
        flash('출석 인원이 11명 미만입니다.','warning'); return redirect(url_for('attendance_page'))
    cands = pick_candidates(sess.id, att_count)
    prev_ids = _get_prev_player_ids(sess.id, 'INTERNAL')
    team = select_11_players_final(cands, prev_ids)
    next_no = _create_internal_match(sess, team)
    flash(f'{next_no}번 경기 생성', 'success')
    return redirect(url_for('board_by_game', game_no=next_no))

# ----- 생성: 자체게임(11 vs 11) — 전법 자동 적용 -----
@app.route('/scheduler/generate_scrimmage', methods=['POST'])
def scheduler_generate_scrimmage():
    sess = get_or_create_today_session()
    att_count = Attendance.query.filter_by(session_id=sess.id).count()
    if att_count < 22:
        flash('출석 인원이 22명 미만입니다.','warning'); return redirect(url_for('attendance_page'))
    cands = pick_candidates(sess.id, att_count)  # 전원 후보 (games_played 오름차순)
    avail = counts_from_candidates(cands)
    avail['GK'] = max(avail.get('GK',0), sum(1 for c in cands if c.pos1=='GK' or c.pos2=='GK'))
    df,mf,fw = choose_formation(avail)
    reqA = {'GK':1,'DF':df,'MF':mf,'FW':fw}
    reqB = reqA.copy()
    teamA, teamB = assign_two_teams(cands, reqA, reqB)
    last = Match.query.filter_by(session_id=sess.id).order_by(Match.game_no.desc()).first()
    next_no = 1 if not last else last.game_no + 1
    match = Match(session_id=sess.id, game_no=next_no, match_type='SCRIMMAGE',
                  event_flavor=f'FORM:{df}-{mf}-{fw}')
    db.session.add(match); db.session.flush()
    tA = Team(match_id=match.id, team_label='BLUE', side='A')
    tB = Team(match_id=match.id, team_label='WHITE', side='B')
    db.session.add_all([tA,tB]); db.session.flush()
    for cand,pos in teamA: db.session.add(TeamAssignment(match_id=match.id, team_id=tA.id, player_id=cand.player.id, assigned_position=pos))
    for cand,pos in teamB: db.session.add(TeamAssignment(match_id=match.id, team_id=tB.id, player_id=cand.player.id, assigned_position=pos))
    db.session.commit(); flash(f'자체게임 {next_no}번 생성 (전법 {df}-{mf}-{fw})','success')
    return redirect(url_for('scrimmage_by_game', game_no=next_no))

# ----- 보드: 한 팀(반쪽 필드) -----
@app.route('/board')
def board_latest():
    sess = get_or_create_today_session()
    m = Match.query.filter_by(session_id=sess.id).order_by(Match.game_no.desc()).first()
    if not m:
        flash('경기가 없습니다.','info'); return redirect(url_for('attendance_page'))
    return redirect(url_for('board_by_game', game_no=m.game_no))

@app.route('/board/<int:game_no>')
def board_by_game(game_no:int):
    sess = get_or_create_today_session()
    m = Match.query.filter_by(session_id=sess.id, game_no=game_no).first()
    if not m:
        flash(f'{game_no}번 경기를 찾을 수 없습니다.','warning'); return redirect(url_for('matches'))
    teams = Team.query.filter_by(match_id=m.id).all()
    t = next((x for x in teams if x.team_label in ('BLUE','WORLD')), teams[0] if teams else None)
    assigns = []
    if t:
        tas = TeamAssignment.query.filter_by(match_id=m.id, team_id=t.id).all()
        for a in tas:
            p = db.session.get(Player, a.player_id)
            assigns.append((p.name, a.assigned_position, p.id, p.skill_grade))
    form_counts = _counts_from_flavor(m.event_flavor)
    dots = layout_positions(assigns, side='left', counts=form_counts)
    return render_template('board_half.html', match=m, dots=dots, team_label=t.team_label if t else 'TEAM', active_tab='board')

# ----- 자체게임 보드: 11 vs 11 (양쪽 필드) -----
@app.route('/scrimmage')
def scrimmage_latest():
    sess = get_or_create_today_session()
    m = Match.query.filter_by(session_id=sess.id, match_type='SCRIMMAGE').order_by(Match.game_no.desc()).first()
    if not m:
        flash('자체게임이 아직 없습니다. 상단에서 "자체게임 생성"을 눌러주세요.','info')
        return redirect(url_for('attendance_page'))
    return redirect(url_for('scrimmage_by_game', game_no=m.game_no))

@app.route('/scrimmage/<int:game_no>')
def scrimmage_by_game(game_no:int):
    sess = get_or_create_today_session()
    m = Match.query.filter_by(session_id=sess.id, game_no=game_no).first()
    if not m:
        flash(f'{game_no}번 경기를 찾을 수 없습니다.','warning'); return redirect(url_for('matches'))
    teams = Team.query.filter_by(match_id=m.id).all()
    blue = next((x for x in teams if x.team_label in ('BLUE','WORLD')), None)
    white = next((x for x in teams if x.team_label in ('WHITE','KLEAGUE')), None)
    left, right = [], []
    if blue:
        for a in TeamAssignment.query.filter_by(match_id=m.id, team_id=blue.id).all():
            p = db.session.get(Player, a.player_id); left.append((p.name, a.assigned_position, p.id, p.skill_grade))
    if white:
        for a in TeamAssignment.query.filter_by(match_id=m.id, team_id=white.id).all():
            p = db.session.get(Player, a.player_id); right.append((p.name, a.assigned_position, p.id, p.skill_grade))
    form_counts = _counts_from_flavor(m.event_flavor)
    dots_left  = layout_positions(left,  side='left',  counts=form_counts)
    dots_right = layout_positions(right, side='right', counts=form_counts)
    return render_template('board_full.html', match=m, left=dots_left, right=dots_right, active_tab='scrimmage')

# ----- 경기 목록 -----
@app.route('/matches')
def matches():
    sess = get_or_create_today_session()
    rows = Match.query.filter_by(session_id=sess.id).order_by(Match.game_no.asc()).all()
    return render_template('matches.html', matches=rows, active_tab='matches')

# ----- 관리자 인증 -----
@app.route('/admin/change_password', methods=['POST'])
def change_password():
    current = request.form.get('current_password', '')
    new_pw  = request.form.get('new_password', '').strip()
    if current != get_password():
        return jsonify({'success': False, 'message': '현재 비밀번호가 틀렸습니다'})
    if not new_pw:
        return jsonify({'success': False, 'message': '새 비밀번호를 입력해주세요'})
    set_password(new_pw)
    return jsonify({'success': True})

# ----- 선수 관리 (매번 비밀번호 입력) -----
@app.route('/players', methods=['GET', 'POST'])
def players_list():
    if request.method == 'GET':
        return render_template('password_check.html', error=False, active_tab='players')
    pw = request.form.get('password', '')
    if pw != get_password():
        return render_template('password_check.html', error=True, active_tab='players')
    players = Player.query.order_by(Player.name).all()
    player_data = []
    for p in players:
        pos1, pos2 = get_player_pos12(p.id)
        player_data.append({'player': p, 'pos1': pos1, 'pos2': pos2})
    return render_template('players.html', player_data=player_data, active_tab='players')

@app.route('/players/new', methods=['GET', 'POST'])
def player_new():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('이름을 입력하세요.', 'warning')
            return redirect(url_for('player_new'))
        bd_s = request.form.get('birth_date', '').strip()
        bd = None
        if bd_s:
            try: bd = datetime.strptime(bd_s, '%Y-%m-%d').date()
            except: bd = None
        skill = request.form.get('skill_grade', 'C').upper()
        if skill not in SKILL_RANK: skill = 'C'
        p = Player(name=name, birth_date=bd, phone=request.form.get('phone') or None, skill_grade=skill)
        db.session.add(p); db.session.flush()
        pos1 = request.form.get('position1', '').upper()
        pos2 = request.form.get('position2', '').upper()
        if pos1 in POSITION_CODES:
            db.session.add(PlayerPosition(player_id=p.id, priority=1, position_code=pos1))
        if pos2 in POSITION_CODES and pos2 != pos1:
            db.session.add(PlayerPosition(player_id=p.id, priority=2, position_code=pos2))
        db.session.commit()
        flash(f'{name} 선수가 추가되었습니다.', 'success')
        return redirect(url_for('players_list'))
    return render_template('player_form.html', action='new', player=None, pos1=None, pos2=None, active_tab='players')

@app.route('/players/<int:player_id>/edit', methods=['GET', 'POST'])
def player_edit(player_id):
    p = db.session.get(Player, player_id)
    if not p:
        flash('선수를 찾을 수 없습니다.', 'warning')
        return redirect(url_for('players_list'))
    pos1, pos2 = get_player_pos12(player_id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('이름을 입력하세요.', 'warning')
            return redirect(url_for('player_edit', player_id=player_id))
        bd_s = request.form.get('birth_date', '').strip()
        bd = None
        if bd_s:
            try: bd = datetime.strptime(bd_s, '%Y-%m-%d').date()
            except: bd = None
        skill = request.form.get('skill_grade', 'C').upper()
        if skill not in SKILL_RANK: skill = 'C'
        p.name = name
        p.birth_date = bd
        p.phone = request.form.get('phone') or None
        p.skill_grade = skill
        PlayerPosition.query.filter_by(player_id=player_id).delete()
        new_pos1 = request.form.get('position1', '').upper()
        new_pos2 = request.form.get('position2', '').upper()
        if new_pos1 in POSITION_CODES:
            db.session.add(PlayerPosition(player_id=player_id, priority=1, position_code=new_pos1))
        if new_pos2 in POSITION_CODES and new_pos2 != new_pos1:
            db.session.add(PlayerPosition(player_id=player_id, priority=2, position_code=new_pos2))
        db.session.commit()
        flash(f'{name} 선수 정보가 수정되었습니다.', 'success')
        return redirect(url_for('players_list'))
    return render_template('player_form.html', action='edit', player=p, pos1=pos1, pos2=pos2, active_tab='players')

@app.route('/players/<int:player_id>/delete', methods=['POST'])
def player_delete(player_id):
    p = db.session.get(Player, player_id)
    if p:
        name = p.name
        PlayerPosition.query.filter_by(player_id=player_id).delete()
        Attendance.query.filter_by(player_id=player_id).delete()
        TeamAssignment.query.filter_by(player_id=player_id).delete()
        db.session.delete(p)
        db.session.commit()
        flash(f'{name} 선수가 삭제되었습니다.', 'success')
    return redirect(url_for('players_list'))

@app.route('/matches/<int:match_id>/delete', methods=['POST'])
def match_delete(match_id):
    m = db.session.get(Match, match_id)
    if m:
        TeamAssignment.query.filter_by(match_id=match_id).delete()
        Team.query.filter_by(match_id=match_id).delete()
        db.session.delete(m)
        db.session.commit()
        flash('경기가 삭제되었습니다.', 'success')
    return redirect(url_for('matches'))

# ===== API: 라인업 조회 =====
@app.get('/api/lineup')
def api_lineup():
    """
    GET /api/lineup?formation=4-4-2
    스펙 좌표(left%, top%) 포함한 11명 선수 JSON 반환
    포지션1/2가 일치하는 선수 우선, 등급 A>B>C, 동점 시 랜덤
    """
    formation = request.args.get('formation', '4-4-2')
    try:
        df_n, mf_n, fw_n = [int(x) for x in formation.split('-')]
    except Exception:
        df_n, mf_n, fw_n = 4, 4, 2

    SPEC_SLOTS = {
        'GK': [(7,  50)],
        'DF': [(21, 18), (21, 38), (21, 62), (21, 82)],
        'MF': [(35, 22), (35, 42), (35, 60), (35, 78)],
        'FW': [(47, 30), (47, 70)],
    }
    need = {'GK': 1, 'DF': df_n, 'MF': mf_n, 'FW': fw_n}
    used = set()
    players_json = []

    from sqlalchemy import case as sa_case
    for pos in ('GK', 'DF', 'MF', 'FW'):
        cnt = need.get(pos, 0)
        if cnt <= 0:
            continue
        grade_order = sa_case(
            (Player.skill_grade == 'A', 1),
            (Player.skill_grade == 'B', 2),
            else_=3
        )
        # filter는 반드시 limit 전에 적용
        q = (
            db.session.query(Player)
            .join(PlayerPosition, PlayerPosition.player_id == Player.id)
            .filter(PlayerPosition.position_code == pos)
        )
        if used:
            q = q.filter(~Player.id.in_(used))
        matched = q.order_by(grade_order, func.random()).limit(cnt).all()
        selected = list(matched)
        for p in selected:
            used.add(p.id)

        # 부족 시 랜덤 보충
        if len(selected) < cnt:
            eq = Player.query
            if used:
                eq = eq.filter(~Player.id.in_(used))
            extra = eq.order_by(func.random()).limit(cnt - len(selected)).all()
            for p in extra:
                selected.append(p)
                used.add(p.id)

        slots = SPEC_SLOTS.get(pos, [(35, 50)])
        for i, p in enumerate(selected[:cnt]):
            sl = slots[i] if i < len(slots) else slots[-1]
            players_json.append({
                'name':     p.name,
                'position': pos,
                'skill':    p.skill_grade,
                'left':     sl[0],
                'top':      sl[1],
            })

    return jsonify({'formation': formation, 'players': players_json})


@app.post('/api/reset')
def api_reset():
    """
    출석/경기 기록 전체 삭제.
    Player / PlayerPosition (선수 명단) 는 보존.
    삭제 순서: 자식 테이블 먼저 → 부모 테이블 나중
    """
    try:
        deleted = {}
        deleted['TeamAssignment'] = TeamAssignment.query.delete()
        deleted['Team']           = Team.query.delete()
        deleted['Match']          = Match.query.delete()
        deleted['Attendance']     = Attendance.query.delete()
        deleted['Session']        = Session.query.delete()
        db.session.commit()
        print(f"[DEBUG] DB 초기화 완료: {deleted}")
        return jsonify({
            'ok': True,
            'message': '초기화 완료',
            'deleted': str(deleted)
        })
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] DB 초기화 실패: {e}")
        import traceback; traceback.print_exc()
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.post('/admin/verify')
def admin_verify():
    """비밀번호만 검증. 세션 저장 안 함 (매번 확인)."""
    try:
        data    = request.get_json(force=True, silent=True) or {}
        pw      = data.get('password', '')
        correct = get_password()
        print(f"[DEBUG] admin_verify — 입력: '{pw}', 저장: '{correct}'")
        if pw == correct:
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'message': '비밀번호 불일치'})
    except Exception as e:
        print(f"[ERROR] admin_verify: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.post('/api/new_scrimmage')
def api_new_scrimmage():
    """자체게임(11 vs 11) JSON API — attendance.html AJAX용"""
    sess = get_or_create_today_session()
    att_count = Attendance.query.filter_by(session_id=sess.id).count()
    if att_count < 22:
        return jsonify({'ok': False, 'msg': '출석 인원이 22명 미만입니다.'}), 400
    cands = pick_candidates(sess.id, att_count)
    avail = counts_from_candidates(cands)
    avail['GK'] = max(avail.get('GK', 0), sum(1 for c in cands if c.pos1 == 'GK' or c.pos2 == 'GK'))
    df, mf, fw = choose_formation(avail)
    reqA = {'GK': 1, 'DF': df, 'MF': mf, 'FW': fw}
    teamA, teamB = assign_two_teams(cands, reqA, reqA.copy())
    last = Match.query.filter_by(session_id=sess.id).order_by(Match.game_no.desc()).first()
    next_no = 1 if not last else last.game_no + 1
    match = Match(session_id=sess.id, game_no=next_no, match_type='SCRIMMAGE',
                  event_flavor=f'FORM:{df}-{mf}-{fw}')
    db.session.add(match); db.session.flush()
    tA = Team(match_id=match.id, team_label='BLUE', side='A')
    tB = Team(match_id=match.id, team_label='WHITE', side='B')
    db.session.add_all([tA, tB]); db.session.flush()
    for cand, pos in teamA:
        db.session.add(TeamAssignment(match_id=match.id, team_id=tA.id,
                                      player_id=cand.player.id, assigned_position=pos))
    for cand, pos in teamB:
        db.session.add(TeamAssignment(match_id=match.id, team_id=tB.id,
                                      player_id=cand.player.id, assigned_position=pos))
    db.session.commit()
    return jsonify({'ok': True, 'game_no': next_no})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
