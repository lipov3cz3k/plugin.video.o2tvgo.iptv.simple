# -*- coding: utf-8 -*-
import sqlite3
import re
import json

class O2tvgoDB:
    def __init__(self, db_path, profile_path, plugin_path, _notification_disable_all_, _logs_, scriptname="O2TVGO/IPTVSimple", logId="O2TVGO/IPTVSimple"):
        self.db_path = db_path
        self.connection = False
        self.cursor = False
        self.connectDB()
        self.profile_path = profile_path
        self.plugin_path = plugin_path
        self._notification_disable_all_ = _notification_disable_all_
        if _logs_:
            self._logs_ = _logs_
        else:
            from logs import Logs
            self._logs_ = Logs(scriptname, logId)
        self.logIdSuffix = "/db.py/O2tvgoDB"
        self.scriptname = scriptname
        self.logId = logId

        self.tablesOK = False

        self.check_tables()
        self.cleanEpgDuplicates(doDelete=True)
        self.cleanChannelDuplicates(doDelete=True)

    def __del__(self):
        self.cleanEpgDuplicates(doDelete=True)
        self.cleanChannelDuplicates(doDelete=True)
        self.closeDB()

    def log(self, msg):
        if self._logs_:
            return self._logs_.log(msg, idSuffix=self.logIdSuffix)
        else:
            print("["+self.logId+self.logIdSuffix+"] LOG: "+msg)
    def logDbg(self, msg):
        if self._logs_:
            return self._logs_.logDbg(msg, idSuffix=self.logIdSuffix)
        else:
            print("["+self.logId+self.logIdSuffix+"] LOG DBG: "+msg)
    def logNtc(self, msg):
        if self._logs_:
            return self._logs_.logNtc(msg, idSuffix=self.logIdSuffix)
        else:
            print("["+self.logId+self.logIdSuffix+"] LOG NTC: "+msg)
    def logWarn(self, msg):
        if self._logs_:
            return self._logs_.logWarn(msg, idSuffix=self.logIdSuffix)
        else:
            print("["+self.logId+self.logIdSuffix+"] LOG WARN: "+msg)
    def logErr(self, msg):
        if self._logs_:
            return self._logs_.logErr(msg, idSuffix=self.logIdSuffix)
        else:
            print("["+self.logId+self.logIdSuffix+"] LOG ERR: "+msg)
    def notificationInfo(self, msg, sound=False, force=False, dialog=True):
        self.logNtc(msg)
        if (dialog and not self._notification_disable_all_) or force:
            if self._logs_:
                return self._logs_.notificationInfo(msg, sound)
            else:
                print("["+self.logId+self.logIdSuffix+"] LOG NOTIF INFO: "+msg)
    def notificationWarning(self, msg, sound=True, force=False, dialog=True):
        self.logWarn(msg)
        if (dialog and not self._notification_disable_all_) or force:
            if self._logs_:
                return self._logs_.notificationWarning(msg, sound)
            else:
                print("["+self.logId+self.logIdSuffix+"] LOG NOTIF WARNING: "+msg)
    def notificationError(self, msg, sound=True, force=False, dialog=True):
        self.logErr(msg)
        if (dialog and not self._notification_disable_all_) or force:
            if self._logs_:
                return self._logs_.notificationError(msg, sound)
            else:
                print("["+self.logId+self.logIdSuffix+"] LOG NOTIF ERROR: "+msg)

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
            self.logWarn("Exception while executing a query ("+sql+"): "+str(ex))

    def cexecscript(self, sql, vals=None):
        if not self.connection:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
            self.connection.text_factory = str
            # enable foreign keys: #
            self.connection.execute("PRAGMA foreign_keys = 1")
            self.cursor = self.connection.cursor()

        try:
            if vals:
                self.cursor.executescript(sql, vals)
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

    def addChannel(self, key, keyClean, name, baseName, icon="", num=0):
        if not self.tablesOK:
            return False
        if not keyClean:
            keyClean = re.sub(r"[^a-zA-Z0-9_]", "_", key)
        id = self.cexec("INSERT INTO channels (\"key\", keyClean, name, baseName, icon, num) VALUES (?, ?, ?, ?, ?, ?)", (key, keyClean, name, baseName, icon, num))
        return id

    def getChannelID(self, id=None, keyOld=None, keyCleanOld=None, nameOld=None, silent=False):
        if not self.tablesOK:
            return False
        if not keyOld and not keyCleanOld and not nameOld and not id:
            self.logWarn("No criteria for getting channel!")
            return False
        if id:
            self.cexec("SELECT id FROM channels WHERE id = ?", (id,))
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
                vars = vars + (keyOld,)
            if keyCleanOld:
                if len(where) > 0:
                    where += " OR"
                    logWhere += " OR"
                where += " keyClean = ?"
                logWhere += " \"keyClean\" = "+keyCleanOld
                vars = vars + (keyCleanOld,)
            if nameOld:
                if len(where) > 0:
                    where += " OR"
                    logWhere += " OR"
                where += " name = ?"
                logWhere += " \"name\" = "+nameOld
                vars = vars + (nameOld,)
            self.cexec("SELECT id FROM channels WHERE "+where, vars)
            all = self.cursor.fetchall()
            rowcount = len(all)
            if rowcount > 1:
                self.logWarn("More than one row match the channel search criteria for: "+logWhere+"!")
                self.cleanChannelDuplicates(doDelete=True)
                return self.getChannelID(id, keyOld, keyCleanOld, nameOld, silent)
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
        id = self.getChannelID(id, keyOld, keyCleanOld, nameOld, True)
        if not id:
            return {}
        self.cexec("SELECT id, \"key\", keyClean, name, baseName, epgLastModTimestamp, icon, num FROM channels WHERE id = ?", (id,))
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
            "baseName": r[4],
            "epgLastModTimestamp": r[5],
            "icon": r[6],
            "num": r[7]
        }

    def getChannels(self):
        self.cexec("SELECT id, \"key\", name, epgLastModTimestamp, icon, num FROM channels")
        i = 0
        channelDict = {}
        for row in self.cursor:
            channelDict[i] = {
                "id": row["id"],
                "name": row["name"],
                "channel_key": row["key"],
                "epgLastModTimestamp": row["epgLastModTimestamp"],
                "icon": row["icon"],
                "num": row["num"]
            }
            i += 1
        return channelDict

    def updateChannel(self, key=None, keyClean=None, name=None, baseName=None, epgLastModTimestamp=None, icon=None, num=None, id=None, keyOld=None, keyCleanOld=None, nameOld=None):
        if not self.tablesOK:
            return False
        id = self.getChannelID(id, keyOld, keyCleanOld, nameOld, True)
        if id:
            rowDict = self.getChannelRow(id)
            if keyClean is None:
                keyClean = rowDict["keyClean"]
            if key is None:
                key = rowDict["key"]
            if name is None:
                name = rowDict["name"]
            if baseName is None:
                baseName = rowDict["baseName"]
            if epgLastModTimestamp is None:
                epgLastModTimestamp = rowDict["epgLastModTimestamp"]
            if icon is None:
                icon = rowDict["icon"]
            if num is None:
                num = rowDict["num"]
            self.cexec("UPDATE channels SET \"key\" = ?, keyClean = ?, name = ?, baseName = ?, epgLastModTimestamp = ?, icon = ?, num = ? WHERE id = ?", (key, keyClean, name, baseName, epgLastModTimestamp, icon, num, id))
        else:
            if not key or not name or not baseName:
                return False
            if not keyClean:
                keyClean = re.sub(r"[^a-zA-Z0-9_]", "_", key)
            if icon is None:
                icon = ""
            if num is None:
                num = 0
            return self.addChannel(key, keyClean, name, baseName, icon, num)
        return id

    def addEpg(self, epgId, start, startTimestamp, startEpgTime, end, endTimestamp, endEpgTime, title, plot="", plotoutline="", fanart_image="", genre="", genres="", isCurrentlyPlaying=None, isNextProgramme=None, inProgressTime=None, isRecentlyWatched=None, isWatchLater=None, channelID=None, channelKey=None, channelKeyClean=None, channelName=None):
        if not self.tablesOK:
            return False
        channelID = self.getChannelID(channelID, channelKey, channelKeyClean, channelName)
        if not channelID:
            return False
        inp = {}
        epgColumns = self._getEpgColumns()
        for col in epgColumns:
            loc = locals()
            if col in loc and loc[col]:
                inp[col] = loc[col]
            elif col in self._getEpgColumnsInt():
                inp[col] = 0
            else:
                inp[col] = ""
        id = self.cexec('''
            INSERT INTO epg (
                epgId, "start", startTimestamp, startEpgTime, "end", endTimestamp, endEpgTime,
                title, plot, plotoutline, fanart_image, genre, genres, channelID,
                isCurrentlyPlaying, isNextProgramme, inProgressTime, isRecentlyWatched, isWatchLater)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (inp["epgId"], inp["start"], inp["startTimestamp"], inp["startEpgTime"], inp["end"], inp["endTimestamp"], inp["endEpgTime"],
                         inp["title"], inp["plot"], inp["plotoutline"], inp["fanart_image"], inp["genre"], inp["genres"], channelID,
                         inp["isCurrentlyPlaying"], inp["isNextProgramme"], inp["inProgressTime"], inp["isRecentlyWatched"], inp["isWatchLater"])
                         )
        return id

    def getEpgID(self, id=None, epgIdOld=None, startOld=None, endOld=None, channelID=None, channelKey=None, channelKeyClean=None, channelName=None, silent=False):
        if not self.tablesOK:
            return False, False
        channelID = self.getChannelID(id=channelID, keyOld=channelKey, keyCleanOld=channelKeyClean, nameOld=channelName)
        if not channelID:
            return False, False

        if not epgIdOld and not startOld and not endOld and not id:
            self.logWarn("No criteria for getting epg!")
            return False, channelID
        if id:
            self.cexec("SELECT id FROM epg WHERE id = ? AND channelID = ?", (id, channelID))
            r = self.cursor.fetchone()
            if not r:
                if not silent:
                    self.logWarn("No row matches the epg search criteria for: id = "+id+" (and channelID = "+channelID+")!")
                return False, channelID
        else:
            where = ""
            logWhere = ""
            vars = ()
            if epgIdOld:
                where += "\"epgId\" = ?"
                logWhere += "\"epgId\" = "+str(epgIdOld)
                vars = vars + (epgIdOld,)
            else:
                if startOld:
                    if len(where) > 0:
                        where += " OR"
                        logWhere += " OR"
                    where += " start = ?"
                    logWhere += " \"start\" = "+str(startOld)
                    vars = vars + (startOld,)
                if endOld:
                    if len(where) > 0:
                        where += " OR"
                        logWhere += " OR"
                    where += " end = ?"
                    logWhere += " \"end\" = "+str(endOld)
                    vars = vars + (endOld,)
            where = "("+where+") AND channelID = ?"
            logWhere = "("+logWhere+") AND channelID = "+str(channelID)
            vars = vars + (channelID,)

            self.cexec("SELECT id FROM epg WHERE "+where, vars)
            all = self.cursor.fetchall()
            rowcount = len(all)
            if rowcount > 1:
                self.logWarn("More than one row match the epg search criteria for: "+logWhere+"!")
                res = self.cleanEpgDuplicates(doDelete=True)
                if res and "cleaned" in res and res["cleaned"]:
                    return self.getEpgID(id, epgIdOld, startOld, endOld, channelID, channelKey, channelKeyClean, channelName, silent)
                else:
                    self.logDbg("Duplicate cleaning result:")
                    self.logDbg(res)
            if rowcount == 0:
                if not silent:
                    self.logWarn("No row matches the epg search criteria for: "+logWhere+"!")
                return False, channelID
            r = all[0]
            id = r[0]
        return id, channelID

    def removeEpgFromList(self, epgRowID, listColumn):
        if not self.tablesOK:
            return False
        self.cexec("UPDATE epg SET "+listColumn+" = ? WHERE id = ?", (0, epgRowID))

    def updateEpg(self, epgId=None, start=None, startTimestamp=None, startEpgTime=None, end=None, endTimestamp=None, endEpgTime=None, title=None, plot=None, plotoutline=None, fanart_image=None, genre=None, genres=None, isCurrentlyPlaying=None, isNextProgramme=None, inProgressTime=None, isRecentlyWatched=None, isWatchLater=None, id=None, epgIdOld=None, startOld=None, endOld=None, channelID=None, channelKey=None, channelKeyClean=None, channelName=None):
        if not self.tablesOK:
            return False
        #def getEpgID(self, id=None, epgIdOld=None, startOld=None, endOld=None, channelID=None, channelKey=None, channelKeyClean=None, channelName=None, silent=False):
        id, channelID = self.getEpgID(id, epgIdOld, startOld, endOld, channelID, channelKey, channelKeyClean, channelName, True)
        if not channelID:
            return False
        if id:
            inp = {"id": id}
            epgRow = self.getEpgRow(id, channelID)
            epgColumns = self._getEpgColumns()
            for col in epgColumns:
                loc = locals()
                if col in loc and loc[col] is not None:
                    inp[col] = loc[col]
                elif col in epgRow and epgRow[col] is not None:
                    inp[col] = epgRow[col]
                elif col in self._getEpgColumnsInt():
                    inp[col] = 0
                else:
                    inp[col] = ""

            self.cexec('''
                UPDATE epg
                SET epgId = ?, "start" = ?, startTimestamp = ?, startEpgTime = ?, "end" = ?, endTimestamp = ?, endEpgTime = ?,
                    title = ?, plot = ?, plotoutline = ?, fanart_image = ?, genre = ?, genres = ?, channelID = ?,
                    isCurrentlyPlaying = ?, isNextProgramme = ?, inProgressTime = ?, isRecentlyWatched = ?, isWatchLater = ?
                WHERE id = ?''', (inp["epgId"], inp["start"], inp["startTimestamp"], inp["startEpgTime"], inp["end"], inp["endTimestamp"], inp["endEpgTime"],
                                  inp["title"], inp["plot"], inp["plotoutline"], inp["fanart_image"], inp["genre"], inp["genres"], inp["channelID"],
                                  inp["isCurrentlyPlaying"], inp["isNextProgramme"], inp["inProgressTime"], inp["isRecentlyWatched"], inp["isWatchLater"],
                                  id))
        else:
            id = self.addEpg(epgId, start, startTimestamp, startEpgTime, end, endTimestamp, endEpgTime, title, plot, plotoutline, fanart_image, genre, genres, isCurrentlyPlaying, isNextProgramme, inProgressTime, isRecentlyWatched, isWatchLater, channelID)
        return id

    def cleanEpgConflicts(self, doDelete=False):
        if not self.tablesOK:
            return False
        query = '''SELECT
                DISTINCT e.id AS id
            FROM epg e1
            JOIN epg e2 ON
                (
                    (e1."start" < e2."start" AND e1."end" > e2."start") OR (e1."start" < e2."end" AND e1."end" > e2."end")
                    OR
                    (((e1."start" <= e2."start" AND e1."end" > e2."start") OR (e1."start" < e2."end" AND e1."end" >= e2."end")) and e1.epgId != e2.epgId)
                ) AND e1.channelID = e2.channelID
            JOIN epg e ON e.id = e1.id OR e.id = e2.id
            LEFT JOIN epg ebef ON e."start" = ebef."end" AND e.channelID = ebef.channelID
            LEFT JOIN epg eaft ON e."end" = eaft."start" AND e.channelID = eaft.channelID
            WHERE ebef.id IS NULL OR eaft.id IS NULL
            ORDER BY e.channelID,e."start"'''
        self.cexec(query)
        toDelete = []
        for row in self.cursor:
            toDelete.append(row["id"])
        deletedCnt = len(toDelete)
        if deletedCnt > 0:
            if doDelete:
                self.cexec("DELETE FROM epg WHERE id IN (%s)" % ','.join('?'*len(toDelete)), toDelete)
                self.logNtc("Successfully deleted "+str(deletedCnt)+" EPG conflicts from the DB - IDs: "+", ".join(map(str, toDelete)))
            else:
                self.logNtc("There are "+str(deletedCnt)+" EPG conflicts to delete from the DB - IDs: "+", ".join(map(str, toDelete)))

        return deletedCnt

    def cleanEpgDuplicates(self, doDelete=False):
        if not self.tablesOK:
            return False
        self.cexec("SELECT epgId, COUNT(epgId) as cnt FROM epg GROUP BY epgId HAVING COUNT(epgId) > 1")
        duplicates = {}
        i = 0
        for row in self.cursor:
            duplicates[i] = {"epgId" : row["epgId"], "cnt": row["cnt"]}
            i += 1
        if not duplicates:
            return {"cleaned": False}
        toDelete = []
        for i in duplicates:
            epgId = duplicates[i]["epgId"]
            cnt = duplicates[i]["cnt"]
            limit = cnt - 1
            self.cexec("SELECT id FROM epg WHERE epgId = ? LIMIT ?", (epgId, limit))
            for row in self.cursor:
                toDelete.append(row["id"])
        if toDelete:
            if doDelete:
                self.logWarn("Deleting "+str(len(toDelete))+" epg duplicates from DB!")
                for id in toDelete:
                    self.cexec("DELETE FROM epg WHERE id = ?", (id,))
            return {
                "duplicates": duplicates,
                "toDelete": toDelete,
                "cleaned": len(toDelete)
            }
        else:
            self.logWarn("There were "+str(len(duplicates))+" duplicate epg IDs counted but no items in toDelete[]")
            return {
                "duplicates": duplicates,
                "cleaned": False
            }

    def cleanChannelDuplicates(self, doDelete=False):
        if not self.tablesOK:
            return False
        self.cexec("SELECT \"key\", COUNT(\"key\") as cnt FROM channels GROUP BY \"key\" HAVING COUNT(\"key\") > 1")
        duplicates = {}
        i = 0
        for row in self.cursor:
            duplicates[i] = {"key" : row["key"], "cnt": row["cnt"]}
            i += 1
        if not duplicates:
            return
        toDelete = []
        for i in duplicates:
            key = duplicates[i]["key"]
            cnt = duplicates[i]["cnt"]
            limit = cnt - 1
            self.cexec("SELECT id FROM channels WHERE \"key\" = ? LIMIT ?", (key, limit))
            for row in self.cursor:
                toDelete.append(row["id"])
        if toDelete:
            if doDelete:
                self.logWarn("Deleting "+str(len(toDelete))+" channel duplicates from DB!")
                for id in toDelete:
                    self.cexec("DELETE FROM channels WHERE id = ?", (id,))
            return {
                "duplicates": duplicates,
                "toDelete": toDelete
            }
        else:
            self.logWarn("There were "+str(len(duplicates))+" duplicate channel keys counted but no items in toDelete[]")
            return {
                "duplicates": duplicates
            }

    def cleanLockDuplicates(self, doDelete=False):
        if not self.tablesOK:
            return False
        self.cexec("SELECT \"name\", COUNT(\"name\") as cnt FROM lock GROUP BY \"name\" HAVING COUNT(\"name\") > 1")
        duplicates = {}
        i = 0
        for row in self.cursor:
            duplicates[i] = {"name" : row["name"], "cnt": row["cnt"]}
            i += 1
        if not duplicates:
            return
        toDelete = []
        for i in duplicates:
            name = duplicates[i]["name"]
            cnt = duplicates[i]["cnt"]
            limit = cnt - 1
            self.cexec("SELECT id FROM lock WHERE \"name\" = ? LIMIT ?", (name, limit))
            for row in self.cursor:
                toDelete.append(row["id"])
        if toDelete:
            if doDelete:
                self.logWarn("Deleting "+str(len(toDelete))+" lock duplicates from DB!")
                for id in toDelete:
                    self.cexec("DELETE FROM lock WHERE id = ?", (id,))
            return {
                "duplicates": duplicates,
                "toDelete": toDelete
            }
        else:
            self.logWarn("There were "+str(len(duplicates))+" duplicate lock names counted but no items in toDelete[]")
            return {
                "duplicates": duplicates
            }

    def cleanFavouriteDuplicates(self, doDelete=False):
        if not self.tablesOK:
            return False
        self.cexec("SELECT \"title_pattern\", COUNT(\"title_pattern\") as cnt FROM favourites GROUP BY \"title_pattern\" HAVING COUNT(\"title_pattern\") > 1")
        duplicates = {}
        i = 0
        for row in self.cursor:
            duplicates[i] = {"title_pattern" : row["title_pattern"], "cnt": row["cnt"]}
            i += 1
        if not duplicates:
            return
        toDelete = []
        for i in duplicates:
            title_pattern = duplicates[i]["title_pattern"]
            cnt = duplicates[i]["cnt"]
            limit = cnt - 1
            self.cexec("SELECT id FROM favourites WHERE \"title_pattern\" = ? LIMIT ?", (title_pattern, limit))
            for row in self.cursor:
                toDelete.append(row["id"])
        if toDelete:
            if doDelete:
                self.logWarn("Deleting "+str(len(toDelete))+" favourites duplicates from DB!")
                for id in toDelete:
                    self.cexec("DELETE FROM favourites WHERE id = ?", (id,))
            return {
                "duplicates": duplicates,
                "toDelete": toDelete
            }
        else:
            self.logWarn("There were "+str(len(duplicates))+" duplicate favourites names counted but no items in toDelete[]")
            return {
                "duplicates": duplicates
            }

    def deleteOldEpg(self, endBefore):
        return self.cexec("DELETE FROM epg WHERE \"end\" < ?", (endBefore,))

    def _getEpgColumns(self):
        return ["epgId", "start", "startTimestamp", "startEpgTime", "end", "endTimestamp", "endEpgTime", "title", "plot", "plotoutline", "fanart_image", "genre", "genres", "channelID",
                "isCurrentlyPlaying", "isNextProgramme", "inProgressTime", "isRecentlyWatched", "isWatchLater"]
    def _getEpgColumnsInt(self):
        return ["epgId", "start", "startTimestamp", "startEpgTime", "end", "endTimestamp", "endEpgTime", "isCurrentlyPlaying", "isNextProgramme", "inProgressTime", "isRecentlyWatched", "isWatchLater", "channelID"]

    def getEpgRow(self, id, channelID):
        if not self.tablesOK:
            return False
        self.cexec("SELECT * FROM epg where id = ? AND channelID = ?", (id, channelID))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
                elif col in self._getEpgColumnsInt():
                    epgDict[col] = 0
                else:
                    epgDict[col] = ""
            return epgDict

    def getEpgRowByStart(self, start, channelID):
        if not self.tablesOK:
            return False
        self.cexec("SELECT * FROM epg where \"start\" = ? AND channelID = ?", (start, channelID))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
                elif col in self._getEpgColumnsInt():
                    epgDict[col] = 0
                else:
                    epgDict[col] = ""
            return epgDict
        # No luck #
        self.cexec("SELECT * FROM epg where \"start\" < ? AND \"end\" > ? AND channelID = ?", (start, start, channelID))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
                elif col in self._getEpgColumnsInt():
                    epgDict[col] = 0
                else:
                    epgDict[col] = ""
            return epgDict
        return {}

    def getEpgRowByEnd(self, end, channelID):
        if not self.tablesOK:
            return False
        self.cexec("SELECT * FROM epg where \"end\" = ? AND channelID = ?", (end, channelID))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
                elif col in self._getEpgColumnsInt():
                    epgDict[col] = 0
                else:
                    epgDict[col] = ""
            return epgDict
        # No luck #
        self.cexec("SELECT * FROM epg where \"start\" < ? AND \"end\" > ? AND channelID = ?", (end, end, channelID))
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
                elif col in self._getEpgColumnsInt():
                    epgDict[col] = 0
                else:
                    epgDict[col] = ""
            return epgDict
        return {}

    def getEpgRows(self, channelID):
        if not self.tablesOK:
            return False
        self.cexec("SELECT * FROM epg where channelID = ?", (channelID,))
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
                elif col in self._getEpgColumnsInt():
                    epgDict[index][col] = 0
                else:
                    epgDict[index][col] = ""
            i += 1
        return epgDict

    def getEpgRowsByList(self, list):
        if not self.tablesOK:
            return False
        if not list in ["favourites", "isRecentlyWatched", "isWatchLater", "inProgressTime"]:
            return []
        if list == "favourites":
            self.cexec("SELECT * FROM favourites")
            where = ""
            vars = ()
            for row in self.cursor:
                if len(where) > 0:
                    where += " OR "
                where += "e.title LIKE ?"
                vars = vars + ("%"+row["title_pattern"]+"%",)
        else:
            where = "e."+list+" > ?"
            vars = (0,)
        if len(where) == 0:
            return []
        self.cexec("SELECT e.*, ch.name AS channelName, CAST(strftime('%s','now') AS INTEGER) > e.\"end\" isPast FROM epg e JOIN channels ch ON e.channelID = ch.id WHERE "+where+" ORDER BY isPast DESC, e.title ASC, e.startTimestamp ASC", vars)
        epgList = []
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"],
                "channelName": row["channelName"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
                elif col in self._getEpgColumnsInt():
                    epgDict[col] = 0
                else:
                    epgDict[col] = ""
            epgList.append(epgDict)
        return epgList

    def getChannelsByGenre(self, genre):
        if not self.tablesOK:
            return False
        query = '''
            SELECT e.channelID, ch.name, ch.icon, COUNT(ch.id) as cnt
            FROM epg e
            JOIN channels ch
            ON e.channelID = ch.id
            WHERE e.genre LIKE ?
            GROUP BY ch.id
            ORDER BY ch.num ASC
        '''
        # AND ch.num > 0
        self.cexec(query, ("%"+genre+"%",))
        channelList = []
        for row in self.cursor:
            channelDict = {
                "channelID": row["channelID"],
                "channelName": row["name"],
                "icon": row["icon"],
                "count": row["cnt"]
            }
            channelList.append(channelDict)
        return channelList

    def getEpgByGenre(self, genre, channelID):
        if not self.tablesOK:
            return False
        self.cexec('''SELECT e.*, ch.name, CAST(strftime('%s','now') AS INTEGER) > e.\"end\" isPast
            FROM epg e JOIN channels ch on e.channelID = ch.id
            WHERE e.genre like ? AND e.channelID = ?
            ORDER BY isPast DESC, e.title ASC, e.startTimestamp ASC''', ("%"+genre+"%", channelID))
        epgList = []
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"],
                "channelName": row["name"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
                elif col in self._getEpgColumnsInt():
                    epgDict[col] = 0
                else:
                    epgDict[col] = ""
            epgList.append(epgDict)
        return epgList

    def moveEpgToWatched(self):
        if not self.tablesOK:
            return False
        timeFromEnd = 10*60
        self.cexec("SELECT id FROM epg WHERE inProgressTime > 0 AND (\"end\" - \"start\" - inProgressTime) < ?", (timeFromEnd,))
        rowCount = len(self.cursor.fetchall())
        if rowCount > 0:
            self.cexec("UPDATE epg SET inProgressTime = 0, isWatchLater = 0, isRecentlyWatched = 1 WHERE inProgressTime > 0 AND (\"end\" - \"start\" - inProgressTime) < ?", (timeFromEnd,))
        return rowCount

    def getEpgChannelRow(self, epgRowID):
        if not self.tablesOK:
            return False
        self.cexec("SELECT e.*, ch.name AS channelName, ch.key AS channelKey FROM epg e JOIN channels ch ON e.channelID = ch.id WHERE e.id = ?", (epgRowID,))
        i = 0
        epgDict = {}
        epgColumns = self._getEpgColumns()
        for row in self.cursor:
            epgDict = {
                "id": row["id"],
                "channelName": row["channelName"],
                "channelKey": row["channelKey"]
            }
            for col in epgColumns:
                if row[col]:
                    epgDict[col] = row[col]
                elif col in self._getEpgColumnsInt():
                    epgDict[col] = 0
                else:
                    epgDict[col] = ""
            i += 1
        return epgDict

    def setLock(self, name, val=None):
        if not self.tablesOK:
            return False
        lockVal = self.getLock(name=name, defaultVal=-1)
        if not val:
            val = 0
        if lockVal == -1:
            self.cexec("INSERT INTO lock (name, val) VALUES (?, ?)", (name, val))
        else:
            self.cexec("UPDATE lock SET val = ? WHERE name = ?", (val, name))

    def getLock(self, name, silent=True, defaultVal=0):
        if not self.tablesOK:
            return False
        self.cexec("SELECT val FROM lock WHERE name = ?", (name,))
        all = self.cursor.fetchall()
        rowcount = len(all)
        if rowcount > 1:
            self.logWarn("More than one row match the lock search criteria for: name = "+name+"!")
            self.cleanLockDuplicates(doDelete=True)
            return self.getLock(name, silent, defaultVal)
        if rowcount == 0:
            if not silent:
                self.logWarn("No row matches the lock search criteria for: name = "+name+"!")
            return defaultVal
        r = all[0]
        val = r[0]
        return val

    def clearCurrentlyPlaying(self):
        self.cexec("UPDATE epg SET isCurrentlyPlaying = ? WHERE isCurrentlyPlaying = ?", (0, 1))

    def clearNextProgramme(self):
        self.cexec("UPDATE epg SET isNextProgramme = ? WHERE isNextProgramme = ?", (0, 1))
    def getFavourites(self):
        if not self.tablesOK:
            return False
        self.cexec("SELECT * FROM favourites ORDER BY title_pattern ASC")
        favList = []
        for row in self.cursor:
            if "title_pattern" in row or not row["title_pattern"]:
                title_pattern = ""
            else:
                title_pattern = row["title_pattern"]
            favDict = {
                "id": row["id"],
                "title_pattern": title_pattern
            }
            favList.append(favDict)
        return favList

    def getFavourite(self, rowID=None, title_pattern=None, silent=True):
        if not self.tablesOK or (not rowID and not title_pattern):
            return False
        if title_pattern:
            self.cexec("SELECT title_pattern FROM favourites WHERE title_pattern = ?", (title_pattern,))
        else:
            self.cexec("SELECT title_pattern FROM favourites WHERE id = ?", (rowID,))
        all = self.cursor.fetchall()
        rowcount = len(all)
        if rowcount > 1:
            self.logWarn("More than one row match the favourites search criteria for: id = "+str(rowID)+"!")
            self.cleanFavouriteDuplicates(doDelete=True)
            return self.getFavourite(rowID)
        if rowcount == 0:
            if not silent:
                self.logWarn("No row matches the favourites search criteria for: id = "+str(rowID)+"!")
            return False
        r = all[0]
        val = r[0]
        return val

    def addFavourite(self, title_pattern):
        if not self.tablesOK:
            return False
        val = self.getFavourite(title_pattern=title_pattern)
        if val:
            return True
        else:
            self.cexec("INSERT INTO favourites (title_pattern) VALUES (?)", (title_pattern,))

    def updateFavourite(self, rowID, title_pattern):
        if not self.tablesOK:
            return False
        self.cexec("UPDATE favourites SET title_pattern = ? WHERE id = ?", (title_pattern, rowID))
        self.cleanFavouriteDuplicates(doDelete=True)

    def removeFavourite(self, rowID):
        if not self.tablesOK:
            return False
        self.cexec("DELETE FROM favourites WHERE id = ?", (rowID,))

    def getEpgListCounts(self, silent=True):
        if not self.tablesOK:
            return False
        sql = '''SELECT SUM(isInProgress) isInProgress, SUM(isRecentlyWatched) isRecentlyWatched, SUM(isWatchLater) isWatchLater, (SELECT COUNT(distinct title_pattern) FROM favourites) favourites
            FROM (
                SELECT id, CASE WHEN inProgressTime > 0 THEN 1 ELSE 0 END isInProgress, CASE WHEN isRecentlyWatched > 0 THEN 1 ELSE 0 END isRecentlyWatched, CASE WHEN isWatchLater > 0 THEN 1 ELSE 0 END isWatchLater
                FROM epg
                WHERE inProgressTime > 0 OR isRecentlyWatched > 0 OR isWatchLater > 0
       ) '''
        self.cexec(sql)
        all = self.cursor.fetchall()
        rowcount = len(all)
        if rowcount > 1:
            self.logWarn("More than one row was returned in getEpgListCounts()!")
        if rowcount == 0:
            if not silent:
                self.logWarn("No row was returned in getEpgListCounts()!")
            return {
                "isInProgress": 0,
                "isRecentlyWatched": 0,
                "isWatchLater": 0,
                "favourites": 0
            }
        r = all[0]
        return {
            "isInProgress": r[0],
            "isRecentlyWatched": r[1],
            "isWatchLater": r[2],
            "favourites": r[3]
        }

    def getEpgGenres(self):
        if not self.tablesOK:
            return False
        query = '''
            SELECT genres, COUNT(genres) AS cnt
            FROM epg
            WHERE genres <> ''
            GROUP BY genres
            ORDER BY cnt DESC
        '''
        self.cexec(query)
        genreUnknown = 'iné/nezaradené'
        genreUnknownKey = 'in_/nezaraden_'
        genreCounts = {}
        genreMap = {}
        for row in self.cursor:
            genresJsonString = row["genres"]
            count = int(row["cnt"])
            try:
                genreList = json.loads(genresJsonString)
                for genre in genreList:
                    genreKey = re.sub(r"[^a-zA-Z0-9_/-]", "_", genre)
                    genreMap[genreKey] = genre
                    if not genreKey in genreCounts:
                        genreCounts[genreKey] = 0
                    genreCounts[genreKey] += count
            except Exception as ex:
                self.logWarn("Exception while loading JSON ("+genresJsonString+"): "+str(ex))
        genres = []
        if genreCounts:
            for genreKey in sorted(genreCounts, key=genreCounts.get, reverse=True):
                if genreKey == genreUnknownKey:
                    continue
                genres.append({
                    "title": genreMap[genreKey],
                    "key": genreKey,
                    "count": genreCounts[genreKey]
                })
            if genreUnknownKey in genreCounts:
                genres.append({
                    "title": genreUnknown,
                    "key": genreUnknownKey,
                    "count": genreCounts[genreUnknownKey]
                })
        return genres
