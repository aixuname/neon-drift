"""Pure result grading and comparisons; safe with older score records."""


def flight_grade(game):
    if game.hidden_completed:
        return 'S'
    return 'A' if game.elapsed>=30 else 'B'


def flight_summary(records,game,name='',exclude_id=None):
    name=name.strip()[:12]
    rounds=[r for r in records if r.get('mode')==game.mode and r.get('id')!=exclude_id]
    personal=[r for r in rounds if name and r.get('name')==name]
    badges=[]
    if name and not personal:
        badges.append('首次航行')
    elif personal and game.score>max(r['score'] for r in personal):
        badges.append('刷新个人纪录')
    if game.hidden_unlocked:
        first=name and not any(r.get('hidden_unlocked',False) for r in personal)
        badges.append('首次进入隐藏关' if first else '解锁隐藏航线')
    if game.hidden_completed:
        badges.append('隐藏关通关')
    if game.best_chain>=6:
        badges.append('连收达人')
    higher=[r for r in rounds if r['score']>game.score]
    gap=None
    if higher:
        target=min(higher,key=lambda r:r['score'])
        gap=target['score']-game.score+1
        comparison=f'再得 {gap} 分可超过「{target["name"][:8]}」'
    elif any(r['score']==game.score for r in rounds):
        comparison='已追平本难度最高分'
    elif rounds:
        comparison='已超越本难度最高分'
    else:
        comparison='成为本难度第一位飞行员'
    return {'grade':flight_grade(game),'achievements':badges,
            'rank_gap':gap,'comparison':comparison}
