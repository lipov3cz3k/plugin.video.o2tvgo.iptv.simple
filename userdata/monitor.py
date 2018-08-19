import json, time, sqlite3, sys, traceback
import xbmc, xbmcgui, xbmcaddon

_addon_o2tvgo_iptvo_simple_ = xbmcaddon.Addon('plugin.video.o2tvgo.iptv.simple')
_profile_ = xbmc.translatePath(_addon_o2tvgo_iptvo_simple_.getAddonInfo('profile')).decode("utf-8")
_scriptname_ = _addon_o2tvgo_iptvo_simple_.getAddonInfo('name')

_next_programme_ = _profile_+'o2tvgo-next_programme.json'
_m3u_json_ = _profile_+'o2tvgo-prgs.json'
_db_path_ = _profile_+'o2tvgo.db'
_logId_ = "O2TVGO/IPTVSimple/monitor.py"
O2TVGO_VIDEO = False
O2TVGO_VIDEO_LIVE = False

class O2tvgoDBMini:
    def __init__(self, db_path, logId):
        self.db_path = db_path
        self.connection = False
        self.cursor = False
        self.logId = logId
        self.logIdSuffix = "/O2tvgoDBMini"

        def log(self, msg, level=xbmc.LOGDEBUG):
            xbmc.log("[%s] %s"%(self.logId+self.logIdSuffix,msg.__str__()), level)
        def logDbg(self, msg):
            self.log(msg, level=xbmc.LOGDEBUG)
        def logNtc(self, msg):
            self.log(msg, level=xbmc.LOGNOTICE)
        def logWarn(self, msg):
            self.log(msg, level=xbmc.LOGWARNING)
        def logErr(self, msg):
            self.log(msg, level=xbmc.LOGERROR)

    def __del__(self):
        self.closeDB()

    def commit(self):
        if self.connection:
            self.connection.commit()

    def connectDB(self):
        if not self.connection:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
            self.connection.text_factory = str
            # enable foreign keys: #
            self.connection.execute("PRAGMA foreign_keys = 1")
            self.cursor = self.connection.cursor()

    def closeDB(self):
        if self.connection:
            self.commit()
            self.connection.close()
            self.connection = False

    def cexec(self, sql, vals=None):
        self.connectDB()
        try:
            if vals:
                self.cursor.execute(sql, vals)
            else:
                self.cursor.execute(sql)
            self.commit()
            return self.cursor.lastrowid
        except Exception as ex:
            self.logErr("Exception while executing a query ("+sql+"): "+str(ex))
            self.closeDB()

    def _getEpgColumns(self):
        return ["epgId", "start", "startTimestamp", "startEpgTime", "end", "endTimestamp", "endEpgTime", "title", "plot", "plotoutline", "fanart_image", "genre", "genres", "channelID",
                  "isCurrentlyPlaying", "isNextProgramme", "inProgressTime", "isRecentlyWatched", "isWatchLater"]

    def _getEpgColumnsInt(self):
        return ["epgId", "start", "startTimestamp", "startEpgTime", "end", "endTimestamp", "endEpgTime", "isCurrentlyPlaying", "isNextProgramme", "inProgressTime", "isRecentlyWatched", "isWatchLater", "channelID"]

    def getNextEpg(self):
        self.cexec("SELECT e.*, ch.name as channelName FROM epg e JOIN channels ch on e.channelID=ch.id WHERE e.isNextProgramme = ?", (1, ))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"],
                "channelName": row["channelName"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
            return epgDict
        return False

    def getCurrentlyPlayingEpg(self):
        self.cexec("SELECT e.*, ch.id as channelID, ch.name as channelName FROM epg e JOIN channels ch on e.channelID=ch.id WHERE e.isCurrentlyPlaying = ?", (1, ))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"],
                "channelName": row["channelName"],
                "channelID": row["channelID"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
                elif col in self._getEpgColumnsInt():
                    epgDict[col] = 0
                else:
                    epgDict[col] = ""
            return epgDict
        return False

    def getChannelByBaseName(self, baseName):
        self.cexec("SELECT id, \"key\", keyClean, name, epgLastModTimestamp FROM channels WHERE baseName LIKE ?", ('%'+baseName+'%', ))
        r = self.cursor.fetchone()
        if not r:
            return {}
        return {
            "id": r[0],
            "key": r[1],
            "keyClean": r[2],
            "name": r[3],
            "epgLastModTimestamp": r[4]
        }

    def getChannelByName(self, name):
        self.cexec("SELECT id, \"key\", keyClean, name, epgLastModTimestamp FROM channels WHERE name = ?", (name, ))
        r = self.cursor.fetchone()
        if not r:
            return {}
        return {
            "id": r[0],
            "key": r[1],
            "keyClean": r[2],
            "name": r[3],
            "epgLastModTimestamp": r[4]
        }

    def getCurrentEpgInfoByChannelName(self, channelName):
        query = '''
            SELECT e.id, e.title, e.channelID, e."end" - e."start" AS "length", CAST(strftime('%s','now') AS INTEGER) - e."start" AS "position", e.inProgressTime, e.isRecentlyWatched, e.isWatchLater
            FROM epg e
            JOIN channels ch ON e.channelID = ch.id
            WHERE
                e."start" <= CAST(strftime('%s','now') AS INTEGER) AND e."end" > CAST(strftime('%s','now') AS INTEGER)
                AND ch.name = ?
        '''
        self.cexec(query, (channelName, ))
        r = self.cursor.fetchone()
        if not r:
            return {}
        return {
            "id": r[0],
            "title": r[1],
            "channelID": r[2],
            "length": r[3],
            "position": r[4],
            "inProgressTime": r[5],
            "isRecentlyWatched": r[6],
            "isWatchLater": r[7],
        }

    def setProgress(self, channelID, epgID, time):
        self.cexec("UPDATE epg SET inProgressTime = ? WHERE channelID = ? AND id = ?", (time, channelID, epgID))

    def setIsNextProgrammeUsed(self):
        self.cexec("UPDATE epg SET isNextProgramme = ? WHERE isNextProgramme = ?", (0, 1))

    def setIsCurrentlyPlayingTo0(self):
        self.cexec("UPDATE epg SET isCurrentlyPlaying = ? WHERE isCurrentlyPlaying = ?", (0, 1))

    def setIsWatchLaterTo0(self, epgID):
        self.cexec("UPDATE epg SET isWatchLater = ? WHERE id = ?", (0, epgID))

    def setIsRecentlyWatchedTo1(self, epgID):
        self.cexec("UPDATE epg SET isRecentlyWatched = ? WHERE id = ?", (1, epgID))

    def getLock(self, name, silent=True):
        self.cexec("SELECT val FROM lock WHERE name = ?", (name, ))
        all = self.cursor.fetchall()
        rowcount = len(all)
        if rowcount > 1:
            self.logWarn("More than one row match the lock search criteria for: name = "+name+"!")
            return 0
        if rowcount == 0:
            if not silent:
                self.logWarn("No row matches the channel lock criteria for: name = "+name+"!")
            return 0
        r = all[0]
        val = r[0]
        return val

_db_ = O2tvgoDBMini(_db_path_, _logId_)

class MyPlayer(xbmc.Player) :

    # def __init__ (self, logId):
    #     #self.logDbg('CALLBACK: __init__')
    #     xbmc.Player.__init__(self)
    #     self.logId = logId
    #     self.logIdSuffix = "/O2tvgoDBMini"

    def __new__ (self, logId):
        #self.logDbg('CALLBACK: __new__')
        self.logId = logId
        self.logIdSuffix = "/MyPlayer"
        return super(MyPlayer, self).__new__(self)

    def log(self, msg, level=xbmc.LOGDEBUG):
        xbmc.log("[%s] %s"%(self.logId+self.logIdSuffix,msg.__str__()), level)
    def logDbg(self, msg):
        self.log(msg, level=xbmc.LOGDEBUG)
    def logNtc(self, msg):
        self.log(msg, level=xbmc.LOGNOTICE)
    def logWarn(self, msg):
        self.log(msg, level=xbmc.LOGWARNING)
    def logErr(self, msg):
        self.log(msg, level=xbmc.LOGERROR)

    #def onPlayBackStarted(self):
        #self.logDbg('CALLBACK: onPlayBackStarted')

    def onPlayBackSeek(self, time, seekOffset):
        self.logDbg('CALLBACK: onPlayBackSeek (time = '+str(time)+', seekOffset = '+str(seekOffset)+')')
        if O2TVGO_VIDEO:
            currentlyPlaying = _db_.getCurrentlyPlayingEpg()
            if currentlyPlaying:
                _db_.setProgress(currentlyPlaying["channelID"], currentlyPlaying["id"], int(time / 1000))
            _db_.closeDB()

    def onPlayBackEnded(self):
        self.logDbg('CALLBACK: onPlayBackEnded')
        _db_.setIsCurrentlyPlayingTo0()
        _db_.closeDB()

        if O2TVGO_VIDEO:
            self._maybePlayNextProgramme()

    def onPlayBackStopped(self):
        self.logDbg('CALLBACK: onPlayBackStopped')
        _db_.setIsCurrentlyPlayingTo0()
        _db_.closeDB()
        if O2TVGO_VIDEO:
            self._maybePlayNextProgramme()

    #def onPlayBackPaused(self):
        #self.logDbg('CALLBACK: onPlayBackPaused')

    #def onPlayBackResumed(self):
        #self.logDbg('CALLBACK: onPlayBackResumed')

    def _maybePlayNextProgramme(self):
        nextProgramme = _db_.getNextEpg()
        _db_.closeDB()

        if not nextProgramme:
            return

        timestampNow = int(time.time())
        if int(nextProgramme['end']) <= timestampNow:
            question = 'Do you want to play the next programme: '+nextProgramme["title"] + '?'
            response = xbmcgui.Dialog().yesno(_scriptname_, question, yeslabel='Yes', nolabel='No')

            if response:
                command = 'RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?playfromepg=1&starttimestamp='
                command += str(nextProgramme["start"])
                command += '&channelname='
                command += str(nextProgramme["channelName"])
                command += ')'
                self.logDbg('command: '+command)
                xbmc.executebuiltin(command)

        else:
            position = timestampNow - int(nextProgramme['start'])
            length = int(nextProgramme['end']) - int(nextProgramme['start'])
            lengthMin = length / 60
            positionMinutes = position / 60
            positionPercent = 10000 * position / length * 0.01
            question = 'Do you want to switch to the currently playing programme on '+nextProgramme["channelName"]+': '+nextProgramme["title"] + ' (' + str(positionMinutes) + ' / ' + str(lengthMin) + ' min [' + str(positionPercent) + '%])?'
            response = xbmcgui.Dialog().yesno(_scriptname_, question, yeslabel='Yes', nolabel='No')

            if response:
                payload = {
                    "jsonrpc": "2.0",
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

                channelID = None
                if "result" in response and "channels" in response["result"]:
                    channels = response["result"]["channels"]
                    for channel in channels:
                        if channel["label"] == nextProgramme["channelName"]:
                            channelID = channel["channelid"]
                            break
                if not channelID and channelID != 0:
                    self.logErr("Could not find the channel's ID")
                    self.logDbg('channelName: '+nextProgramme["channelName"])
                    self.logDbg('channels: '+jsonResponse)
                else:
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
                                self.logErr("Could not play "+nextProgramme["channelKey"]+": "+responseDecoded["error"]["message"])
                            else:
                                self.logErr("Could not play "+nextProgramme["channelKey"])
                            self.logDbg('payloadJson: '+payloadJson)
                            self.logDbg('jsonResponse: '+jsonResponse)
                    else:
                        self.logErr("Could not play "+nextProgramme["channelKey"]+": No response from JSONRPC")
                        self.logDbg('payloadJson: '+payloadJson)
                        self.logDbg('jsonResponse: '+jsonResponse)

        _db_.setIsNextProgrammeUsed()
        _db_.closeDB()

player=MyPlayer(_logId_)

def _logDbg(msg, level=xbmc.LOGDEBUG, logIdSuffix=""):
    global _logId_
    xbmc.log("[%s] %s"%(_logId_+logIdSuffix,msg.__str__()), level)

def o2TVGoRefreshHome(section=None):
    ts = str(int(time.time() / 5))
    if not section:
        xbmcgui.Window(10000).setProperty('O2TVGoRefreshHomeWatched', ts)
        xbmcgui.Window(10000).setProperty('O2TVGoRefreshHomeInProgress', ts)
        xbmcgui.Window(10000).setProperty('O2TVGoRefreshHomeWatchLater', ts)
        xbmcgui.Window(10000).setProperty('O2TVGoRefreshHomeFavourites', ts)
    else:
        xbmcgui.Window(10000).setProperty('O2TVGoRefreshHome'+section, ts)

def jsonRPCgetNowPlaying():
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

def setPlayingTime(position = None, remainingTime = None, length = None):
    w = xbmcgui.Window(10115)
    if position is None or position < 0:
        propIsLiveChannel = w.getProperty('O2TVGo.IsLiveChannel')
        if propIsLiveChannel == "" or propIsLiveChannel == "true":
            w.setProperty('O2TVGo.IsLiveChannel', "false")
            w.clearProperty('O2TVGo.LiveChannel.PlayerTime')
            w.clearProperty('O2TVGo.LiveChannel.PlayerRemainingTime')
#            _logDbg(msg='clearing position.', logIdSuffix="/setPlayingTime()")
#        else:
#            _logDbg(msg='O2TVGo.IsLiveChannel = '+propIsLiveChannel, logIdSuffix="/setPlayingTime()")
    else:
        w.setProperty('O2TVGo.IsLiveChannel', "true")

        try:
            position = int(position - (position % 5))
#            _logDbg(msg='position: '+str(position), logIdSuffix="/setPlayingTime()")
            if length is not None and length < 3600:
                strPosition = time.strftime('%M:%S', time.gmtime(position))
            else:
                strPosition = time.strftime('%H:%M:%S', time.gmtime(position))
            w.setProperty('O2TVGo.LiveChannel.PlayerTime', strPosition)
        except Exception as ex:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            _logDbg("An exception occured while setting position: "+str(ex), logIdSuffix="/setPlayingTime()")
            _logDbg(msg=traceback.format_exc(), logIdSuffix="/setPlayingTime()")
            setPlayingTime(-1)
        if remainingTime is not None and remainingTime > 0:
            try:
                if remainingTime < 3600:
                    strRemainingTime = time.strftime('%M:%S', time.gmtime(remainingTime))
                else:
                    strRemainingTime = time.strftime('%H:%M:%S', time.gmtime(remainingTime))
                w.setProperty('O2TVGo.LiveChannel.PlayerRemainingTime', strRemainingTime)
            except Exception as ex:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                _logDbg("An exception occured while setting remaining time: "+str(ex), logIdSuffix="/setPlayingTime()")
                w.clearProperty('O2TVGo.LiveChannel.PlayerRemainingTime')
                _logDbg(msg=traceback.format_exc(), logIdSuffix="/setPlayingTime()")
        else:
            w.clearProperty('O2TVGo.LiveChannel.PlayerRemainingTime')

    return

def isPlayingVideoO2TVGO():
    currentlyPlaying = _db_.getCurrentlyPlayingEpg()
    _db_.closeDB()
    if currentlyPlaying:
        #epgTimeshift = _db_.getLock("timeshift")
        #timeShift = epgTimeshift * 60 * 60
        #timestampNow = int(time.time()) - int(timeShift)
        #position = timestampNow - int(currentlyPlaying['start'])
        position = int(xbmc.Player().getTime())
        length = int(currentlyPlaying['end']) - int(currentlyPlaying['start'])
        #_logDbg(msg='Currently playing:  '+str(length)+", "+str(position)+", "+str(timestampNow)+", "+currentlyPlaying["channelName"]+", "+str(currentlyPlaying["title"]), logIdSuffix="/isPlayingVideoO2TVGO()")
        if length - position < (10*60):
            if currentlyPlaying["inProgressTime"] > 0:
                _db_.setProgress(currentlyPlaying["channelID"], currentlyPlaying["id"], 0)
                o2TVGoRefreshHome("InProgress")
            if currentlyPlaying["isRecentlyWatched"] != 1:
                _db_.setIsRecentlyWatchedTo1(currentlyPlaying["id"])
                o2TVGoRefreshHome("Watched")
                o2TVGoRefreshHome("Favourites")
            if currentlyPlaying["isWatchLater"] > 0:
                _db_.setIsWatchLaterTo0(currentlyPlaying["id"])
                o2TVGoRefreshHome("WatchLater")
        else:
            _db_.setProgress(currentlyPlaying["channelID"], currentlyPlaying["id"], position)
        _db_.closeDB()
        setPlayingTime(-1)
        return True
    playingNow = xbmc.Player().getPlayingFile()
    if not playingNow.endswith("m3u8"):
        if playingNow.startswith("pvr://"):
            #_logDbg(msg='Is playing a live channel: '+playingNow, logIdSuffix="/isPlayingVideoO2TVGO()")
            global O2TVGO_VIDEO_LIVE
            try:
                item = jsonRPCgetNowPlaying()
                if item and 'type' in item and item["type"] == 'channel' and 'label' in item and 'id' in item:
                    if not O2TVGO_VIDEO_LIVE:
                        o2TVGoRefreshHome()
                    O2TVGO_VIDEO_LIVE = True
                    channelName = item['label']

                    #channelNum = item['id']
                    #_logDbg(msg='The currently playing live channel is #'+str(channelNum)+": "+channelName, logIdSuffix="/isPlayingVideoO2TVGO()")

                    epgInfo = _db_.getCurrentEpgInfoByChannelName(channelName = channelName)
                    if epgInfo and "id" in epgInfo:
                        #_logDbg(msg='The currently playing live programme is "'+epgInfo["title"]+'", at position '+str(epgInfo["position"])+" / "+str(epgInfo["length"]), logIdSuffix="/isPlayingVideoO2TVGO()")
                        iRemainingTime = epgInfo["length"] - epgInfo["position"]
                        setPlayingTime(position=epgInfo["position"], remainingTime=iRemainingTime, length=epgInfo["length"])
                        if iRemainingTime < 10*60:
                            if epgInfo["inProgressTime"] > 0:
                                #_logDbg(msg='Setting Progress to 0', logIdSuffix="/isPlayingVideoO2TVGO()")
                                _db_.setProgress(epgInfo["channelID"], epgInfo["id"], 0)
                                o2TVGoRefreshHome("InProgress")
                            if epgInfo["isRecentlyWatched"] != 1:
                                #_logDbg(msg='Setting Watched to 1', logIdSuffix="/isPlayingVideoO2TVGO()")
                                _db_.setIsRecentlyWatchedTo1(epgInfo["id"])
                                o2TVGoRefreshHome("Watched")
                                o2TVGoRefreshHome("Favourites")
                            if epgInfo["isWatchLater"] > 0:
                                #_logDbg(msg='Setting WatchLater to 0', logIdSuffix="/isPlayingVideoO2TVGO()")
                                _db_.setIsWatchLaterTo0(epgInfo["id"])
                                o2TVGoRefreshHome("WatchLater")
                        else:
                            #_logDbg(msg='Setting Progress to '+str(epgInfo["position"]), logIdSuffix="/isPlayingVideoO2TVGO()")
                            _db_.setProgress(epgInfo["channelID"], epgInfo["id"], epgInfo["position"])
                    else:
                        _logDbg(msg='Epg name not found for channel '+channelName, logIdSuffix="/isPlayingVideoO2TVGO()")
                        setPlayingTime(-1)
                    _db_.closeDB()
                else:
                    O2TVGO_VIDEO_LIVE = False
            except Exception as ex:
                _logDbg("An exception occured: "+str(ex))
                O2TVGO_VIDEO_LIVE = False
                _db_.closeDB()
                setPlayingTime(-1)
        #_logDbg(msg='Not playing m3u8', logIdSuffix="/isPlayingVideoO2TVGO()")
        return False
    setPlayingTime(-1)
    aPlayingNow = playingNow.split('/')
    sPlayingNowFileName = aPlayingNow[-1]
    aPlayingNowFileName = sPlayingNowFileName.split('.')
    sPlayingNowFileNameBase = aPlayingNowFileName[0]
    aParts = sPlayingNowFileNameBase.split('-')
    _logDbg(aParts)
    iCount = len(aParts)
    if iCount == 5:
        sChannelBaseName = sPlayingNowFileNameBase.rsplit('-', 2)[0]
    elif iCount == 4:
        sChannelBaseName = sPlayingNowFileNameBase.rpartition('-')[0]
    else:
        return False

    channelDict = _db_.getChannelByBaseName(sChannelBaseName)
    _db_.closeDB()
    if channelDict:
        return True
    else:
        return False

monitor = xbmc.Monitor()

while not monitor.abortRequested() and not xbmc.abortRequested:
    # Sleep/wait for abort for 5 seconds
    if monitor.waitForAbort(4) or xbmc.abortRequested:
        # Abort was requested while waiting. We should exit
        _logDbg(msg="abort was requested", logIdSuffix="/while")
        break

    if xbmc.Player().isPlayingVideo():
        try:
            O2TVGO_VIDEO = isPlayingVideoO2TVGO()
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            e = sys.exc_info()[0]
            _logDbg(msg='isPlayingVideoO2TVGO exception: ' + str(e), logIdSuffix="/while/exception")
            _logDbg(msg=traceback.format_exc(), logIdSuffix="/while/exception")
            O2TVGO_VIDEO = False
            setPlayingTime(-1)

    else:
        O2TVGO_VIDEO = False
        setPlayingTime(-1)


#    if not O2TVGO_VIDEO:
#        _db_.setIsCurrentlyPlayingTo0()
#        _db_.closeDB()
