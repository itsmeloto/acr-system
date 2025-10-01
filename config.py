BOT_PREFIX = ":"


ACCESS_LEVELS = {
    1: [1396916919562407997], # Moderation team
    2: [1396916564540002325], # Admin team
    3: [1396914257357967380], # Head Team
    4: [1396913496213553203, 1396918162083282977], # Management team, Development team
    5: [1416837436432187562, 1396910973712863304]  # Lead Team, Ownership team (Ownership has all access)
}

# Promotion permission rules by Team Role ID
# Each key is an invoker's Team Role ID; the value is a set of allowed TARGET team role IDs.
# Ownership can promote any team (including Lead). Developers cannot promote/demote at all (handled in code).
TEAM_ROLE_IDS = {
    "moderation": 1396916919562407997,
    "admin": 1396916564540002325,
    "head": 1396914257357967380,
    "management": 1396913496213553203,
    "development": 1396918162083282977,
    "lead": 1416837436432187562,
    "ownership": 1396910973712863304
}

PROMOTION_RULES = {
    TEAM_ROLE_IDS["admin"]: {TEAM_ROLE_IDS["moderation"]},
    TEAM_ROLE_IDS["head"]: {TEAM_ROLE_IDS["moderation"], TEAM_ROLE_IDS["admin"]},
    TEAM_ROLE_IDS["management"]: {TEAM_ROLE_IDS["moderation"], TEAM_ROLE_IDS["admin"], TEAM_ROLE_IDS["head"], TEAM_ROLE_IDS["development"]},
    # Lead can promote everything except Lead itself; handled in code by excluding lead
    TEAM_ROLE_IDS["lead"]: {TEAM_ROLE_IDS["moderation"], TEAM_ROLE_IDS["admin"], TEAM_ROLE_IDS["head"], TEAM_ROLE_IDS["development"], TEAM_ROLE_IDS["management"]},
    # Ownership handled in code as full allow
}

# Channel Variables: Map short names to Discord Channel IDs
CHANNEL_VARS = {
    "ann-main": 1397192753535909898, # Main Announcement channel
    "ann-sub": 1397194885282533517, # Secondary Announcement channel
    "ann-staff": 1397221732393156748, # Staff Announcement channel
    "ann-tester": 1400445306004312145, # Testers Announcement channel
    "ann-trello": 1419991143034257439, # Trello Announcement channel
    "updates": 1397197916652703926, # Updates Channel
    "sneak-peaks": 1397198608037580902, # Sneak Peaks channel
    "log-channel": 1422486586414600212, # Bot action log channel
    "promotion-channel": 1397222014175023236 # Channel for promotion messages
}

# Appeal System Configuration
APPEAL_SERVER_INVITE_LINK = "https://discord.gg/FA2235sd"
MAIN_SERVER_INVITE_LINK = "https://discord.gg/cardrealms"
APPEAL_LOG_CHANNEL = 1422536527614967830 # Channel on main server where appeals are posted for staff review
APPEAL_CHANNEL_ID = 1422536278200549448 # Appeal command allowed only in this channel (Appeal Server)
MAIN_GUILD_ID = 1396909186868183181 # Set this to your main server Guild ID for unban to work from appeal reviews

# Rank System Configuration
# Each rank has 3 roles: Permission Role, Display Role, Team Role
RANKS = {
    "Content Creator": {
        "perm_role": 1422919230889656432,
        "display_role": 1399814306513686699,
        "team_role": 1422919230889656432
    },
    "Staff": {
        "perm_role": 1396917926715457666,
        "display_role": 1396964353298927706,
        "team_role": 1396964353298927706
    },
    "Senior Hoster": {
        "perm_role": 1422919230889656432,
        "display_role": 1417093531163430983,
        "team_role": 1400048117633777705
    },
    "Giveaway Hoster": {
        "perm_role": 1422919230889656432,
        "display_role": 1400048528247623720,
        "team_role": 1400048117633777705
    },
    "Event Hoster": {
        "perm_role": 1422919230889656432,
        "display_role": 1400048446701961350,
        "team_role": 1400048117633777705
    },
    "Trial Developer": {
        "perm_role": 1396917926715457666,
        "display_role": 1397006193880338554,
        "team_role": 1396917869333450753
    },
    "Senior Helper": {
        "perm_role": 1396917926715457666,
        "display_role": 1397149946179751979,
        "team_role": 1417099271240548456
    },
    "Helper": {
        "perm_role": 1396917926715457666,
        "display_role": 1397149809961467944,
        "team_role": 1417099271240548456
    },
    "Trial Helper": {
        "display_role": 1397006250998501436,
        "team_role": 1417099271240548456
    },
    "Trial Staff": {
        "perm_role": 1396917926715457666,
        "display_role": 1396918081971945483,
        "team_role": 1396917869333450753
    },
    "Moderator": {
        "perm_role": 1396917645818859610,
        "display_role": 1396917738429087744,
        "team_role": 1396916919562407997
    },
    "Senior Moderator": {
        "perm_role": 1396917645818859610,
        "display_role": 1396917675237572679,
        "team_role": 1396916919562407997
    },
    "Administrator": {
        "perm_role": 1396916841837756598,
        "display_role": 1396917138702205078,
        "team_role": 1396916564540002325
    },
    "Senior Administrator": {
        "perm_role": 1396916841837756598,
        "display_role": 1396916870329929758,
        "team_role": 1396916564540002325
    },
    "Junior Administrator": {
        "perm_role": 1396916841837756598,
        "display_role": 1396917247116709898,
        "team_role": 1396916564540002325
    },
    "Head Administrator": {
        "perm_role": 1396914588204662907,
        "display_role": 1396915927009857596,
        "team_role": 1396914257357967380
    },
    "Head Moderator": {
        "perm_role": 1396914588204662907,
        "display_role": 1396916212721651963,
        "team_role": 1396914257357967380
    },
    "Head Helper": {
        "perm_role": 1396914588204662907,
        "display_role": 1396916319512690688,
        "team_role": 1396914257357967380
    },
    "Staff Supervisor": {
        "perm_role": 1396914588204662907,
        "display_role": 1400172042401222828,
        "team_role": 1396914257357967380
    },
    "Developer": {
        "perm_role": 1396918303531995299,
        "display_role": 1396918466077790351,
        "team_role": 1396918162083282977
    },
    "Senior Developer": {
        "perm_role": 1396918303531995299,
        "display_role": 1396918399812108378,
        "team_role": 1396918162083282977
    },
    "Server Manager": {
        "perm_role": 1396913937370320896,
        "display_role": 1396913993561669662,
        "team_role": 1396913496213553203
    },
    "Community Manager": {
        "perm_role": 1396913937370320896,
        "display_role": 1396914064063729787,
        "team_role": 1396913496213553203
    },
    "Project Lead": {
        "perm_role": 1396913132055826483,
        "display_role": 1396912477358395472,
        "team_role": 1416837436432187562
    },
    "Server Lead": {
        "perm_role": 1396913132055826483,
        "display_role": 1396913401304715435,
        "team_role": 1416837436432187562
    },
    "Team Lead": {
        "perm_role": 1396913132055826483,
        "display_role": 1396913233516036271,
        "team_role": 1416837436432187562
    },
    "Co-Owner": {
        "perm_role": 1396909732144353422,
        "display_role": 1396912411566407861,
        "team_role": 1396910973712863304
    },
    "Owner": {
        "perm_role": 1396909732144353422,
        "display_role": 1396912191621435545,
        "team_role": 1396910973712863304
    },
    "Founder": {
        "perm_role": 1396912288983945378,
        "display_role": 1396910827046441121,
        "team_role": 1396910973712863304
    }
}

# Customize Bot Profile
BOT_PFP_URL = ""
BOT_BIO = "ACR - System"

# Optional visuals for the Panel/Dashboard
PANEL_BANNER_URL = ""
PANEL_LED_GIF_URL = ""

# Optional: If set, panel will mention Sapphire when sending s!lock/s!unlock
SAPPHIRE_BOT_ID = 678344927997853742

