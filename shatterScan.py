import re
from datetime import datetime
import sqlite3

path = r"C:\Users\<yourUsernameHere>\AppData\Local\WorldExplorers\Saved\Logs\WorldExplorers.log"

db = sqlite3.connect('shatter.db')

db.execute("""DROP TABLE IF EXISTS damage;""")
db.execute("""DROP TABLE IF EXISTS fights;""")
db.execute("""DROP TABLE IF EXISTS rewards;""")
db.execute("""CREATE TABLE IF NOT EXISTS damage (fightID int, character TEXT, damage INT, NullAttacks INT, attacks INT);""")
db.execute("""CREATE TABLE IF NOT EXISTS fights (user TEXT, fightID int, levelID TEXT, 'timestamp' timestamp, duration INT, victory BOOLEAN);""")
db.execute("""CREATE TABLE IF NOT EXISTS rewards (fightID int, rewardName TEXT, rewardCount INT);""")

with open(path) as file:
	fileLines = file.readlines()

latestRow = db.execute("""SELECT MAX(fightID) FROM damage;""")
fightNum = (latestRow.fetchone()[0] or 0)

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
		damage_log = {}
		for idx2, l in enumerate(fileLines[idx:]):
			# if "LogWExp: UWExpGameOverWidget - Finalize Successful" in l:
			if "LogWExp: UWExpGameOverWidget - Finalize Successful" in l:
				fight = fileLines[idx:idx + idx2]
				# print(l, end='')
				break
	if fight:
		boardPopulated = False
		rewardsRE = r'LogProfileSys: MCP-Profile: .+? gained (\d+?) x (.*)'
		damageRE = r'^WEXCombat: Turn (\d+?) \(Damage\) "(.+?)" aka (.+?)  Received ([\d|,|\.]+?) of ([\d|,|\.]+?) (\w+?) damage from (.+?)\.'
		fightRewards = {}
		fightStartTime = datetime.strptime(fight[0][1:24], '%Y.%m.%d-%H.%M.%S:%f')
		fightEndTime = datetime.strptime(fight[-1][1:24], '%Y.%m.%d-%H.%M.%S:%f')
		win = False
		lvlName = None
		party = {}
		enemies = {}
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

			if not fightStartTime:
				fightStartTime = datetime.strptime(evtTime, '%Y.%m.%d-%H.%M.%S:%f')

			dmgRE = re.match(damageRE, msg)
			if dmgRE:
				turn = dmgRE.group(1)
				victim = dmgRE.group(2)
				victimID = dmgRE.group(3)
				dmgTaken = dmgRE.group(4)
				dmgType = dmgRE.group(6)
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
		# print(fightStartTime, lvlName)
		# print("Fight:", fightNum)
		# print("Level:", lvlName)
		# print("Start Time:", fightStartTime)
		for i in party:
			if party[i].get('Damage'):
				db.execute("""INSERT INTO damage (fightID, character, damage, NullAttacks, attacks)
					VALUES ($1, $2, $3, $4, $5)""", (fightNum, party[i]['Name'], party[i]['Damage'], party[i]['NullAtks'], party[i]['Attacks']))
				# print('', party[i]['Name'], party[i]['Damage'])
		# print(party)
		# print()
		# print(fightRewards)
		# print(user)

		db.execute("""INSERT INTO fights (user, fightID, levelID, 'timestamp', duration, victory)
			VALUES ($1, $2, $3, $4, $5, $6)
			""", (user, fightNum, lvlName, fightStartTime, (fightEndTime - fightStartTime).total_seconds(), win))

		for reward in fightRewards:
			db.execute("""INSERT INTO rewards (fightID, rewardName, rewardCount)
				VALUES ($1, $2, $3)
				""", (fightNum, reward, fightRewards[reward]))
		# 	print(reward, fightRewards[reward])
		# print()

		db.commit()
""" Print total rewards from session """
# for reward in totalRewards:
# 	print(reward.split(':')[1], totalRewards[reward])
