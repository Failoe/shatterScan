import re
from datetime import datetime
import sqlite3
from os import listdir
from os.path import isfile, join
# 11-7, 9-8, 21-3,
computerUserName = '<yourusernamehere>'
logfiles = [f for f in listdir(f'C:\\Users\\{computerUserName}\\AppData\\Local\\WorldExplorers\\Saved\\Logs') if (isfile(join(f'C:\\Users\\{computerUserName}\\AppData\\Local\\WorldExplorers\\Saved\\Logs', f)) and f.startswith('WorldExplorers'))]

def shatterScan(filename='WorldExplorers.log'):
	db = sqlite3.connect('shatter.db')

	path = f'C:\\Users\\{computerUserName}\\AppData\\Local\\WorldExplorers\\Saved\\Logs\\{filename}'
	# db.execute("""DROP TABLE IF EXISTS damage;""")
	# db.execute("""DROP TABLE IF EXISTS fights;""")
	# db.execute("""DROP TABLE IF EXISTS rewards;""")
	db.execute("""CREATE TABLE IF NOT EXISTS damage (fightID int, character TEXT, damage INT, NullAttacks INT, attacks INT);""")
	db.execute("""CREATE TABLE IF NOT EXISTS fights (user TEXT, fightID int, levelID TEXT, 'timestamp' timestamp, duration INT, victory BOOLEAN, accountXP INT, auto BOOLEAN);""")
	db.execute("""CREATE TABLE IF NOT EXISTS rewards (fightID int, rewardName TEXT, rewardCount INT);""")

	with open(path) as file:
		fileLines = file.readlines()

	latestRow = db.execute("""SELECT MAX(fightID) FROM damage;""")
	fightNum = (latestRow.fetchone()[0] or 0)
	fightsLogged = 0
	totalRewards = {}
	user = None
	for idx, line in enumerate(fileLines):
		if not user:
			username = re.match(r'LogInit.+?-epicusername=(.+?) ', line)
			if username:
				user = username.group(1)
		fight = []
		if 'LogProfileSys: MCP-Profile: Command InitializeLevel queued to send' in line:
			# print(idx)
			for idx2, l in enumerate(fileLines[idx:]):
				# if "LogWExp: UWExpGameOverWidget - Finalize Successful" in l:
				if "LogWExp: UWExpGameOverWidget - Finalize Successful" in l:
					fight = fileLines[idx:idx + idx2]
					# print(l, end='')
					break
		if fight:
			fightNum += 1
			boardPopulated = False
			rewardsRE = r'LogProfileSys: MCP-Profile: .+? gained (\d+?) x (.*)'
			damageRE = r'^WEXCombat: Turn (\d+?) \(Damage\) "(.+?)" aka (.+?)  Received ([\d|,|\.]+?) of ([\d|,|\.]+?) (\w+?) damage from (.+?)\.'
			fightRewards = {}
			fightStartTime = datetime.strptime(fight[0][1:20], '%Y.%m.%d-%H.%M.%S')

			""" If we find that we have an entry for this fight we will skip adding it. """
			dupeCheck = db.execute(
				"""SELECT * FROM fights WHERE user = $1 AND fights.timestamp = $2;""",
				(user, fightStartTime))

			if dupeCheck.fetchone():
				continue

			fightEndTime = datetime.strptime(fight[-1][1:20], '%Y.%m.%d-%H.%M.%S')
			win = False
			lvlName = None
			party = {}
			enemies = {}
			accountXP = 0
			totalTurns = None
			autoTurns = None
			for fIdx, f in enumerate(fight):
				evtTime = f[1:24]
				msg = f[30:]
				if party == {} and msg == 'LogWExp: ... Finished populating game board!\n':
					boardPopulated = True
					continue

				if boardPopulated and msg.startswith('WEXCombat: COMBATANT-SPAWNED '):
					character = msg[30:].split('" aka ')
					party[character[1].strip()] = {'Name': character[0], 'Damage': 0, 'NullAtks': 0, 'Attacks': 0}
					continue

				if boardPopulated and msg.startswith('WEXCombat: Turn 1 '):
					boardPopulated = False
					continue

				if msg.startswith('LogWExp: Display: Spawning Level: '):
					lvlName = msg[34:].strip()
					continue

				if msg.startswith('LogWExp: ACCOUNT ITEM PICKUP - StandIn:AccountXp x '):
					xp = int(msg[51:].replace(',', ''))
					accountXP += xp

				dmgRE = re.match(damageRE, msg)
				if dmgRE:
					# turn = dmgRE.group(1)
					# victim = dmgRE.group(2)
					victimID = dmgRE.group(3)
					dmgTaken = dmgRE.group(4)
					# dmgType = dmgRE.group(6)
					dmgInstigator = dmgRE.group(7)
					if not party.get(victimID):
						for dID, v in party.items():
							if v['Name'] in dmgInstigator:
								"""Find fully Blocked Attacks"""
								if int(dmgRE.group(4).replace(',', '')) == 1:
									party[dID]['NullAtks'] = party[dID]['NullAtks'] + 1
								party[dID]['Damage'] = int(party[dID].get('Damage') or 0) + int(dmgTaken.replace(',', ''))
								party[dID]['Attacks'] = party[dID]['Attacks'] + 1

				"""Rewards Calculation"""
				s = re.search(rewardsRE, msg)
				if s:
					rewardAmount = int(s.group(1))
					rewardType = s.group(2)
					if rewardType.split(':')[0] not in ["Energy", "Level"]:
						fightRewards[rewardType] = (fightRewards.get(rewardType) or 0) + rewardAmount
						totalRewards[rewardType] = (totalRewards.get(rewardType) or 0) + rewardAmount
				if "WEXCombat: Oh yea, you're such a winner!" in msg:
					win = True

				if msg.startswith('WEXAnalytics: Warning:    Stat_InteractiveTurns = '):
					totalTurns = int(msg[50:].replace(',', ''))
				if msg.startswith('WEXAnalytics: Warning:    Stat_AutoplayTurns = '):
					autoTurns = int(msg[47:].replace(',', ''))

			# print(f'T: {totalTurns}, A: {autoTurns}')
			""" Insert damage data """
			for i in party:
				if party[i].get('Damage'):
					db.execute("""INSERT INTO damage (fightID, character, damage, NullAttacks, attacks)
						VALUES ($1, $2, $3, $4, $5)""", (fightNum, party[i]['Name'], party[i]['Damage'], party[i]['NullAtks'], party[i]['Attacks']))

			""" Insert fight metadata """
			db.execute("""INSERT INTO fights (user, fightID, levelID, 'timestamp', duration, victory, accountXP, auto)
				VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
				""", (user, fightNum, lvlName, fightStartTime, (fightEndTime - fightStartTime).total_seconds(), win, accountXP, (totalTurns and autoTurns and totalTurns - autoTurns < 5) or 0))

			""" Insert reward data """
			for reward in fightRewards:
				db.execute("""INSERT INTO rewards (fightID, rewardName, rewardCount)
					VALUES ($1, $2, $3)
					""", (fightNum, reward, fightRewards[reward]))
			# 	print(reward, fightRewards[reward])
			# print()
			fightsLogged += 1
			db.commit()
	print(f'Fights Logged: {fightsLogged}')
	""" Print total rewards from session """
	# for reward in totalRewards:
	# 	print(reward.split(':')[1], totalRewards[reward])


for lf in logfiles:
	shatterScan(lf)

shatterScan()
