#!/usr/bin/env python
# -*- coding: utf-8 -*-

## START: Copied from the original plugin by Štěpán Ort ##
import sys
import os
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import urllib, urllib2
import json
import random
from uuid import getnode as get_mac
## END: Copied from the original plugin by Štěpán Ort ##
import datetime
import time
import gzip
import re
import glob
import traceback
try:
    # Python 3
    from urllib.parse import urlparse, parse_qs
except ImportError:
    # Python 2
    from urlparse import urlparse, parse_qs
import xml.etree.ElementTree as etree

from o2tvgo import O2TVGO, LiveChannel, AuthenticationError, ChannelIsNotBroadcastingError, TooManyDevicesError, RequestError
from logs import Logs
from jsonrpc import JsonRPC
from db import O2tvgoDB

reload(sys)
sys.setdefaultencoding('utf-8')

params = False

try:
    ###############################################################################
    ## Globals ##
    _addon_ = xbmcaddon.Addon('plugin.video.o2tvgo.iptv.simple')
    _scriptname_ = _addon_.getAddonInfo('name')
    _logId_ = "O2TVGO/IPTVSimple"
    _logs_ = Logs(scriptname=_scriptname_, id=_logId_)
    _jsonRPC_ = JsonRPC(_logs_=_logs_, scriptname=_scriptname_, logId=_logId_)
    _addon_pvrIptvSimple_ = None
    _useIptvSimpleTimeshift_ = True
    _epgTimeshift_ = 0

    def _isAddonInstalled(addonId):
        addons = _jsonRPC_._getAddons()
        if addons:
            for addon in addons:
                if addonId == addon["addonid"]:
                    return True
            return False
        else:
            # No/incorrect response from jsonrpc server
            return False

    def _getPvrIptvSimpleEpgShift(default):
        global _addon_pvrIptvSimple_
        shift = None
        if not _addon_pvrIptvSimple_:
            pluginDetails = _jsonRPC_._getAddonDetails("pvr.iptvsimple")
            if pluginDetails:
                #logNtc("Response: "+_toString(pluginDetails))
                enabled = pluginDetails["enabled"]
                if enabled:
                    _addon_pvrIptvSimple_ = xbmcaddon.Addon('pvr.iptvsimple')
                else:
                    response = _jsonRPC_._setAddonEnabled("pvr.iptvsimple", True)
                    if response:
                        xbmc.sleep(1000)
                        _addon_pvrIptvSimple_ = xbmcaddon.Addon('pvr.iptvsimple')
        if _addon_pvrIptvSimple_:
            shift = _addon_pvrIptvSimple_.getSetting("epgTimeShift")
        if not shift:
            msg = _lang_(30250) % default
            notificationWarning(msg)
            logErr(msg)
            shift = default
        return float(shift)

    ## START: Copied from the original plugin by Štěpán Ort ##
    def _deviceId():
        mac = get_mac()
        hexed = hex((mac*7919)%(2**64))
        return ('0000000000000000'+hexed[2:-1])[16:]

    def _randomHex16():
        return ''.join([random.choice('0123456789abcdef') for x in range(16)])

    ## START changes by @ch ##

    ## First run ##
    if not (_addon_.getSetting("settings_init_done") == 'true'):
        O2TVGO_SETTING_KEYS = ['username', 'password', 'send_errors', 'device_id']
        o2tvGoAddonId = "plugin.video.o2tvgo"
        isO2TVGoInstalled = _isAddonInstalled(o2tvGoAddonId)
        if isO2TVGoInstalled:
            o2tvGoPluginDetails = _jsonRPC_._getAddonDetails(o2tvGoAddonId)
            if o2tvGoPluginDetails and "enabled" in o2tvGoPluginDetails:
                isO2TVGoEnabled = o2tvGoPluginDetails["enabled"]
                if isO2TVGoEnabled:
                    _logs_.logNtc("Setting values from O2TV Go plugin")
                    _addon_o2tvgo_ = xbmcaddon.Addon(o2tvGoAddonId)
                    for settingKey in O2TVGO_SETTING_KEYS:
                        settingVal = _addon_o2tvgo_.getSetting(settingKey)
                        if settingVal:
                            _addon_.setSetting(settingKey, settingVal)
        _logs_.logNtc("Setting default values")
        DEFAULT_SETTING_VALUES = {
            'send_errors' : 'false',
            'use_iptv_simple_timeshift': 'true',
            'epg_timeshift' : str(_getPvrIptvSimpleEpgShift(0)),
            'channel_refresh_rate': '3',
            'epg_refresh_rate': '12',
            'limit_epg_per_batch': 'true',
            'epg_fetch_batch_limit': '10',
            'epg_fetch_batch_timeout': '10',
            'force_restart': 'false',
            'use_additional_m3u': '0',
            'use_additional_epg': '0',
            'configure_cron': 'false',
            'notification_disable_all': 'false',
            'notification_refreshing_started': 'true',
            'notification_pvr_restart': 'true',
        }
        for setting in DEFAULT_SETTING_VALUES.keys():
            val = _addon_.getSetting(setting)
            if not val:
                _addon_.setSetting(setting, DEFAULT_SETTING_VALUES[setting])
        _addon_.setSetting("settings_init_done", "true")

    ## Get / set timeshift ##
    _useIptvSimpleTimeshift_ = (_addon_.getSetting('use_iptv_simple_timeshift') == 'true')
    if _useIptvSimpleTimeshift_:
        _epgTimeshift_ = _getPvrIptvSimpleEpgShift(0)
        timeshiftLoc = _addon_.getSetting('epg_timeshift')
        if float(timeshiftLoc) != _epgTimeshift_:
            _addon_.setSetting("epg_timeshift", str(_epgTimeshift_))
    else:
        _epgTimeshift_ = _addon_.getSetting('epg_timeshift')
        if _epgTimeshift_:
            _epgTimeshift_ = float(_epgTimeshift_)

    ## Get refresh rates and limits and other settings as global vars ##
    _epg_refresh_rate_ = (int(_addon_.getSetting('epg_refresh_rate')) * 60 * 60) - (10 * 60)
    _limit_epg_per_batch_ = (_addon_.getSetting('limit_epg_per_batch') == 'true')
    _epg_fetch_batch_limit_ = 999999
    _epgLockTimeout_ = 0
    _requestErrorTimeoutMin_ = 15
    _requestErrorTimeout_ = _requestErrorTimeoutMin_*60
    if _limit_epg_per_batch_:
        _epg_fetch_batch_limit_ = int(_addon_.getSetting('epg_fetch_batch_limit'))
        _epgLockTimeout_ = (int(_addon_.getSetting('epg_fetch_batch_timeout')) * 60)
    _channel_refresh_rate_ = (int(_addon_.getSetting('channel_refresh_rate')) * 60 * 60) - (10 * 60)
    _force_restart_ = (_addon_.getSetting('force_restart') == 'true')
    _use_additional_m3u_ = not (_addon_.getSetting('use_additional_m3u') == '0')
    if _use_additional_m3u_:
        # TODO: 1 - file, 2 - folder, 3 - pattern
        _m3u_additional_ = xbmc.translatePath('special://home/o2tvgo-prgs-additional.m3u')
    _use_additional_epg_ = not (_addon_.getSetting('use_additional_epg') == '0')
    if _use_additional_epg_:
        # TODO: 1 - file, 2 - folder, 3 - pattern
        _xmltv_additional_filelist_pattern_ = xbmc.translatePath('special://home/rytecxmltv*.gz')
        _xmltv_additional_ = xbmc.translatePath('special://home/merged_epg.xml')
        _xmltv_additional_gzip_ = xbmc.translatePath('special://home/merged_epg.xml.gz')
        _xmltv_test_output_file_ = xbmc.translatePath('special://home/merged_xml_test_out.xml')
    _configure_cron_ = (_addon_.getSetting('configure_cron') == 'true')
    _notification_disable_all_ = (_addon_.getSetting('notification_disable_all') == 'true')
    _notification_refreshing_started_ = (_addon_.getSetting('notification_refreshing_started') == 'true')
    _notification_pvr_restart_ = (_addon_.getSetting('notification_pvr_restart') == 'true')
    _logFilePath_ = xbmc.translatePath('special://logpath/kodi.log')

    ## END changes by @ch ##

    _device_id_ = _addon_.getSetting("device_id")
    if not _device_id_:
        first_device_id = _deviceId()
        second_device_id = _deviceId()
        if first_device_id == second_device_id:
            _device_id_ = first_device_id
        else:
            _device_id_ = _randomHex16()
            ## START changes by @ch ##
#            if _device_name_:
#                _device_id_ = _fromDeviceId()
#            else:
#                _device_id_ = _randomHex16()
            ## END changes by @ch ##
        _addon_.setSetting("device_id", _device_id_)

    ###############################################################################
    _profile_ = xbmc.translatePath(_addon_.getAddonInfo('profile')).decode("utf-8")
    _lang_ = _addon_.getLocalizedString
    _xml_lang_ = "cz"
#    _first_error_ = (_addon_.getSetting('first_error') == "true")
    _send_errors_ = (_addon_.getSetting('send_errors') == "true")
    _version_ = _addon_.getAddonInfo('version')
    _username_ = _addon_.getSetting("username")
    _password_ = _addon_.getSetting("password")
    _format_ = 'video/' + _addon_.getSetting('format').lower()
    _icon_o2tvgo_ = xbmc.translatePath(os.path.join(_addon_.getAddonInfo('path'), 'icon.png'))
    _icon_folder_ = xbmc.translatePath(os.path.join(_addon_.getAddonInfo('path'), 'icons/'))
    _epg_genre_icon_folder_ = _icon_folder_ + 'genres/t-'
    _epg_genre_icon_map_ = {
        "sci-fi/fantasy": "sci-fi-and-fantasy.png",
        "ak_n_/dobrodru_n_": "action-and-adventure.png",
        "dokument": "documentary.png",
        "drama": "drama.png",
        "krimi": "crime.png",
        "thriller": "thriller.png",
        "komedi_ln_": "comedy.png",
        "d_tsk_/rodinn_": "family.png",
        "serial": "tv-series.png",
        "romantick_": "romance.png",
        "sport": "sport.png",
        "in_/nezaraden_": "default.png",
        "default": "default.png"
    }
    _handle_ = int(sys.argv[1])
    _baseurl_ = sys.argv[0]

    _o2tvgo_ = O2TVGO(_device_id_, _username_, _password_, _logs_, _scriptname_, _logId_)

    _db_path_ = _profile_+'o2tvgo.db'
    _addon_path_ = _addon_.getAddonInfo('path')+"/"
    _db_ = O2tvgoDB(_db_path_, _profile_, _addon_path_, _notification_disable_all_, _logs_, _scriptname_, _logId_)

    _db_.setLock("timeshift", _epgTimeshift_)

    ###############################################################################
    def _fetchChannels():
        global _o2tvgo_
        channels = None
        ex = False
        while not channels:
            try:
                channels = _o2tvgo_.live_channels()
            except AuthenticationError:
                if ex:
                    return None
                ex = True
                d = xbmcgui.Dialog()
                d.notification(_scriptname_, _lang_(30003), xbmcgui.NOTIFICATION_ERROR)
                _reload_settings()
            except TooManyDevicesError:
                d = xbmcgui.Dialog()
                d.notification(_scriptname_, _lang_(30006), xbmcgui.NOTIFICATION_ERROR)
                return None
            except RequestError:
                _db_.setLock("saveEpgRunning", time.time()+_requestErrorTimeout_)
                d.notification(_scriptname_, _lang_(30513) % str(_requestErrorTimeoutMin_)+" minutes", xbmcgui.NOTIFICATION_ERROR)
                return None
        return channels

    def _reload_settings():
        _addon_.openSettings()
#        global _first_error_
#        _first_error_ = (_addon_.getSetting('first_error') == "true")
        global _send_errors_
        _send_errors_ = (_addon_.getSetting('send_errors') == "true")
        global _username_
        _username_ = _addon_.getSetting("username")
        global _password_
        _password_ = _addon_.getSetting("password")
        global _o2tvgo_
        _o2tvgo_ = O2TVGO(_device_id_, _username_, _password_, _logs_, _scriptname_, _logId_)


    ## END: Copied from the original plugin by Štěpán Ort ##

    ###############################################################################
    ## Logging, debugging, messages - just redeclaring the methods from Logging so I don't have to rewrite every occurence
    def _toString(text):
        return _logs_._toString(text)
    def log(msg, level=xbmc.LOGDEBUG, idSuffix=""):
        return _logs_.log(msg, level, idSuffix)
    def logDbg(msg, idSuffix=""):
        return _logs_.logDbg(msg, idSuffix)
    def logNtc(msg, idSuffix=""):
        return _logs_.logNtc(msg, idSuffix)
    def logWarn(msg, idSuffix=""):
        return _logs_.logWarn(msg, idSuffix)
    def logErr(msg, idSuffix=""):
        return _logs_.logErr(msg, idSuffix)
    def notificationInfo(msg, sound=False, force=False, dialog=True, idSuffix=""):
        logNtc(msg, idSuffix)
        if (dialog and not _notification_disable_all_) or force:
            return _logs_.notificationInfo(msg, sound)
    def notificationWarning(msg, sound=True, force=False, dialog=True, idSuffix=""):
        logWarn(msg, idSuffix)
        if (dialog and not _notification_disable_all_) or force:
            return _logs_.notificationWarning(msg, sound)
    def notificationError(msg, sound=True, force=False, dialog=True, idSuffix=""):
        logErr(msg, idSuffix)
        if (dialog and not _notification_disable_all_) or force:
            return _logs_.notificationError(msg, sound)

    ###############################################################################
    ## Globals ##
    _xmltv_ = xbmc.translatePath('special://home/o2tvgo-epg.xml')
    _m3u_ = xbmc.translatePath('special://home/o2tvgo-prgs.m3u')
    # DEPRECATED BEGIN #
    _xmltv_json_base_ = _profile_+'o2tvgo-epg-'
    _m3u_json_ = _profile_+'o2tvgo-prgs.json'
    _next_programme_ = _profile_+'o2tvgo-next_programme.json'
    _restart_ok_ = _profile_+'o2tvgo-restart_ok.txt'
    _save_epg_lock_file_ = _profile_+'o2tvgo-save_epg.lock'
    # DEPRECATED END #

    ###############################################################################
    def _emptyFunction():
        logDbg("function was replaced with a dummy empty one")

    def upgradeConfigsFromJsonToDb():
        silentAdd = True
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
                        id = _db_.getChannelID(keyOld=ch["channel_key"], keyCleanOld=channelKeyClean, silent=silentAdd)
                        if not id:
                            index = indexesByKey[ch["channel_key"]]
                            baseName = baseNamesByIndexes[index]
                            idNew = _db_.addChannel(ch["channel_key"], channelKeyClean, ch["name"], baseName)
                            if not idNew:
                                successM3U = False
                if channelsDict and "chJsNumByIndex" in channelsDict:
                    for i in channelsDict["chJsNumByIndex"]:
                        channelKey = channelsDict["keysByIndex"][i]
                        channelKeyClean = re.sub(r"[^a-zA-Z0-9_]", "_", channelKey)
                        channelID = _db_.getChannelID(keyOld=channelKey, keyCleanOld=channelKeyClean)
                        successEpg = True
                        jsonEpgFile = None
                        if channelID:
                            channelJsonNumber = channelsDict["chJsNumByIndex"][i]
                            jsonEpgFilePath = _xmltv_json_base_ + str(channelJsonNumber) + ".json"
                            jsonEpgFile = xbmc.translatePath(jsonEpgFilePath)
                            if os.path.exists(jsonEpgFile):
                                successEpg = False
                                with open(jsonEpgFile) as data_file:
                                    epg = json.load(data_file)
                                    successEpg = True
                                    for key in sorted(epg.iterkeys()):
                                        oneEpg = epg[key]
                                        idEpg, channelIDFound = _db_.getEpgID(epgIdOld=oneEpg["epgId"], startOld=oneEpg["start"], channelID=channelID, silent=silentAdd)
                                        if not idEpg:
                                            idNew = _db_.addEpg(
                                                epgId=oneEpg["epgId"],
                                                start=oneEpg["start"],
                                                startTimestamp=oneEpg["startTimestamp"],
                                                startEpgTime=oneEpg["startEpgTime"],
                                                end=oneEpg["end"],
                                                endTimestamp=oneEpg["endTimestamp"],
                                                endEpgTime=oneEpg["endEpgTime"],
                                                title=oneEpg["title"],
                                                plot=oneEpg["plot"],
                                                plotoutline=oneEpg["plotoutline"],
                                                fanart_image=oneEpg["fanart_image"],
                                                genre=oneEpg["genre"],
                                                genres=json.dumps(oneEpg["genres"]),
                                                channelID=channelID)
                                            if idNew:
                                                logNtc("Successfully imported EPG #"+str(oneEpg["epgId"])+" with new ID #"+str(idNew)+" from JSON file into DB.")
                                            else:
                                                successEpg = False
                                                successM3U = False
                                    if successEpg:
                                        logNtc("Successfully imported all EPG of channel #"+str(channelID)+" from JSON file into DB.")
                                        if jsonEpgFile:
                                            logNtc("Removing JSON file: "+jsonEpgFile)
                                            os.remove(jsonEpgFile)

                if successM3U:
                    logNtc("Successfully imported all JSON channels into DB. Removing JSON file: "+_m3u_json_)
                    os.remove(_m3u_json_)

            except Exception as e:
#                exc_type, exc_value, exc_traceback = sys.exc_info()
#                traceback.print_tb(exc_traceback, file=sys.stdout)
                logWarn("Exception while reading channels from json: "+str(e))
                return False
        if os.path.exists(_restart_ok_):
            lastRestartOK = os.path.getmtime(_restart_ok_)
            _db_.setLock("lastRestart", lastRestartOK)
            os.remove(_restart_ok_)

        if os.path.exists(_save_epg_lock_file_):
            fMtime = os.path.getmtime(_save_epg_lock_file_)
            _db_.setLock("saveEpgRunning", fMtime)
            os.remove(_save_epg_lock_file_)
        queries = {
            'emptyGenreUpdated': [
                "UPDATE epg SET genre = 'jiné/nezařazené' WHERE genre = ''"
            ],
            'genreUpdated': [
                "UPDATE epg SET genre = REPLACE(genre, ' - ', ' / ') WHERE genre LIKE '% - %'",
                "UPDATE epg SET genre = REPLACE(genre, 'akční / dobrodružné','akční/dobrodružné') WHERE genre LIKE '%akční / dobrodružné%'",
                "UPDATE epg SET genre = REPLACE(genre, 'dětské / rodinné','dětské/rodinné') WHERE genre LIKE '%dětské / rodinné%'",
                "UPDATE epg SET genre = REPLACE(genre, 'sci-fi / fantasy','sci-fi/fantasy') WHERE genre LIKE '%sci-fi / fantasy%'",
                "UPDATE epg SET genre = REPLACE(genre, 'jiné / nezařazené','jiné/nezařazené') WHERE genre LIKE '%jiné / nezařazené%'"
            ],
            'channelColumnsAdded': [
                "ALTER TABLE channels ADD icon TEXT",
                "ALTER TABLE channels ADD num INTEGER DEFAULT 0"
            ]
        }
        for lockName in queries:
            lockVal = _db_.getLock(lockName)
            if not lockVal:
                for query in queries[lockName]:
                    _db_.cexec(query)
                _db_.setLock(lockName, time.time())
        return True

    def _openIptvSimpleClientSettings():
        pluginDetails = _jsonRPC_._getAddonDetails("pvr.iptvsimple")
        if pluginDetails:
            enabled = pluginDetails["enabled"]
            if enabled:
                addon = xbmcaddon.Addon('pvr.iptvsimple')
                addon.openSettings()

    def _fetchEpg(channel_key, hoursToLoad=24, hoursToLoadFrom=None, forceFromTimestamp=None):
        global _o2tvgo_
        _o2tvgo_.channel_key = channel_key
        _o2tvgo_.hoursToLoad = hoursToLoad
        if forceFromTimestamp:
            _o2tvgo_.forceFromTimestamp = forceFromTimestamp
        elif hoursToLoadFrom:
            _o2tvgo_.hoursToLoadFrom = hoursToLoadFrom
        epg_list = _o2tvgo_.channel_epg()
        return epg_list

    def _fetchEpgDetail(epg_id):
        global _o2tvgo_
        _o2tvgo_.epg_id = epg_id
        epg_detail = _o2tvgo_.epg_detail()
        return epg_detail

        player = xbmc.Player()
        isPlaying = player.isPlayingVideo()
        if not isPlaying:
            return None, None
        playingNow = player.getPlayingFile()
        if not playingNow:
            return None, None
        aPlayingNow = playingNow.split('/')
        playingNowFileName = aPlayingNow[-1]
        logDbg(playingNowFileName)
        return playingNow, playingNowFileName

#    def compareChannelHosts(ch1, ch2):
#        aCh1 = ch1.split('/')
#        aCh2 = ch2.split('/')
#        return aCh1[3] == aCh2[3]

    def dirListing(what=None, refresh=0, calledFrom=None, genre=None, channelID=None):
        if not what:
            # TODO: icons
            counts = _db_.getEpgListCounts()
            if counts["isInProgress"] > 0:
                addDirectoryItem("In progress", _baseurl_+"?inprogr=1", image=_icon_folder_ + "in-progress.png", isFolder=True)
            if counts["isWatchLater"] > 0:
                addDirectoryItem("Watch later", _baseurl_+"?watchlater=1", image=_icon_folder_ + "watch-later.png", isFolder=True)
            addDirectoryItem("Favourites", _baseurl_+"?favourites=1", isFolder=True, image=_icon_folder_ + "favourites.png")
            if counts["isRecentlyWatched"] > 0:
                addDirectoryItem("Watched", _baseurl_+"?recentlywatched=1", image=_icon_folder_ + "watched.png", isFolder=True)
            addDirectoryItem("Genres", _baseurl_+"?genres=1", image=_epg_genre_icon_folder_ + _epg_genre_icon_map_["default"], isFolder=True)
            addDirectoryItem("Show logs", _baseurl_+"?showlogs=1", image=_icon_folder_ + "eventlog.png", isFolder=False)
            addDirectoryItem("Refresh channels and/or EPG", _baseurl_+"?saveepg=1&forcenotifications=1", image=_icon_folder_ + "refresh.png", isFolder=False)
            cacheToDisc = True
        else:
            cacheToDisc = False
            #cacheToDisc=True
            if what == "inProgress":
                itemRows = _db_.getEpgRowsByList(list="inProgressTime")
            elif what == "favourites":
                itemRows = _db_.getEpgRowsByList(list="favourites")
            elif what == "recentlyWatched":
                itemRows = _db_.getEpgRowsByList(list="isRecentlyWatched")
            elif what == "watchLater":
                itemRows = _db_.getEpgRowsByList(list="isWatchLater")
            elif what == "favouritesKeywords":
                itemRows = _db_.getFavourites()
            elif what == 'Genres':
                itemRows = _db_.getEpgGenres()
                #logDbg(itemRows)
            elif what == 'GenreChannels':
                itemRows = _db_.getChannelsByGenre(genre)
                xbmcgui.Window(10025).setProperty('SearchedGenre', genre)
            elif what == 'GenreEpg':
                itemRows = _db_.getEpgByGenre(genre, channelID)
                xbmcgui.Window(10025).setProperty('SearchedGenre', genre)
                channelRow = _db_.getChannelRow(id=channelID)
                xbmcgui.Window(10025).setProperty('ChannelName', channelRow["name"])
            else:
                itemRows = []
            if itemRows:
                for item in itemRows:
                    if "fanart_image" in item and len(item["fanart_image"]) > 0:
                        imageNew = _getLogoUrl(item["fanart_image"])
                        if imageNew != item["fanart_image"]:
                            item["fanart_image"] = imageNew
                            _db_.updateEpg(id=item["id"], channelID=item["channelID"], fanart_image=imageNew)
                    if what == "favouritesKeywords":
                        addDirectoryItem(item["title_pattern"], _baseurl_+"?favouritekeywordedit=1&rowid="+str(item["id"]), isFolder=False, calledFromList=what, item=item)
                    elif what == 'Genres':
                        if item["key"] in _epg_genre_icon_map_:
                            genreIcon = _epg_genre_icon_folder_ + _epg_genre_icon_map_[item["key"]]
                        else:
                            genreIcon = _epg_genre_icon_folder_ + _epg_genre_icon_map_["default"]
                        addDirectoryItem(item["title"]+" ("+str(item["count"])+")", _baseurl_+"?genrechannels="+item["title"], isFolder=True, image=genreIcon)
                    elif what == 'GenreChannels':
                        if "icon" in item and len(item["icon"]) > 0:
                            channelIcon = item["icon"]
                            channelIconNew = _getLogoUrl(channelIcon)
                            if channelIcon != channelIconNew:
                                channelIcon = channelIconNew
                                _db_.updateChannel(icon=channelIcon, id=item["channelID"])
                        else:
                            channelIcon = _icon_o2tvgo_
                        addDirectoryItem(item["channelName"]+" ("+str(item["count"])+")", _baseurl_+"?genreepg="+genre+"&channelid="+str(item["channelID"]), image=channelIcon, isFolder=True)
                    else:
                        itemInfo = ""
                        progressInfo = ""
                        hasProgress = False
                        if what == "inProgress":
                            inProgressTime = item["inProgressTime"]
                            length = item["end"] - item["start"]
                            sTimeProgress = time.strftime('%H:%M:%S', time.gmtime(inProgressTime))
                            sTimeLength = time.strftime('%H:%M:%S', time.gmtime(length))
                            progressInfo = sTimeProgress+" / "+sTimeLength+" | "
                        elif "inProgressTime" in item and item["inProgressTime"] > 0:
                            hasProgress = True
                            inProgressTime = item["inProgressTime"]
                            length = item["end"] - item["start"]
                            sTimeProgress = time.strftime('%H:%M:%S', time.gmtime(inProgressTime))
                            sTimeLength = time.strftime('%H:%M:%S', time.gmtime(length))
                        olderThan = (int(time.time()) -  (2*24*3600))
                        ttlSeconds = item["end"] - olderThan
                        ttlMinus = ""
                        if ttlSeconds < 0:
                            ttlMinus = "-"
                            ttlSeconds = 0-ttlSeconds
                        if ttlSeconds >= (24*3600):
                            ttlSeconds -= (24*3600) # Because time.gmtime() shows day 0 as 1 (date)
                            ttlFormat = '-%d %H:%M'
                        else:
                            ttlFormat = '%d %H:%M'
                        ttl = ttlMinus+time.strftime(ttlFormat, time.gmtime(ttlSeconds))
                        airingTime = _timestampToNiceDateTime(item["start"], item["end"])
                        if calledFrom == "home":
                            if what == "favourites" and (("isRecentlyWatched" in item and item["isRecentlyWatched"] > 0) or hasProgress or ("isWatchLater" in item and item["isWatchLater"] > 0)):
                                continue
                            if "end" in item and item["end"] >= time.time():
                                continue
                            itemTitle = item["channelName"]
                        elif what == "GenreEpg":
                            itemTitle = item["title"]+" | "+progressInfo+airingTime + " | TTL: "+ttl
                        else:
                            itemTitle = item["channelName"]+": "+item["title"]+" | "+progressInfo+airingTime + " | TTL: "+ttl
                        itemInfo += airingTime+"\n"
                        if progressInfo or hasProgress:
                            itemInfo += "Progress: "+sTimeProgress+" / "+sTimeLength+"\n"
                        itemInfo += "TTL: "+ttl+"\n"
                        itemInfo += "\n"
                        if item['fanart_image']:
                            icon = item["fanart_image"]
                        else:
                            icon = _icon_o2tvgo_
                        addDirectoryItem(itemTitle, _baseurl_+"?playfromepg=1&epgrowid="+str(item["id"])+'&calledfrom='+what, image=icon, icon=icon, isFolder=False, title=item["title"], item=item, calledFromList=what, itemInfo=itemInfo)
            if what == "favourites" and calledFrom != "home":
                addDirectoryItem("Edit keywords", _baseurl_+"?favouriteskeywords=1", image=_icon_o2tvgo_, isFolder=True)
            if what == "favouritesKeywords":
                addDirectoryItem("[Add keyword]", _baseurl_+"?favouritekeywordadd=1", image=_icon_o2tvgo_, isFolder=False)

        updateListing = False
        if refresh:
            updateListing = True
        xbmcplugin.endOfDirectory(_handle_, cacheToDisc=cacheToDisc, updateListing=updateListing)
        if refresh:
            xbmc.executebuiltin('Container.Refresh')

    def addDirectoryItem(label, url, plot=None, title=None, icon=_icon_o2tvgo_, image=None, isFolder=True, calledFromList=None, item=None, itemInfo=None):
        li = xbmcgui.ListItem(label)
        if calledFromList is not None and len(calledFromList) > 0:
            li.setProperty("O2TVGoItem", calledFromList)
        elif isFolder:
            li.setProperty("O2TVGoItem", "Folder")
        else:
            li.setProperty("O2TVGoItem", "Item")

        if item is not None and len(item) > 0:
            if "id" in item:
                li.setProperty('EpgRowID', str(item["id"]))
            if "channelID" in item:
                li.setProperty('ChannelID', str(item["channelID"]))

        videoinfo = {}
        if calledFromList and calledFromList != "inProgress" and item is not None and "isRecentlyWatched" in item and item["isRecentlyWatched"]:
            videoinfo["playcount"] = 1
        if len(videoinfo) > 0:
            li.setInfo('video', videoinfo)

        actionList = []
        timeNow = time.time()
        if item and len(item)>0:
            if "end" in item and item["end"] < timeNow:
                if "start" in item and "channelID" in item:
                    previousProgrammeEpg = _db_.getEpgRowByEnd(end=item["start"], channelID=item["channelID"])
                    if previousProgrammeEpg and "start" in previousProgrammeEpg and "end" in previousProgrammeEpg and "id" in previousProgrammeEpg:
                        offsetFromEnd = 10*60
                        length = (previousProgrammeEpg["end"] - previousProgrammeEpg["start"])
                        if (length)>offsetFromEnd:
                            startOffset = length - offsetFromEnd
                        else:
                            startOffset = 0
                        action = 'RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?playfromepg=1&epgrowid='+str(previousProgrammeEpg["id"])+'&startoffset='+str(startOffset)+')'
                        actionList.append(('Play previous programme (last 10 minutes)', action))
                        li.setProperty('O2TVGoItem.Action.PlayPrevious', action)
                if "channelID" in item and calledFromList and calledFromList != "recentlyWatched" and "isRecentlyWatched" in item and item["isRecentlyWatched"] == 0:
                    action = 'RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?markaswatched=1&epgrowid='+str(item["id"])+'&channelid='+str(item["channelID"])+')'
                    actionList.append(('Mark as watched (O2TVGo)', action))
                    li.setProperty('O2TVGoItem.Action.MarkWatched', action)
            elif "title" in item:
                li.setLabel("("+label+")")
                url=_baseurl_+"?notification_programmeinfuture=1&programmetitle="+item["title"]
        if calledFromList and calledFromList == "favouritesKeywords":
            action = 'RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?favouritekeywordedit=1&rowid='+str(item["id"])+')'
            actionList.append(('Edit', action))
            li.setProperty('O2TVGoItem.Action.EditFavouriteKeyword', action)
            action = 'RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?favouritekeyworddelete=1&rowid='+str(item["id"])+')'
            actionList.append(('Remove', action))
            li.setProperty('O2TVGoItem.Action.RemoveFavouriteKeyword', action)
#            li.addContextMenuItems(actionList)
            xbmcplugin.addDirectoryItem(handle=_handle_, url=url, listitem=li, isFolder=isFolder)
            return
        if item is not None and (("plotoutline" in item and len(item["plotoutline"]) > 0) or ("plot" in item and len(item["plot"]) > 0)) and "id" in item and "channelID" in item:
            #actionList.append(('Show plot','RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?showplot=1&epgrowid='+str(item["id"])+'&channelid='+str(item["channelID"])+')'))
            action = 'Action(info)'
            actionList.append(('Show info', action))
            li.setProperty('O2TVGoItem.Action.ShowInfo', action)
        if not title:
            title = label
        liVideo = {'title': title}
        if plot:
            liVideo['plot'] = plot
        if item:
            if "fanart_image" in item and item["fanart_image"] and len(item["fanart_image"]) > 0:
                li.setArt({
                  'icon': item["fanart_image"],
                  "fanart": item["fanart_image"],
                  "poster": item["fanart_image"]
                })
            if "plot" in item and item["plot"] and len(item["plot"]) > 0:
                liVideo['plot'] = item['plot']
            if "plotoutline" in item and item["plotoutline"] and len(item["plotoutline"]) > 0:
                liVideo['plotoutline'] = item['plotoutline']
            if "genre" in item and item["genre"]:
                liVideo['genre'] = item["genre"]
            li.addStreamInfo('video', {'duration': item["end"]-item["start"]})

        if calledFromList:
            if calledFromList == "inProgress" or (item and len(item)>0 and "inProgressTime" in item and item["inProgressTime"] > 0):
                li.setProperty('StartOffset', str(item["inProgressTime"]))
                li.setProperty("ResumeTime", str(item["inProgressTime"]))
                action = 'RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?playfromepg=1&epgrowid='+str(item["id"])+')'
                actionList.append(('Play from beginning', action))
                li.setProperty('O2TVGoItem.Action.PlayFromBeginning', action)
            if calledFromList != "watchLater" and "isRecentlyWatched" in item and item["isRecentlyWatched"] == 0:
                if "isWatchLater" in item:
                    if item["isWatchLater"]:
                        action = 'RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?removefromlist=watchLater&epgrowid='+str(item["id"])+')'
                        actionList.append(('Don\'t watch later', action))
                        li.setProperty('O2TVGoItem.Action.DontWatchLater', action)
                    else:
                        action = 'RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?addtowatchlater=1&channelid='+str(item["channelID"])+'&epgrowid='+str(item["id"])+')'
                        actionList.append(('Watch later', action))
                        li.setProperty('O2TVGoItem.Action.WatchLater', action)
            if calledFromList != "favourites" and calledFromList != "GenreEpg" and item is not None and "id" in item:
                action = 'RunPlugin(plugin://plugin.video.o2tvgo.iptv.simple?removefromlist='+calledFromList+'&epgrowid='+str(item["id"])+')'
                actionList.append(('Remove from this list', action))
                li.setProperty('O2TVGoItem.Action.RemoveFromList', action)
                #logDbg("Setting property "+'O2TVGoItem.Action.RemoveFromList_'+calledFromList)
                li.setProperty('O2TVGoItem.Action.RemoveFromList_'+calledFromList, action)
#        if actionList:
#            li.addContextMenuItems(actionList)

        if image:
            li.setThumbnailImage(image)
        li.setIconImage(icon)
        if itemInfo:
            if 'plot' in liVideo:
                liVideo['plot'] = itemInfo+liVideo['plot']
            else:
                liVideo['plot'] = itemInfo
        li.setInfo("video", liVideo)
#        if "genre" in liVideo:
#            logDbg("GENRE")
#            logDbg(liVideo["genre"])
#            logDbg(li.getProperty("GenreType"))
        xbmcplugin.addDirectoryItem(handle=_handle_, url=url, listitem=li, isFolder=isFolder)

    def openGenreDirListing(genre):
        xbmc.executebuiltin('ActivateWindow(10025, "plugin://plugin.video.o2tvgo.iptv.simple?genre='+genre+'",return)')
        return

    def refreshHome(section=None):
        ts = str(int(time.time() / 2))
        if not section:
            xbmcgui.Window(10000).setProperty('O2TVGoRefreshHomeWatched', ts)
            xbmcgui.Window(10000).setProperty('O2TVGoRefreshHomeInProgress', ts)
            xbmcgui.Window(10000).setProperty('O2TVGoRefreshHomeWatchLater', ts)
            xbmcgui.Window(10000).setProperty('O2TVGoRefreshHomeFavourites', ts)
            xbmcgui.Window(10000).setProperty('O2TVGoRefreshHomeGenres', ts)
        else:
            xbmcgui.Window(10000).setProperty('O2TVGoRefreshHome'+section, ts)
        xbmc.executebuiltin('Container.Refresh')

    def showEpgPlot(epgRowID, channelID):
        epg = _db_.getEpgRow(id=epgRowID, channelID=channelID)
        if not epg:
            notificationWarning("Couldn't retrieve EPG for rowID="+str(epgRowID)+" and channelID="+str(channelID))
            return
        plot = ""
        if "plot" in epg:
            plot += epg["plot"]
        if "plotoutline" in epg and len(epg["plotoutline"]) > 0 and epg["plotoutline"] not in plot:
            if len(plot) > 0:
                plot = "\n\n" + plot
            plot = epg["plotoutline"] + plot
        if len(plot) > 0:
            xbmcgui.Dialog().textviewer("Plot: "+epg["title"], plot)

    def favouriteKeywordAction(action, rowID=None, titlePattern=None):
        if action=="edit":
            if not rowID:
                return False
            titlePattern = _db_.getFavourite(rowID=rowID)
            if titlePattern:
                titlePatternNew = xbmcgui.Dialog().input("Edit favourite", defaultt=titlePattern, type=xbmcgui.INPUT_ALPHANUM)
                if not titlePatternNew:
                    return False
                _db_.updateFavourite(rowID=rowID, title_pattern=titlePatternNew)
                notificationInfo(_lang_(30277) % titlePatternNew)
        elif action=="delete":
            if not rowID:
                return False
            _db_.removeFavourite(rowID=rowID)
            notificationInfo(_lang_(30276))
        elif action=="add":
            defaultVal = ""
            if titlePattern:
                defaultVal = titlePattern
            titlePatternNew = xbmcgui.Dialog().input("Add favourite", defaultt=defaultVal, type=xbmcgui.INPUT_ALPHANUM)
            if not titlePatternNew:
                return False
            _db_.addFavourite(title_pattern=titlePatternNew)
            notificationInfo(_lang_(30274) % titlePatternNew)
        xbmc.executebuiltin('Container.Refresh')
        refreshHome("Favourites")

    def showNotification(type, programmeTitle=None):
        if type == "programmeInFuture" and programmeTitle:
            notificationWarning(_lang_(30260) % programmeTitle, sound=False, force=True)

    def removeEpgFromList(removeFromList, epgRowID):
        logDbg("Removing epg with id "+str(epgRowID)+" from list "+removeFromList)
        listColDict = {
            "inProgress": "inProgressTime",
            "favourites": "isFavourite",
            "recentlyWatched": "isRecentlyWatched",
            "watchLater": "isWatchLater"
        }
#        listHomeSectionDict = {
#            "inProgress": "InProgress",
#            "favourites": "Favourites",
#            "recentlyWatched": "Watched",
#            "watchLater": "WatchLater"
#        }
        if not removeFromList in listColDict:
            return
        listColumn = listColDict[removeFromList]
        _db_.removeEpgFromList(epgRowID, listColumn)
        notificationInfo(_lang_(30275))
        #refreshHome(listHomeSectionDict[removeFromList])
        refreshHome()

    def showLogs():
        if os.path.exists(_logFilePath_):
            logFile = open(_logFilePath_, 'r')
            if logFile:
                contentLines = []
                isPreviousLineOurs = False
                for logEntry in logFile:
                    if _scriptname_ in logEntry or _logId_ in logEntry:
                        if "showlogs=1" in logEntry:
                            continue
                        line = re.sub(r"T\:\d+\s*", "", logEntry).replace(_scriptname_, _logId_)
                        contentLines.append(line)
                        isPreviousLineOurs = True
                    elif "Previous line repeats" in logEntry and isPreviousLineOurs:
                        line = re.sub(r"T\:\d+\s*", "", logEntry)
                        contentLines.append(line)
                        isPreviousLineOurs = False
                    else:
                        isPreviousLineOurs = False
                logFile.close()

                if contentLines:
                    content = ""
                    for logEntry in reversed(contentLines):
                        content += logEntry + "\n"
                else:
                    notificationInfo(_lang_(30271) % _logFilePath_)
                    return True
            else:
                notificationError(_lang_(30508) % _logFilePath_)
                return False
        else:
            notificationError(_lang_(30512) % _logFilePath_)
            return False
        xbmcgui.Dialog().textviewer(_scriptname_+" | Logs", content)
        return True

    def _maybeRestartPVR(refreshRate):
        lastRestart = _db_.getLock("lastRestart")
        if lastRestart > 0:
            timestampNow = int(time.time())
            if (timestampNow - lastRestart) >= (refreshRate):
                _restartPVR()
        else:
            _restartPVR()

    def _is_saveEpg_running():
        locktime = _db_.getLock("saveEpgRunning")
        if locktime == False:
            logDbg("Couldn't retrieve lock: saveEpgRunning")
            return False
        timestampNow = int(time.time())
        if (timestampNow - locktime) >= (_epgLockTimeout_):
            return False
        else:
            logDbg("Epg lock is on: locked "+str(int(timestampNow - locktime))+"s ago")
            return True

    def _setSaveEpgLock():
        _db_.setLock("saveEpgRunning", time.time())

    def _getLogoUrl(logoUrl):
        m = re.match(r"^(.*sizes/)(\d+x\d+)(/.*/)(\d+x\d+)(/.*)$", logoUrl)
        if m:
            sizes = ["256x256"]
            beginning = m.group(1)
            size1 = m.group(2)
            size2 = m.group(4)
            between = m.group(3)
            end = m.group(5)
            if size1 in sizes or size2 in sizes:
                return logoUrl
            if size1 != size2:
                logWarn("Sizes in logo url are different")
            for size in sizes:
                newUrl = beginning+size+between+size+end
                request = urllib2.Request(newUrl)
                request.get_method = lambda : 'HEAD'
                try:
                    urllib2.urlopen(request)
                    return newUrl
                except:
                    continue
        return logoUrl

    def saveChannels(restartPVR=True, forceNotifications=False):
#        if not forceNotifications:
#            return False
        notification = _notification_refreshing_started_ or forceNotifications
        dialogDebug = False or forceNotifications
        logIdSuffix = "/saveChannels()/"+datetime.datetime.fromtimestamp(int(time.time())).strftime('%H%M%S')

        msg = _lang_(30262) % "saveChannels()"
        notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)

        if os.path.exists(_m3u_):
            lastModTimeM3U = os.path.getmtime(_m3u_)
            timestampNow = int(time.time())
            if _use_additional_m3u_ and os.path.exists(_m3u_additional_):
                lastModTimeM3UAdditional = os.path.getmtime(_m3u_additional_)
                if (timestampNow - lastModTimeM3U) <= (_channel_refresh_rate_) and (lastModTimeM3U - lastModTimeM3UAdditional) >= 0:
                    msg = _lang_(30263) % (_m3u_, _m3u_additional_)
                    notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
                    _maybeRestartPVR(_channel_refresh_rate_)
                    return True
            elif (timestampNow - lastModTimeM3U) < (_channel_refresh_rate_):
                msg = _lang_(30264) % _m3u_
                notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
                _maybeRestartPVR(_channel_refresh_rate_)
                return True
        msg = _lang_(30265)
        notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
        channels = _fetchChannels()
        if not channels:
            msg = _lang_(30507)
            notificationError(msg, True, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
            return False
        notificationInfo(_lang_(30251), False, forceNotifications, notification)

        channels_sorted = sorted(channels.values(), key=lambda channel: channel.weight)
        numberOfChannels = len(channels_sorted)
        channelNum = 1
        iChannelJsonNumber = 0
        m3uLines = []
        m3uLines.append("#EXTM3U")
        for channel in channels_sorted:
            channelKey = _toString(channel.channel_key)
            channelKeyClean = re.sub(r"[^a-zA-Z0-9_]", "_", channelKey)
            try:
#                logDbg("Processing channel "+channel.name+" ("+str(iChannelJsonNumber+1)+"/"+str(numberOfChannels)+")")
                channelName = _toString(channel.name)
                channelLogoUrl = _toString(channel.logo_url)
                channelLogoUrl = _getLogoUrl(channelLogoUrl)
                line = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="O2TVGO", %s' % (channelKey, channelName, channelLogoUrl, channelName)
                m3uLines.append(line)

                channel_url = _toString(channel.url())
                m3uLines.append(channel_url)

                aUrl = channel_url.split('/')
                sUrlFileName = aUrl[-1]
                aUrlFileName = sUrlFileName.split('.')
                channelUrlBaseName = aUrlFileName[0]

                _db_.updateChannel(key=channelKey, keyClean=channelKeyClean, name=channelName, baseName=channelUrlBaseName, icon=channelLogoUrl, num=channelNum, id=None, keyOld=channelKey, keyCleanOld=channelKeyClean, nameOld=None)

                iChannelJsonNumber += 1
                channelNum += 1
            except ChannelIsNotBroadcastingError:
                logDbg("Channel "+channel.name+" ("+str(iChannelJsonNumber+1)+"/"+str(numberOfChannels)+") is not broadcasting; skipping it", idSuffix=logIdSuffix)
                _db_.updateChannel(num=10000, id=None, keyOld=channelKey, keyCleanOld=channelKeyClean, nameOld=None)
                iChannelJsonNumber += 1 # Otherwise the EPG guides get mixed up!

        m3u = "\n".join(m3uLines)
#        logDbg("After joining lines")

#        logNtc("DEVEL STOP")
#        return False

        if _use_additional_m3u_ and os.path.exists(_m3u_additional_):
            additional_m3u = open(_m3u_additional_, 'r')
            if additional_m3u:
                additional_prgs = additional_m3u.read()
                additional_m3u.close()
                if additional_prgs:
                    m3u += additional_prgs
            else:
                msg = _lang_(30508) % _m3u_additional_
                notificationError(msg, True, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
                return False
        m3u_file = open(_m3u_, 'w+')
        if m3u_file:
            m3u_file.write(m3u)
            m3u_file.close()
            msg = _lang_(30266) % _m3u_
            notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
            if restartPVR:
                _restartPVR()
        else:
            msg = _lang_(30509) % _m3u_
            notificationError(msg, True, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
            return False
        return True

    def _getChannelsListDict():
        channelsDict = _db_.getChannels()
        if channelsDict:
            return channelsDict
        else:
            channelsDict = {}
        i = 0
        logNtc("Fetching channels")
        channels = _fetchChannels()
        channels_sorted = sorted(channels.values(), key=lambda channel: channel.weight)
        for channel in channels_sorted:
            channelKeyClean = re.sub(r"[^a-zA-Z0-9_]", "_", channel.channel_key)
            _db_.updateChannel(key=channel.channel_key, keyClean=None, name=channel.name, baseName=None, id=None, keyOld=channel.channel_key, keyCleanOld=channelKeyClean, nameOld=None)
            channelsDict[i] = {
               "id": 0,
                "name": channel.name,
                "channel_key": channel.channel_key,
                "epgLastModTimestamp": 0
            }
            i += 1
        logNtc("Saved channel list")
        return channelsDict

    def saveEPG(restartPVR=False, forceNotifications=False):
        notification = _notification_refreshing_started_ or forceNotifications
        dialogDebug = False or forceNotifications
        logIdSuffix = "/saveEPG()/"+datetime.datetime.fromtimestamp(int(time.time())).strftime('%H%M%S')

        msg = _lang_(30262) % "saveEPG()"
        notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)

        if _is_saveEpg_running():
            msg = _lang_(30257) % "saveEPG()"
            notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
            _maybeRestartPVR(_epg_refresh_rate_)
            return True

        if os.path.exists(_xmltv_):
            lastModTimeXML = os.path.getmtime(_xmltv_)
            timestampNow = int(time.time())
            if _use_additional_m3u_ and os.path.exists(_m3u_additional_):
                lastModTimeM3UAdditional = os.path.getmtime(_m3u_additional_)
                if (timestampNow - lastModTimeXML) <= (_epg_refresh_rate_) and (lastModTimeXML - lastModTimeM3UAdditional) >= 0:
                    msg = _lang_(30263) % (_xmltv_, _m3u_additional_)
                    notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
                    _maybeRestartPVR(_epg_refresh_rate_)
                    return True
            elif (timestampNow - lastModTimeXML) <= (_epg_refresh_rate_):
                msg = _lang_(30264) % _xmltv_
                notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
                _maybeRestartPVR(_epg_refresh_rate_)
                return True

        msg = _lang_(30258)
        notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)

        channelsDict = _getChannelsListDict()
        if not channelsDict:
            msg = _lang_(30510)
            notificationError(msg, True, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
            return False
        _setSaveEpgLock()

        _db_.cleanEpgConflicts(doDelete=True)

        notificationInfo(_lang_(30252), False, forceNotifications, notification, idSuffix=logIdSuffix)

        numberOfChannels = len(channelsDict)
        #logDbg("saveEPG() - checkpoint 1", idSuffix=logIdSuffix)
        i = 0
        et_tv = etree.Element("tv")
        #logDbg("saveEPG() - checkpoint 2", idSuffix=logIdSuffix)
        #logDbg(channelsDict, idSuffix=logIdSuffix)
        #logDbg(str(numberOfChannels), idSuffix=logIdSuffix)
        #while i < numberOfChannels or str(i) in channelsDict:
        for key in channelsDict:
            #logDbg("saveEPG() - checkpoint 3b", idSuffix=logIdSuffix)
            channel = channelsDict[key]
            et_channel = etree.SubElement(et_tv, "channel", id=channel["channel_key"])
            etree.SubElement(et_channel, "display-name", lang=_xml_lang_).text = channel["name"]
            i += 1
        _setSaveEpgLock()
        #logDbg("saveEPG() - checkpoint 4", idSuffix=logIdSuffix)

        iFetchedChannel = 0
        i = 0
        errorOccured = False
        #while i < numberOfChannels or str(i) in channelsDict:
        for key in channelsDict:
#            key = str(j)
#            if not key in channelsDict:
#                logDbg("No channel at position "+str(i+1)+"/"+str(numberOfChannels)+"; skipping it", idSuffix=logIdSuffix)
#                i += 1
#                continue
            channel = channelsDict[key]
            #logDbg("Starting refresh of EPG for channel "+channel["name"], idSuffix=logIdSuffix)
            # read the db and delete old entries #
            epgDict = None
            useFromTimestamp = False
            useDB = False
            timestampNow = int(time.time())

            if not channel["epgLastModTimestamp"]:
                useDB = True
            elif (timestampNow - channel["epgLastModTimestamp"]) <= _epg_refresh_rate_:
                # use this instead of asking for the data #
                useDB = True
                #logNtc(channel["name"]+" 1", idSuffix=logIdSuffix)
            olderThan = (timestampNow -  (2*24*3600))
            _db_.deleteOldEpg(endBefore=olderThan)
            refreshHome()
            #logDbg("EPG refresh - channel "+channel["name"]+": checkpoint 1", idSuffix=logIdSuffix)
            epgDict = _db_.getEpgRows(channel["id"])
            if not epgDict:
                # if there were no epg entries with for this channel, so just use an empty dictionary #
                epgDict = {}
                useDB = False
                #logNtc(channel["name"]+" 2", idSuffix=logIdSuffix)
            else:
                # check if the latest programme in the epg starts in the future #
                maxTimestamp = max(epgDict, key=int)
                if (int(maxTimestamp) - int(timestampNow)) < _epg_refresh_rate_:
                    # Data is not fresh enough, we need to load new data - enough to do so from the maxTimestamp #
                    useDB = False
                    useFromTimestamp = True
                    #logNtc(channel["name"]+" 3", idSuffix=logIdSuffix)
                    #logNtc("Age of latest programme in seconds: "+str(int(maxTimestamp) - int(timestampNow)), idSuffix=logIdSuffix)
                    #logNtc("Latest programme: "+str(maxTimestamp)+" => "+_toString(epgDict[maxTimestamp]), idSuffix=logIdSuffix)
            #logDbg("EPG refresh - channel "+channel["name"]+": checkpoint 2", idSuffix=logIdSuffix)
            _setSaveEpgLock()
            #logDbg("EPG refresh - channel "+channel["name"]+": checkpoint 3", idSuffix=logIdSuffix)

            if useDB:
                msg = _lang_(30259) % (channel["name"], i+1, numberOfChannels)
                notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
            else:
                if iFetchedChannel >= _epg_fetch_batch_limit_:
                    msg = _lang_(30267) % _epg_fetch_batch_limit_
                    notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
                    return True
                msg = _lang_(30268) % (channel["name"], i+1, numberOfChannels)
                notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
#                logNtc("DEVEL STOP", idSuffix=logIdSuffix)
#                return False
                forceFromTimestamp = None
                if useFromTimestamp:
                    forceFromTimestamp = maxTimestamp
                try:
                    epg = _fetchEpg(channel["channel_key"], 2 * 24, 2 * 24, forceFromTimestamp)
                except RequestError:
                    _db_.setLock("saveEpgRunning", time.time()+_requestErrorTimeout_)
                    notificationError(_lang_(30513) % str(_requestErrorTimeoutMin_)+" minutes", idSuffix=logIdSuffix)
                    return True
                if epg:
                    for prg in epg:
                        epg_id = prg['epgId']
                        try:
                            prg_detail = _fetchEpgDetail(epg_id)
                        except RequestError:
                            _db_.setLock("saveEpgRunning", time.time()+_requestErrorTimeout_)
                            notificationError(_lang_(30513) % str(_requestErrorTimeoutMin_)+" minutes", idSuffix=logIdSuffix)
                            return True
                        if prg_detail['picture']:
                            if prg_detail['picture'].startswith("http://app.o2tv.cz") or prg_detail['picture'].startswith("http://www.o2tv.cz"):
                                fanart_image = prg_detail['picture']
                            else:
                                fanart_image = "http://app.o2tv.cz" + prg_detail['picture']
                            fanart_image = _getLogoUrl(fanart_image)
                        elif prg['picture']:
                            if prg['picture'].startswith("http://app.o2tv.cz") or prg['picture'].startswith("http://www.o2tv.cz"):
                                fanart_image = prg['picture']
                            else:
                                fanart_image = "http://app.o2tv.cz" + prg['picture']
                            fanart_image = _getLogoUrl(fanart_image)
                        else:
                            fanart_image = ""
                        genres = None
                        genre = None
                        if prg_detail['genres']:
                            genres = prg_detail['genres']
                            genre = " / ".join(genres)
                        if genre is None or len(genre) == 0:
                            genre = "jiné/nezařazené"
                            genres = [genre, ]
                        genreDB = genre
                        genresDB = json.dumps(genres)
                        start = _timestampishToTimestamp(prg['startTimestamp'])
                        epgDict[start] = {
                                "start": start,
                                "end": _timestampishToTimestamp(prg['endTimestamp']),
                                "startEpgTime": _timestampishToEpgTime(prg['startTimestamp']),
                                "endEpgTime": _timestampishToEpgTime(prg['endTimestamp']),
                                "startTimestamp": prg['startTimestamp'],
                                "endTimestamp": prg['endTimestamp'],
                                "epgId": prg["epgId"],
                                "title": prg['name'],
                                "fanart_image": fanart_image,
                                "plotoutline": prg['shortDescription'],
                                "plot": prg_detail['longDescription'],
                                "genres": genres,
                                "genre": genre
                        }
                        #logDbg("Updating EPG of channel "+channel["name"], idSuffix=logIdSuffix)
                        #logDbg(epgDict[start], idSuffix=logIdSuffix)
                        _db_.updateEpg(start = start,
                                   end = _timestampishToTimestamp(prg['endTimestamp']),
                                   startEpgTime = _timestampishToEpgTime(prg['startTimestamp']),
                                   endEpgTime = _timestampishToEpgTime(prg['endTimestamp']),
                                   startTimestamp = prg['startTimestamp'],
                                   endTimestamp = prg['endTimestamp'],
                                   epgId = prg['epgId'],
                                   title = prg['name'],
                                   fanart_image = fanart_image,
                                   plotoutline = prg['shortDescription'],
                                   plot = prg_detail['longDescription'],
                                   genres = genresDB,
                                   genre = genreDB,
                                   channelID = channel["id"],
                                   startOld = start,
                                   epgIdOld = prg['epgId']
                                   )
                        _db_.updateChannel(id=channel["id"], epgLastModTimestamp=int(time.time()))
                        _setSaveEpgLock()
                else:
                    msg = _lang_(30511) % _toString(epg)
                    notificationError(msg, True, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
                    errorOccured = True
                iFetchedChannel += 1
                #logNtc("DEVEL STOP", idSuffix=logIdSuffix)
                #return False

            _setSaveEpgLock()

            # building the actual xml file #
            for epgDictKey in sorted(epgDict.iterkeys()):
                prg = epgDict[epgDictKey]
                et_programme = etree.SubElement(et_tv, "programme", channel=channel["channel_key"])
                if "startEpgTime" in prg:
                    et_programme.set("start", str(prg['startEpgTime']))
                    et_programme.set("stop", str(prg['endEpgTime']))
                else:
                    et_programme.set("start", str(_timestampishToEpgTime(prg['startTimestamp'])))
                    et_programme.set("stop", str(_timestampishToEpgTime(prg['endTimestamp'])))
                etree.SubElement(et_programme, "title", lang=_xml_lang_).text = prg['title']
                etree.SubElement(et_programme, "sub-title", lang=_xml_lang_).text = prg['plotoutline']
                etree.SubElement(et_programme, "desc", lang=_xml_lang_).text = prg['plot']
                if "fanart_image" in prg and prg["fanart_image"]:
                    et_programme_icon = etree.SubElement(et_programme, "icon")
                    et_programme_icon.set("src", prg["fanart_image"])
                if "genre" in prg and prg["genre"]:
                    etree.SubElement(et_programme, "category", lang=_xml_lang_).text = prg["genre"]
                _setSaveEpgLock()
            i += 1
        ## END: for
        # logDbg("saveEPG() 2", idSuffix=logIdSuffix)

        if errorOccured:
            return False

#        xmlElTree = etree.ElementTree(et_tv)
        xmlString = etree.tostring(et_tv, encoding='utf8')
        xmltv_file = open(_xmltv_, 'w+')
        if xmltv_file:
            xmltv_file.write(xmlString)
            xmltv_file.close()
            msg = _lang_(30269) % _xmltv_
            notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
            if restartPVR:
                _restartPVR()
            else:
                _maybeRestartPVR(_epg_refresh_rate_)
        _setSaveEpgLock()
        if not _use_additional_epg_:
            return True
        needToRestart = False
        et_tv, needToRestart = _merge_additional_epg_xml(et_tv)
        if needToRestart:
#            xmlElTree = etree.ElementTree(et_tv)
            xmlString = etree.tostring(et_tv, encoding='utf8')
            xmltv_file = open(_xmltv_, 'w+')
            if xmltv_file:
                xmltv_file.write(xmlString)
                xmltv_file.close()
                msg = _lang_(30270) % _xmltv_
                notificationInfo(msg, False, forceNotifications, dialogDebug, idSuffix=logIdSuffix)
                if restartPVR:
                    _restartPVR()
                else:
                    _maybeRestartPVR(_epg_refresh_rate_)
            _setSaveEpgLock()
        return True

    def _restartPVR():
        # Queue for restart if something fails #
        _db_.setLock("lastRestart", 0)

        if not _force_restart_:
            player = xbmc.Player()
            isPlaying = player.isPlayingVideo()
            if isPlaying:
                playingNow = player.getPlayingFile()
                if playingNow.startswith("pvr://"):
                    logNtc("Player is currently playing a pvr channel, not restarting")
                    return

        # Prevent restarting by another thread #
        _db_.setLock("lastRestart", time.time())
        dialog_id = xbmcgui.getCurrentWindowId()
        reopen = False
        if dialog_id == 10100 or (dialog_id >= 10600 and dialog_id < 10800) or dialog_id == 10000:
            xbmc.executebuiltin("ActivateWindow(10025, 'plugin://plugin.video.o2tvgo.iptv.simple',return)")
            reopen = True
            xbmc.sleep(1000)

        pluginDetails = _jsonRPC_._getAddonDetails("pvr.iptvsimple")
        if pluginDetails:
            #logDbg("Plugin details response: "+_toString(pluginDetails))
            refreshHome()
            enabled = pluginDetails["enabled"]
            if enabled:
                logNtc("Stopping IPTV Simple PVR manager")
                response = _jsonRPC_._setAddonEnabled("pvr.iptvsimple", False)
                if response:
                    logNtc("Starting IPTV Simple PVR manager")
                    response = _jsonRPC_._setAddonEnabled("pvr.iptvsimple", True)
                    if response:
                        if _notification_pvr_restart_:
                            notificationInfo(_lang_(30253))
                        else:
                            logNtc(_lang_(30253))
                        _db_.setLock("lastRestart", time.time())
                        if reopen:
                            xbmc.executebuiltin("ActivateWindow("+str(dialog_id)+")")
                        return True
                    else:
                        # Couldn't enable the plugin => Queue for restart #
                        _db_.setLock("lastRestart", 0)
                        if reopen:
                            xbmc.executebuiltin("ActivateWindow("+str(dialog_id)+")")
                        return False
                else:
                    # Couldn't disable the plugin => Queue for restart #
                    _db_.setLock("lastRestart", 0)
                    if reopen:
                        xbmc.executebuiltin("ActivateWindow("+str(dialog_id)+")")
                    return False
            else:
                # plugin is disabled
                logNtc("Starting IPTV Simple PVR manager")
                response = _jsonRPC_._setAddonEnabled("pvr.iptvsimple", True)
                if response:
                    logNtc("IPTV Simple PVR manager start done")
                    if _notification_pvr_restart_:
                        notificationInfo(_lang_(30254))
                    else:
                        logNtc(_lang_(30254))
                    _db_.setLock("lastRestart", time.time())
                    if reopen:
                        xbmc.executebuiltin("ActivateWindow("+str(dialog_id)+")")
                    return True
                else:
                    # Couldn't enable the plugin => Queue for restart #
                    _db_.setLock("lastRestart", 0)
                    if reopen:
                        xbmc.executebuiltin("ActivateWindow("+str(dialog_id)+")")
                    return False
        else:
            # Couldn't get plugin details => Queue for restart #
            _db_.setLock("lastRestart", 0)
            if reopen:
                xbmc.executebuiltin("ActivateWindow("+str(dialog_id)+")")
            return False

    def _merge_additional_epg_xml(et_tv, test=False):
        logNtc("Starting merge of additional epg xml files to '"+_xmltv_+"'")
        if test:
            et_tv = etree.Element("tv")
            et_programme = etree.SubElement(et_tv, "programme", id="prg1")
            et_programme.set("start", "201701142000")
            et_programme.set("stop", "201701142100")
            etree.SubElement(et_programme, "title", lang=_xml_lang_).text = "title"
            logDbg(etree.tostring(et_tv, encoding='utf8'))
        #else:
            #return et_tv, False
        ##^temporary
        additional_xml_file_list = glob.glob(_xmltv_additional_filelist_pattern_)
        if additional_xml_file_list:
            #logDbg('Found the following additional epg xml files:')
            #logDbg(additional_xml_file_list)
            for filepath in additional_xml_file_list:
                additional_xml_file = gzip.open(filepath, 'r')
                additional_xml = additional_xml_file.read()
                additional_xml_file.close()
                if additional_xml:
                    logNtc("Starting merge of epg from file '"+filepath+"'")
                    et_tv = _merge_additional_epg_xml_from_filecontents(et_tv, additional_xml)
                else:
                    logErr("Could not open '"+filepath+"' for reading")
                    return et_tv, False
        else:
            additionalXML = False
            if os.path.exists(_xmltv_additional_):
                additional_xml_file = open(_xmltv_additional_, 'r')
                additional_xml = additional_xml_file.read()
                additional_xml_file.close()
                additionalXML = True
                filepath = _xmltv_additional_
            elif os.path.exists(_xmltv_additional_gzip_):
                additional_xml_file = gzip.open(_xmltv_additional_gzip_, 'r')
                additional_xml = additional_xml_file.read()
                additional_xml_file.close()
                additionalXML = True
                filepath = _xmltv_additional_gzip_
            if additionalXML:
                if additional_xml:
                    logNtc("Starting merge of epg from file '"+filepath+"'")
                    et_tv = _merge_additional_epg_xml_from_filecontents(et_tv, additional_xml)
                else:
                    logErr("Could not open '"+filepath+"' for reading")
                    return et_tv, False
        if test:
#            xmlElTree = etree.ElementTree(et_tv)
            xmlString = etree.tostring(et_tv, encoding='utf8')
            xmltv_file = open(_xmltv_test_output_file_, 'w+')
            if xmltv_file:
                xmltv_file.write(xmlString)
                xmltv_file.close()
                logNtc("'"+_xmltv_test_output_file_+"' file saved successfully")
        return et_tv, True

    def _merge_additional_epg_xml_from_filecontents(et_tv, additional_xml):
        additional_channel_list = _getAdditionalChannelNames()
        #parser = etree.XMLParser(encoding="utf-8") #only in v >=2.7
        #additional_xml_root = etree.fromstring(additional_xml, parser=parser) #only in v >=2.7
        additional_xml_root = etree.fromstring(additional_xml)
        for channel_id in additional_channel_list:
            logNtc("Looking for 'channel' tag for '"+channel_id+"'")
            #channel_elem = additional_xml_root.find("channel[@id='"+channel_id+"']") #only in v >=2.7
            channel_elem = None
            channel_elems = additional_xml_root.findall("channel")
            for chelem in channel_elems:
                if chelem.attrib.get('id') == channel_id:
                    channel_elem = chelem
                    break
            if channel_elem:
                logNtc("Found 'channel' tag for '"+channel_id+"'")
                et_tv.append(channel_elem)
            logNtc("Looking for 'programme' tags for '"+channel_id+"'")
            #program_elems = additional_xml_root.findall("programme[@channel='"+channel_id+"']") #only in v >=2.7
            program_elems = additional_xml_root.findall("programme")
            if program_elems:
                logged = False
                for program_elem in program_elems:
                    if program_elem.attrib.get('channel') == channel_id:
                        if not logged:
                            logNtc("Found 'programme' tags for '"+channel_id+"'")
                            logged = True
                        et_tv.append(program_elem)
        return et_tv

    def _getAdditionalChannelNames():
        if _use_additional_m3u_ and os.path.exists(_m3u_additional_):
            additional_m3u = open(_m3u_additional_, 'r')
            if additional_m3u:
                additional_prgs = additional_m3u.read()
                additional_m3u.close()
            else:
                logErr("Could not open 'o2tvgo-prgs-additional.m3u' for reading")
                return []
        else:
            return []
        iterator = re.finditer('(?<=tvg-id=")[^"]*(?=")', additional_prgs, re.DOTALL | re.MULTILINE)
        return [additional_prgs[m.start():m.end()] for m in iterator]

    def _timestampishToEpgTime(timestamp):
        return datetime.datetime.fromtimestamp(
            _timestampishToTimestamp(timestamp)
        ).strftime('%Y%m%d%H%M%S')

    def _timestampishToTime(timestamp):
        return datetime.datetime.fromtimestamp(
            _timestampishToTimestamp(timestamp)
        ).strftime('%H:%M')

    def _timestampishToEpgHistoryTime(timestamp):
        return datetime.datetime.fromtimestamp(
            _timestampishToTimestamp(timestamp)
        ).strftime('%Y%m%dT%H%M%S')

    def _timestampishToTimestamp(timestamp):
        return int(timestamp)/1000

    def _timestampToNiceDateTime(fromTimestamp, toTimestamp=None):
        if not toTimestamp:
            return datetime.datetime.fromtimestamp(
                fromTimestamp
            ).strftime('%Y/%m/%dT%H:%M:%S')
        else:
            sDateFrom = datetime.datetime.fromtimestamp(
                fromTimestamp
            ).strftime('%Y/%m/%d')
            sDateTo = datetime.datetime.fromtimestamp(
                toTimestamp
            ).strftime('%Y/%m/%d')
            sTimeFrom = datetime.datetime.fromtimestamp(
                fromTimestamp
            ).strftime('%H:%M')
            sTimeTo = datetime.datetime.fromtimestamp(
                toTimestamp
            ).strftime('%H:%M')
            if sDateFrom == sDateTo:
                return sDateFrom + " " + sTimeFrom + " - " + sTimeTo
            else:
                return sDateFrom + " " + sTimeFrom + " - " + sDateTo + " " + sTimeTo

    def getChannelKeyPvr(playingNow):
        return False #TODO: convert to DB if needed#
        #logDbg(playingNow)
        aPlayingNow = playingNow.split('/')
        sPlayingNowFileName = aPlayingNow[-1]
        aPlayingNowFileName = sPlayingNowFileName.split('.')
        channelIndex = aPlayingNowFileName[0]
        with open(_m3u_json_) as data_file:
            channels = json.load(data_file)
        channelKey = channels["keysByIndex"][channelIndex]
        return channelIndex, channelKey

    def getChannelKeyVideo(playingNow):
        return False #TODO: convert to DB if needed#
        aPlayingNow = playingNow.split('/')
        sPlayingNowFileName = aPlayingNow[-1]
        aPlayingNowFileName = sPlayingNowFileName.split('.')
        sPlayingNowFileNameBase = aPlayingNowFileName[0]
        aParts = sPlayingNowFileNameBase.split('-')
        iCount = len(aParts)
        if iCount == 5:
            sChannelBaseName = sPlayingNowFileNameBase.rsplit('-', 2)[0]
        elif iCount == 4:
            sChannelBaseName = sPlayingNowFileNameBase.rpartition('-')[0]
        else:
            return None, None
        # Instead of this, just get the channel by its baseName #
        with open(_m3u_json_) as data_file:
            channels = json.load(data_file)
        channelIndex = channels["indexesByBaseNames"][sChannelBaseName]
        channelKey = channels["keysByIndex"][channelIndex]
        return channelIndex, channelKey

    def getChannelKeyByIndex(channelIndex):
        return False #TODO: convert to DB if needed#
        with open(_m3u_json_) as data_file:
            channels = json.load(data_file)
        channelKey = channels["keysByIndex"][str(channelIndex)]
        #logNtc(channelKey)
        return channelKey

    def getChannelJsonNumberByIndex(channelIndex):
        return False #TODO: convert to DB if needed#
        with open(_m3u_json_) as data_file:
            channels = json.load(data_file)
        if "chJsNumByIndex" in channels:
            channelJsonNumber = channels["chJsNumByIndex"][str(channelIndex)]
        else:
            channelJsonNumber = channelIndex
        #logNtc(channelJsonNumber)
        return channelJsonNumber

    def getEpgByChannelIndexAndTimestamp(channelIndex, timestamp):
        return False #TODO: convert to DB if needed#
        channelJsonNumber = getChannelJsonNumberByIndex(channelIndex)
        jsonEpgFilePath = _xmltv_json_base_ + str(channelJsonNumber) + ".json"
        jsonEpgFile = xbmc.translatePath(jsonEpgFilePath)
        with open(jsonEpgFile) as data_file:
            epg = json.load(data_file)

        epgNowKey = None
        epgNow = None
        startPos = None
        for key in sorted(epg.iterkeys()):
            if epg[key]["start"] == timestamp:
                epgNowKey = key
                epgNow = epg[key]
                startPos = timestamp - int(epg[key]["start"])
                return epgNowKey, epgNow, startPos

        for key in sorted(epg.iterkeys()):
            if epg[key]["start"] <= timestamp and timestamp <= epg[key]["end"]:
                epgNowKey = key
                epgNow = epg[key]
                startPos = timestamp - int(epg[key]["start"])
                return epgNowKey, epgNow, startPos
        return None, None, None

    def getChannelTimeshiftUrl(epg, channelKey, toTimestamp=None):
        global _o2tvgo_
        objChannel = LiveChannel(o2tv=_o2tvgo_, channel_key=channelKey, name=None, logo_url=None, weight=None, _logs_=_logs_, scriptname=_scriptname_, logId=_logId_)
        startTimestamp = epg["startTimestamp"]
        if not toTimestamp:
            toTimestamp = epg["endTimestamp"]

        channelUrlTimeshift = objChannel.urlTimeshift(startTimestamp, toTimestamp)
        logNtc("timeshift: " + channelUrlTimeshift)

        return channelUrlTimeshift

    def getChannelStartoverUrl(epg, channelKey):
        global _o2tvgo_
        objChannel = LiveChannel(o2tv=_o2tvgo_, channel_key=channelKey, name=None, logo_url=None, weight=None, _logs_=_logs_, scriptname=_scriptname_, logId=_logId_)
        startTimestamp = epg["startTimestamp"]

        channelUrlStartover = objChannel.urlStartover(startTimestamp)
        logNtc("startover: " + channelUrlStartover)

        return channelUrlStartover

    def setWatchPosition(epgId, watchPosition):
        global _o2tvgo_
        _o2tvgo_.setWatchPosition(epgId, watchPosition)

    def getTimestampFromDayTime(day, sTime):
        if len(day) == 3:
            days = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        else:
            days = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
        dayWeekday = days[day]
        todayWeekday = datetime.datetime.today().weekday()
        if dayWeekday <= todayWeekday:
            diff = todayWeekday - dayWeekday
        else:
            dayWeekday -= 7
            diff = todayWeekday - dayWeekday
        date = datetime.datetime.today() - datetime.timedelta(days=diff)
        sDateTime = date.strftime('%Y%m%d')+" "+sTime
        try:
            dateTime = datetime.datetime.strptime(sDateTime, "%Y%m%d %H:%M")
        except TypeError:
            dateTime = datetime.datetime(*(time.strptime(sDateTime, "%Y%m%d %H:%M")[0:6]))
        timeDelta = (dateTime - datetime.datetime(1970, 1, 1))
        epgShift = _epgTimeshift_ * 60 * 60
        timestamp = timeDelta.total_seconds() + epgShift
        return int(timestamp)

    def addToWatchLater(programmeTitle, startTime, channelName, startDate, epgRowID=None, channelID=None):
        if not epgRowID or not channelID:
            channelRow = _db_.getChannelRow(nameOld=channelName)
            if not channelRow:
                notificationError(_lang_(30505))
                return
            timestamp = getTimestampFromDayTime(startDate, startTime)
            if not timestamp:
                notificationError(_lang_(30504))
                logDbg([startDate, startTime, channelName])
                return
            epg = _db_.getEpgRowByStart(start=timestamp, channelID=channelRow["id"])
        else:
            epg = _db_.getEpgRow(id=epgRowID, channelID=channelID)
        _db_.updateEpg(id=epg["id"], channelID=epg["channelID"], isWatchLater=1)
        dialog_id = xbmcgui.getCurrentWindowId()
        reopen = False
        if dialog_id == 12003:
            reopen = True
            xbmc.executebuiltin("ActivateWindow(10000)")
        notificationInfo(_lang_(30273) % epg["title"])
        refreshHome()
        if reopen:
            xbmc.executebuiltin('Action(info)')
        xbmc.executebuiltin('Container.Refresh')

    def addToWatched(epgRowID, channelID):
        _db_.updateEpg(id=epgRowID, channelID=channelID, isRecentlyWatched=1, inProgressTime=0, isWatchLater=0)
        notificationInfo("Programme has been marked as watched successfully")
        refreshHome()
        xbmc.executebuiltin('Container.Refresh')

    def playChannelFromEpg(startTime, startDate, channelName, channelNumber, playingCurrently=False, startTimestamp=None, channelIndex=None, epgRowID=None, calledFromList=None, startOffset=0):
        player = xbmc.Player()

        logNtc("playing from epg")
        #logDbg(startDate)
        #logDbg(startTime)
        #logDbg(channelName)

        epg = None
        channelRow = None
        timestamp = None
        watchedCount = 0
        if epgRowID:
            epg = _db_.getEpgChannelRow(epgRowID)
            if epg and "channelKey" in epg:
                channelKey = epg["channelKey"]
                channelID = epg["channelID"]
                if not startOffset and calledFromList and "inProgressTime" in epg and epg["inProgressTime"] and epg["inProgressTime"] > 5:
                    startOffset = epg["inProgressTime"] - 5
                elif calledFromList == "recentlyWatched":
                    watchedCount = 1
        else:
            if startTimestamp:
                timestamp = int(startTimestamp)
            else:
                if playingCurrently:
                    timestamp = int(time.time())
                else:
                    timestamp = getTimestampFromDayTime(startDate, startTime)
                    #logDbg(timestamp)

                if not timestamp:
                    notificationError(_lang_(30504))
                    logDbg([startDate, startTime, channelName])
                    return

            channelRow = _db_.getChannelRow(nameOld=channelName)
            if not channelRow:
                notificationError(_lang_(30505))
                return
            epg = _db_.getEpgRowByStart(start=timestamp, channelID=channelRow["id"])
            channelKey = channelRow["key"]
            channelID = channelRow["id"]
            if epg and "isRecentlyWatched" in epg and epg["isRecentlyWatched"] > 0:
                watchedCount = 1
            elif startOffset == 0 and epg and "inProgressTime" in epg and epg["inProgressTime"] > 5:
                startOffset = epg["inProgressTime"] - 5
        if not epg:
            notificationError(_lang_(30506))
            logDbg([channelRow, timestamp, epgRowID, epg])
            return
        #startPos = timestamp - int(epg["start"])

        #logDbg(epg)
        # TODO: check if timeshift is needed here!
        timeShift = _epgTimeshift_ * 60 * 60 * 1000
        timestampNow = int(time.time()) * 1000
        if timestampNow < epg["endTimestamp"] + timeShift:
            if timestampNow < epg["startTimestamp"] + timeShift:
                notificationWarning(_lang_(30260) % epg["title"])
                return
            notificationWarning(_lang_(30261) % epg["title"])
            return
            notificationInfo(_lang_(30256) % epg["title"])
            #endTimestamp = timestampNow
            #channelUrlNew = getChannelTimeshiftUrl(epg, channelKey, endTimestamp)
            channelUrlNew = getChannelStartoverUrl(epg, channelKey)
        else:
            if startOffset > 0:
                notificationInfo(_lang_(30272) % (epg["title"], time.strftime('%H:%M:%S', time.gmtime(float(startOffset)))))
            else:
                notificationInfo(_lang_(30255) % epg["title"])
            endTimestamp = epg["endTimestamp"]
            channelUrlNew = getChannelTimeshiftUrl(epg, channelKey, endTimestamp)

        pl=xbmc.PlayList(1)
        pl.clear()
        li = xbmcgui.ListItem(epg["title"])

        if "fanart_image" in epg and epg["fanart_image"] and len(epg["fanart_image"]) > 0:
            li.setArt({
              'icon': epg["fanart_image"],
              "fanart": epg["fanart_image"],
              "poster": epg["fanart_image"]
            })
        videoinfo = {}
        if "plot" in epg and epg["plot"] and len(epg["plot"]) > 0:
            videoinfo['plot'] = epg['plot']
        if "plotoutline" in epg and epg["plotoutline"] and len(epg["plotoutline"]) > 0:
            videoinfo['plotoutline'] = epg['plotoutline']
        if "genre" in epg and epg["genre"]:
            videoinfo['genre'] = epg["genre"]
        if startOffset > 0:
            li.setProperty('StartOffset', str(startOffset))
        if watchedCount > 0:
            li.setProperty('WatchedCount', str(watchedCount))
            videoinfo["playcount"] = 1
        if len(videoinfo) > 0:
            li.setInfo('video', videoinfo)

        player.play(channelUrlNew, li)
        _db_.clearCurrentlyPlaying()
        _db_.clearNextProgramme()
        _db_.updateEpg(id=epg["id"], channelID=channelID, isCurrentlyPlaying=1, inProgressTime=1)
        refreshHome("InProgress")

        logDbg("Looking for next programme")
        timestampNext = int(epg["end"])
#        epgKeyNext, epgNext, startPosNext = getEpgByChannelIndexAndTimestamp(channelIndex, timestampNext)

        epgNext = _db_.getEpgRowByStart(start=timestampNext, channelID=channelID)
        if not epgNext:
            logErr("Didn't find next programme in epg")
            logDbg([channelRow, timestamp, epg])
        else:
            _db_.updateEpg(id=epgNext["id"], channelID=channelID, isNextProgramme=1)

    def pausePlayer(channelNumber=None):
        return False #TODO: convert to DB if needed#
        logNtc("pausing")
        player = xbmc.Player()
        isPlaying = player.isPlayingVideo()
        if not isPlaying:
            logNtc("not playing: nothing to pause")
            return
        playingNow = player.getPlayingFile()
        channelIndex = None
        channelKey = None
        if playingNow.startswith("pvr://"):
            logNtc("playing pvr")
            if channelNumber:
                channelIndex = int(channelNumber) - 1
                channelKey = getChannelKeyByIndex(channelIndex)
            else:
                channelIndex, channelKey = getChannelKeyPvr(playingNow)
        elif playingNow.endswith("m3u8"):
            logNtc("not playing pvr")
            channelIndex, channelKey = getChannelKeyVideo(playingNow)
            if not channelKey:
                logErr("not playing O2TVGO stream")
                logDbg([playingNow, channelIndex, channelKey])
                return

        timestampNow = int(time.time())
        epgNowKey, epgNow, startPos = getEpgByChannelIndexAndTimestamp(channelIndex, timestampNow)
        if not epgNowKey or not epgNow or (not startPos and startPos != 0):
            notificationError(_lang_(30506))
            logDbg([channelIndex, timestampNow, epgNowKey, epgNow, startPos])
            return

#        toTimestamp = timestampNow * 1000
        #channelUrlNew = getChannelTimeshiftUrl(epgNow, channelKey, toTimestamp)
        channelUrlNew = getChannelStartoverUrl(epgNow, channelKey)

        pl=xbmc.PlayList(1)
        pl.clear()
        li = xbmcgui.ListItem(epgNow["title"])

        player.play(channelUrlNew, li)
        setWatchPosition(epgNow["epgId"], startPos)

        player.pause()

    def logPlayingInfo():
        return False #TODO: convert to DB if needed#
        player = xbmc.Player()
        isPlaying = player.isPlayingVideo()
        if not isPlaying:
            logNtc("PlayingInfo: not playing")
            return
        playingNow = player.getPlayingFile()
        channelIndex = None
        channelKey = None
        if playingNow.startswith("pvr://"):
            logNtc("PlayingInfo: playing pvr")
            channelIndex, channelKey = getChannelKeyPvr(playingNow)
        elif playingNow.endswith("m3u8"):
            logNtc("PlayingInfo: playing m3u8 playlist file")
            channelIndex, channelKey = getChannelKeyVideo(playingNow)
            if not channelKey:
                logNtc("PlayingInfo: not playing an O2TVGO stream")
                logDbg(playingNow)
                return

        logNtc(channelIndex)
        logNtc(channelKey)
        return

    def _test():
        logNtc("Executing _test()")
        logNtc("Nothing to do defined in _test()")

    def get_params():
        param=[]
        paramstring=sys.argv[2]
        if len(paramstring)>=2:
            params=sys.argv[2]
            cleanedparams=params.replace('?','')
            if (params[len(params)-1]=='/'):
                params=params[0:len(params)-2]
            pairsofparams=cleanedparams.split('&')
            param={}
            for i in range(len(pairsofparams)):
                splitparams={}
                splitparams=pairsofparams[i].split('=')
                if (len(splitparams))==2:
                    param[splitparams[0]]=splitparams[1]
        return param

    def assign_params(params):
        for param in params:
            try:
                globals()[param]=urllib.unquote_plus(params[param])
            except:
                pass

    if __name__ == '__main__':
        # Get rid of the JSON files and store all in DB #
        upgradeConfigsFromJsonToDb()
        # Mark any in progress (and watch later) programmes as watched if applicable #
        moved = _db_.moveEpgToWatched()
        if moved:
            refreshHome()

        pause = None
        saveepg = None
        forcenotifications = None
        showlogs = None
        mergeepg = None
        test = None
        showplayinginfo = None
        playfromepg = None
        epgrowid = None
        startoffset = None
        calledfrom = None
        removefromlist = None
        starttime = None
        startdate = None
        channelname = None
        channelnumber = None
        channelid = None
        playingcurrently = None
        starttimestamp = None
        channelindex = None
        iptv_simple_settings = None
        favourites = None
        favouriteskeywords  =  None
        rowid = None
        markaswatched = None
        favouritekeywordedit = None
        favouritekeyworddelete = None
        favouritekeywordadd = None
        showplot = None
        addtowatchlater = None
        programmetitle = None
        inprogr = None
        recentlywatched = None
        watchlater = None
        genres = None
        homegenre = None
        genrechannels = None
        genreepg = None
        notification_programmeinfuture = None
        refresh = 0
        refreshhome = None
#        showinfohome = None

        params = get_params()
        assign_params(params)

    #    logDbg(params)

        if saveepg:
            forceNotifications = (forcenotifications and forcenotifications == '1')
    #        logDbg(forcenotifications)
    #        logDbg(_toString(forceNotifications))
            ok = saveChannels(True, forceNotifications)
            if ok:
                ok = saveEPG(False, forceNotifications)
        elif playfromepg:
            playChannelFromEpg(starttime, startdate, channelname, channelnumber, playingcurrently, starttimestamp, channelindex, epgRowID=epgrowid, calledFromList=calledfrom, startOffset=startoffset)
        elif iptv_simple_settings:
            _openIptvSimpleClientSettings()
        elif showlogs:
            showLogs()
        elif mergeepg:
            _merge_additional_epg_xml(None, True)
        elif pause:
            # Attempt to implement startover - not successful (yet)
            pausePlayer(channelnumber)
        elif showplayinginfo:
            logPlayingInfo()
        elif test:
            _test()
        elif recentlywatched:
            dirListing(what="recentlyWatched", refresh=refresh, calledFrom=calledfrom)
        elif favourites:
            dirListing(what="favourites", refresh=refresh, calledFrom=calledfrom)
        elif inprogr:
            dirListing(what="inProgress", refresh=refresh, calledFrom=calledfrom)
        elif watchlater:
            dirListing(what="watchLater", refresh=refresh, calledFrom=calledfrom)
        elif genres:
            dirListing(what="Genres", refresh=refresh, calledFrom=calledfrom)
        elif homegenre:
            openGenreDirListing(genre=homegenre)
        elif genrechannels:
            dirListing(what="GenreChannels", genre=genrechannels)
        elif genreepg:
            dirListing(what="GenreEpg", genre=genreepg, channelID=channelid)
        elif removefromlist:
            removeEpgFromList(removefromlist, epgrowid)
        elif favouriteskeywords:
            dirListing("favouritesKeywords")
        elif favouritekeywordedit:
            favouriteKeywordAction(action="edit", rowID=rowid)
        elif favouritekeyworddelete:
            favouriteKeywordAction(action="delete", rowID=rowid)
        elif favouritekeywordadd:
            favouriteKeywordAction(action="add", titlePattern=programmetitle)
        elif addtowatchlater:
            #addtowatchlater=1&programmetitle=$INFO[ListItem.Title]&starttime=$INFO[ListItem.StartTime]&channelname=$INFO[ListItem.ChannelName]&startdate=$INFO[ListItem.StartDate]
            addToWatchLater(programmeTitle=programmetitle, startTime=starttime, channelName=channelname, startDate=startdate, epgRowID=epgrowid, channelID=channelid)
        elif markaswatched:
            addToWatched(epgRowID=epgrowid, channelID=channelid)
        elif notification_programmeinfuture:
            showNotification(type="programmeInFuture", programmeTitle=programmetitle)
        elif refreshhome:
            refreshHome()
            #xbmc.executebuiltin('Container.Refresh')
            notificationInfo("Refresh done")
#        elif showinfohome:
#            notificationInfo("Getting there...")
#            xbmc.executebuiltin('ActivateWindow(10600, "plugin://plugin.video.o2tvgo.iptv.simple?genre='+genre+'",return)')
            #xbmc.executebuiltin('ActivateWindow(10600)')
        elif showplot:
            showEpgPlot(epgRowID=epgrowid, channelID=channelid)
        else:
            dirListing()
        _db_.closeDB()
except Exception as ex:
    exc_type, exc_value, exc_traceback = sys.exc_info()
    _logs_ = Logs(_scriptname_, _logId_)
    xbmcgui.Dialog().notification(_scriptname_, _logs_._toString(exc_value), xbmcgui.NOTIFICATION_ERROR)
    _logs_.logErr(_logs_._toString(exc_value))
    _logs_.logDbg(traceback.format_exc())
#    if not _first_error_:
#        if xbmcgui.Dialog().yesno(_scriptname_, _lang_(30500), _lang_(30501)):
#            _addon_.setSetting("send_errors", "true")
#            _send_errors_ = (_addon_.getSetting('send_errors') == "true")
#        _addon_.setSetting("first_error", "true")
#        _first_error_ = (_addon_.getSetting('first_error') == "true")
#    if _send_errors_:
#        if _sendError(params, exc_type, exc_value, exc_traceback):
#            xbmcgui.Dialog().notification(_scriptname_, _lang_(30502), xbmcgui.NOTIFICATION_INFO)
#        else:
#            xbmcgui.Dialog().notification(_scriptname_, _lang_(30503), xbmcgui.NOTIFICATION_ERROR)
#            traceback.print_exception(exc_type, exc_value, exc_traceback)
