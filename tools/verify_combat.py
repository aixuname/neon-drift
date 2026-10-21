"""Validate the intense 30-second combat edition without touching real saves."""
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'temp')
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['SDL_AUDIODRIVER']='dummy'
sys.path.insert(0,str(ROOT))
from game import App, Storage, pygame
from combat import Actor, Block, Bullet, HIDDEN_SECONDS, HIT_Z, MAX_LIVES, MODES, PATTERNS, ROUND_SECONDS, Round, Wave


def empty(mode='normal'):
    game=Round(mode,random.Random(32),events_enabled=False)
    game.spawn_in=999
    return game


def crossing(game,blocks=None,opening=None,orbs=None):
    game.waves=[Wave(HIT_Z+.03,blocks or [],opening,orbs or [])]
    game.update(.02)


class FlightPhysics(unittest.TestCase):
    def test_round_is_thirty_seconds_and_stops(self):
        game=empty()
        game.lives=2
        self.assertEqual(ROUND_SECONDS,30)
        game.update(29.99)
        self.assertFalse(game.ended)
        game.update(5)
        self.assertEqual(game.elapsed,30)
        self.assertTrue(game.ended)
        self.assertEqual(game.remaining,0)
        score=game.score
        game.update(50)
        self.assertEqual(game.score,score)

    def test_distance_is_independent_of_frame_rate(self):
        fast,slow=empty(),empty()
        for _ in range(1800):
            fast.update(1/60)
        for _ in range(60):
            slow.update(.5)
        self.assertAlmostEqual(fast.distance,slow.distance,places=5)
        self.assertEqual(fast.score,1500)
        self.assertEqual(fast.score,slow.score)

    def test_difficulty_speed_and_spawn_density_increase(self):
        self.assertEqual([MODES[m]['speed'] for m in ('easy','normal','hard')],[15,20,25])
        self.assertLessEqual(MODES['normal']['interval'],.8)
        counts=[]
        for mode in ('easy','normal','hard'):
            game=Round(mode,random.Random(1),events_enabled=False)
            game.invulnerable=99
            game.update(30)
            counts.append(game.spawned)
        self.assertLess(counts[0],counts[1])
        self.assertLess(counts[1],counts[2])
        self.assertGreater(counts[1],35)
        self.assertGreater(counts[2],45)

    def test_contact_damage_cooldown_and_three_lives(self):
        game=empty()
        self.assertEqual(game.lives,3)
        crossing(game,[Block(0,0)])
        self.assertEqual(game.lives,2)
        crossing(game,[Block(0,0)])
        self.assertEqual(game.lives,2)
        for expected in (1,0):
            game.invulnerable=0
            crossing(game,[Block(0,0)])
            self.assertEqual(game.lives,expected)
        self.assertTrue(game.ended)

    def test_two_second_shield_protects_then_expires(self):
        game=empty()
        self.assertTrue(game.activate_shield())
        self.assertEqual(game.shield,2)
        self.assertEqual(game.charge,0)
        self.assertFalse(game.activate_shield())
        crossing(game,[Block(0,0)])
        self.assertEqual(game.lives,3)
        game.update(2.1)
        crossing(game,[Block(0,0)])
        self.assertEqual(game.lives,2)

    def test_collect_chain_and_recharge(self):
        game=empty()
        game.charge=0
        for _ in range(6):
            crossing(game,orbs=[(0,0)])
        self.assertEqual(game.orbs,6)
        self.assertEqual(game.best_chain,6)
        self.assertEqual(game.charge,100)
        crossing(game,orbs=[(.6,.4)])
        self.assertEqual(game.chain,0)

    def test_frame_stall_still_detects_collision(self):
        game=empty()
        game.waves=[Wave(8,[Block(0,0)])]
        game.update(.6)
        self.assertEqual(game.lives,2)

    def test_control_response_and_flight_boundary(self):
        game=empty()
        game.target=(.5,.1)
        game.update(1)
        self.assertAlmostEqual(game.x,.5,places=5)
        game.axis=(1,1)
        game.update(2)
        self.assertLessEqual(math.hypot(game.x,game.y),.840001)

    def test_diagonal_speed_normalized(self):
        a,b=empty(),empty()
        a.axis=(1,0)
        b.axis=(1,1)
        a.update(.2)
        b.update(.2)
        self.assertAlmostEqual(a.x,math.hypot(b.x,b.y),places=5)

    def test_phases_stay_inside_thirty_seconds(self):
        game=empty()
        self.assertEqual(game.phase,0)
        game.update(10.01)
        self.assertEqual(game.phase,1)
        game.update(10)
        self.assertEqual(game.phase,2)


class HiddenRoute(unittest.TestCase):
    def test_full_health_unlocks_exactly_at_thirty_seconds_in_every_mode(self):
        for mode in MODES:
            original=dict(MODES[mode])
            game=empty(mode)
            game.update(29.99)
            self.assertFalse(game.hidden_unlocked)
            speed=game.speed
            game.update(.01)
            self.assertTrue(game.hidden_unlocked)
            self.assertFalse(game.ended)
            self.assertEqual(game.elapsed,30)
            self.assertEqual(game.remaining,HIDDEN_SECONDS)
            self.assertGreater(game.speed,speed*1.25)
            self.assertLess(game.config['interval'],original['interval'])
            self.assertEqual(game.attack_mode,'hard')
            self.assertEqual(game.phase,3)
            self.assertEqual(game.mode,mode)
            self.assertEqual(MODES[mode],original)
            fresh=Round(mode)
            self.assertFalse(fresh.hidden_unlocked)
            self.assertEqual(fresh.config,original)

    def test_missing_health_settles_without_unlocking(self):
        for lives in (1,2):
            game=empty()
            game.lives=lives
            game.update(100)
            self.assertTrue(game.ended)
            self.assertFalse(game.hidden_unlocked)
            self.assertEqual(game.elapsed,30)
            self.assertEqual(game.reason,'穿越完成')

    def test_damage_on_final_frame_prevents_unlock(self):
        game=empty()
        game.elapsed=29.99
        game.waves=[Wave(HIT_Z+.001,[Block(0,0)])]
        game.update(.01)
        self.assertEqual(game.lives,2)
        self.assertTrue(game.ended)
        self.assertFalse(game.hidden_unlocked)

    def test_shielded_final_contact_still_qualifies_and_keeps_progress(self):
        game=empty()
        game.elapsed=29.99
        game.distance=200
        game.bonus=123
        game.orbs=4
        game.chain=2
        game.activate_shield()
        game.waves=[Wave(HIT_Z+.001,[Block(0,0)])]
        game.update(.01)
        self.assertTrue(game.hidden_unlocked)
        self.assertEqual(game.lives,3)
        self.assertEqual(game.charge,0)
        self.assertAlmostEqual(game.shield,1.99)
        self.assertEqual((game.bonus,game.orbs,game.chain),(123,4,2))
        self.assertGreater(game.distance,200)
        self.assertFalse(game.waves)

    def test_large_update_crosses_boundary_without_losing_time(self):
        game=empty()
        game.update(30.25)
        self.assertTrue(game.hidden_unlocked)
        self.assertAlmostEqual(game.elapsed,30.25)
        self.assertAlmostEqual(game.remaining,14.75)
        self.assertEqual(sum(e[0]=='hidden_start' for e in game.events),1)

    def test_hidden_round_ends_once_at_forty_five_seconds(self):
        game=empty()
        game.invulnerable=100
        game.update(100)
        self.assertTrue(game.ended)
        self.assertTrue(game.hidden_completed)
        self.assertEqual(game.elapsed,45)
        self.assertEqual(game.remaining,0)
        self.assertEqual(game.reason,'隐藏关通关')
        self.assertEqual(sum(e[0]=='hidden_start' for e in game.events),1)
        score=game.score
        game.update(100)
        self.assertEqual(game.score,score)

    def test_hidden_failure_stops_without_completion(self):
        game=empty()
        game.update(30)
        game.spawn_in=999
        game.special_schedule=[]
        for _ in range(3):
            game.invulnerable=0
            game.damage(0,0)
        self.assertTrue(game.ended)
        self.assertTrue(game.hidden_unlocked)
        self.assertFalse(game.hidden_completed)
        self.assertEqual(game.reason,'隐藏关挑战结束')
        game.update(5)
        self.assertEqual(game.elapsed,30)


class ObstacleGeometry(unittest.TestCase):
    def test_crystal_corners_and_energy_beam_caps_match_visible_shapes(self):
        crystal=Block(0,0,.4,.34)
        self.assertFalse(crystal.collides(.19,-.16))
        self.assertTrue(crystal.collides(0,0))
        self.assertTrue(crystal.collides(.23,.04))
        beam=Block(0,0,1.2,.2,shape='laser')
        self.assertFalse(beam.collides(.61,.12))
        self.assertTrue(beam.collides(.61,0))

    def test_oval_gate_uses_curved_aperture(self):
        wave=Wave(opening=(0,0,.8,1.1),kind='moving')
        x,y,w,h=wave.opening_at()
        self.assertFalse(wave.collides(x,y))
        self.assertFalse(wave.collides(x,y+h*.35))
        self.assertTrue(wave.collides(x+w*.42,y+h*.42))

    def test_all_six_styles_appear(self):
        game=empty()
        for _ in range(18):
            game.spawn()
        self.assertEqual({wave.kind for wave in game.waves},set(PATTERNS))

    def test_rotation_changes_collision_geometry(self):
        horizontal=Block(0,0,1.2,.06)
        vertical=Block(0,0,1.2,.06,math.pi/2)
        self.assertTrue(horizontal.collides(.4,0))
        self.assertFalse(vertical.collides(.4,0))
        self.assertTrue(vertical.collides(0,.4))

    def test_lasers_rotate_with_simulation_time(self):
        wave=Wave(kind='laser',phase=.1)
        before=wave.geometry()[0].angle
        wave.age=1
        self.assertNotEqual(wave.geometry()[0].angle,before)

    def test_moving_gap_updates_visible_and_collision_position(self):
        wave=Wave(opening=(0,0,.63,.6),kind='moving')
        first=wave.opening_at()
        wave.age=1.3
        second=wave.opening_at()
        self.assertNotEqual(first,second)
        self.assertFalse(wave.collides(second[0],second[1]))
        self.assertTrue(wave.collides(-.8,-.7))

    def test_ring_and_round_mine_collision(self):
        wave=Wave(opening=(.1,-.1,.86,.86),kind='ring')
        self.assertFalse(wave.collides(.1,-.1))
        self.assertTrue(wave.collides(.7,.2))
        mine=Block(0,0,.26,.26,shape='mine')
        self.assertTrue(mine.collides(.1,0))
        self.assertFalse(mine.collides(.3,.3))

    def test_every_pattern_has_reachable_space_even_while_moving(self):
        points=[(x/20,y/20) for x in range(-16,17,2) for y in range(-16,17,2)
                if math.hypot(x/20,y/20)<.82]
        for mode in MODES:
            game=Round(mode,random.Random(51),events_enabled=False)
            for _ in range(36):
                game.spawn()
                wave=game.waves[-1]
                for age in (0.,.8,1.6,2.4):
                    wave.age=age
                    self.assertTrue(any(not wave.collides(x,y) for x,y in points),(mode,wave.kind,age))


class DragonAndBulletRules(unittest.TestCase):
    def test_three_encounters_include_gunner_and_leave_recovery_time(self):
        seen=set()
        for seed in range(20):
            normal=Round(rng=random.Random(seed))
            self.assertEqual(len(normal.special_schedule),3)
            self.assertIn('gunner',[k for _,k in normal.special_schedule])
            hard=Round('hard',random.Random(seed))
            self.assertEqual(len(hard.special_schedule),3)
            self.assertIn('gunner',[k for _,k in hard.special_schedule])
            seen.update(k for _,k in hard.special_schedule)
            easy=Round('easy',random.Random(seed))
            for game in (easy,normal,hard):
                self.assertEqual(len(game.special_schedule),3)
                self.assertEqual(len({kind for _,kind in game.special_schedule}),3)
                previous_end=0
                for start,kind in game.special_schedule:
                    self.assertGreater(start-previous_end,3.6)
                    previous_end=start+{'brute':4.5,'swarm':4.6,'trickster':4.5,'gunner':5.1}[kind]
                    self.assertLess(previous_end,30)
        self.assertEqual(seen,{'brute','swarm','trickster','gunner'})

    def test_regular_traffic_is_not_cleared_or_paused_by_event(self):
        game=empty()
        wave=Wave(30,[Block(.6,.4)])
        game.waves=[wave]
        game.spawn_in=0
        game.invulnerable=10
        game.begin_special('gunner')
        self.assertIn(wave,game.waves)
        game.update(.2)
        self.assertEqual(game.spawned,0)
        game.update(1.1)
        self.assertGreater(game.spawned,0)
        self.assertLess(wave.z,30)

    def test_enemy_attack_reduces_traffic_in_every_difficulty(self):
        for mode in MODES:
            baseline,attack=empty(mode),empty(mode)
            baseline.spawn_in=attack.spawn_in=0
            attack.begin_special('trickster')
            baseline.invulnerable=attack.invulnerable=10
            baseline.update(4)
            attack.update(4)
            self.assertLess(attack.spawned,baseline.spawned,(mode,attack.spawned,baseline.spawned))

    def test_extreme_overlaps_extra_event_while_normal_does_not(self):
        normal=empty()
        normal.begin_special('gunner')
        self.assertFalse(normal.begin_special('meteor'))
        hard=empty('hard')
        hard.invulnerable=10
        hard.begin_special('gunner')
        hard.update(1.6)
        self.assertEqual({e.kind for e in hard.encounters},{'gunner','rush'})
        self.assertFalse(hard.begin_special('meteor'))
        brute=empty('hard')
        brute.invulnerable=10
        brute.begin_special('brute')
        self.assertFalse(brute.begin_special('swarm'))
        brute.update(1.6)
        self.assertEqual({e.kind for e in brute.encounters},{'brute','rush'})

    def test_gunner_keeps_wider_routes_in_existing_and_new_traffic(self):
        game=empty()
        wall=Wave(opening=(0,0,.63,.60),kind='moving')
        laser=Wave(kind='laser')
        grid=Wave(kind='grid')
        game.waves=[wall,laser,grid]
        self.assertEqual(len(laser.geometry()),2)
        self.assertEqual(len(grid.geometry()),3)
        game.begin_special('gunner')
        self.assertAlmostEqual(wall.opening[2],.75)
        self.assertEqual(len(laser.geometry()),1)
        self.assertEqual(len(grid.geometry()),2)
        game.spawned=4
        game.spawn()
        self.assertEqual(game.waves[-1].kind,'ring')
        self.assertAlmostEqual(game.waves[-1].opening[2],.98)
        game.ease_for_encounter(wall)
        self.assertAlmostEqual(wall.opening[2],.75)

    def test_brute_locks_a_charge_and_approaches(self):
        game=empty()
        game.invulnerable=10
        game.begin_special('brute')
        game.update(.4)
        actor=game.actors[0]
        self.assertEqual(actor.variant,'brute')
        self.assertGreater(actor.size,.6)
        before=actor.z
        game.update(.2)
        self.assertLess(actor.z,before)

    def test_swarm_has_multiple_separate_lanes(self):
        game=empty()
        game.invulnerable=10
        game.begin_special('swarm')
        game.update(2.1)
        actors=[a for a in game.actors if a.variant=='plain']
        self.assertEqual(len(actors),2)
        self.assertEqual(len({a.lane for a in actors}),2)

    def test_charge_and_swarm_counts_and_simultaneous_enemies_are_limited(self):
        for mode in MODES:
            for kind in ('brute','swarm','trickster'):
                game=empty(mode)
                game.invulnerable=10
                game.begin_special(kind)
                event=game.encounters[0]
                peak=0
                for _ in range(185):
                    game.update(.025)
                    peak=max(peak,len(game.actors))
                self.assertLessEqual(peak,1 if mode=='easy' else 2,(mode,kind,peak))
                if kind=='brute':
                    self.assertEqual(event.spawned,2 if mode=='hard' else 1)
                if kind=='swarm':
                    self.assertEqual(event.spawned,1 if mode=='easy' else 2)

    def test_trickster_reverses_direction(self):
        actor=Actor('trickster','trickster',1.1,0,duration=3.5,lane=0)
        actor.advance(.6)
        x1=actor.x
        actor.advance(.5)
        x2=actor.x
        actor.advance(.5)
        x3=actor.x
        self.assertLess(x2,x1)
        self.assertGreater(x3,x2)
        self.assertEqual(actor.variant,'trickster')

    def test_gunner_emits_different_bullet_patterns(self):
        game=empty()
        game.invulnerable=10
        game.begin_special('gunner')
        game.update(2.6)
        event=game.encounters[0]
        self.assertEqual(event.shots,3)
        self.assertGreater(len(game.bullets),0)
        self.assertEqual({b.color for b in game.bullets},{'orange','pink'})
        self.assertTrue(any(b.vx<0 for b in game.bullets))
        self.assertTrue(any(b.vx>0 for b in game.bullets))

    def test_three_bursts_have_reduced_counts_and_no_aimed_center_shot(self):
        for mode,counts in [('easy',(4,4,6)),('normal',(8,6,8)),('hard',(12,10,10))]:
            game=empty(mode)
            game.begin_special('gunner')
            event=game.encounters[0]
            for pattern,count in enumerate(counts):
                game.bullets=[]
                game.emit_bullets(event)
                self.assertEqual(len(game.bullets),count,(mode,pattern))
                if pattern==0:
                    for bullet in game.bullets:
                        aimed=math.atan2(game.y-bullet.y,game.x-bullet.x)
                        fired=math.atan2(bullet.vy,bullet.vx)
                        difference=abs((fired-aimed+math.pi)%math.tau-math.pi)
                        self.assertGreater(difference,.29)

    def test_grazing_bullet_is_safe_but_hull_contact_hits(self):
        game=empty()
        game.bullets=[Bullet(.075,0,0,0,age=.2)]
        game.update(.05)
        self.assertEqual(game.lives,3)
        game.bullets=[Bullet(.03,0,0,0,age=.2)]
        game.update(.05)
        self.assertEqual(game.lives,2)

    def test_muzzle_grace_prevents_instant_contact_damage(self):
        game=empty()
        game.bullets=[Bullet(0,0,0,0)]
        game.update(.1)
        self.assertEqual(game.lives,3)
        game.update(.075)
        self.assertEqual(game.lives,2)

    def test_fast_bullet_hit_and_shield_consumption(self):
        game=empty()
        game.bullets=[Bullet(-.5,0,3.5,0)]
        game.update(.2)
        self.assertEqual(game.lives,2)
        self.assertFalse(game.bullets)
        game.invulnerable=0
        game.activate_shield()
        game.bullets=[Bullet(.3,0,-2,0)]
        game.update(.2)
        self.assertEqual(game.lives,2)
        self.assertFalse(game.bullets)

    def test_bullets_expire_and_remain_bounded(self):
        game=empty()
        game.bullets=[Bullet(1.3,1,2,0),Bullet(.8,.8,0,0,age=4.19)]
        game.update(.2)
        self.assertFalse(game.bullets)

    def test_full_intense_round_still_stops_at_thirty_seconds(self):
        for mode in MODES:
            game=Round(mode,random.Random(8))
            game.lives=2
            game.invulnerable=90
            game.update(40)
            self.assertTrue(game.ended)
            self.assertEqual(game.elapsed,30)
            self.assertLessEqual(len(game.bullets),320)
            self.assertEqual(len([kind for kind in game.special_history if kind!='rush']),3)


class Persistence(unittest.TestCase):
    def setUp(self):
        self.folder=ROOT/'previews'/'test-data'/uuid.uuid4().hex
        self.storage=Storage(self.folder)

    def test_names_repeat_without_overwriting_other_rounds(self):
        game=empty('hard')
        game.update(10)
        self.storage.add('奶龙闪避王',game)
        self.storage.add('奶龙闪避王',game)
        fresh=Storage(self.folder)
        self.assertEqual(len(fresh.records),2)
        self.assertNotEqual(fresh.records[0]['id'],fresh.records[1]['id'])
        self.assertEqual(fresh.settings['last_name'],'奶龙闪避王')

    def test_top_ten_modes_and_all_records_retained(self):
        game=empty('easy')
        for i in range(14):
            game.bonus=i*20
            self.storage.add('玩家'+str(i),game)
        self.storage.add('极限玩家',empty('hard'))
        self.assertEqual(len(self.storage.records),15)
        self.assertEqual(len(self.storage.top('easy')),10)
        self.assertEqual(self.storage.top('easy')[0]['score'],260)
        self.assertEqual(len(self.storage.top('hard')),1)

    def test_corrupt_file_is_backed_up(self):
        (self.folder/'scores.json').write_text('{broken',encoding='utf-8')
        self.assertFalse(Storage(self.folder).records)
        self.assertEqual(len(list(self.folder.glob('scores-backup-*.json'))),1)


class Interface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=App(Storage(ROOT/'previews'/'test-data'/uuid.uuid4().hex))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def play(self):
        app=self.app
        app.mode='normal'
        app.control='mouse'
        app.start()
        app.update(3.01)
        app.game.spawn_in=999
        app.game.special_schedule=[]
        return app

    def test_countdown_excluded_and_full_round_name_save_replay(self):
        app=self.play()
        self.assertEqual(app.game.remaining,30)
        app.game.lives=2
        app.update(30)
        self.assertEqual(app.state,'result')
        count=len(app.storage.records)
        app.name=''
        app.handle(pygame.event.Event(pygame.TEXTINPUT,text='弹幕大师'))
        app.handle(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN,mod=0))
        self.assertTrue(app.saved)
        app.submit()
        self.assertEqual(len(app.storage.records),count+1)
        app.start()
        self.assertFalse(app.saved)
        self.assertEqual(app.game.remaining,30)

    def test_ime_enter_guard_and_m_letter(self):
        app=self.play()
        app.game.lives=2
        app.update(30)
        app.name=''
        app.handle(pygame.event.Event(pygame.TEXTEDITING,text='long',start=0,length=4))
        app.handle(pygame.event.Event(pygame.TEXTINPUT,text='龙'))
        app.handle(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN,mod=0))
        self.assertFalse(app.saved)
        muted=app.audio.muted
        app.handle(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_m,mod=0))
        app.handle(pygame.event.Event(pygame.TEXTINPUT,text='m'))
        self.assertEqual(app.audio.muted,muted)
        self.assertEqual(app.name,'龙m')
        app.update(.3)
        app.submit()
        self.assertTrue(app.saved)

    def test_hidden_route_pause_and_single_final_name_save(self):
        app=self.play()
        count=len(app.storage.records)
        app.game.invulnerable=100
        app.update(30)
        self.assertEqual(app.state,'playing')
        self.assertTrue(app.game.hidden_unlocked)
        self.assertEqual(app.game.remaining,15)
        self.assertEqual(len(app.storage.records),count)
        app.draw()
        app.pause()
        app.update(5)
        self.assertEqual(app.game.remaining,15)
        app.resume()
        app.update(1)
        self.assertTrue(any(a.variant=='gunner' for a in app.game.actors))
        app.draw()
        app.update(14)
        self.assertEqual(app.state,'result')
        self.assertTrue(app.game.hidden_completed)
        app.name='隐藏航线王'
        app.submit()
        app.submit()
        self.assertEqual(len(app.storage.records),count+1)
        record=Storage(app.storage.folder).records[-1]
        self.assertEqual(record['name'],'隐藏航线王')
        self.assertEqual(record['mode'],'normal')
        self.assertEqual(record['seconds'],45)
        self.assertTrue(record['hidden_unlocked'])
        self.assertTrue(record['hidden_completed'])
        app.draw()
        app.start()
        self.assertFalse(app.game.hidden_unlocked)
        self.assertEqual(app.game.remaining,30)
        self.assertEqual(app.game.config,MODES['normal'])

    def test_pause_freezes_bullets_actors_and_round_timer(self):
        app=self.play()
        app.game.begin_special('gunner')
        app.game.invulnerable=10
        app.update(1)
        self.assertTrue(app.game.bullets)
        bullet=app.game.bullets[0]
        values=(bullet.x,bullet.y,app.game.actors[0].age,app.game.elapsed)
        app.handle(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        app.update(10)
        self.assertEqual(values,(bullet.x,bullet.y,app.game.actors[0].age,app.game.elapsed))
        app.resume()
        app.update(.1)
        self.assertGreater(app.game.elapsed,values[3])

    def test_no_shield_instruction_popup_when_unavailable(self):
        app=self.play()
        app.game.charge=0
        app.toast_left=0
        app.handle(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_SPACE,mod=0))
        self.assertEqual(app.toast_left,0)

    def test_all_screens_audio_and_resizing(self):
        app=self.app
        self.assertEqual(len(app.audio.sounds),10)
        self.assertTrue(all(s.get_length()>0 for s in app.audio.sounds.values()))
        for state in ('menu','countdown','playing','paused','result','leaderboard'):
            app.state=state
            app.countdown=2
            app.draw()
        app.screen=pygame.display.set_mode((960,630))
        self.assertEqual(app.pos((480,315)),(640,420))
        app.screen=pygame.display.set_mode((1280,840))

    def test_four_transparent_character_assets_have_clear_borders(self):
        contents=[]
        for kind in ('brute','plain','trickster','gunner'):
            image=pygame.image.load(str(ROOT/'assets'/'mascot'/'combat'/(kind+'.png')))
            self.assertEqual(image.get_size(),(400,400))
            self.assertTrue(image.get_masks()[3])
            for point in ((0,0),(399,0),(0,399),(399,399)):
                self.assertEqual(image.get_at(point).a,0)
            contents.append(pygame.image.tobytes(image,'RGBA'))
        self.assertEqual(len(set(contents)),4)


def snapshot_and_benchmark():
    app=App(Storage(ROOT/'previews'/'sample-data'))
    app.state='menu'
    app.t=13
    app.scene_time=8.4
    app.draw()
    pygame.image.save(app.canvas,str(ROOT/'previews'/'menu.png'))
    for kind,age in [('brute',1.22),('swarm',1.65),('trickster',1.55),('gunner',2.6),('meteor',1.55),('rush',1.3)]:
        app.game=Round('hard',random.Random(8),events_enabled=False)
        app.game.elapsed=13
        app.game.distance=320
        app.game.invulnerable=99
        app.game.begin_special(kind)
        app.game.target=(.48,.55)
        app.game.update(age)
        app.game.invulnerable=0
        app.game.lives=MAX_LIVES
        app.state='playing'
        app.scene_time=app.game.elapsed
        app.draw()
        pygame.image.save(app.canvas,str(ROOT/'previews'/('combat-'+kind+'.png')))
    for index,kind in enumerate(PATTERNS):
        game=empty()
        game.spawned=index
        game.spawn()
        game.waves[0].z=5.8
        game.waves[0].age=1.4
        game.elapsed=17
        app.game=game
        app.state='playing'
        app.scene_time=17
        app.draw()
        pygame.image.save(app.canvas,str(ROOT/'previews'/('obstacle-'+kind+'.png')))
    app.game=empty()
    app.game.invulnerable=100
    app.game.update(30)
    app.state='playing'
    app.scene_time=30
    app.draw()
    pygame.image.save(app.canvas,str(ROOT/'previews'/'hidden-unlock.png'))
    app.game.target=(.48,.55)
    app.game.update(3)
    app.game.invulnerable=0
    app.scene_time=33
    app.draw()
    pygame.image.save(app.canvas,str(ROOT/'previews'/'hidden-playing.png'))
    app.game=Round('hard',random.Random(22),events_enabled=False)
    app.game.elapsed=15
    app.game.distance=350
    app.game.invulnerable=99
    app.game.begin_special('gunner')
    app.game.update(2.6)
    app.game.invulnerable=0
    app.game.lives=MAX_LIVES
    app.state='playing'
    durations=[]
    for i in range(90):
        app.scene_time+=1/60
        start=time.perf_counter()
        app.draw()
        durations.append((time.perf_counter()-start)*1000)
    pygame.image.save(app.canvas,str(ROOT/'previews'/'playing.png'))
    result={'median_frame_ms':round(statistics.median(durations),2),
            'p95_frame_ms':round(sorted(durations)[85],2),'bullets':len(app.game.bullets),
            'obstacle_waves':len(app.game.waves),'actors':len(app.game.actors),
            'resolution':[1280,840],'frames':90,'video_driver':'dummy'}
    app.game.elapsed=30
    app.game.reason='穿越完成'
    app.name='弹幕大师'
    app.saved=False
    app.state='result'
    app.draw()
    pygame.image.save(app.canvas,str(ROOT/'previews'/'result.png'))
    pygame.quit()
    return result


def run():
    scores=ROOT/'data'/'scores.json'
    before=hashlib.sha256(scores.read_bytes()).hexdigest() if scores.exists() else None
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors)}
    if result.wasSuccessful():
        report['combat_render_benchmark']=snapshot_and_benchmark()
    after=hashlib.sha256(scores.read_bytes()).hexdigest() if scores.exists() else None
    report['player_scores_unchanged']=before==after
    (ROOT/'previews'/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    return 0 if result.wasSuccessful() and before==after else 1


if __name__=='__main__':
    sys.exit(run())
