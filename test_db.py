#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os,  json,  re, traceback,  sys,  time
from db import O2tvgoDB
_m3u_json_= "/home/kajo/.kodi/userdata/addon_data/plugin.video.o2tvgo.iptv.simple/o2tvgo-prgs.json."
_xmltv_json_base_ = "/home/kajo/.kodi/userdata/addon_data/plugin.video.o2tvgo.iptv.simple/o2tvgo-epg-"
_restart_ok_ = "/home/kajo/.kodi/userdata/addon_data/plugin.video.o2tvgo.iptv.simple/o2tvgo-restart_ok.txt"
_save_epg_lock_file_ = '/home/kajo/.kodi/userdata/addon_data/plugin.video.o2tvgo.iptv.simple/o2tvgo-save_epg.lock'

_db_ = None
def upgradeConfigsFromJsonToDb():
    if os.path.exists(_m3u_json_):
        try:
            successM3U = False
            with open(_m3u_json_) as data_file:
                channelsDict = json.load(data_file)
            if channelsDict and "list" in channelsDict:
                channelListDict = channelsDict["list"]
                indexesByBaseNames = channelsDict["indexesByBaseNames"]
                baseNamesByIndexes = {}
                for baseName in indexesByBaseNames:
                    i = indexesByBaseNames[baseName]
                    baseNamesByIndexes[i] = baseName
                indexesByKey = channelsDict["indexesByKey"]
                successM3U = True
                for k in channelListDict:
                    ch = channelListDict[k]
                    channelKeyClean = re.sub(r"[^a-zA-Z0-9_]", "_", ch["channel_key"])
                    id = _db_.getChannelID(keyOld=ch["channel_key"], keyCleanOld=channelKeyClean, silent=True)
                    if not id:
                        index = indexesByKey[ch["channel_key"]]
                        baseName = baseNamesByIndexes[index]
                        idNew = _db_.addChannel(ch["channel_key"],  channelKeyClean,  ch["name"], baseName)
                        if not idNew:
                            successM3U = False
            if "chJsNumByIndex" in channelsDict:
                for i in channelsDict["chJsNumByIndex"]:
                    channelKey = channelsDict["keysByIndex"][i]
                    channelKeyClean = re.sub(r"[^a-zA-Z0-9_]", "_", channelKey)
                    channelID = _db_.getChannelID(keyOld=channelKey, keyCleanOld=channelKeyClean)
                    successEpg = True
                    if channelID:
                        channelJsonNumber = channelsDict["chJsNumByIndex"][i]
                        jsonEpgFilePath = _xmltv_json_base_ + str(channelJsonNumber) + ".json"
    #                    jsonEpgFile = xbmc.translatePath(jsonEpgFilePath)
                        jsonEpgFile = jsonEpgFilePath
                        successEpg = False
                        with open(jsonEpgFile) as data_file:
                            epg = json.load(data_file)
                            successEpg = True
                            for key in sorted(epg.iterkeys()):
                                oneEpg = epg[key]
                                idEpg = _db_.getEpgID(epgIdOld=oneEpg["epgId"], channelID=channelID, silent=True)
                                if not idEpg:
                                    idNew = _db_.addEpg(
                                        epgId = oneEpg["epgId"],
                                        start = oneEpg["start"],
                                        startTimestamp = oneEpg["startTimestamp"],
                                        startEpgTime = oneEpg["startEpgTime"],
                                        end = oneEpg["end"],
                                        endTimestamp = oneEpg["endTimestamp"],
                                        endEpgTime = oneEpg["endEpgTime"],
                                        title = oneEpg["title"],
                                        plot = oneEpg["plot"],
                                        plotoutline = oneEpg["plotoutline"],
                                        fanart_image = oneEpg["fanart_image"],
                                        genre = oneEpg["genre"],
                                        genres = json.dumps(oneEpg["genres"]),
                                        channelID=channelID)
                                    if idNew:
                                        print("Success - JSON "+str(i)+"!")
#                                        logNtc("Successfully imported EPG #"+str(oneEpg["epgId"])+" from JSON file into DB. Removing JSON file.")
                                    else:
                                        successEpg = False
                                        successM3U = False
                    if successEpg:
                        print("Successfully imported all EPG of channel #"+str(channelID)+" from JSON file into DB. Removing JSON file.")
                        #os.remove(jsonEpgFile)

            if successM3U:
                print("Success!")
#                os.remove(_m3u_json_)

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_tb(exc_traceback, file=sys.stdout)
            print("Exception: "+str(e))
#            logNtc("Exception while reading channels from json: "+str(e))
            return False

    if os.path.exists(_restart_ok_):
        lastRestartOK = os.path.getmtime(_restart_ok_)
        _db_.setLock("lastRestart", lastRestartOK)
        #os.remove(_restart_ok_)
    if os.path.exists(_save_epg_lock_file_):
        fMtime = os.path.getmtime(_save_epg_lock_file_)
        _db_.setLock("saveEpgRunning", fMtime)
        #os.remove(_save_epg_lock_file_)
    return True

if __name__ == '__main__':
    db_path = "/home/kajo/.kodi/userdata/addon_data/plugin.video.o2tvgo.iptv.simple/o2tvgo.db"
    _db_ = O2tvgoDB(db_path=db_path, profile_path="/home/kajo/.kodi/userdata/addon_data/plugin.video.o2tvgo.iptv.simple/",  plugin_path="",_notification_disable_all_=False, _logs_=None)

#    res = upgradeConfigsFromJsonToDb()

    print(_db_.getLock("lastRestart"))

#    timestampNow = int(time.time())
#    olderThan = (timestampNow -  (2*24*3600))
#    print(timestampNow,  olderThan)
#    _db_.deleteOldEpg(endBefore = olderThan)

    _epgLockTimeout_ = 10*60
    locktime = _db_.getLock("saveEpgRunning")
    if locktime == False:
        print("Couldn't retrieve lock: saveEpgRunning")
    else:
        timestampNow = int(time.time())
        if (timestampNow - locktime) >= (_epgLockTimeout_):
            print("Epg lock is off")
        else:
            print("Epg lock is on")
        print(str(timestampNow))
        print(str(locktime))
        print(str(timestampNow - locktime))

    print(_db_.getEpgRow(7497,  35))

#    res = _db_.cleanEpgDuplicates(doDelete = True)
#    if res:
#        if res["duplicates"]:
#            print(len(res["duplicates"]))
#        if res["toDelete"]:
#            print(len(res["toDelete"]))
#    print(res)

#    print(_db_.getChannelRow(4))
#    print(_db_.getChannels())
#    print(_db_.getEpgRows(10))

#    id = _db_.getChannelID(None, 'Jednotka HD1', 'Jednotka_HD1', 'Jednotka HD1')
#    print(id)
#    if not id:
#        id = _db_.addChannel('Jednotka HD', 'Jednotka_HD', 'Jednotka HD', '5001-tv-tablet')
#        print(id)
#    id2 = _db_.updateChannel('Jednotka HD1', 'Jednotka_HD1', 'Jednotka HD1', '5001-tv-tablet',  id)
#    print(id2)
#    id = _db_.updateChannel('Jednotka HD2', 'Jednotka_HD2', 'Jednotka HD2', '5001-tv-tablet')
#    print(id)
#    id = _db_.updateChannel('Jednotka HD2', 'Jednotka_HD2', 'Jednotka HD2', '5001-tv-tablet',  None,  None,  'Jednotka_HD1')
#    print(id)
#    id = _db_.updateChannel('Jednotka HD2', 'Jednotka_HD2', 'Jednotka HD2', '5001-tv-tablet',  None,  None,  'Jednotka_HD2')
#    print(id)
#    id = _db_.addEpg(epgId=123, start=123, startTimestamp=1234, startEpgTime=1234, end=234, endTimestamp=234, endEpgTime=234, title="title", channelID=id,  channelKeyClean='Jednotka_HD1')
#    print(id)
#    id = _db_.addEpg(epgId=123, start=123, startTimestamp=1234, startEpgTime=1234, end=234, endTimestamp=234, endEpgTime=234, title="title", channelKeyClean='Jednotka_HD1')
#    print(id)
