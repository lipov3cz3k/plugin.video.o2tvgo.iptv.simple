#!/usr/bin/env python
# -*- coding: utf-8 -*-

import xbmc,  xbmcgui,  xbmcaddon

class Logs:
    def __init__(self, scriptname = None):
        if scriptname:
            self.scriptname = scriptname
        else:
            _addon_ = xbmcaddon.Addon('plugin.video.o2tvgo.iptv.simple')
            self.scriptname = _addon_.getAddonInfo('name')
    
    def _toString(self, text):
        if type(text).__name__=='unicode':
            output = text.encode('utf-8')
        else:
            output = str(text)
        return output

    def log(self, msg, level=xbmc.LOGDEBUG):
        if type(msg).__name__=='unicode':
            msg = msg.encode('utf-8')
        xbmc.log("[%s] %s"%(self.scriptname,msg.__str__()), level)

    def logDbg(self, msg):
        self.log(msg,level=xbmc.LOGDEBUG)

    def logNtc(self, msg):
        self.log(msg,level=xbmc.LOGNOTICE)

    def logErr(self, msg):
        self.log(msg,level=xbmc.LOGERROR)

    def notificationInfo(self, msg, sound = False):
        d = xbmcgui.Dialog()
        d.notification(self.scriptname, msg, xbmcgui.NOTIFICATION_INFO, 5000, sound)

    def notificationWarning(self, msg, sound = True):
        d = xbmcgui.Dialog()
        d.notification(self.scriptname, msg, xbmcgui.NOTIFICATION_WARNING, 5000, sound)

    def notificationError(self, msg, sound = True):
        d = xbmcgui.Dialog()
        d.notification(self.scriptname, msg, xbmcgui.NOTIFICATION_ERROR, 5000, sound)
