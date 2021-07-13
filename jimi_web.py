from flask import Flask, request, render_template, make_response, redirect, send_file, flash, send_from_directory
from werkzeug.utils import secure_filename
import _thread
import time
import json
import requests
import uuid
from pathlib import Path
import re
import subprocess
import os
from operator import itemgetter
import logging

logging.basicConfig(level=logging.ERROR)

# Setup and define API ( required before other modules )
from core import api, settings
apiSettings = settings.config["api"]["web"]

api.createServer("jimi_web",template_folder=str(Path("web","build")),static_folder=str(Path("web","build","static")))

import jimi

from web import ui

# Other pages
from web import modelEditor, conductEditor, codify

# Add plugin blueprints
pluginPages = []
plugins = os.listdir("plugins")
for plugin in plugins:
	if os.path.isfile(Path("plugins/{0}/web/{0}.py".format(plugin))):
		mod = __import__("plugins.{0}.web.{0}".format(plugin), fromlist=["pluginPages"])
		jimi.api.webServer.register_blueprint(mod.pluginPages,url_prefix='/plugin/{0}'.format(plugin))
		hidden = False
		try:
			hidden = mod.pluginPagesHidden
		except:
			pass
		if not hidden:
			pluginPages.append(plugin)
jimi.plugin.loadedPluginPages = pluginPages

# Installing
if "webui" not in jimi.db.list_collection_names():
	if jimi.logging.debugEnabled:
		jimi.logging.debug("DB Collection webui Not Found : Creating...")
	jimi.model.registerModel("flowData","_flowData","_document","core.models.webui")

@jimi.api.webServer.route("/")
def indexPage():
	return jimi.api.make_response(redirect("/status/"))

@jimi.api.webServer.route("/login/")
def loginPage():
	return render_template("login.html")

@jimi.api.webServer.route("/debugFlow/")
def debugFlowPage():
	return render_template("debugFlowEditor.html",CSRF=jimi.api.g.sessionData["CSRF"])

@jimi.api.webServer.route("/administration/", methods=["GET"])
@jimi.auth.adminEndpoint
def administrationPage():
	clusterMembers = jimi.cluster._clusterMember().query()["results"]
	return render_template("administration.html",CSRF=jimi.api.g.sessionData["CSRF"],clusterMembers=clusterMembers)

# Should be migrated into plugins.py
@jimi.api.webServer.route(jimi.api.base+"plugins/")
def loadPluginPages():
	userPlugins = []
	userModels = jimi.plugin._plugin().getAsClass(sessionData=jimi.api.g.sessionData,query={ "name" : { "$in" : pluginPages } },sort=[("name", 1)])
	for userModel in userModels:
		if userModel.name in pluginPages:
			userPlugins.append({ "id" : userModel._id, "name" : userModel.name})
	return { "results"  : userPlugins }, 200

# Should be migrated into models/conduct.py
@jimi.api.webServer.route(jimi.api.base+"conducts/")
def loadConducts():
	return { "results" : jimi.conduct._conduct().query(sessionData=jimi.api.g.sessionData,query={ "name" : { "$exists" : True } },sort=[( "name", 1 )])["results"] }, 200

# Should be migrated into workers.py
@jimi.api.webServer.route(jimi.api.base+"/workers/", methods=["GET"])
@jimi.auth.adminEndpoint
def workerPage():
	apiEndpoint = "workers/"
	servers = jimi.cluster.getAll()
	results = []
	for url in servers:
		response = jimi.helpers.apiCall("GET",apiEndpoint,token=jimi.api.g.sessionToken,overrideURL=url)
		responseJson = json.loads(response.text)
		if responseJson:
			for job in responseJson["results"]:
				job["server"] = url
				results.append(job)
	return { "results" : results }, 200

@jimi.api.webServer.route(jimi.api.base+"/workers/stats/", methods=["GET"])
@jimi.auth.adminEndpoint
def workerStatusPage():
	apiEndpoint = "workers/stats/"
	servers = jimi.cluster.getAll()
	results = []
	for url in servers:
		response = jimi.helpers.apiCall("GET",apiEndpoint,token=jimi.api.g.sessionToken,overrideURL=url)
		responseJson = json.loads(response.text)
		if responseJson:
			responseJson = responseJson["results"][0]
			responseJson["url"] = url
			results.append(responseJson)
	return { "results" : results }, 200

# Should be migrated into admin.py or cache.py
@jimi.api.webServer.route(jimi.api.base+"/clearCache/", methods=["GET"])
@jimi.auth.adminEndpoint
def clearCachePage():
	results = []
	apiEndpoint = "admin/clearCache/"
	servers = jimi.cluster.getAll()
	for url in servers:
		response = jimi.helpers.apiCall("GET",apiEndpoint,token=jimi.api.g.sessionToken,overrideURL=url)
		if response.status_code != 200:
			results.append({ "server" : url, "result" : False })
		else:
			results.append({ "server" : url, "result" : True, "results" : json.loads(response.text) })
	return { "results" : results }, 200

# Should be migrated into admin.py
@jimi.api.webServer.route(jimi.api.base+"/clearStartChecks/", methods=["GET"])
@jimi.auth.adminEndpoint
def clearStartChecksPage():
	apiEndpoint = "admin/clearStartChecks/"
	url = jimi.cluster.getMaster()
	response = jimi.helpers.apiCall("GET",apiEndpoint,token=jimi.api.g.sessionToken,overrideURL=url)
	if response.status_code != 200:
		return { "server" : url, "result" : False }, 403
	else:
		return { "server" : url, "result" : True }, 200

# @jimi.api.webServer.route("/login")
# def loginPage():
# 	return render_template("index.html")

@jimi.api.webServer.route("/conduct/PropertyTypes/", methods=["GET"])
def getConductPropertyTypes():
	result = []
	models = jimi.model._model().query(jimi.api.g.sessionData,query={ 
		"$and" : [ 
			{ 
				"$or" : [ 
					{ "name" : "action" }, 
					{ "classType" : "_action" }, 
					{ "classType" : "_trigger" }, 
					{ "name" : "trigger" } 
				]
			},
			{ 
				"$or" : [ 
					{ "hidden" : False }, 
					{ "hidden" : { "$exists" : False } }
				]
			}
		]
	},sort=[( "name", 1 )])["results"]
	for modelItem in models:
		result.append({ "_id" : modelItem["_id"], "name" : modelItem["name"] })
	return { "results" : result }, 200

@jimi.api.webServer.route("/conduct/<conductID>/flowProperties/<flowID>/", methods=["GET"])
def getConductFlowProperties(conductID,flowID):
	conductObj = jimi.conduct._conduct().query(jimi.api.g.sessionData,id=conductID)["results"]
	if len(conductObj) == 1:
		conductObj = conductObj[0]
	else:
		return {}, 404
	flow = [ x for x in conductObj["flow"] if x["flowID"] ==  flowID]
	if len(flow) == 1:
		flow = flow[0]
		formData = None
		manifest = None
		whereUsed = None
		if "type" in flow:
			if flow["type"] == "trigger":
				triggerObj = jimi.trigger._trigger().query(jimi.api.g.sessionData,id=flow["triggerID"])["results"]
				if len(triggerObj) == 1:
					triggerObj = triggerObj[0]
				else:
					return {}, 404
				_class = jimi.model._model().getAsClass(id=triggerObj["classID"])
				if len(_class) == 1:
					_class = _class[0].classObject()
				else:
					return {}, 404
				triggerObj = _class().getAsClass(jimi.api.g.sessionData,id=triggerObj["_id"])
				if len(triggerObj) == 1:
					triggerObj = triggerObj[0]
				else:
					return {},404
				if "_properties" in dir(triggerObj):
					formData = triggerObj._properties().generate(triggerObj)
				else:
					formData = jimi.webui._properties().generate(triggerObj)
				manifest = triggerObj.manifest__
				whereUsed = triggerObj.whereUsed()
			elif flow["type"] == "action":
				actionObj = jimi.action._action().query(jimi.api.g.sessionData,id=flow["actionID"])["results"]
				if len(actionObj) == 1:
					actionObj = actionObj[0]
				else:
					return {},404
				_class = jimi.model._model().getAsClass(id=actionObj["classID"])
				if len(_class) == 1:
					_class = _class[0].classObject()
				actionObj = _class().getAsClass(jimi.api.g.sessionData,id=actionObj["_id"])
				if len(actionObj) == 1:
					actionObj = actionObj[0]
				else:
					return {}, 404
				if "_properties" in dir(actionObj):
					formData = actionObj._properties().generate(actionObj)
				else:
					formData = jimi.webui._properties().generate(actionObj)
				manifest = actionObj.manifest__
				whereUsed = actionObj.whereUsed()
		return { "formData" : formData, "manifest" : manifest, "whereUsed" : whereUsed }, 200

@jimi.api.webServer.route("/conduct/<conductID>/flow/<flowID>/", methods=["GET"])
def getConductFlow(conductID,flowID):
	conductObj = jimi.conduct._conduct().query(jimi.api.g.sessionData,id=conductID)["results"]
	if len(conductObj) == 1:
		conductObj = conductObj[0]
	else:
		return {},404
	flow = [ x for x in conductObj["flow"] if x["flowID"] ==  flowID]
	if len(flow) == 1:
		flow = flow[0]
		if "type" in flow:
			flowType = flow["type"]
			if "{0}{1}".format(flowType,"ID") in flow:
				result = { "type" : flowType, "{0}{1}".format(flowType,"ID") : flow["{0}{1}".format(flowType,"ID")]}
				return { "result" : result }, 200
	return { }, 404

@jimi.api.webServer.route("/conduct/<conductID>/forceTrigger/<flowID>/", methods=["POST"])
def forceTrigger(conductID,flowID):
	conductObj = jimi.conduct._conduct().query(jimi.api.g.sessionData,id=conductID)["results"]
	if len(conductObj) == 1:
		conductObj = conductObj[0]
	else:
		return {}, 404
	flow = [ x for x in conductObj["flow"] if x["flowID"] ==  flowID]
	flow = flow[0]
	data = json.loads(api.request.data)
	apiEndpoint = "scheduler/{0}/".format(flow["triggerID"])
	if "_id" in jimi.api.g.sessionData:
		jimi.audit._audit().add("trigger","force",{ "_id" : jimi.api.g.sessionData["_id"], "user" : jimi.api.g.sessionData["user"], "conductID" : conductID, "flowID" : flowID })
	else:
		jimi.audit._audit().add("trigger","force",{ "user" : "system", "conductID" : conductID, "flowID" : flowID })
	host,port = jimi.cluster.getMaster()
	url="http://{0}:{1}".format(host,port)
	jimi.helpers.apiCall("POST",apiEndpoint,{ "action" : "trigger", "events" : data["events"] },token=jimi.api.g.sessionToken,overrideURL=url)
	return { }, 200

@jimi.api.webServer.route("/conduct/<conductID>/flowlogic/<flowID>/<nextflowID>/", methods=["GET"])
def getConductFlowLogic(conductID,flowID,nextflowID):
	conductObj = jimi.conduct._conduct().query(jimi.api.g.sessionData,id=conductID)["results"]
	if len(conductObj) == 1:
		conductObj = conductObj[0]
	else:
		return {}, 404
	flow = [ x for x in conductObj["flow"] if x["flowID"] ==  flowID]
	if len(flow) == 1:
		flow = flow[0]
		if "next" in flow:
			for nextFlow in flow["next"]:
				if type(nextFlow) is str:
					if nextflowID == nextFlow:
						return {"result" : {"logic" : True}}, 200
				elif type(nextFlow) is dict:
					if "order" not in nextFlow:
						nextFlow["order"] = 0
					if nextflowID == nextFlow["flowID"]:
						return {"result" : {"logic" : nextFlow["logic"], "order" : nextFlow["order"]}}, 200
	return { }, 404	

@jimi.api.webServer.route("/conduct/<conductID>/flowlogic/<flowID>/<nextflowID>/", methods=["POST"])
def setConductFlowLogic(conductID,flowID,nextflowID):
	conductObj = jimi.conduct._conduct().getAsClass(jimi.api.g.sessionData,id=conductID)
	if len(conductObj) == 1:
		conductObj = conductObj[0]
	else:
		return {},404
	access, accessIDs, adminBypass = jimi.db.ACLAccess(jimi.api.g.sessionData,conductObj.acl,"write")
	if access:
		flow = [ x for x in conductObj.flow if x["flowID"] ==  flowID]
		data = json.loads(jimi.api.request.data)
		if len(flow) == 1:
			flow = flow[0]
			if "next" in flow:
				found = False
				for key, nextFlow in enumerate(flow["next"]):
					if type(nextFlow) is str:
						if nextFlow == nextflowID:
							nextFlow = {"flowID" : nextflowID}
							found = True
					elif type(nextFlow) is dict:
						if nextFlow["flowID"] == nextflowID:
							found = True	
					if found:
						if "true" == data["logic"].lower():
							flow["next"][key] = {"flowID" : nextFlow["flowID"], "logic" : True, "order" : 0}
						elif "false" == data["logic"].lower():
							flow["next"][key] = {"flowID" : nextFlow["flowID"], "logic" : False, "order" : 0}
						elif data["logic"].startswith("if"):
							flow["next"][key] = {"flowID" : nextFlow["flowID"], "logic" : data["logic"], "order" : 0}
						elif data["logic"] == "*":
							flow["next"][key] = {"flowID" : nextFlow["flowID"], "logic" : data["logic"], "order" : 0}
						else:
							try:
								flow["next"][key] = {"flowID" : nextFlow["flowID"], "logic" : int(data["logic"]), "order" : 0}
							except ValueError:
								return { }, 403
						flow["next"][key]["order"] = int(data["order"])
						# Sorting the list so we dont need to do this at flow runtime
						try:
							flow["next"] = sorted(flow["next"], key=itemgetter("order"), reverse=False) 
						except KeyError:
							for value in flow["next"]:
								if "order" not in value:
									value["order"] = 0
							flow["next"] = sorted(flow["next"], key=itemgetter("order"), reverse=False) 
						if "_id" in api.g.sessionData:
							jimi.audit._audit().add("flowLogic","update",{ "_id" : jimi.api.g.sessionData["_id"], "user" : jimi.api.g.sessionData["user"], "conductID" : conductID, "flowID" : flowID, "nextflowID" : nextflowID, "logic" : data["logic"] })
						else:
							jimi.audit._audit().add("flowLogic","update",{ "user" : "system", "conductID" : conductID, "flowID" : flowID , "nextflowID" : nextflowID, "logic" : data["logic"] })
						conductObj.update(["flow"],sessionData=jimi.api.g.sessionData)
						return { }, 200
	else:
		return {},403
	return { }, 404	

@jimi.api.webServer.route("/cleanup/", methods=["GET","DELETE"])
@jimi.auth.adminEndpoint
def cleanupPage():
	actions = jimi.action._action().query(jimi.api.g.sessionData,query={ "name" : { "$nin" : ["resetTrigger","failedTriggers"] } },fields=["_id","name","lastUpdateTime"])["results"]
	triggers = jimi.trigger._trigger().query(jimi.api.g.sessionData,query={ "name" : { "$nin" : ["resetTrigger","failedTriggers"] } },fields=["_id","name","lastUpdateTime"])["results"]
	actionids = [ x["_id"] for x in actions ]
	triggerids = [ x["_id"] for x in triggers ]
	conducts = jimi.conduct._conduct().query(jimi.api.g.sessionData,query={ "$or" : [ { "flow.triggerID" : { "$in" : triggerids } }, { "flow.actionID" : { "$in" : actionids } } ] },fields=["_id","name","flow"])["results"]
	for c in conducts:
		for flow in c["flow"]:
			if "actionID" in flow:
				if flow["actionID"] in actionids:
					actionids.remove(flow["actionID"])
			if "triggerID" in flow:
				if flow["triggerID"] in triggerids:
					triggerids.remove(flow["triggerID"])
	unusedActionObjects = []
	unusedActionObjectsIds = []
	for actionid in actionids:
		a = [ x for x in actions if x["_id"] == actionid ]
		if a:
			unusedActionObjects.append({ "name" : a[0]["name"], "_id" : a[0]["_id"] })
			unusedActionObjectsIds.append(jimi.db.ObjectId(a[0]["_id"]))
	unusedTriggerObjects = []
	unusedTriggerObjectsIds = []
	for triggerid in triggerids:
		t= [ x for x in triggers if x["_id"] == triggerid ]
		if t:
			unusedTriggerObjects.append({ "name" : t[0]["name"], "_id" : t[0]["_id"] })
			unusedTriggerObjectsIds.append(jimi.db.ObjectId(t[0]["_id"]))
	if request.method == "DELETE":
		jimi.action._action().api_delete(query={ "_id" : { "$in" : unusedActionObjectsIds } })
		jimi.trigger._trigger().api_delete(query={ "_id" : { "$in" : unusedTriggerObjectsIds } })
		return { },200
	return render_template("cleanupObjects.html", unusedActionObjects=unusedActionObjects, unusedTriggerObjects=unusedTriggerObjects, CSRF=api.g.sessionData["CSRF"])

@jimi.api.webServer.route("/status/")
def statusPage():
	triggers = jimi.trigger._trigger().query(sessionData=api.g.sessionData,query={})["results"]
	data = { "running" : [], "pending" : [], "failed" : [] }
	for trigger in triggers:
		# Apply fix for default 60 seconds if not defined ( new installs not affected as DB defines this now )
		if trigger["maxDuration"] == 0:
			trigger["maxDuration"] = 60
		if ((trigger["startCheck"] > 0 and trigger["startCheck"] + trigger["maxDuration"] > time.time()) or (trigger["lastCheck"] > (time.time() - 1))):
			data["running"].append(trigger)
		elif trigger["startCheck"] == 0:
			data["pending"].append(trigger)
		else:
			data["failed"].append(trigger)
	return render_template("status.html",CSRF=jimi.api.g.sessionData["CSRF"],triggers=data)

@jimi.api.webServer.route("/status/triggerStatus/", methods=["POST"])
def statusPageTriggerStatusAPI():
	doughnut = ui.doughnut()
	triggers = jimi.trigger._trigger().getAsClass(sessionData=api.g.sessionData,query={})
	doughnut.addLabel("Running")
	doughnut.addLabel("Pending")
	doughnut.addLabel("Failed")
	data = [0,0,0]
	for trigger in triggers:
		# Apply fix for default 60 seconds if not defined ( new installs not affected as DB defines this now )
		if trigger.maxDuration == 0:
			trigger.maxDuration = 60
		if ((trigger.startCheck > 0 and trigger.startCheck + trigger.maxDuration > time.time()) or (trigger.lastCheck + 2.5 > (time.time()))):
			data[0] += 1
		elif trigger.startCheck == 0:
			data[1] += 1
		else:
			data[2] += 1
	doughnut.addDataset("Triggers",data)
	data = json.loads(jimi.api.request.data)
	return doughnut.generate(data), 200

@jimi.api.webServer.route("/status/conductStatus/", methods=["POST"])
def statusPageConductStatusAPI():
	pie = ui.pie()
	conducts = jimi.conduct._conduct().getAsClass(sessionData=api.g.sessionData,query={})
	pie.addLabel("Enabled")
	pie.addLabel("Disabled")
	data = [0,0]
	for conduct in conducts:
		if conduct.enabled:
			data[0] += 1
		else:
			data[1] += 1
	pie.addDataset("Conducts",data)
	data = json.loads(jimi.api.request.data)
	return pie.generate(data), 200

@jimi.api.webServer.route("/status/triggerChart/", methods=["GET"])
def statusPageTriggerChartAPI():
	triggers = jimi.trigger._trigger().query(sessionData=api.g.sessionData,query={},fields=["_id","name","enabled","startCheck","maxDuration","lastCheck"])
	for trigger in triggers["results"]:
		# Apply fix for default 60 seconds if not defined ( new installs not affected as DB defines this now )
		if trigger["maxDuration"] == 0:
			trigger["maxDuration"] = 60
		if ((trigger["startCheck"] > 0 and trigger["startCheck"] + trigger["maxDuration"] > time.time()) or (trigger["lastCheck"] + 2.5 > (time.time()))):
			trigger["status"] = "Running"
		elif trigger["startCheck"] == 0:
			trigger["status"] = "Enabled"
		else:
			trigger["status"] = "Failed"
	return triggers, 200

api.startServer(False,host=apiSettings["bind"], port=apiSettings["port"])
