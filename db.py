import sqlite3,  re

class O2tvgoDB:
    def __init__(self,  db_path, profile_path, plugin_path, _notification_disable_all_, _logs_):
        self.db_path = db_path
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.text_factory = str
        # enable foreign keys: #
        self.connection.execute("PRAGMA foreign_keys = 1")
        self.cursor = self.connection.cursor()
        self.profile_path = profile_path
        self.plugin_path = plugin_path
        self._notification_disable_all_ = _notification_disable_all_
        self._logs_ = _logs_
        self.tablesOK = False
        
        self.check_tables()
    
    def log(self, msg,  level):
        if self._logs_:
            return self._logs_.log(msg,  level)
        else:
            print("LOG: "+msg)
    def logDbg(self, msg):
        if self._logs_:
            return self._logs_.logDbg(msg)
        else:
            print("LOG DBG: "+msg)
    def logNtc(self, msg):
        if self._logs_:
            return self._logs_.logNtc(msg)
        else:
            print("LOG NTC: "+msg)
    def logWarn(self, msg):
        if self._logs_:
            return self._logs_.logWarn(msg)
        else:
            print("LOG WARN: "+msg)
    def logErr(self, msg):
        if self._logs_:
            return self._logs_.logErr(msg)
        else:
            print("LOG ERR: "+msg)
    def notificationInfo(self, msg, sound = False,  force = False, dialog = True):
        self.logNtc(msg)
        if (dialog and not self._notification_disable_all_) or force:
            if self._logs_:
                return self._logs_.notificationInfo(msg,  sound)
            else:
                print("LOG NOTIF INFO: "+msg)
    def notificationWarning(self, msg, sound = True,  force = False, dialog = True):
        self.logWarn(msg)
        if (dialog and not self._notification_disable_all_) or force:
            if self._logs_:
                return self._logs_.notificationWarning(msg,  sound)
            else:
                print("LOG NOTIF WARNING: "+msg)
    def notificationError(self, msg, sound = True,  force = False, dialog = True):
        self.logErr(msg)
        if (dialog and not self._notification_disable_all_) or force:
            if self._logs_:
                return self._logs_.notificationError(msg,  sound)
            else:
                print("LOG NOTIF ERROR: "+msg)

    def commit(self):
        self.connection.commit()
    
    def cexec(self, sql, vals=None):
        try:
            if vals:
                self.cursor.execute(sql, vals)
            else:
                self.cursor.execute(sql)
            self.commit()
            return self.cursor.lastrowid
        except Exception as ex:
            self.logWarn("Exception while executing a query ("+sql+"): "+str(ex))
    
    def cexecscript(self, sql, vals=None):
        try:
            if vals:
                self.cursor.executescript(sql,  vals)
            else:
                self.cursor.executescript(sql)
            self.commit()
            return True
        except Exception as ex:
            self.logWarn("Exception while creating a script query: "+str(ex))
            self.logNtc("The script query was: "+sql)
        return False
    
    def check_tables(self):
        expectedCount = 4
        self.cexec("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('epg', 'channels', 'favourites', 'lock');")
        rowcount = len(self.cursor.fetchall())
        createTablesSql = None
        createTablesPath = None
        if rowcount == expectedCount:
            self.tablesOK = True
            # self.logNtc("All tables exist")
        else:
            self.logNtc("Creating tables")
            try:
                createTablesPath = self.plugin_path + "create_tables.sql"
                with open(createTablesPath) as f:
                    createTablesSql = f.read()
                    res = self.cexecscript(createTablesSql)
                    if res:
                        self.tablesOK = True
            except Exception as ex:
                self.logWarn("Exception while creating tables: "+str(ex))
                print(createTablesPath)
                print(createTablesSql)
    
    def addChannel(self, key, keyClean, name, baseName):
        if not self.tablesOK:
            return False
        if not keyClean:
            keyClean = re.sub(r"[^a-zA-Z0-9_]", "_", key)
        id = self.cexec("INSERT INTO channels (\"key\", keyClean, name, baseName) VALUES (?, ?, ?, ?)",  (key, keyClean, name, baseName))
        return id
    
    def getChannelID(self, id=None, keyOld=None, keyCleanOld=None, nameOld=None, silent=False):
        if not self.tablesOK:
            return False
        if not keyOld and not keyCleanOld and not nameOld and not id:
            self.logWarn("No criteria for getting channel!")
            return False
        if id:
            self.cexec("SELECT id FROM channels WHERE id = ?",  (id, ))
            r = self.cursor.fetchone()
            if not r:
                if not silent:
                    self.logWarn("No row matches the channel search criteria for: id = "+id+"!")
                return False
        else:
            where = ""
            logWhere = ""
            vars = ()
            if keyOld:
                where += "\"key\" = ?"
                logWhere += "\"key\" = "+keyOld
                vars = vars + (keyOld, )
            if keyCleanOld:
                if len(where) > 0:
                    where += " OR"
                    logWhere += " OR"
                where += " keyClean = ?"
                logWhere += " \"keyClean\" = "+keyCleanOld
                vars = vars + (keyCleanOld, )
            if nameOld:
                if len(where) > 0:
                    where += " OR"
                    logWhere += " OR"
                where += " name = ?"
                logWhere += " \"name\" = "+nameOld
                vars = vars + (nameOld, )
            self.cexec("SELECT id FROM channels WHERE "+where,  vars)
            all = self.cursor.fetchall()
            rowcount = len(all)
            if rowcount > 1:
                self.logWarn("More than one row match the channel search criteria for: "+logWhere+"!")
                return False
            elif rowcount == 0:
                if not silent:
                    self.logWarn("No row matches the channel search criteria for: key = "+logWhere+"!")
                return False
            r = all[0]
            id = r[0]
        return id
    
    def getChannelRow(self, id=None, keyOld=None, keyCleanOld=None, nameOld=None, silent=False):
        if not self.tablesOK:
            return False
        id = self.getChannelID(id, keyOld, keyCleanOld, nameOld,  True)
        if not id:
            return {}
        self.cexec("SELECT id, \"key\", keyClean, name, epgLastModTimestamp FROM channels WHERE id = ?",  (id, ))
        r = self.cursor.fetchone()
        if not r:
            if not silent:
                self.logWarn("No row matches the channel search criteria for: id = "+id+"!")
            return {}
        return {
            "id": r[0], 
            "key": r[1], 
            "keyClean": r[2], 
            "name": r[3], 
            "epgLastModTimestamp": r[4]
        }
    
    def getChannels(self):
        self.cexec("SELECT id, \"key\", name, epgLastModTimestamp FROM channels")
        i = 0
        channelDict = {}
        for row in self.cursor:
            channelDict[i] = {
                "id": row["id"], 
                "name": row["name"],
                "channel_key": row["key"], 
                "epgLastModTimestamp": row["epgLastModTimestamp"]
            }
            i += 1
        return channelDict
    
    def updateChannel(self, key=None, keyClean=None, name=None, baseName=None, epgLastModTimestamp=None,  id=None, keyOld=None, keyCleanOld=None, nameOld=None):
        if not self.tablesOK:
            return False
        id = self.getChannelID(id, keyOld, keyCleanOld, nameOld,  True)
        if id:
            rowDict = self.getChannelRow(id)
            if not keyClean:
                keyClean = rowDict["keyClean"]
            if not key:
                key = rowDict["key"]
            if not name:
                name = rowDict["name"]
            if not baseName:
                baseName = rowDict["baseName"]
            if not epgLastModTimestamp:
                epgLastModTimestamp = rowDict["epgLastModTimestamp"]
            self.cexec("UPDATE channels SET \"key\" = ?, keyClean = ?, name = ?, baseName = ?, epgLastModTimestamp = ? WHERE id = ?",  (key, keyClean, name, baseName, epgLastModTimestamp, id ))
        else:
            if not key or not name or not baseName:
                return False
            if not keyClean:
                keyClean = re.sub(r"[^a-zA-Z0-9_]", "_", key)
            return self.addChannel(key, keyClean, name, baseName)
        return id

    def addEpg(self, epgId, start, startTimestamp, startEpgTime, end, endTimestamp, endEpgTime, title, plot="", plotoutline="", fanart_image="", genre="", genres="", isCurrentlyPlaying=None, isNextProgramme=None, inProgressTime=None, isRecentlyWatched=None, isWatchLater=None, channelID=None,  channelKey=None,  channelKeyClean=None,  channelName=None):
        if not self.tablesOK:
            return False
        channelID = self.getChannelID(channelID,  channelKey,  channelKeyClean,  channelName)
        if not channelID:
            return False
        id = self.cexec('''
            INSERT INTO epg (
                epgId, "start", startTimestamp, startEpgTime, "end", endTimestamp, endEpgTime,
                title, plot, plotoutline, fanart_image, genre, genres, channelID,
                isCurrentlyPlaying, isNextProgramme, inProgressTime, isRecentlyWatched, isWatchLater)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                          (epgId, start, startTimestamp, startEpgTime, end, endTimestamp, endEpgTime,
                            title, plot, plotoutline, fanart_image, genre, genres, channelID, 
                            isCurrentlyPlaying, isNextProgramme, inProgressTime, isRecentlyWatched, isWatchLater)
        )
        return id
    
    def getEpgID(self, id=None, epgIdOld=None, startOld=None, endOld=None, channelID=None,  channelKey=None,  channelKeyClean=None,  channelName=None, silent=False):
        if not self.tablesOK:
            return False, False
        channelID = self.getChannelID(id=channelID,  keyOld=channelKey,  keyCleanOld = channelKeyClean,  nameOld = channelName)
        if not channelID:
            return False, False
        
        if not epgIdOld and not startOld and not endOld and not id:
            self.logWarn("No criteria for getting epg!")
            return False, False
        if id:
            self.cexec("SELECT id FROM epg WHERE id = ? AND channelID = ?",  (id, channelID))
            r = self.cursor.fetchone()
            if not r:
                if not silent:
                    self.logWarn("No row matches the epg search criteria for: id = "+id+" (and channelID = "+channelID+")!")
                return False, False
        else:
            where = ""
            logWhere = ""
            vars = ()
            if epgIdOld:
                where += "\"epgId\" = ?"
                logWhere += "\"epgId\" = "+str(epgIdOld)
                vars = vars + (epgIdOld, )
            if startOld:
                if len(where) > 0:
                    where += " OR"
                    logWhere += " OR"
                where += " start = ?"
                logWhere += " \"start\" = "+str(startOld)
                vars = vars + (startOld, )
            if endOld:
                if len(where) > 0:
                    where += " OR"
                    logWhere += " OR"
                where += " end = ?"
                logWhere += " \"end\" = "+str(endOld)
                vars = vars + (endOld, )
            where = "("+where+") AND channelID = ?"
            logWhere = "("+logWhere+") AND channelID = "+str(channelID)
            vars = vars + (channelID, )
            
            self.cexec("SELECT id FROM epg WHERE "+where,  vars)
            all = self.cursor.fetchall()
            rowcount = len(all)
            if rowcount > 1:
                self.logWarn("More than one row match the epg search criteria for: "+logWhere+"!")
                return False, False
            if rowcount == 0:
                if not silent:
                    self.logWarn("No row matches the epg search criteria for: "+logWhere+"!")
                return False, False
            r = all[0]
            id = r[0]
        return id, channelID
    
    def updateEpg(self, epgId=None, start=None, startTimestamp=None, startEpgTime=None, end=None, endTimestamp=None, endEpgTime=None, title=None, plot="", plotoutline="", fanart_image="", genre="", genres="", isCurrentlyPlaying=None, isNextProgramme=None, inProgressTime=None, isRecentlyWatched=None, isWatchLater=None, id=None, epgIdOld=None, startOld=None, endOld=None, channelID=None,  channelKey=None,  channelKeyClean=None,  channelName=None):
        if not self.tablesOK:
            return False
        id, channelID = self.getEpgID(id, epgIdOld, startOld, endOld, channelID, channelKey, channelKeyClean, channelName,  True)
        if not channelID:
            return False
        if id:
            inp = {"id": id}
            epgRow = self.getEpgRow(id, channelID)
            epgColumns = self._getEpgColumns()
            for col in epgColumns:
                loc = locals()
                if col in loc and loc[col]:
                    inp[col] = loc[col]
                elif col in epgRow and epgRow[col]:
                    inp[col] = epgRow[col]
                elif col in {"isCurrentlyPlaying", "isNextProgramme", "isInProgress", "isRecentlyWatched", "isWatchLater"}:
                    inp[col] = 0
                else:
                    inp[col] = None
                    
            self.cexec('''
                UPDATE epg
                SET epgId = ?, "start" = ?, startTimestamp = ?, startEpgTime = ?, "end" = ?, endTimestamp = ?, endEpgTime = ?,
                    title = ?, plot = ?, plotoutline = ?, fanart_image = ?, genre = ?, genres = ?, channelID = ?,
                    isCurrentlyPlaying = ?, isNextProgramme = ?, inProgressTime = ?, isRecentlyWatched = ?, isWatchLater = ?
                WHERE id = ?''',  (inp["epgId"], inp["start"], inp["startTimestamp"], inp["startEpgTime"], inp["end"], inp["endTimestamp"], inp["endEpgTime"],
                                    inp["title"], inp["plot"], inp["plotoutline"], inp["fanart_image"], inp["genre"], inp["genres"], inp["channelID"],
                                    inp["isCurrentlyPlaying"], inp["isNextProgramme"], inp["inProgressTime"], inp["isRecentlyWatched"], inp["isWatchLater"],
                                    id ))
        else:
            id = self.addEpg(epgId, start, startTimestamp, startEpgTime, end, endTimestamp, endEpgTime, title, plot, plotoutline, fanart_image, genre, genres, isCurrentlyPlaying, isNextProgramme, inProgressTime, isRecentlyWatched, isWatchLater, channelID)
        return id
    
    def deleteOldEpg(self, endBefore):
        return self.cexec("DELETE FROM epg WHERE \"end\" < ?",  (endBefore, ))
    
    def _getEpgColumns(self):
        return ["epgId", "start", "startTimestamp", "startEpgTime", "end", "endTimestamp", "endEpgTime", "title", "plot", "plotoutline", "fanart_image", "genre", "genres", "channelID",
                  "isCurrentlyPlaying", "isNextProgramme", "inProgressTime", "isRecentlyWatched", "isWatchLater"]
    
    def getEpgRow(self, id, channelID):
        if not self.tablesOK:
            return False
        self.cexec("SELECT * FROM epg where id = ? AND channelID = ?",  (id, channelID))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"]
            }
            for col in epgColumns:
                if row[col] or row[col] == 0 or row[col] == '0':
                    epgDict[col] = row[col]
            return epgDict

    def getEpgRowByStart(self, start, channelID):
        if not self.tablesOK:
            return False
        self.cexec("SELECT * FROM epg where \"start\" = ? AND channelID = ?",  (start, channelID))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
            return epgDict
        # No luck #
        self.cexec("SELECT * FROM epg where \"start\" < ? AND \"end\" > ? AND channelID = ?",  (start, start, channelID))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
            return epgDict
        return {}

    def getEpgRows(self, channelID):
        if not self.tablesOK:
            return False
        self.cexec("SELECT * FROM epg where channelID = ?",  (channelID, ))
        i = 0
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            index = row["start"]
            epgDict[index] = {
                "id": row["id"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[index][col] = row[col]
            i += 1
        return epgDict
    
    def setLock(self, name, val=None):
        if not self.tablesOK:
            return False
        if val:
            self.cexec("INSERT OR REPLACE INTO lock (name, val) VALUES (?, ?)",  (name, val))
        else:
            self.cexec("INSERT OR REPLACE INTO lock (name, val) VALUES (?, ?)",  (name, 0 ))
    
    def getLock(self, name,  silent=True):
        if not self.tablesOK:
            return False
        self.cexec("SELECT val FROM lock WHERE name = ?",  (name, ))
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
        
    def clearCurrentlyPlaying(self):
        self.cexec("UPDATE epg SET isCurrentlyPlaying = ? WHERE isCurrentlyPlaying = ?",  (0, 1))
        
    def clearNextProgramme(self):
        self.cexec("UPDATE epg SET isNextProgramme = ? WHERE isNextProgramme = ?",  (0, 1))