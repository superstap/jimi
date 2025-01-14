import jimi

#Will be deprecated in v4.0
config = jimi.config

class _settings(jimi.db._document):
	name = str()
	values = dict()
	
	_dbCollection = jimi.db.db["settings"]

	def new(self,name,values):
		self.name = name
		self.values = values
		self.acl = { "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] } 
		return super(_settings, self).new()

def getSetting(name,settingName):
	return jimi.cache.globalCache.get("settingsCache","{0}:{1}".format(name,settingName),getSettingValue,name,settingName)

def getSettingValue(uid,sessionData,name,settingName):
	try:
		setting = _settings(False).query(sessionData,query={ "name" : name })["results"][0]
		if settingName:
			return setting["values"][settingName]
		return setting["values"]
	except:
		return None

try:
	cpuSaver = getSetting("cpuSaver",None)
except:
	cpuSaver = { "enabled" : True, "loopT" : 0.01, "loopL" : 100 }
