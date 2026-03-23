"""방식 B 로테이션 시뮬레이션 — DB 없이 로직만 테스트"""

def has_pos(p, pos):
    return pos in [p.get('position1',''), p.get('position2',''),
                   p.get('position3',''), p.get('position4','')]

def sort_key(p):
    skill_order = {'A':0,'B':1,'C':2}.get(p.get('skill','C'),3)
    age = p.get('age', 99)
    return (p.get('play_count',0), skill_order, age)

def assign_positions(players):
    needed = [('GK',1),('DF',4),('MF',4),('FW',2)]
    result = []
    unplaced = list(players)
    for pos, cnt in needed:
        placed = []
        for p in list(unplaced):
            if len(placed) >= cnt: break
            if has_pos(p, pos):
                placed.append({**p,'display_pos':pos}); unplaced.remove(p)
        for p in list(unplaced):
            if len(placed) >= cnt: break
            placed.append({**p,'display_pos':pos}); unplaced.remove(p)
        result.extend(placed)
    if result and 'GK' not in [p['display_pos'] for p in result]:
        result[0]['display_pos'] = 'GK'
    return result[:11]

def select_11_final(attended, prev_ids):
    field = sorted([p for p in attended if p['id'] not in prev_ids], key=sort_key)
    bench = sorted([p for p in attended if p['id'] in prev_ids], key=sort_key)
    cands = list(field)
    if len(cands) < 11:
        cands += bench[:11-len(cands)]
    # 그래도 부족하면 전체 반복
    all_sorted = sorted(attended, key=sort_key)
    while len(cands) < 11:
        for p in all_sorted:
            if len(cands) >= 11: break
            cands.append(p)
    return assign_positions(cands[:11])

# 21명 출석 모의
skills = ['A','B','C']
mock = [
    {'id':i,'name':f'선수{i:02d}','skill':skills[(i-1)%3],
     'age':20+i,'play_count':0,
     'position1':'MF','position2':'DF','position3':'FW','position4':'GK'}
    for i in range(1,22)
]

prev = set()
print("=== 방식 B 로테이션 시뮬레이션 (출석 21명, 5경기) ===\n")
for game_no in range(1, 6):
    team = select_11_final(mock, prev)
    ids  = {p['id'] for p in team}
    overlap = ids & prev
    names = [f"{p['name']}({p['skill']})" for p in team]
    print(f"{game_no}경기: {', '.join(names)}")
    print(f"  직전 중복: {len(overlap)}명 {'✅' if len(overlap) <= 1 else '❌'}")
    for p in mock:
        if p['id'] in ids:
            p['play_count'] += 1
    prev = ids

print("\n=== 5경기 후 출전 횟수 ===")
counts = sorted([(p['name'],p['play_count'],p['skill']) for p in mock], key=lambda x:-x[1])
for name, cnt, skill in counts:
    bar = '█'*cnt
    print(f"  {name}({skill}): {cnt}회 {bar}")

max_c = max(p['play_count'] for p in mock)
min_c = min(p['play_count'] for p in mock)
print(f"\n최다: {max_c}회 / 최소: {min_c}회 / 편차: {max_c-min_c}회")
print(f"편차 2회 이내: {'✅' if max_c - min_c <= 2 else '❌'}")
