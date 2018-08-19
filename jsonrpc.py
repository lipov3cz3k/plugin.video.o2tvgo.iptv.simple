#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json, xbmc, sys

class JsonRPC:
    def __init__(self, _logs_=None, scriptname="O2TVGO/IPTVSimple", logId="O2TVGO/IPTVSimple"):
        if _logs_:
            self._logs_ = _logs_
        else:
            from logs import Logs
            self._logs_ = Logs(scriptname, logId)
        self.logIdSuffix = "/jsonrpc.py/JsonRPC"
        self.scriptname = scriptname
        self.logId = logId

    def log(self, msg):
        return self._logs_.log(msg=msg, idSuffix=self.logIdSuffix)
    def logDbg(self, msg):
        return self._logs_.logDbg(msg=msg, idSuffix=self.logIdSuffix)
    def logNtc(self, msg):
        return self._logs_.logNtc(msg=msg, idSuffix=self.logIdSuffix)
    def logWarn(self, msg):
        return self._logs_.logWarn(msg=msg, idSuffix=self.logIdSuffix)
    def logErr(self, msg):
        return self._logs_.logErr(msg=msg, idSuffix=self.logIdSuffix)

    def _getAddons(self):
        payloadGetAddons = {
                            "jsonrpc": "2.0",
                            "id": "1",
                            "method": "Addons.GetAddons",
        }
        payloadGetAddonsJson = json.dumps(payloadGetAddons)
        jsonGetAddonsResponse = xbmc.executeJSONRPC(payloadGetAddonsJson)
        if jsonGetAddonsResponse:
            try:
                responseGetAddons = json.loads(jsonGetAddonsResponse)
                if "result" in responseGetAddons and responseGetAddons["result"] and "addons" in responseGetAddons["result"] and responseGetAddons["result"]["addons"]:
                    return responseGetAddons["result"]["addons"]
                else:
                    self.logErr("Invalid response from 'Addons.GetAddonDetails': "+self._logs_._toString(responseGetAddons))
                    return False
            except:
                self.logErr("An exception was raised by 'Addons.GetAddonDetails': "+self._logs_._toString(sys.exc_info()[0]))
                return False
        else:
            self.logErr("No response from 'Addons.GetAddonDetails'")
            return False

    def _getAddonDetails(self, addonId):
        payloadGetDetails = {"jsonrpc": "2.0",
                             "id": "1",
                             "method": "Addons.GetAddonDetails",
                             "params": {
                               "addonid": addonId,
                               "properties": ["enabled","name"]
                            }
        }
        payloadGetDetailsJson = json.dumps(payloadGetDetails)
        jsonGetDetailsResponse = xbmc.executeJSONRPC(payloadGetDetailsJson)
        if jsonGetDetailsResponse:
            try:
                responseGetDetails = json.loads(jsonGetDetailsResponse)
                if "result" in responseGetDetails and responseGetDetails["result"] and "addon" in responseGetDetails["result"] and responseGetDetails["result"]["addon"] and "enabled" in responseGetDetails["result"]["addon"]:
                    return responseGetDetails["result"]["addon"]
                else:
                    self.logErr("Invalid response from 'Addons.GetAddonDetails' for "+addonId+": "+self._logs_._toString(responseGetDetails))
                    return False
            except:
                self.logErr("An exception was raised by 'Addons.GetAddonDetails' for "+addonId+": "+self._logs_._toString(sys.exc_info()[0]))
                return False
        else:
            self.logErr("No response from 'Addons.GetAddonDetails' for "+addonId)
            return False

    def _setAddonEnabled(self, addonId, enabled=True):
        if enabled:
            strAction = "enabling"
        else:
            strAction = "disabling"
        payloadSetEnabled = {"jsonrpc": "2.0",
                             "id":"1",
                             "method": "Addons.SetAddonEnabled",
                             "params": {
                               "addonid": addonId,
                               "enabled": enabled
                            }
        }
        payloadSetEnabledJson = json.dumps(payloadSetEnabled)
        jsonSetEnabledResponse = xbmc.executeJSONRPC(payloadSetEnabledJson)
        if jsonSetEnabledResponse:
            try:
                responseSetEnabled = json.loads(jsonSetEnabledResponse)
                if "result" in responseSetEnabled and self._logs_._toString(responseSetEnabled["result"]).lower() == "ok":
                    return True
                else:
                    self.logErr("Invalid response from 'Addons.SetAddonEnabled' for "+strAction+" "+addonId+": "+self._logs_._toString(responseSetEnabled))
                    if "result" in responseSetEnabled:
                        self.logNtc(self._logs_._toString(responseSetEnabled["result"]))
                    return False
            except:
                self.logErr("An exception was raised by 'Addons.SetAddonEnabled' for "+strAction+" "+addonId+": "+self._logs_._toString(sys.exc_info()[0]))
                return False
        else:
            self.logErr("No response from 'Addons.SetAddonEnabled' for "+strAction+" "+addonId)
            return False

    def _getPVRChannels(self):
        payload = {"jsonrpc": "2.0",
                   "id":"1",
                   "method": "PVR.GetChannels",
                   "params": {
                       "channelgroupid": "alltv"
                       }
        }
        payloadJson = json.dumps(payload)
        jsonResponse = xbmc.executeJSONRPC(payloadJson)
        if jsonResponse:
            response = json.loads(jsonResponse)

        if "result" in response and "channels" in response["result"]:
            return response["result"]["channels"]
        return False

    def _switchToChannel(self, channelID):
        payload = {
          "jsonrpc": "2.0",
          "id":"1",
          "method": "Player.Open",
          "params": {
            "item":{
              "channelid": channelID
            }
          }
        }
        payloadJson = json.dumps(payload)
        jsonResponse = xbmc.executeJSONRPC(payloadJson)
        if jsonResponse:
            responseDecoded = json.loads(jsonResponse)
            if "error" in responseDecoded:
                if "message" in responseDecoded["error"]:
                    self.logErr("Could not channel ID "+str(channelID)+": "+responseDecoded["error"]["message"])
                else:
                    self.logErr("Could not play channel ID "+str(channelID))
                self.logDbg('payloadJson: '+payloadJson)
                self.logDbg('jsonResponse: '+jsonResponse)
        else:
            self.logErr("Could not channel ID "+str(channelID)+": No response from JSONRPC")
            self.logDbg('payloadJson: '+payloadJson)
            self.logDbg('jsonResponse: '+jsonResponse)

    def getNowPlayed(self):
        payload = {
            'jsonrpc': '2.0',
            'method': 'Player.GetItem',
            'params': {
                'playerid': 1,
                'properties': ['file', 'showtitle', 'season', 'episode']
            },
            'id': '1'
        }
        payloadJson = json.dumps(payload)
        jsonResponse = xbmc.executeJSONRPC(payloadJson)
        if jsonResponse:
            respponseDecoded = json.loads(jsonResponse)

        if "result" in respponseDecoded and "item" in respponseDecoded["result"]:
            return respponseDecoded["result"]["item"]
        return False
